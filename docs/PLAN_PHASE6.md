# Plan: Phase 6 — Dashboard, ArcGIS maps and stretch development

> **Superseded in part (2026-11-02):** the AGS code lists are now committed, not git-ignored, and the AGS viewer was added. See `docs/PLAN_AGS_VIEWER.md`. This file is kept as the record of the Phase 6 plan.

## Context
Phases 1–5 of the EDD QA/QC engine are built and verified (17 tests pass). Phase 6 stretch items from `CLAUDE.md` are not started. The user wants a **public, clickable dashboard** for a portfolio, with **maps made in ArcGIS**, while the pipeline and its results stay **local**. Decisions made:
- Dashboard in **Streamlit**, in a **separate repo** `C:\Users\priya\Desktop\EDD-QC-Dashboard`, hosted free on Streamlit Community Cloud.
- Pipeline results are exported from local SQL Server to a **DuckDB file** (tables for charts) and a **GeoPackage** (map layers), kept locally and published to the dashboard.
- Maps are built in **ArcGIS Online** from the GeoPackage and **embedded** in Streamlit.
- In scope: dashboard, UK screening report, AGS4, ArcGIS maps. **Out of scope:** groundwater checks (ion balance, field vs lab pH/EC).

Other decisions: DuckDB chosen over Parquet / Azure SQL for hosting (Azure SQL free tier kept as a possible later upgrade); AGS work stays in Repo 1; AGS export follows **AGS 4.2** and the official AGS code lists supplied by the user.

Principles kept from the existing build: reference values live in `src/eddqc/refdata.py` (seed SQL is regenerated); outputs read SQL **views**, never raw tables; site, lab and criteria stay labelled fictional/illustrative.

---

## Architecture

**Pull model (decided):** the pipeline repo knows nothing about the dashboard. The dashboard repo pulls from the local SQL Server views.

```
REPO 1  EDD-Validation-Engine-and-QA-QC (local)
  data/incoming EDDs → run-all → SQL Server EnvDataQC (stg_ → qc_ → dt_ → vw_ views)
  python -m eddqc gis-export → data/gis/site_qc.gpkg → upload to ArcGIS Online

REPO 2  EDD-QC-Dashboard
  scripts/refresh_data.py  (runs on the laptop only)
     reads vw_ views from .\SQLEXPRESS → data/envdataqc.duckdb + data/manifest.json
     --push: git commit + push
  GitHub → Streamlit Community Cloud → public URL
     app reads data/envdataqc.duckdb (charts, tables)
     app embeds ArcGIS Online maps from config/maps.toml (iframe)
```

- No live link between SQL Server and DuckDB: `refresh_data.py` is a one-way copy run on demand. The hosted site is a snapshot.
- Hosted app deps (`requirements.txt`): `streamlit`, `pandas`, `duckdb`, `plotly`. Refresh-only deps (`requirements-dev.txt`): `pyodbc`, `sqlalchemy`. The hosted app never needs `pyodbc`.
- Updating the website: Repo 1 `run-all` → Repo 2 `python scripts/refresh_data.py --push` → overwrite the ArcGIS Online layer with the new GeoPackage (same item, embeds keep working).

---

## Phase 6A — Reporting views and GeoPackage export (Repo 1)

**`sql/09_dashboard_views.sql`** (add to `SCRIPT_ORDER` in `src/eddqc/db.py`):
- `vw_Batch_Summary` — one row per batch: rows, passed, qualified, held, critical/warning, held fraction, status, loaded time.
- `vw_Qualifier_Summary` — final validator qualifier counts by batch, method, analyte group.
- `vw_Held_Rows` — rows held in staging with their exception messages.
- `vw_Result_Timeseries` — usable TRG results for N/FD samples with `monitoring_round`, `plot_value` (result if detect, RL if non-detect), `point_class` (Detect / Non-detect / Qualified), criterion value (after 6B).

