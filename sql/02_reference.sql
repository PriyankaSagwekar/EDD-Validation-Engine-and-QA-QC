/* 02 - Reference (lookup) tables. Limits and rules live here, not in code. */
SET NOCOUNT ON;

CREATE TABLE dbo.ref_Site (
    site_code      varchar(20)   NOT NULL PRIMARY KEY,
    site_name      nvarchar(200) NOT NULL,
    county         nvarchar(100) NULL,
    grid_crs       varchar(20)   NOT NULL
);

CREATE TABLE dbo.ref_Location (
    location_code    varchar(20)   NOT NULL PRIMARY KEY,
    site_code        varchar(20)   NOT NULL REFERENCES dbo.ref_Site(site_code),
    location_type    varchar(10)   NOT NULL,          -- MW monitoring well, BH borehole, TP trial pit
    easting          decimal(10,2) NOT NULL,          -- British National Grid
    northing         decimal(10,2) NOT NULL,
    ground_level_mod decimal(7,2)  NULL,
    final_depth_m    decimal(6,2)  NOT NULL,
    screen_top_m     decimal(6,2)  NULL,
    screen_base_m    decimal(6,2)  NULL,
    CONSTRAINT ck_ref_Location_screen CHECK (screen_top_m IS NULL OR screen_top_m < screen_base_m)
);

CREATE TABLE dbo.ref_Lab (
    lab_code      varchar(20)   NOT NULL PRIMARY KEY,
    lab_name      nvarchar(200) NOT NULL,
    accreditation nvarchar(200) NULL
);

CREATE TABLE dbo.ref_Analyte (
    cas_rn                 varchar(30)   NOT NULL PRIMARY KEY,
    chemical_name          nvarchar(100) NOT NULL,
    analyte_group          varchar(20)   NOT NULL,
    is_surrogate           bit           NOT NULL DEFAULT 0,
    common_lab_contaminant bit           NOT NULL DEFAULT 0,
    sum_into_cas           varchar(30)   NULL      -- component of a reported total, e.g. BTEX-TOT
);

CREATE TABLE dbo.ref_Method (
    method_code             varchar(30)   NOT NULL,
    matrix                  varchar(5)    NOT NULL,
    method_name             nvarchar(100) NOT NULL,
    analyte_group           varchar(20)   NOT NULL,
    holding_time_days       int           NOT NULL,  -- counted from extraction when extraction_holding_days is set
    extraction_holding_days int           NULL,
    temp_min_c              decimal(4,1)  NULL,
    temp_max_c              decimal(4,1)  NULL,
    ph_max                  decimal(4,1)  NULL,
    preservation            nvarchar(100) NULL,
    CONSTRAINT pk_ref_Method PRIMARY KEY (method_code, matrix)
);

CREATE TABLE dbo.ref_Method_Analyte (
    method_code varchar(30) NOT NULL,
    matrix      varchar(5)  NOT NULL,
    cas_rn      varchar(30) NOT NULL REFERENCES dbo.ref_Analyte(cas_rn),
    mdl         float       NOT NULL,
    rl          float       NOT NULL,
    unit        varchar(10) NOT NULL,
    CONSTRAINT pk_ref_Method_Analyte PRIMARY KEY (method_code, matrix, cas_rn),
    CONSTRAINT fk_ref_Method_Analyte_Method FOREIGN KEY (method_code, matrix) REFERENCES dbo.ref_Method(method_code, matrix),
    CONSTRAINT ck_ref_Method_Analyte_limits CHECK (mdl > 0 AND rl >= mdl)
);

CREATE TABLE dbo.ref_Surrogate_Limit (
    method_code varchar(30)  NOT NULL,
    cas_rn      varchar(30)  NOT NULL REFERENCES dbo.ref_Analyte(cas_rn),
    lower_pct   decimal(5,1) NOT NULL,
    upper_pct   decimal(5,1) NOT NULL,
    CONSTRAINT pk_ref_Surrogate_Limit PRIMARY KEY (method_code, cas_rn)
);

CREATE TABLE dbo.ref_Spike_Limit (
    method_code varchar(30)  NOT NULL,
    cas_rn      varchar(30)  NOT NULL REFERENCES dbo.ref_Analyte(cas_rn),
    qc_type     varchar(5)   NOT NULL,   -- MS (also used for MSD) or LCS
    lower_pct   decimal(5,1) NOT NULL,
    upper_pct   decimal(5,1) NOT NULL,
    rpd_max     decimal(5,1) NULL,
    CONSTRAINT pk_ref_Spike_Limit PRIMARY KEY (method_code, cas_rn, qc_type)
);

CREATE TABLE dbo.ref_Screening_Criterion (
    cas_rn          varchar(30)   NOT NULL REFERENCES dbo.ref_Analyte(cas_rn),
    matrix          varchar(5)    NOT NULL,
    criterion_name  nvarchar(100) NOT NULL,
    criterion_value float         NOT NULL,
    unit            varchar(10)   NOT NULL,
    source_note     nvarchar(200) NULL,
    CONSTRAINT pk_ref_Screening_Criterion PRIMARY KEY (cas_rn, matrix, criterion_name)
);

CREATE TABLE dbo.ref_Valid_Value (
    domain      varchar(30)   NOT NULL,
    code        varchar(20)   NOT NULL,
    description nvarchar(200) NULL,
    CONSTRAINT pk_ref_Valid_Value PRIMARY KEY (domain, code)
);
GO
