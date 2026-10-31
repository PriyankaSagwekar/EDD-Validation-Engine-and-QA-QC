/* 08 - Promote a validated batch from staging to the master tables.
   Rows with qc_status = 'HELD' stay in staging for review. Everything else is
   inserted (or updated on resubmission) with its validator qualifier, in one transaction. */
SET NOCOUNT ON;
GO

CREATE OR ALTER PROCEDURE dbo.usp_Promote_Batch
    @batch_id int
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    IF NOT EXISTS (SELECT 1 FROM dbo.stg_Batch WHERE batch_id = @batch_id AND status = 'VALIDATED')
        THROW 50001, 'Batch must exist and have status VALIDATED before promotion.', 1;

    BEGIN TRANSACTION;

    /* Rows that passed the gate, with typed values. */
    SELECT  s.source_row_no,
            s.sys_sample_code,
            s.lab_sample_id,
            s.sample_type,
            NULLIF(s.parent_sample_code, '')               AS parent_sample_code,
            NULLIF(s.location_code, '')                    AS location_code,
            s.matrix,
            TRY_CONVERT(datetime2(0), s.sample_date)       AS sample_datetime,
            TRY_CONVERT(decimal(6,2), s.depth_top_m)       AS depth_top_m,
            TRY_CONVERT(decimal(6,2), s.depth_base_m)      AS depth_base_m,
            NULLIF(s.coc_id, '')                           AS coc_id,
            NULLIF(s.cooler_id, '')                        AS cooler_id,
            TRY_CONVERT(datetime2(0), s.receipt_date)      AS receipt_datetime,
            TRY_CONVERT(decimal(4,1), s.cooler_temp_c)     AS cooler_temp_c,
            s.custody_seal_intact,
            TRY_CONVERT(decimal(4,1), s.sample_ph)         AS sample_ph,
            s.lab_code,
            s.method_code,
            ISNULL(NULLIF(s.fraction, ''), 'N')            AS fraction,
            s.lab_batch_id,
            TRY_CONVERT(datetime2(0), s.extraction_date)   AS extraction_datetime,
            TRY_CONVERT(datetime2(0), s.analysis_date)     AS analysis_datetime,
            ISNULL(TRY_CONVERT(float, s.dilution_factor), 1) AS dilution_factor,
            s.cas_rn,
            s.result_type,
            TRY_CONVERT(float, s.result_value)             AS result_value,
            s.detect_flag,
            TRY_CONVERT(float, s.mdl)                      AS mdl,
            TRY_CONVERT(float, s.rl)                       AS rl,
            s.unit,
            TRY_CONVERT(float, s.spike_added)              AS spike_added,
            TRY_CONVERT(float, s.percent_recovery)         AS percent_recovery,
            NULLIF(s.lab_qualifier, '')                    AS lab_qualifier,
            s.validator_qualifier,
            s.validator_reason
    INTO #ok
    FROM dbo.stg_Result s
    WHERE s.batch_id = @batch_id
      AND s.qc_status IN ('PASS', 'QUALIFIED');

    /* Samples: one header per sys_sample_code. */
    ;WITH hdr AS (
        SELECT *, ROW_NUMBER() OVER (PARTITION BY sys_sample_code ORDER BY source_row_no) AS rn
        FROM #ok
    )
    INSERT INTO dbo.dt_Sample (sys_sample_code, location_code, sample_type, matrix, sample_datetime,
                               depth_top_m, depth_base_m, parent_sample_code, coc_id, cooler_id, batch_id)
    SELECT h.sys_sample_code, h.location_code, h.sample_type, h.matrix, h.sample_datetime,
           h.depth_top_m, h.depth_base_m, h.parent_sample_code, h.coc_id, h.cooler_id, @batch_id
    FROM hdr h
    WHERE h.rn = 1
      AND NOT EXISTS (SELECT 1 FROM dbo.dt_Sample d WHERE d.sys_sample_code = h.sys_sample_code);

    /* Receipt: one row per chain of custody and cooler. */
    ;WITH rc AS (
        SELECT *, ROW_NUMBER() OVER (PARTITION BY coc_id, cooler_id ORDER BY source_row_no) AS rn
        FROM #ok WHERE coc_id IS NOT NULL AND cooler_id IS NOT NULL
    )
    INSERT INTO dbo.dt_Receipt (coc_id, cooler_id, lab_code, receipt_datetime, cooler_temp_c, custody_seal_intact)
    SELECT rc.coc_id, rc.cooler_id, rc.lab_code, rc.receipt_datetime, rc.cooler_temp_c, rc.custody_seal_intact
    FROM rc
    WHERE rc.rn = 1
      AND NOT EXISTS (SELECT 1 FROM dbo.dt_Receipt d WHERE d.coc_id = rc.coc_id AND d.cooler_id = rc.cooler_id);

    /* Tests: one per sample, method and fraction. */
    ;WITH tst AS (
        SELECT o.*, d.sample_id,
               ROW_NUMBER() OVER (PARTITION BY d.sample_id, o.method_code, o.fraction ORDER BY o.source_row_no) AS rn
        FROM #ok o
        JOIN dbo.dt_Sample d ON d.sys_sample_code = o.sys_sample_code
    )
    INSERT INTO dbo.dt_Test (sample_id, method_code, fraction, lab_code, lab_sample_id, lab_batch_id,
                             extraction_datetime, analysis_datetime, dilution_factor, sample_ph)
    SELECT t.sample_id, t.method_code, t.fraction, t.lab_code, t.lab_sample_id, t.lab_batch_id,
           t.extraction_datetime, t.analysis_datetime, t.dilution_factor, t.sample_ph
    FROM tst t
    WHERE t.rn = 1
      AND NOT EXISTS (SELECT 1 FROM dbo.dt_Test x
                      WHERE x.sample_id = t.sample_id AND x.method_code = t.method_code AND x.fraction = t.fraction);

    /* Results: insert new, update resubmitted. */
    MERGE dbo.dt_Result AS tgt
    USING (
        SELECT t.test_id, o.*
        FROM #ok o
        JOIN dbo.dt_Sample d ON d.sys_sample_code = o.sys_sample_code
        JOIN dbo.dt_Test   t ON t.sample_id = d.sample_id AND t.method_code = o.method_code AND t.fraction = o.fraction
    ) AS src
    ON tgt.test_id = src.test_id AND tgt.cas_rn = src.cas_rn AND tgt.result_type = src.result_type
    WHEN MATCHED THEN UPDATE SET
        result_value = src.result_value, detect_flag = src.detect_flag, mdl = src.mdl, rl = src.rl,
        unit = src.unit, spike_added = src.spike_added, percent_recovery = src.percent_recovery,
        lab_qualifier = src.lab_qualifier, validator_qualifier = src.validator_qualifier,
        validator_reason = src.validator_reason, batch_id = @batch_id, source_row_no = src.source_row_no
    WHEN NOT MATCHED THEN INSERT
        (test_id, cas_rn, result_type, result_value, detect_flag, mdl, rl, unit, spike_added,
         percent_recovery, lab_qualifier, validator_qualifier, validator_reason, batch_id, source_row_no)
    VALUES
        (src.test_id, src.cas_rn, src.result_type, src.result_value, src.detect_flag, src.mdl, src.rl,
         src.unit, src.spike_added, src.percent_recovery, src.lab_qualifier, src.validator_qualifier,
         src.validator_reason, @batch_id, src.source_row_no);

    DECLARE @promoted int = (SELECT COUNT(*) FROM #ok);
    DECLARE @held int = (SELECT COUNT(*) FROM dbo.stg_Result WHERE batch_id = @batch_id AND qc_status = 'HELD');

    UPDATE dbo.stg_Batch
    SET status = 'PROMOTED', promoted_utc = SYSUTCDATETIME(), rows_promoted = @promoted, rows_held = @held
    WHERE batch_id = @batch_id;

    COMMIT TRANSACTION;

    SELECT @batch_id AS batch_id, @promoted AS rows_promoted, @held AS rows_held;
END
GO
