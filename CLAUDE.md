# CLAUDE.md

This file anchors the approved project plan for the Automated Environmental QA/QC & EDD Validation Engine. The plan below is the version approved on 2026-10-31. Where the finished build differs from it, the section **Implementation notes** at the end describes what the code actually does. Trust that section over the plan text.

---

# Plan: Automated Environmental QA/QC & EDD Validation Engine

## Context
Portfolio project targeting a UK environmental data management role (EQuIS-type systems, lab EDDs, AGS data, SQL automation, GIS, dashboards, contaminated land / groundwater monitoring).
Goal: a working pipeline that takes raw lab EDDs (CSV/Excel), loads them to a SQL Server staging area, runs automated QA/QC rules, writes a QA/QC Exception Report, and only promotes clean data to a master database.

Environment found:
- Project folder is empty (greenfield).
- SQL Server Express running locally: `.\SQLEXPRESS`, Windows auth, **ODBC Driver 17 for SQL Server**, `sqlcmd` installed.
- Python 3.14.5. No packages yet (pandas, pyodbc, sqlalchemy, openpyxl, numpy, faker, pytest needed).

Decisions (defaults chosen to match the job description):
- **Interface:** Python CLI + formatted Excel exception report. Dashboard is a later stretch phase.
- **Analytes:** UK ground investigation / groundwater suite: metals, speciated PAH-16, BTEX + VOCs, TPH-CWG. Surrogates apply to organics only.
- **Import rule:** stage, then gate. Critical failures stay in staging; clean or qualified records promote to master with qualifiers.
- **Data model:** EQuIS-inspired (location → sample → test → result), so terminology carries over in interviews.
- **Coordinates:** British National Grid (EPSG:27700) easting/northing so outputs open directly in ArcGIS.

## Folder structure
```
Environment Data Manager Projects/
  README.md                  project story, ERD, how to run, screenshots
  requirements.txt
  config/settings.toml       connection string, paths, default thresholds
  sql/
    01_create_database.sql   CREATE DATABASE EnvDataQC
    02_reference.sql         ref_* lookup tables
    03_staging.sql           stg_* tables
    04_master.sql            dt_* master tables
    05_qc.sql                qc_* rule/exception/run tables
    06_seed_reference.sql    methods, analytes, holding times, limits, rules
    07_views.sql             reporting views
    08_sp_promote_batch.sql  stored procedure: staging → master
  src/eddqc/
    config.py  db.py          settings + SQLAlchemy/pyodbc engine
    simulate.py               synthetic sites, samples, lab EDDs with injected defects
    loader.py                 read CSV/XLSX EDD, map columns, write to staging
    rules/
      base.py                 Rule interface: id, severity, run(df, ref) → exceptions df
      completeness.py         required fields, valid values, duplicates, units
      referential.py          location/method/analyte/parent-sample links
      structural.py           depth and date integrity
      preservation.py         cooler temperature, pH, custody
      holding_time.py
      detection.py            MDL/RL boundary and screening criteria
      blanks.py               method, field, equipment, trip blanks
      surrogates.py
      spikes.py               LCS, MS/MSD recovery and RPD
      duplicates.py           field duplicate RPD
      qualifiers.py           combines exceptions into final qualifier per result
    engine.py                 runs all rules for a batch, writes qc_Exception
    report.py                 Excel exception report (openpyxl)
    gis_export.py             location QC status → CSV/GeoJSON for ArcGIS
    cli.py                    `python -m eddqc <command>`
  data/incoming/ processed/ rejected/ reports/
  tests/                      pytest, uses simulator answer keys
```

## Phase 1: Data model (SQL Server `EnvDataQC`)
**Reference tables (ref_)**
- `ref_Site`, `ref_Location` (location_code, type BH/MW/TP, easting, northing, ground_level_mOD, **final_depth_m, screen_top_m, screen_base_m**).
- `ref_Lab`.
- `ref_Analyte` (cas_rn, chemical_name, analyte_group, default_unit, common_lab_contaminant flag).
- `ref_Method` (method_code, analyte_group, matrix, holding_time_days, extraction_holding_days, **preservation_code, temp_min_c 0, temp_max_c 6, ph_max**).
- `ref_Method_Analyte` (method, cas_rn, matrix, MDL, RL, unit). Detection limits live here.
- `ref_Surrogate_Limit` (method, surrogate cas_rn, lower_pct default 70, upper_pct default 130).
- `ref_Spike_Limit` (method, cas_rn, qc_type MS/MSD/LCS, lower_pct, upper_pct, rpd_max).
- `ref_Screening_Criterion` (cas_rn, matrix, criterion_name, value, unit). Used by the detection boundary check.
- `ref_Valid_Value` (domain, code): matrix (WG, SO, WQ), sample_type (N, FD, FB, EB, TB, MB, LCS, MS), units, qualifiers.
- `qc_Rule` (rule_id, name, severity CRITICAL/WARNING, action REJECT/QUALIFY, qualifier_code, active).

