/* 04 - Master tables (EQuIS-style location > sample > test > result).
   Only rows that pass the QA/QC gate are promoted here. */
SET NOCOUNT ON;

CREATE TABLE dbo.dt_Sample (
    sample_id          int IDENTITY(1,1) PRIMARY KEY,
    sys_sample_code    nvarchar(60) NOT NULL CONSTRAINT uq_dt_Sample_code UNIQUE,
    location_code      varchar(20)  NULL REFERENCES dbo.ref_Location(location_code),
    sample_type        varchar(5)   NOT NULL,
    matrix             varchar(5)   NOT NULL,
    sample_datetime    datetime2(0) NULL,
    depth_top_m        decimal(6,2) NULL,
    depth_base_m       decimal(6,2) NULL,
    parent_sample_code nvarchar(60) NULL,
    coc_id             varchar(30)  NULL,
    cooler_id          varchar(30)  NULL,
    batch_id           int          NOT NULL REFERENCES dbo.stg_Batch(batch_id)
);

CREATE TABLE dbo.dt_Receipt (
    coc_id              varchar(30)  NOT NULL,
    cooler_id           varchar(30)  NOT NULL,
    lab_code            varchar(20)  NULL REFERENCES dbo.ref_Lab(lab_code),
    receipt_datetime    datetime2(0) NULL,
    cooler_temp_c       decimal(4,1) NULL,
    custody_seal_intact char(1)      NULL,
    CONSTRAINT pk_dt_Receipt PRIMARY KEY (coc_id, cooler_id)
);

CREATE TABLE dbo.dt_Test (
    test_id             int IDENTITY(1,1) PRIMARY KEY,
    sample_id           int          NOT NULL REFERENCES dbo.dt_Sample(sample_id),
    method_code         varchar(30)  NOT NULL,
    fraction            char(1)      NOT NULL,
    lab_code            varchar(20)  NULL REFERENCES dbo.ref_Lab(lab_code),
    lab_sample_id       nvarchar(60) NULL,
    lab_batch_id        varchar(30)  NULL,
    extraction_datetime datetime2(0) NULL,
    analysis_datetime   datetime2(0) NULL,
    dilution_factor     float        NULL,
    sample_ph           decimal(4,1) NULL,
    CONSTRAINT uq_dt_Test UNIQUE (sample_id, method_code, fraction)
);

CREATE TABLE dbo.dt_Result (
    result_id           int IDENTITY(1,1) PRIMARY KEY,
    test_id             int          NOT NULL REFERENCES dbo.dt_Test(test_id),
    cas_rn              varchar(30)  NOT NULL REFERENCES dbo.ref_Analyte(cas_rn),
    result_type         varchar(5)   NOT NULL,
    result_value        float        NULL,
    detect_flag         char(1)      NOT NULL,
    mdl                 float        NULL,
    rl                  float        NULL,
    unit                varchar(10)  NOT NULL,
    spike_added         float        NULL,
    percent_recovery    float        NULL,
    lab_qualifier       varchar(10)  NULL,
    validator_qualifier varchar(5)   NULL,
    validator_reason    varchar(200) NULL,
    batch_id            int          NOT NULL REFERENCES dbo.stg_Batch(batch_id),
    source_row_no       int          NOT NULL,
    CONSTRAINT uq_dt_Result UNIQUE (test_id, cas_rn, result_type)
);
GO
