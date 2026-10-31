/* 03 - Staging tables. Every EDD row lands here as text, exactly as received. */
SET NOCOUNT ON;

CREATE TABLE dbo.stg_Batch (
    batch_id       int IDENTITY(1,1) PRIMARY KEY,
    file_name      nvarchar(260) NOT NULL,
    file_hash      char(64)      NOT NULL CONSTRAINT uq_stg_Batch_hash UNIQUE,
    lab_code       varchar(20)   NULL,
    loaded_utc     datetime2(0)  NOT NULL DEFAULT SYSUTCDATETIME(),
    row_count      int           NOT NULL,
    status         varchar(12)   NOT NULL DEFAULT 'LOADED'
        CONSTRAINT ck_stg_Batch_status CHECK (status IN ('LOADED','VALIDATED','PROMOTED','REJECTED')),
    validated_utc  datetime2(0)  NULL,
    promoted_utc   datetime2(0)  NULL,
    rows_promoted  int           NULL,
    rows_held      int           NULL
);

CREATE TABLE dbo.stg_Result (
    batch_id            int           NOT NULL REFERENCES dbo.stg_Batch(batch_id),
    source_row_no       int           NOT NULL,   -- line number in the EDD file (header is line 1)
    sys_sample_code     nvarchar(60)  NULL,
    lab_sample_id       nvarchar(60)  NULL,
    sample_type         nvarchar(20)  NULL,
    parent_sample_code  nvarchar(60)  NULL,
    location_code       nvarchar(30)  NULL,
    matrix              nvarchar(10)  NULL,
    sample_date         nvarchar(30)  NULL,
    depth_top_m         nvarchar(20)  NULL,
    depth_base_m        nvarchar(20)  NULL,
    coc_id              nvarchar(30)  NULL,
    cooler_id           nvarchar(30)  NULL,
    receipt_date        nvarchar(30)  NULL,
    cooler_temp_c       nvarchar(20)  NULL,
    custody_seal_intact nvarchar(10)  NULL,
    sample_ph           nvarchar(20)  NULL,
    lab_code            nvarchar(20)  NULL,
    method_code         nvarchar(30)  NULL,
    fraction            nvarchar(5)   NULL,
    lab_batch_id        nvarchar(30)  NULL,
    extraction_date     nvarchar(30)  NULL,
    analysis_date       nvarchar(30)  NULL,
    dilution_factor     nvarchar(20)  NULL,
    cas_rn              nvarchar(30)  NULL,
    chemical_name       nvarchar(100) NULL,
    result_value        nvarchar(30)  NULL,
    detect_flag         nvarchar(5)   NULL,
    mdl                 nvarchar(30)  NULL,
    rl                  nvarchar(30)  NULL,
    unit                nvarchar(15)  NULL,
    result_type         nvarchar(10)  NULL,
    spike_added         nvarchar(30)  NULL,
    percent_recovery    nvarchar(30)  NULL,
    lab_qualifier       nvarchar(10)  NULL,
    -- written by the validation engine
    validator_qualifier varchar(5)    NULL,
    validator_reason    varchar(200)  NULL,
    qc_status           varchar(10)   NULL
        CONSTRAINT ck_stg_Result_status CHECK (qc_status IN ('PASS','QUALIFIED','HELD')),
    CONSTRAINT pk_stg_Result PRIMARY KEY (batch_id, source_row_no)
);
GO