**GeoPackage export:** extend `src/eddqc/gis_export.py` (`export_locations` already reads `vw_Location_QC_Status`) so `gis-export` (and the end of `run-all`) also writes `data/gis/site_qc.gpkg` (EPSG:27700) with the items below, via `geopandas`/`pyogrio`. Fallback: GeoJSON + CSV if geopandas will not install on Python 3.14. Existing CSV/GeoJSON outputs stay.

**GeoPackage contents (for ArcGIS)**
| Item | Type | Source | Used for |
|---|---|---|---|
| `location_qc_status` | points | `vw_Location_QC_Status` | Site map, RAG by `qc_rag`, pop-up counts |
| `results_timeseries` | table (relate on `location_code`) | `vw_Result_Timeseries` | Results chart in ArcGIS Dashboard |
| `screening_results` | table | `vw_Screening_Exceedance` (6B) | Screening details |
| `location_screening_summary` | points | `vw_Screening_Exceedance` grouped by location | Screening map by worst exceedance band |

**Tests (Repo 1):** new views' totals agree with `stg_Batch` and `vw_Exception_Summary` (using the `EnvDataQC_Test` fixture from `tests/test_pipeline_db.py`); GeoPackage layers are EPSG:27700; `plot_value` = RL for every non-detect.

---

## Phase 6B — UK screening report (Repo 1)
- `refdata.SCREENING`: several criteria sets per matrix (`DWS`, `EQS-freshwater`, `GAC-residential`), values illustrative.
- `vw_Screening_Exceedance`: usable results vs criterion with ratio; classes Exceeds / Below / ND compliant / ND inconclusive (RL > criterion, same logic as DET-04).
- `src/eddqc/screening.py` + CLI `screen [--set DWS]` → `data/reports/Screening_<set>.xlsx`, reusing `report.py` formatting.
- Picked up automatically by `refresh_data.py` (DuckDB table) and `gis-export` (two GeoPackage items).
- Tests: edit a clean simulated EDD for at-criterion, above, and ND-with-high-RL cases.

---

## Phase 6C — ArcGIS Online maps (done by the user; guide in `docs/ARCGIS_GUIDE.md`)
1. Check the account type supports hosted feature layers and public sharing (ArcGIS Online org, or ArcGIS Location Platform free tier).
2. Upload `site_qc.gpkg` → hosted feature layer.
3. Web map **Site QC**: `location_qc_status` symbolised by `qc_rag`; pop-ups with counts; "fictional site" note.
4. Web map **Screening**: `location_screening_summary` by exceedance band; pop-up shows worst analyte and ratio.
5. ArcGIS Dashboard **Results explorer**: map + selectors (location, analyte) + serial chart of `plot_value` over time split by `point_class`, criterion as reference line.
6. Share all items **Everyone (public)**; copy their URLs into Repo 2 `config/maps.toml`.
7. Updating: Item → Update data → Overwrite with the new GeoPackage (same item id, embeds keep working).
8. ArcGIS Pro report figure (recommended, covers the "ArcGIS map layout" stretch item): BNG map with legend, scale bar, north arrow and "fictional site" note, exported as PDF/PNG for the README; RAG symbology saved as `gis/location_qc_status.lyrx`.
- Also closes the outstanding CLAUDE.md check: the GeoPackage/GeoJSON plots at the site in EPSG:27700.

---