**Staging (stg_)**: `stg_Batch` (batch_id, file_name, lab, received_utc, status LOADED/VALIDATED/PROMOTED/REJECTED, row_count), `stg_Result` (one row per raw EDD line + batch_id + source_row_no; all columns kept as text plus typed copies).

**Master (dt_)**: `dt_Sample` (sys_sample_code, location, sample_type, matrix, sample_datetime, **depth_top_m, depth_base_m**, parent_sample_code for FD/MS/MSD), `dt_Receipt` (lab, coc_id, receipt_datetime, **cooler_temp_c**, custody_seal_intact, sample_ph), `dt_Test` (sample, method, lab, lab_sample_id, extraction_datetime, analysis_datetime, dilution_factor, lab_batch_id for blank and spike linkage), `dt_Result` (test, cas_rn, result_value, detect_flag, MDL, RL, unit, result_type TRG/SUR/SPK, spike_added, percent_recovery, lab_qualifier, **validator_qualifier**, batch_id).

**QC**: `qc_Run` (run_id, batch_id, started, finished, totals), `qc_Exception` (run_id, batch_id, source_row_no, sys_sample_code, cas_rn, rule_id, severity, observed_value, limit_value, message).

Views: `vw_Exception_Summary` (counts by rule/severity/batch), `vw_Location_QC_Status` (for GIS), `vw_Result_Validated` (master results with qualifiers).
Stored procedure: `usp_Promote_Batch @batch_id` moves rows without CRITICAL exceptions into dt_ tables inside a transaction, applies qualifiers from WARNING exceptions, updates batch status.

## Phase 2: Data simulation (`simulate.py`)
- Seeded (`--seed`) for reproducibility. One site, ~15 boreholes/monitoring wells with BNG coordinates, quarterly groundwater rounds plus soil samples.
- Lab EDD CSV in an EQuIS-EFW2-like layout: sys_sample_code, lab_sample_id, sample_type, matrix, location, sample_date/time, method, lab_batch_id, prep/analysis date, cas_rn, chemical_name, result_value, detect_flag, MDL, RL, unit, result_type, lab_qualifier.
- Each lab batch contains normal samples, a field duplicate, a field/equipment blank, a trip blank (VOC), a method blank, an LCS, an MS/MSD pair, and surrogate rows for organics.
- EDD carries receipt fields too: COC id, receipt datetime, cooler temperature, sample pH, custody seal flag. Soil samples carry depth top/base.
- **Injected defects at configurable rates**, one per rule in Phase 4: holding-time and extraction-time exceedances, warm coolers and bad pH, surrogate/LCS/MS recoveries out of limits, high MS/MSD RPD, blank detections > MDL, detects below MDL, non-detects with values, RL above screening criterion, inverted or too-deep sample depths, unknown locations/methods/CAS numbers, orphan duplicates, analysis before sampling, missing fields, invalid codes/units, duplicate rows.
- Writes a matching `*_answer_key.csv` listing every injected defect, used by tests.
- Outputs a few files as `.xlsx` too, to prove Excel ingestion.

## Phase 3: Loader (`loader.py`)
- Read CSV/XLSX with pandas, normalise headers via a column-map dict, keep raw text, attach batch_id and source_row_no.
- File-level checks before load: required columns present, file not loaded before (hash in stg_Batch).
- Bulk insert to staging (`fast_executemany`).

## Phase 4: Validation rules (`rules/`, `engine.py`)
Thresholds come from ref tables, not hard-coded. Each rule returns a DataFrame of exceptions. Rules run in the order below, since later rules rely on rows passing the earlier ones.

All seven checks the user asked for are covered. Their rule families are marked ★.

