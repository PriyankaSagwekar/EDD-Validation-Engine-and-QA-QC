/* 09 - Views for the dashboard, screening report and ArcGIS package. */
SET NOCOUNT ON;
GO

/* One row per EDD batch with the totals from its latest validation run. */
CREATE OR ALTER VIEW dbo.vw_Batch_Summary AS
SELECT  b.batch_id,
        b.file_name,
        b.lab_code,
        b.status,
        b.loaded_utc,
        b.validated_utc,
        b.promoted_utc,
        b.row_count,
        dates.first_sample_date,
        dates.last_sample_date,
        r.run_id,
        ISNULL(r.n_exceptions, 0)   AS n_exceptions,
        ISNULL(r.n_critical, 0)     AS n_critical,
        ISNULL(r.n_warning, 0)      AS n_warning,
        ISNULL(r.n_info, 0)         AS n_info,
        ISNULL(r.rows_held, 0)      AS rows_held,
        ISNULL(r.rows_qualified, 0) AS rows_qualified,
        b.row_count - ISNULL(r.rows_held, 0) - ISNULL(r.rows_qualified, 0) AS rows_passed,
        CAST(ISNULL(r.rows_held, 0) AS float) / NULLIF(b.row_count, 0)  AS held_fraction,
        ISNULL(b.rows_promoted, 0) AS rows_promoted
FROM dbo.stg_Batch b
OUTER APPLY (SELECT TOP 1 * FROM dbo.qc_Run q WHERE q.batch_id = b.batch_id ORDER BY q.run_id DESC) r
OUTER APPLY (SELECT MIN(TRY_CONVERT(date, s.sample_date)) AS first_sample_date,
                    MAX(TRY_CONVERT(date, s.sample_date)) AS last_sample_date
             FROM dbo.stg_Result s WHERE s.batch_id = b.batch_id) dates;
GO

/* Every exception from each batch's latest validation run, with rule family and analyte name. */
CREATE OR ALTER VIEW dbo.vw_Exception_Detail AS
SELECT  e.batch_id,
        b.file_name,
        r.family,
        e.rule_id,
        r.rule_name,
        e.severity,
        e.source_row_no,
        e.sys_sample_code,
        s.location_code,
        e.method_code,
        e.cas_rn,
        s.chemical_name,
        e.observed_value,
        e.limit_value,
        e.message
FROM dbo.qc_Exception e
JOIN dbo.qc_Rule   r ON r.rule_id  = e.rule_id
JOIN dbo.stg_Batch b ON b.batch_id = e.batch_id
LEFT JOIN dbo.stg_Result s ON s.batch_id = e.batch_id AND s.source_row_no = e.source_row_no
WHERE e.run_id = (SELECT MAX(q.run_id) FROM dbo.qc_Run q WHERE q.batch_id = e.batch_id);
GO

/* Final validator qualifiers on promoted results. 'None' means the result passed unqualified. */
CREATE OR ALTER VIEW dbo.vw_Qualifier_Summary AS
SELECT  batch_id,
        method_code,
        analyte_group,
        ISNULL(validator_qualifier, 'None') AS validator_qualifier,
        COUNT(*)                            AS n_results
FROM dbo.vw_Result_Validated
GROUP BY batch_id, method_code, analyte_group, ISNULL(validator_qualifier, 'None');
GO

/* Rows kept in staging, with the rules and messages from the batch's latest run. */
CREATE OR ALTER VIEW dbo.vw_Held_Rows AS
SELECT  s.batch_id,
        s.source_row_no,
        s.sys_sample_code,
        s.location_code,
        s.sample_type,
        s.matrix,
        s.method_code,
        s.cas_rn,
        s.chemical_name,
        s.result_value,
        s.unit,
        s.validator_qualifier,
        exc.rules,
        exc.messages
FROM dbo.stg_Result s
OUTER APPLY (SELECT TOP 1 q.run_id FROM dbo.qc_Run q WHERE q.batch_id = s.batch_id ORDER BY q.run_id DESC) r
OUTER APPLY (SELECT STRING_AGG(e.rule_id, ', ') WITHIN GROUP (ORDER BY e.rule_id) AS rules,
                    STRING_AGG(CAST(e.message AS nvarchar(max)), ' | ') WITHIN GROUP (ORDER BY e.rule_id) AS messages
             FROM dbo.qc_Exception e
             WHERE e.run_id = r.run_id AND e.source_row_no = s.source_row_no) exc
WHERE s.qc_status = 'HELD';
GO

/* Usable target results for field samples, ready to plot over time. Non-detects are
   plotted at the RL. The criterion comes from the primary set for the matrix. */
CREATE OR ALTER VIEW dbo.vw_Result_Timeseries AS
SELECT  v.location_code,
        v.easting,
        v.northing,
        v.sys_sample_code,
        v.sample_type,
        v.matrix,
        v.sample_datetime,
        CONVERT(char(7), v.sample_datetime, 120) AS monitoring_round,
        v.depth_top_m,
        v.method_code,
        v.fraction,
        v.cas_rn,
        v.chemical_name,
        v.analyte_group,
        v.result_value,
        v.detect_flag,
        v.rl,
        v.unit,
        CASE WHEN v.detect_flag = 'Y' THEN v.result_value ELSE v.rl END AS plot_value,
        CASE WHEN v.detect_flag = 'N' THEN 'Non-detect'
             WHEN v.validator_qualifier IS NOT NULL THEN 'Qualified'
             ELSE 'Detect' END AS point_class,
        v.validator_qualifier,
        c.criterion_set,
        c.criterion_value,
        v.batch_id