## Phase 6D — Streamlit dashboard (Repo 2: `C:\Users\priya\Desktop\EDD-QC-Dashboard`)
```
EDD-QC-Dashboard/
  app.py                 overview page + "fictional data" banner + "Data as of" from manifest
  pages/                 one file per page
  lib/data.py            DuckDB queries (read-only), cached with st.cache_data
  lib/maps.py            reads config/maps.toml, embeds with st.components.v1.iframe
  config/maps.toml       ArcGIS Online URLs
  scripts/refresh_data.py  reads views from .\SQLEXPRESS (server/database via env vars
                           EDDQC_SERVER / EDDQC_DATABASE, defaults as Repo 1 settings.toml),
                           writes a fresh data/envdataqc.duckdb + data/manifest.json
                           (export time, Repo 1 git commit, table names, row counts, schema version,
                           max_held_fraction); --push commits and pushes
  data/envdataqc.duckdb, data/manifest.json
  requirements.txt       streamlit, pandas, duckdb, plotly          (hosted app)
  requirements-dev.txt   pyodbc, sqlalchemy, pytest                  (refresh script + tests)
  tests/                 AppTest smoke tests
  README.md
```
Pages:
1. **Overview** — KPI tiles, batch status table, held fraction vs 10 % limit (DuckDB).
2. **Exceptions** — filters by batch/family/severity/rule, bar chart, drill-down table, CSV download (DuckDB).
3. **Batch detail** — GO/NO-GO, promoted vs held, held rows with reasons (DuckDB; GO/NO-GO rule copied from `report.decision()` in Repo 1, threshold stored in manifest).
4. **Site map** — embedded ArcGIS web map *Site QC*.
5. **Results explorer** — embedded ArcGIS Dashboard; below it a Plotly chart from DuckDB for the same data (hollow non-detects, qualifier marks, criterion line) as backup.
6. **Screening** — embedded ArcGIS *Screening* map + Plotly location × analyte heatmap from DuckDB (ArcGIS Online Dashboards have no matrix heat chart).

Startup checks: manifest present, required tables exist, warn if schema version differs; if a map URL is missing, show a notice instead of a broken frame.

Deploy: push Repo 2 to GitHub → share.streamlit.io → New app → `app.py` → `https://<name>.streamlit.app`. Free apps sleep when idle (~30 s wake).

**Tests (Repo 2):** `streamlit.testing.v1.AppTest` renders every page against a small committed test DuckDB without errors; refresh test (skipped if SQL Server is unreachable) checks each DuckDB table row count equals its source view.

---

## Phase 6E — AGS4 export and import (Repo 1, same repo)
Kept in Repo 1 because import feeds the existing loader and rules, export reads `vw_Result_Validated`, and both share `edd_schema.py`, `refdata.py` and the simulator. Isolated in its own subpackage so it could be split out later.

**Standard followed: AGS 4.2 (December 2025)**, from the user's copy of the spec (`docs/reference/AGS-v-4-2-Dec-2025.pdf`, git-ignored). Key consequences:
- **ERES is removed in 4.2 → results go in ELRG** (Environmental Laboratory Reporting, child of SAMP).
- TRAN_AGS = `4.2`. CSV rules 1–20 (section 4.1.1) apply: ASCII, every item double-quoted, CRLF line ends, GROUP/HEADING/UNIT/TYPE/DATA rows, headings in dictionary order, user headings appended at the end in DICT order.
- Every PA code used must be in ABBR, every unit in UNIT (case-sensitive, e.g. `ug/l`, `mg/kg`), every type in TYPE.

**Files:** `src/eddqc/ags/` → `dictionary.py` (the subset of AGS 4.2 groups/headings we use, with status */R, unit, type, in dictionary order — transcribed from the PDF), `mapping.py` (EDD column ↔ AGS heading, code lists), `writer.py`, `reader.py`, `checker.py` (our own implementation of the rules we rely on: 1–7, 10a/10b/10c, 12–17, 18–19b). `python-ags4` used only as an optional second check if it installs and supports 4.2.