| Family | Rule | Logic | Severity / qualifier |
|---|---|---|---|
| Completeness | COMP-01..05 | required fields, valid values, numeric parse, duplicate key, unit matches method | CRITICAL, reject row |
| ★ Referential integrity | REF-01 | location not in ref_Location | CRITICAL |
| | REF-02 | method or CAS number not in ref tables, or analyte not valid for that method | CRITICAL |
| | REF-03 | FD/MS/MSD parent sample missing from batch or master | WARNING |
| | REF-04 | normal sample has no method blank in its lab_batch_id; VOC sample has no trip blank | WARNING |
| | REF-05 | result rows with no sample or test header (orphans) | CRITICAL |
| ★ Structural / depth | STR-01 | depth_top > depth_base | CRITICAL |
| | STR-02 | depth_base > borehole final_depth, or negative depths | CRITICAL |
| | STR-03 | soil sample missing depths; groundwater sample depth outside well screen | WARNING |
| | STR-04 | analysis before sampling, extraction before sampling, sample date in future | CRITICAL |
| | STR-05 | same location + depth + date sampled twice with different sample codes | WARNING |
| ★ Thermal preservation | PRES-01 | cooler_temp_c outside 0–6 °C (above 10 °C escalates) | WARNING `J`/`UJ`, escalate CRITICAL `R` |
| | PRES-02 | sample pH above method limit (e.g. metals > 2, VOCs > 2) | WARNING `J-`/`UJ` |
| | PRES-03 | custody seal broken or receipt missing | WARNING |
| ★ Holding time | HT-01 | (analysis − sample) days > holding_time_days | WARNING `J`/`UJ` plus `H`; > 2× limit CRITICAL `R` |
| | HT-02 | extraction holding time exceeded (organics) | same as HT-01 |
| ★ Detection boundary | DET-01 | detect reported below MDL | WARNING, set to non-detect `U` |
| | DET-02 | detect between MDL and RL with no `J` flag | WARNING `J` |
| | DET-03 | non-detect with a non-blank value not equal to RL | WARNING |
| | DET-04 | RL > screening criterion, so non-detects cannot show compliance | WARNING, report only |
| | DET-05 | RL < MDL in the EDD, or MDL/RL differ from ref values without a dilution factor | WARNING |
| ★ Method blank and other blanks | BLK-01 | method blank detect > MDL; flag samples in same lab_batch_id where result < 5× blank (10× for common lab contaminants) | WARNING `B` (or `U` if below action level) |
| | BLK-02 | field/equipment blank detect > MDL; flag samples from same date and round | WARNING `B` |
| | BLK-03 | trip blank VOC detect > MDL; flag VOC samples in same cooler | WARNING `B` |
| Surrogates | SUR-01 | surrogate %REC outside 70–130 % (method limits) | high `J+`, low `J-`/`UJ`; < 10 % CRITICAL `R` |
| ★ Matrix spike | MS-01 | MS/MSD %REC outside limits; flag parent sample only | high `J+`, low `J-`/`UJ`; < 10 % CRITICAL `R` |
| | MS-02 | MS vs MSD RPD > rpd_max | WARNING `J` |
| | MS-03 | spike not assessable because parent result > 4× spike added | INFO, no qualifier |
| Lab control sample | LCS-01 | LCS %REC outside limits; flag whole lab batch | high `J+`, low `J-`/`UJ`; < 10 % `R` |
| Field duplicates | FD-01 | RPD > 30 % water / 50 % soil when both > 5× RL; absolute difference test when near RL | WARNING `J` |
| Plausibility | PLB-01 | dissolved metal > total metal for same sample beyond 10 % | WARNING |
| | PLB-02 | sum of BTEX or TPH bands > total reported | WARNING |

**Qualifier coverage.** `qualifiers.py` combines all exceptions for a result into one final validator qualifier, using a precedence order `R` > `J-`/`J+`/`UJ` > `J` > `B` > `U`. Codes follow the US EPA National Functional Guidelines, which EQuIS uses by default. Each code has an entry in ref_Valid_Value:

| Code | Meaning | Produced by |
|---|---|---|
| U | not detected at the reported limit | DET-01, BLK-* |
| J | estimated value | HT, PRES, DET-02, MS-02, FD-01 |
| J+ / J- | estimated, likely biased high / low | SUR, MS, LCS, PRES-02 |
| UJ | not detected, limit is estimated | HT, PRES, SUR, MS, LCS on non-detects |
| B | analyte also found in an associated blank | BLK-* |
| H | holding time exceeded | HT-* |
| R | rejected, unusable | CRITICAL escalations |

Lab-supplied flags such as E (above calibration range) and D (diluted) pass through unchanged in lab_qualifier.