FROM dbo.vw_Result_Validated v
LEFT JOIN dbo.ref_Screening_Criterion c
       ON c.cas_rn = v.cas_rn AND c.matrix = v.matrix AND c.unit = v.unit AND c.is_primary = 1
WHERE v.result_type = 'TRG'
  AND v.sample_type IN ('N', 'FD')
  AND v.is_usable = 1
  AND v.location_code IS NOT NULL;
GO

/* Each usable primary-sample result compared with every criteria set for its matrix.
   A result equal to the criterion is not an exceedance. */
CREATE OR ALTER VIEW dbo.vw_Screening_Exceedance AS
SELECT  v.location_code,
        v.easting,
        v.northing,
        v.sys_sample_code,
        v.matrix,
        v.sample_datetime,
        v.depth_top_m,
        v.depth_base_m,
        v.cas_rn,
        v.chemical_name,
        v.analyte_group,
        v.result_value,
        v.detect_flag,
        v.rl,
        v.unit,
        v.validator_qualifier,
        c.criterion_set,
        c.criterion_name,
        c.is_primary,
        c.criterion_value,
        CASE WHEN v.detect_flag = 'Y' THEN v.result_value / c.criterion_value END AS exceedance_ratio,
        CASE WHEN v.detect_flag = 'N' THEN v.rl / c.criterion_value END           AS rl_ratio,
        CASE WHEN v.detect_flag = 'Y' AND v.result_value > c.criterion_value THEN 'Exceeds'
             WHEN v.detect_flag = 'Y'                                        THEN 'Below'
             WHEN v.rl > c.criterion_value                                   THEN 'ND inconclusive'
             ELSE 'ND compliant' END AS screening_class,
        v.batch_id
FROM dbo.vw_Result_Validated v
JOIN dbo.ref_Screening_Criterion c
  ON c.cas_rn = v.cas_rn AND c.matrix = v.matrix AND c.unit = v.unit
WHERE v.result_type = 'TRG'
  AND v.sample_type = 'N'
  AND v.is_usable = 1
  AND v.location_code IS NOT NULL;
GO

/* One row per location, analyte and criteria set: the worst result screened. */
CREATE OR ALTER VIEW dbo.vw_Screening_Summary AS
SELECT  location_code,
        MAX(easting)  AS easting,
        MAX(northing) AS northing,
        matrix,
        cas_rn,
        chemical_name,
        criterion_set,
        MAX(CAST(is_primary AS int)) AS is_primary,
        MAX(criterion_value) AS criterion_value,
        MAX(unit)            AS unit,
        COUNT(*)             AS n_results,
        SUM(CASE WHEN screening_class = 'Exceeds' THEN 1 ELSE 0 END)         AS n_exceed,
        SUM(CASE WHEN screening_class = 'ND inconclusive' THEN 1 ELSE 0 END) AS n_inconclusive,
        MAX(CASE WHEN detect_flag = 'Y' THEN result_value END)               AS max_result,
        MAX(exceedance_ratio)                                                AS max_ratio,
        CASE WHEN SUM(CASE WHEN screening_class = 'Exceeds' THEN 1 ELSE 0 END) > 0 THEN 'Exceeds'
             WHEN SUM(CASE WHEN screening_class = 'ND inconclusive' THEN 1 ELSE 0 END) > 0 THEN 'ND inconclusive'
             WHEN SUM(CASE WHEN screening_class = 'Below' THEN 1 ELSE 0 END) > 0 THEN 'Below'
             ELSE 'ND compliant' END AS worst_class
FROM dbo.vw_Screening_Exceedance
GROUP BY location_code, matrix, cas_rn, chemical_name, criterion_set;
GO

/* One row per location against the primary criteria sets: the worst exceedance and its band. */
CREATE OR ALTER VIEW dbo.vw_Screening_Location AS
WITH ranked AS (
    SELECT  s.*,
            ROW_NUMBER() OVER (PARTITION BY s.location_code
                               ORDER BY ISNULL(s.max_ratio, 0) DESC, s.n_inconclusive DESC, s.chemical_name) AS rn
    FROM dbo.vw_Screening_Summary s
    WHERE s.is_primary = 1
), totals AS (
    SELECT  location_code,
            SUM(CASE WHEN n_exceed > 0 THEN 1 ELSE 0 END)       AS n_analytes_exceeding,
            SUM(CASE WHEN n_inconclusive > 0 THEN 1 ELSE 0 END) AS n_analytes_inconclusive
    FROM dbo.vw_Screening_Summary
    WHERE is_primary = 1
    GROUP BY location_code
)
SELECT  l.location_code,
        l.location_type,
        l.easting,
        l.northing,
        r.chemical_name   AS worst_analyte,
        r.max_result      AS worst_result,
        r.criterion_value AS worst_criterion,
        r.unit            AS worst_unit,
        r.criterion_set,
        r.max_ratio,
        ISNULL(t.n_analytes_exceeding, 0)    AS n_analytes_exceeding,
        ISNULL(t.n_analytes_inconclusive, 0) AS n_analytes_inconclusive,
        CASE WHEN r.location_code IS NULL THEN 'No data'
             WHEN r.max_ratio > 10 THEN '>10x'
             WHEN r.max_ratio > 1  THEN '1-10x'
             WHEN ISNULL(t.n_analytes_inconclusive, 0) > 0 THEN 'Inconclusive'
             ELSE 'Below criterion' END AS ratio_band
FROM dbo.ref_Location l
LEFT JOIN ranked r ON r.location_code = l.location_code AND r.rn = 1
LEFT JOIN totals t ON t.location_code = l.location_code;
GO