**Groups written** (headings verified against AGS 4.2):
| Group | Headings we populate | Source |
|---|---|---|
| PROJ | PROJ_ID*R, PROJ_NAME, PROJ_LOC, PROJ_CLNT, PROJ_ENG, PROJ_MEMO ("fictional data") | `refdata.SITE` |
| TRAN | TRAN_ISNO*R, TRAN_DATE R, TRAN_PROD R, TRAN_STAT R, TRAN_DESC, TRAN_AGS R (`4.2`), TRAN_RECV R, TRAN_DLIM, TRAN_RCON | export run |
| TYPE / UNIT | TYPE_TYPE*R, TYPE_DESC R / UNIT_UNIT*R, UNIT_DESC R | generated from what is used |
| ABBR | ABBR_HDNG*R, ABBR_CODE*R, ABBR_DESC R, ABBR_LIST | LOCA_TYPE, SAMP_TYPE, ELRG_CODE, ELRG_MATX (SOLID/LIQUID), ELRG_RTYP (INITIAL), ELRG_TADE, DICT_TYPE/DICT_STAT |
| DICT | DICT_TYPE*R, DICT_GRP*R, DICT_HDNG*, DICT_STAT, DICT_DTYP, DICT_DESC R, DICT_UNIT | user headings below |
| LOCA | LOCA_ID*, LOCA_TYPE, LOCA_NATE, LOCA_NATN, LOCA_GREF (`OSGB`), LOCA_GL, LOCA_FDEP, LOCA_NSRI (`27700`), LOCA_REM | `ref_Location` |
| MONG | LOCA_ID*, MONG_ID*, MONG_DIS*, MONG_TYPE, MONG_TRZ, MONG_BRZ (well screen) | `ref_Location` screen depths |
| SAMP | LOCA_ID*, SAMP_TOP*, SAMP_REF*, SAMP_TYPE*, SAMP_ID*, SAMP_BASE, SAMP_DTIM, SAMP_MATX, SAMP_TYPC (Normal / blank / duplicate / spike), SAMP_LINK (RL to parent sample for FD/MS/MSD), SAMP_REM | `dt_Sample` |
| CHOC | sample keys, CHOC_REF* (COC id), CHOC_TO, CHOC_DDIS, CHOC_BTCH | `dt_Receipt` |
| ELRG | sample keys, SPEC_REF*, SPEC_DPTH*, ELRG_CODE*R, ELRG_METH*, ELRG_MATX*, ELRG_RTYP*, ELRG_TADE*, ELRG_TICN*, ELRG_RUNI*R, ELRG_LSID, ELRG_RTCD (TRG / SUR / IC), ELRG_IQLF (validator qualifier), ELRG_LQLF (lab qualifier), ELRG_RVAL, ELRG_RTXT (e.g. `<0.5`), ELRG_NAME, ELRG_DCAT, ELRG_DETF, ELRG_ORG, ELRG_RDLM (RL), ELRG_MDLM (MDL), ELRG_DUNI, ELRG_CASC (CAS), ELRG_RDAT, ELRG_SGRP (lab batch), ELRG_DTIM, ELRG_TORD, ELRG_DIL, ELRG_LAB, ELRG_CRED, ELRG_FDEV/ELRG_DEV (e.g. "Holding time"), ELRG_REM (validator reason) | `vw_Result_Validated` |

**User-defined headings (DICT)** — only for data AGS 4.2 has no heading for; names follow Rule 19a/19b (≤9 chars, group prefix):
| Heading | Meaning |
|---|---|
| CHOC_CTMP | cooler temperature on receipt (DegC) |
| CHOC_SEAL | custody seal intact (YN) |
| ELRG_PH | sample pH on receipt |
| ELRG_EXDT | extraction date/time |
| ELRG_SPKA | spike added |
| ELRG_PREC | percent recovery (%) |

**Official AGS code lists (supplied by the user: ELRG.csv, ABBR.csv, UNITS.csv, DATATYPE.csv)** — stored locally in `docs/reference/ags/` and git-ignored (AGS lists are a registered-user download). The checker validates against them when present; a small derived mapping of the codes we actually use lives in `refdata.py` so tests run without them.