`engine.py` runs the rules for a batch, writes `qc_Run` + `qc_Exception`, sets batch status.

## Phase 5: Exception report and CLI
`report.py` builds `reports/<batch>_QAQC_Exception_Report.xlsx`:
- Summary sheet: batch metadata, pass/fail counts by rule and severity, go/no-go for import.
- One sheet per rule family with failed records, observed vs limit, conditional formatting.
- "Promoted vs Held" sheet.

CLI commands:
```
python -m eddqc init-db            # runs sql/*.sql via sqlcmd/pyodbc
python -m eddqc simulate --batches 6 --seed 42
python -m eddqc load data/incoming/<file>
python -m eddqc validate --batch <id>
python -m eddqc report --batch <id>
python -m eddqc promote --batch <id>
python -m eddqc run-all data/incoming   # load → validate → report → promote, moves files
python -m eddqc gis-export          # CSV/GeoJSON of locations + QC status for ArcGIS
```

## Phase 6: Stretch items (role-aligned, after core works)
- AGS4 output/input for the lab data (ABBR/SAMP/ERES groups) to show AGS familiarity.
- Dashboard: Streamlit or Power BI over the reporting views.
- Screening results against UK groundwater criteria (e.g. DWS/EQS) as a separate report. DET-04 already uses the same criteria table.
- Groundwater-specific checks: ion balance error > 10 %, field vs lab pH/EC difference.
- ArcGIS map layout using the GIS export.

## Build order
1. `requirements.txt`, venv, install packages; confirm pyodbc connects to `.\SQLEXPRESS`.
2. SQL scripts 01–06, run `init-db`, check tables and seed rows.
3. Simulator, produce sample EDDs + answer keys.
4. Loader → rules one at a time, each with a pytest against the answer key.
5. Engine, report, promote procedure, `run-all`.
6. GIS export, README with ERD and screenshots.

## Verification
- `pytest`: every injected defect in the answer key appears in `qc_Exception` with the right rule_id; a clean simulated batch yields zero exceptions.
- Unit tests per rule with small hand-built DataFrames for edge cases, such as a result exactly at the MDL, a cooler at exactly 6 °C, or a spike where the parent exceeds 4× the spike amount.
- Qualifier precedence test: a result hit by several rules ends up with the single expected final code.
- End to end: `simulate --seed 42` then `run-all`; check with sqlcmd that `dt_Result` row count = staged rows − CRITICAL rows, and qualifiers match WARNING exceptions.
- Open the Excel report and confirm the summary totals match `vw_Exception_Summary`.
- Load the GeoJSON in ArcGIS/QGIS to confirm locations plot in the right place.

## Risks
- Python 3.14 is very new. If a pyodbc wheel fails to install, use a Python 3.12 venv.
- SQL Express has a 10 GB limit, which is far above what this project needs.

---

# Implementation notes

## Status (2026-11-02)
- Phases 1 to 5 are built and verified.
- Phase 6 is built: reporting views, screening report, GeoPackage, AGS 4.2 export/import, and the Streamlit dashboard in a separate repo (`..\EDD-QC-Dashboard`). The plan is in `docs/PLAN_PHASE6.md`. 32 tests pass in this repo, 10 in the dashboard repo.
- Groundwater checks (ion balance, field vs lab pH/EC) were dropped from Phase 6 at the user's request.
- Still to do by the user: build the ArcGIS Pro figure and ArcGIS Online maps (`docs/ARCGIS_GUIDE.md`), which also closes the outstanding check that the points plot correctly in ArcGIS; deploy the dashboard to Streamlit Community Cloud.

