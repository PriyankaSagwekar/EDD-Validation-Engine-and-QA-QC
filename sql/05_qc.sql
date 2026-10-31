/* 05 - QA/QC rule catalogue, validation runs, exceptions and qualifier assignments. */
SET NOCOUNT ON;

CREATE TABLE dbo.qc_Rule (
    rule_id           varchar(10)   NOT NULL PRIMARY KEY,
    family            nvarchar(50)  NOT NULL,
    rule_name         nvarchar(100) NOT NULL,
    severity          varchar(10)   NOT NULL CHECK (severity IN ('CRITICAL','WARNING','INFO')),
    default_qualifier varchar(5)    NULL,
    description       nvarchar(300) NULL,
    active            bit           NOT NULL DEFAULT 1
);

CREATE TABLE dbo.qc_Run (
    run_id         int IDENTITY(1,1) PRIMARY KEY,
    batch_id       int          NOT NULL REFERENCES dbo.stg_Batch(batch_id),
    started_utc    datetime2(0) NOT NULL,
    finished_utc   datetime2(0) NULL,
    rows_checked   int          NULL,
    n_exceptions   int          NULL,
    n_critical     int          NULL,
    n_warning      int          NULL,
    n_info         int          NULL,
    rows_held      int          NULL,
    rows_qualified int          NULL
);

/* One row per finding, linked to the EDD row that triggered it. */
CREATE TABLE dbo.qc_Exception (
    exception_id    int IDENTITY(1,1) PRIMARY KEY,
    run_id          int           NOT NULL REFERENCES dbo.qc_Run(run_id),
    batch_id        int           NOT NULL REFERENCES dbo.stg_Batch(batch_id),
    source_row_no   int           NULL,
    rule_id         varchar(10)   NOT NULL REFERENCES dbo.qc_Rule(rule_id),
    severity        varchar(10)   NOT NULL,
    sys_sample_code nvarchar(60)  NULL,
    method_code     nvarchar(30)  NULL,
    cas_rn          nvarchar(30)  NULL,
    observed_value  nvarchar(100) NULL,
    limit_value     nvarchar(100) NULL,
    message         nvarchar(400) NOT NULL
);
CREATE INDEX ix_qc_Exception_batch ON dbo.qc_Exception(batch_id, rule_id);

/* One row per qualifier a rule applies to a result: the trigger row or associated rows. */
CREATE TABLE dbo.qc_Result_Qualifier (
    run_id        int         NOT NULL REFERENCES dbo.qc_Run(run_id),
    batch_id      int         NOT NULL,
    source_row_no int         NOT NULL,
    rule_id       varchar(10) NOT NULL REFERENCES dbo.qc_Rule(rule_id),
    qualifier     varchar(5)  NOT NULL
);
CREATE INDEX ix_qc_Result_Qualifier_row ON dbo.qc_Result_Qualifier(batch_id, source_row_no);
GO
