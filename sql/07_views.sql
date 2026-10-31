/* 07 - Reporting views used by the Excel report, GIS export and any dashboard. */
SET NOCOUNT ON;
GO

/* Exception counts by batch, rule and severity. */
CREATE OR ALTER VIEW dbo.vw_Exception_Summary AS
SELECT  b.batch_id,
        b.file_name,
        r.family,
        e.rule_id,
        r.rule_name,
        e.severity,
        COUNT(*)                          AS n_exceptions,
        COUNT(DISTINCT e.sys_sample_code) AS n_samples
FROM dbo.qc_Exception e
JOIN dbo.qc_Rule   r ON r.rule_id  = e.rule_id
JOIN dbo.stg_Batch b ON b.batch_id = e.batch_id
GROUP BY b.batch_id, b.file_name, r.family, e.rule_id, r.rule_name, e.severity;
GO

/* QC status per location, with British National Grid coordinates for ArcGIS/QGIS.
   RAG: RED = rows held from import, AMBER = rows qualified, GREEN = all passed, GREY = no data. */
CREATE OR ALTER VIEW dbo.vw_Location_QC_Status AS
WITH res AS (
    SELECT  s.location_code,
            COUNT(DISTINCT s.sys_sample_code)                          AS n_samples,
            COUNT(*)                                                   AS n_results,
            SUM(CASE WHEN s.qc_status = 'HELD'      THEN 1 ELSE 0 END) AS n_held,
            SUM(CASE WHEN s.qc_status = 'QUALIFIED' THEN 1 ELSE 0 END) AS n_qualified,
            MAX(TRY_CONVERT(datetime2(0), s.sample_date))              AS last_sample_date
    FROM dbo.stg_Result s
    WHERE s.location_code IS NOT NULL
    GROUP BY s.location_code
), exc AS (
    SELECT  s.location_code,
            SUM(CASE WHEN e.severity = 'CRITICAL' THEN 1 ELSE 0 END) AS n_critical,
            SUM(CASE WHEN e.severity = 'WARNING'  THEN 1 ELSE 0 END) AS n_warning
    FROM dbo.qc_Exception e
    JOIN dbo.stg_Result s ON s.batch_id = e.batch_id AND s.source_row_no = e.source_row_no
    WHERE s.location_code IS NOT NULL
    GROUP BY s.location_code
)
SELECT  l.location_code,
        l.location_type,
        l.easting,
        l.northing,
        l.final_depth_m,
        ISNULL(res.n_samples, 0)   AS n_samples,
        ISNULL(res.n_results, 0)   AS n_results,
        ISNULL(res.n_held, 0)      AS n_held,
        ISNULL(res.n_qualified, 0) AS n_qualified,
        ISNULL(exc.n_critical, 0)  AS n_critical_exceptions,
        ISNULL(exc.n_warning, 0)   AS n_warning_exceptions,
        res.last_sample_date,
        CASE WHEN res.n_results IS NULL THEN 'GREY'
             WHEN res.n_held > 0        THEN 'RED'
             WHEN res.n_qualified > 0   THEN 'AMBER'
             ELSE 'GREEN' END      AS qc_rag
FROM dbo.ref_Location l
LEFT JOIN res ON res.location_code = l.location_code
LEFT JOIN exc ON exc.location_code = l.location_code;
GO

/* Validated master results, ready for reporting or GIS. */
CREATE OR ALTER VIEW dbo.vw_Result_Validated AS
SELECT  s.sys_sample_code,
        s.location_code,
        l.easting,
        l.northing,
        s.sample_type,
        s.matrix,
        s.sample_datetime,
        s.depth_top_m,
        s.depth_base_m,
        t.method_code,
        t.fraction,
        t.lab_batch_id,
        t.analysis_datetime,
        r.cas_rn,
        a.chemical_name,
        a.analyte_group,
        r.result_type,
        r.result_value,
        r.detect_flag,
        r.mdl,
        r.rl,
        r.unit,
        r.lab_qualifier,
        r.validator_qualifier,
        r.validator_reason,
        CASE WHEN r.validator_qualifier = 'R' THEN 0 ELSE 1 END AS is_usable,
        r.batch_id
FROM dbo.dt_Result r
JOIN dbo.dt_Test     t ON t.test_id   = r.test_id
JOIN dbo.dt_Sample   s ON s.sample_id = t.sample_id
JOIN dbo.ref_Analyte a ON a.cas_rn    = r.cas_rn
LEFT JOIN dbo.ref_Location l ON l.location_code = s.location_code;
GO