*ELRG_CODE mapping* (our analyte code → AGS code), held as `refdata.AGS_ELRG_CODE`:
| Our code | AGS ELRG_CODE | AGS description |
|---|---|---|
| 7 metals, Benzene, Toluene, Ethylbenzene, o-Xylene, TCE, PCE, Vinyl chloride, DCM, all 16 PAH | same CAS number | approved CAS codes |
| 179601-23-1 m/p-Xylene | **P1374** | m,p-Xylenes |
| BTEX-TOT | **P1330** | Total BTEX |
| TPH-ALI >C10-12 / >C12-16 / >C16-21 / >C21-35 | **P1410 / P1411 / P1412 / P1413** | Aliphatics >C10-12 … >C21-35 |
| TPH-ARO >C10-12 / >C12-16 / >C16-21 / >C21-35 | **P1357 / P1358 / P1359 / P1360** | Aromatics >C10-12 … >C21-35 |
| TPH-TOT-C10C40 | **P1404** | TPH >C10-40 |
| Surrogates 1868-53-7, 2037-26-5, 460-00-4, 321-60-8, 1718-51-0 | same CAS number | approved |
| 84-15-1 o-Terphenyl (surr) | *not in AGS list* → project code `84-15-1` declared in ABBR with ABBR_LIST = `RIE01` | only non-standard determinand |
ELRG_CASC carries the CAS number where one exists; ELRG_NAME carries our chemical name.

*Pick-list codes (all standard AGS 4.2 unless stated):*
| Heading | Our value → AGS code |
|---|---|
| LOCA_TYPE | BH, MW → `CP` (cable percussion); TP → `TP`. "MW" is not an AGS code; the well is described in MONG instead (MONG_TYPE `GWMP` groundwater monitoring point, MONG_TRZ/BRZ = screen) |
| LOCA_GREF | `OSGB` |
| SAMP_TYPE | soil → `ES`, water (incl. blanks) → `EW` |
| SAMP_TYPC (free text, no ABBR needed) | Normal, Field duplicate, Field blank, Equipment blank, Trip blank, Matrix spike, Matrix spike duplicate, Method blank, Laboratory control sample |
| ELRG_MATX | SO → `SOLID`; WG, WQ → `LIQUID` |
| ELRG_RTYP | `INITIAL` |
| ELRG_RTCD | target → `TRG`; surrogate → `SUR`; spiked compound in MS/MSD/LCS → `IC` (replaces the planned user heading ELRG_RSTY) |
| ELRG_LOCN | `LAB` |
| ELRG_TORD (text) | from `dt_Test.fraction` (Total / Dissolved) |
| DICT_TYPE / DICT_STAT / DICT_DTYP | `HEADING`; `OTHER`; `1DP`, `YN`, `DT`, `U` |

*Units* (UNITS.csv is case-sensitive): our `ug/L` → **`ug/l`**, `mg/kg`, `%`, `DegC`, `m`, pH → **`UNITLESS`**, dates `yyyy-mm-dd`, `yyyy-mm-ddThh:mm`. Mapping in `refdata.AGS_UNIT`; the writer refuses any unit not in the list.

*Lab-only QC samples* (method blanks, LCS) have no field location. Default export contains field samples only (N, FD, FB, EB, TB, MS, MSD). `--include-lab-qc` adds them under a project location `LAB` with LOCA_TYPE project code `LABQC` declared in ABBR (ABBR_LIST = `RIE01`), so a full round trip is possible.

*Checker additions:* every ELRG_CODE is an approved code or declared in ABBR; every PA value is in the AGS ABBR list or declared in the file's ABBR group; every unit is in UNITS; every TYPE is in DATATYPE.

**Export** `python -m eddqc ags-export [--batch N] [--usable-only] [--include-lab-qc]`: query views → build one DataFrame per group → write `data/ags/RIE01_<date>.ags` → run `checker.py` (and python-ags4 if available); fail on errors.