## Phase 6 implementation notes
- **Views.** `sql/09_dashboard_views.sql` holds the dashboard, screening and GIS views. Outputs read views, never raw tables (the dashboard's rule catalogue is the one exception).
- **Screening sets.** `refdata.SCREENING_SETS` replaces `SCREENING`/`SCREENING_NAME`. `ref_Screening_Criterion` has `criterion_set` and `is_primary`; DET-04 and the chart criterion line use the primary set (DWS for groundwater, GAC-RES for soil). All values are illustrative.
- **GeoPackage.** `gis_export.export_package` writes `data/gis/site_qc.gpkg` (EPSG:27700) with `geopandas`/`pyogrio`; both install on Python 3.14.
- **AGS 4.2.** `src/eddqc/ags/`. Results go in ELRG (ERES was removed in 4.2; legacy ERES files are read with a warning). Code mappings are `refdata.AGS_ELRG_CODE`, `AGS_PROJECT_CODES` (o-terphenyl) and `AGS_UNIT`. Total and dissolved results of one sample are separate specimens (`SPEC_REF` = fraction) so the ELRG keys stay unique. Field blanks without a location sit under LOCA_ID `FIELDQC`, lab QC under `LABQC` (only with `--include-lab-qc`). Receipt, pH, extraction and spike data are DICT user headings. Imported rows keep their AGS file line as `source_row_no`.
- **AGS reference files.** The AGS 4.2 PDF and the ELRG/ABBR/UNITS/DATATYPE lists live in `docs/reference/ags/`, which is git-ignored (registered-user material). Without them the checker uses a built-in subset.
- **Line endings.** `.gitattributes` marks `*.ags` as `-text` so files keep CRLF (AGS Rule 2a).
- **Dashboard repo.** Pull model: `scripts/refresh_data.py` there reads this database's views into `data/envdataqc.duckdb` and can push. The hosted app needs no SQL Server driver. Map pages embed ArcGIS Online URLs from `config/maps.toml`, falling back to a built-in map.

## Where the build differs from the plan
- **Reference data source.** `src/eddqc/refdata.py` holds all lookup values and limits. `sql/06_seed_reference.sql` is regenerated from it by `seed.py` on every `init-db`, so edit `refdata.py`, never the SQL file.
- **Extra modules.** `edd_schema.py` holds the EDD column list and header aliases. `rules/plausibility.py` holds PLB-01 and PLB-02, not `duplicates.py`.
- **Extra table.** `qc_Result_Qualifier` records every qualifier a rule applies to a result row. A pseudo-qualifier `HOLD` marks rows that must stay in staging.
- **Gate logic.** A row is HELD if it has a CRITICAL exception, a HOLD, or a final qualifier of R. R-qualified data therefore stays in staging and is not promoted. A batch with more than 10% of rows held is NO-GO and gets status REJECTED. The threshold is `max_held_fraction` in `config/settings.toml`.
- **Qualifier precedence.** The code uses R > UJ > J+/J- > J > U > B. J+ with J- gives J. An estimated non-detect, or a detect reclassified U, gives UJ.
- **H code.** H is not stored as a qualifier. Holding time exceedances show as HT-01 or HT-02 in `validator_reason`.
- **REF-05.** A flat EDD has no separate header records, so REF-05 checks for conflicting sample attributes across rows, and for one lab sample id used by several samples.
- **Blanks.** Associated samples get B only, with no U variant. BLK-02 and BLK-03 link blanks to samples by `coc_id`.
- **Result types.** Only TRG and SUR are used. Spike rows are TRG rows on LCS, MS and MSD samples, carrying `spike_added` and `percent_recovery`.
- **Receipt and pH.** `dt_Receipt` is keyed by `coc_id` and `cooler_id`. `sample_ph` lives on `dt_Test`, because pH belongs to each preserved bottle.
- **CLI.** `simulate` takes `--events` and `--clean`, not `--batches`. Extra commands are `status`, and `promote --force` to override NO-GO.
- **Dependencies.** faker is not used. pandas 3 needs keyword arguments in `to_excel`.
- **Edge-case tests.** These edit a clean simulated EDD instead of hand-building DataFrames. `Ref.from_refdata()` lets rule tests run without a database.

## Working on this project
- Environment: SQL Server Express at `.\SQLEXPRESS` with Windows authentication, database `EnvDataQC`, Python venv in `.venv`.
- Rebuild and rerun everything:
  ```powershell
  .\.venv\Scripts\python.exe -m eddqc init-db --reset
  .\.venv\Scripts\python.exe -m eddqc simulate --seed 42
  .\.venv\Scripts\python.exe -m eddqc run-all
  .\.venv\Scripts\python.exe -m eddqc screen
  .\.venv\Scripts\python.exe -m eddqc ags-export
  .\.venv\Scripts\python.exe -m pytest
  # then, in ..\EDD-QC-Dashboard: python scripts\refresh_data.py [--push]
  ```
- The pipeline test creates and drops a separate `EnvDataQC_Test` database. It never touches `EnvDataQC`.
- When adding a rule: add it to `RULES` in `refdata.py`, implement it in the matching `rules/` module, add an injector to `DEFECTS` in `simulate.py`, and confirm that clean files still raise zero exceptions.
- The site, lab and data are fictional, and the screening criteria are illustrative. Keep them labelled that way.