**Import** `python -m eddqc ags-import <file.ags>` (and `run-all` accepts `.ags` in `data/incoming`):
1. Run the checker; reject the file (move to `data/rejected`) on errors, like `EDDFormatError` today. Older files using ERES (AGS 4.0/4.1) are read and mapped the same way, with a warning.
2. Join ELRG → SAMP → LOCA (+ CHOC) and rename headings to EDD columns from `edd_schema.py`.
3. Pass the DataFrame into the existing loader path in `loader.py` (hash check, staging insert), so every QA/QC rule runs unchanged.
4. Files from other producers that lack the DICT fields get blank receipt/spike data; the existing rules (e.g. PRES-03) then flag it, which is the realistic outcome.

**Tests:** round trip with `--include-lab-qc` (export → import → validate) gives the same results and qualifiers; without it, the re-imported file raises REF-04 (no method blank), which is expected; exported file passes the checker; a small hand-made third-party-style AGS file imports and is flagged for missing receipt data; a corrupt AGS file is rejected before load.

---

## Phase 6F — Documentation
- Repo 1 README: architecture diagram, `gis-export`, `screen`, `ags-export` / `ags-import` commands, link to the dashboard.
- Repo 2 README: demo URL at the top, screenshots, how data arrives, how to refresh.
- `docs/ARCGIS_GUIDE.md`; update `CLAUDE.md` implementation notes; refresh `docs/PLAN_PHASE6.md` with this plan.

**Interview prep: `interview_prep/Interview_QA.md`** (private, git-ignored; currently Parts 1–14, Q1–Q137). Update it at the end of each phase so answers describe what was actually built, with a final pass in 6F. Keep the existing style: first-person answers, outcome first, one concrete project detail, US EPA vs UK practice called out.

*Revise existing answers that become out of date:*
| Question | Change |
|---|---|
| Q1–Q3 elevator pitches | add the public dashboard link, ArcGIS maps, screening report and AGS 4.2 import/export; replace "what I'd add next" |
| Q36 "How does it compare to AGS4?" | **correct the error**: ERES was removed in AGS 4.2, lab results now go in ELRG; describe the mapping as built |
| Q104–Q105 GIS export | add the GeoPackage (EPSG:27700) and why it suits ArcGIS better than GeoJSON |
| Q106 "Power BI?" | why Streamlit + ArcGIS Online were chosen, and how Power BI could read the same views |
| Q107–Q108 dashboards / concentrations in ArcGIS | answer from the built dashboard and screening map |
| Q110 screening criteria | describe the built screening report (criteria sets, ND inconclusive class) |
| Q116 "How would you add AGS4?" | becomes "How did you add AGS 4.2?" |
| Q120 limitations, Q127 do differently | update (snapshot not live, illustrative criteria, AGS lists not redistributable) |
| Part 14 quick reference card | add EPSG 27700, AGS codes (P1374, P1330, P1404, P1410–P1413, P1357–P1360), new CLI commands, dashboard URL |

*Add new parts (numbering continues from Q137):*
- **Part 15 — Dashboard and hosting:** why a separate dashboard repo; why DuckDB snapshot not live SQL Server (laptop not reachable, Windows auth, no credentials in the cloud); the pull model and `refresh_data.py`; manifest and schema-version check; Azure SQL as the upgrade path and its trade-offs; how the hosted app avoids pyodbc; testing with AppTest; data freshness and how a user knows the "data as of" date.
- **Part 16 — Screening report:** DWS vs EQS vs GAC (what each protects); why only usable (non-R) results are screened; the four classes; why an ND with RL above the criterion is "inconclusive" not "compliant"; illustrative-values disclaimer.
- **Part 17 — AGS 4.2:** group hierarchy (PROJ → LOCA → SAMP → ELRG); KEY vs REQUIRED headings; ABBR/UNIT/TYPE/DICT and Rules 15–19; ELRG_CODE (CAS vs P-codes, the o-terphenyl project code); unit case-sensitivity (`ug/l`); lab-only QC samples with no location; the round-trip test; what happens when a third-party AGS file lacks receipt data; BS 8574 data-management context.
- **Part 18 — ArcGIS:** GeoPackage layers and relates; RAG symbology and `.lyrx`; ArcGIS Online hosted layers, overwrite to keep embeds working; layout figure conventions (BNG, scale bar, north arrow); live query-layer option against SQL Server.
- **Behavioural addition:** "Tell me about a time you got something wrong" — planned AGS headings from memory, checked against the AGS 4.2 spec and code lists, found ERES had been replaced by ELRG and two codes needed P-codes, corrected before building.

## Build order
0. Refresh `docs/PLAN_PHASE6.md` with this plan.
1. 6A views + GeoPackage → 2. 6D Repo 2 dashboard (DuckDB pages first, map pages show "map not configured") → deploy → 3. 6B screening (republish) → 4. 6C ArcGIS Online maps, add URLs → 5. 6E AGS4 → 6. 6F docs. Each step ends with tests green, a commit, and the matching `Interview_QA.md` section updated (that file is git-ignored, so it is never committed).

## Publishing Repo 1 to GitHub (end of Phase 6)
- Target: the user's existing **private** repo `PriyankaSagwekar/EDD-Validation-Engine-and-QA-QC` (local repo currently has no remote).
- Only after every phase is done, full `pytest` is green, README/CLAUDE.md are updated, and a final check confirms git-ignored items stay out (`interview_prep/`, `docs/reference/`, `.venv/`, generated `data/` folders).
- Steps: `git remote add origin https://github.com/PriyankaSagwekar/EDD-Validation-Engine-and-QA-QC.git` → `git fetch origin` and check the remote is empty (if it has an initial commit such as a README or licence, merge it rather than force-push) → `git push -u origin main`.
- Repo 2 (dashboard) needs its own GitHub repo for Streamlit Community Cloud; the user creates it and does the Streamlit sign-in. Confirm with the user before pushing either repo.

## Critical files
- Repo 1 modify: `src/eddqc/cli.py`, `src/eddqc/db.py`, `src/eddqc/gis_export.py`, `src/eddqc/refdata.py` (screening sets, `AGS_ELRG_CODE`, `AGS_UNIT`), `src/eddqc/loader.py` (accept `.ags`), `requirements.txt` (`geopandas`), `.gitignore` (`docs/reference/`), `README.md`, `CLAUDE.md`.
- Repo 1 new: `sql/09_dashboard_views.sql`, `src/eddqc/screening.py`, `src/eddqc/ags/` (dictionary, mapping, writer, reader, checker), `docs/ARCGIS_GUIDE.md`, tests.
- Local only (git-ignored): `docs/reference/ags/AGS-v-4-2-Dec-2025.pdf`, `docs/reference/ags/{ELRG,ABBR,UNITS,DATATYPE}.csv` (present as of 2026-11-02; add `docs/reference/` to `.gitignore` before any commit).
- Repo 2: everything new (layout above).
- Private (git-ignored): `interview_prep/Interview_QA.md` — revised and extended as above.
- Reuse: `db.get_engine`, `db.read_sql`, `config.load_settings`, `report.decision`, `report.py` formatting, `gis_export.export_locations`, `loader.load_file`, fixtures in `tests/conftest.py`.

## Verification
```powershell
# Repo 1
.\.venv\Scripts\python.exe -m eddqc init-db --reset
.\.venv\Scripts\python.exe -m eddqc simulate --seed 42
.\.venv\Scripts\python.exe -m eddqc run-all
.\.venv\Scripts\python.exe -m pytest
# Repo 2
python scripts\refresh_data.py
streamlit run app.py
pytest
```
- Dashboard totals match `python -m eddqc status` and the Excel report summary.
- `site_qc.gpkg` opens in ArcGIS Pro in EPSG:27700; after upload, ArcGIS Online RAG colours match the Overview counts.
- Public Streamlit URL opens in a private window with no login; embedded maps load.
- Screening workbook counts match `vw_Screening_Exceedance`; AGS4 file passes the checker.
