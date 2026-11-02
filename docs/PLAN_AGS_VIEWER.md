# Plan: AGS Viewer & Borehole Log Profiler (dashboard page)

Status: draft for review, 2026-11-02.

## Goal
Add a page to the Streamlit dashboard (Repo 2, `EDD-QC-Dashboard`). On it, a visitor can upload any AGS 4 file, or open a bundled example, and see:
1. whether the file follows the AGS format rules,
2. every data group as a table,
3. a borehole log for each location: geology, water strikes, well screen and sample depths,
4. groundwater levels over time for each monitoring well.

This covers the "AGS 4 Borehole & Groundwater Log Profiler" idea on the portfolio site, building on the AGS 4.2 reader and checker that already exist.

Why it is needed: today the AGS code is CLI-only, and the simulated site has no geology, water strike or water level data. So both repos need work.

## Headings and codes (checked against AGS 4.2 PDF section 3.6 and ABBR.csv)

| Group | Parent | Key headings (*) | Other headings we fill |
|---|---|---|---|
| GEOL Field geological descriptions | LOCA | LOCA_ID, GEOL_TOP, GEOL_BASE | GEOL_DESC, GEOL_LEG, GEOL_GEOL, GEOL_FORM, GEOL_REM |
| WSTG Water strike, general | LOCA | LOCA_ID, WSTG_DPTH | WSTG_DTIM, WSTG_REM |
| WSTD Water strike, details | WSTG | LOCA_ID, WSTG_DPTH, WSTD_NMIN | WSTD_POST |
| MOND Monitoring readings | MONG | LOCA_ID, MONG_ID, MONG_DIS, MOND_DTIM, MOND_TYPE, MOND_REF | MOND_RDNG, MOND_UNIT (R), MOND_METH, MOND_REM |

- GEOL_LEG uses approved legend codes: 102 MADE GROUND, 202 Silty CLAY, 501 GRAVEL, 801 MUDSTONE (plus 101 TOPSOIL and 401 SAND where needed).
- GEOL_GEOL has no approved list. Codes such as MG, ALV, RTD and MDST are declared in ABBR with `ABBR_LIST = RIE01`.
- MOND_TYPE uses `WDEP` (depth to water from the LOCA datum), with MOND_UNIT `m`.
- HDPH (hole construction) is left out, because a log does not need it.

## Part A: pipeline repo (Repo 1)

**A1. Site investigation data** (new `src/eddqc/site_investigation.py`, values in `refdata.py`)
- Fictional conceptual site model: Made Ground (0 to about 1 m) over Alluvium (silty clay) over River Terrace Deposits (gravel, the aquifer) over Mudstone bedrock.
- Layer depths vary by location from a fixed seed. They are consistent with `final_depth_m`, and every well screen sits in the gravel or mudstone.
- Water strikes in BH and MW holes: struck in the gravel, then rising over 20 minutes (WSTD readings at 0, 5, 10 and 20 min).
- Water levels: one dip reading for each well at every groundwater event in the simulator. A seasonal pattern plus noise stays above the screen base.
- New tables `ref_Geology`, `ref_Water_Strike` and `dt_Water_Level`, seeded through `seed.py` as now. Edit `refdata.py`, never the SQL.

**A2. AGS export and import**
- Add GEOL, WSTG, WSTD and MOND to `ags/dictionary.py` (with PARENT entries) and to the writer.
- `export_from_db` writes them. The checker already handles parent keys (Rule 10c) and ABBR codes (Rule 16).
- The reader ignores these groups for the EDD load, as it ignores MONG today, so QA/QC is unchanged.
- To make the checker easy to copy into the dashboard:
  - `reference.py` takes the reference folder as a parameter, not `PROJECT_ROOT`.
  - `model.py`, `dictionary.py`, `checker.py` and `reference.py` import nothing else from `eddqc`.

**A3. Tests**
- The export contains the four groups and passes the checker.
- Geology layers are continuous from 0 to final depth, with no gaps or overlaps.
- Every screen sits inside the aquifer layers.
- Every water level is above the well base.
- The AGS round-trip test still gives identical exceptions.

## Part B: dashboard repo (Repo 2)

**B1. Sharing the AGS code.** Recommended: copy the four files into `lib/ags/` with `scripts/sync_ags.py`. That script copies them from the sibling repo and records the source commit at the top of each file, and a test checks the copies are unchanged.
- Why: the hosted app stays light. Both repos are public (2026-11-02), so `pip install` from GitHub would work, but it would pull in all of the pipeline's dependencies (pyodbc, SQLAlchemy, geopandas, openpyxl) for four small files.
- **Official code lists are committed as CSVs** (user decision, 2026-11-02). The lists are freely downloadable, and the AGS states no use terms for them.
  - **Repo 1:** change `.gitignore` so the four CSVs in `docs/reference/ags/` are tracked. The PDF stays ignored.
  - **Repo 2:** `scripts/sync_ags.py` copies the CSVs into `lib/ags/reference/` together with the code files.
  - **Attribution:** a `SOURCE.md` beside the CSVs credits the source as "© The Association of Geotechnical and Geoenvironmental Specialists". It also gives the AGS website and the download date, and says the lists are included unchanged for a non-commercial portfolio project.
  - **Fallback:** the built-in subset stays, for when the CSVs are absent.
- **List statuses.** The user will replace the CSVs with versions that also contain Proposed and Declined rows. The checker reads the `Status` column:

  | Status of a code or unit used in a file | Result |
  |---|---|
  | Approved | OK |
  | Accepted (ELRG only, 26 codes) | INFO: accepted, not yet marked Approved |
  | Proposed | WARNING: proposed, not yet approved by the AGS |
  | Deprecated (64 ELRG codes, 1 unit: g/cm3) | WARNING: deprecated; use the current code |
  | Declined | ERROR: the AGS declined this code; use the approved alternative |
  | Not in the list | Code marked `AGS4`: ERROR (Rule 16). Unit: WARNING (Rule 15). Project codes (`ABBR_LIST` other than AGS4): OK if declared in the file. |

  The writer in Repo 1 still refuses anything that is not Approved, or not a declared project code.
- **List files as uploaded (2026-11-02):**
  - ABBR: 1,043 Approved, 43 Proposed, 15 Declined.
  - UNITS: 158 Approved, 1 Deprecated.
  - ELRG: 2,383 Approved, 26 Accepted, 212 Proposed, 64 Deprecated, 258 Declined.
  - The data type list is now named `DATATYPES.csv`, with a `Version` column and one row per version (e.g. DT for 4.0 and for 4.1/4.2).
  - Every code and unit our export writes is Approved.
- **Loader fixes:**
  - Accept `DATATYPES.csv` or `DATATYPE.csv`. Today a missing `DATATYPE.csv` silently switches the checker to the built-in subset.
  - Keep only the rows whose `Version` includes `4.2`.
- **AGS versions** (user decision, 2026-11-02). The code lists are always checked using their 4.2 rows. A `strict_version` option decides what happens to other versions:
  - **Dashboard AGS viewer (strict):** a file whose TRAN_AGS is not `4.2`, or that has no TRAN group, is rejected with "Only AGS 4.2 files are accepted". Nothing else is shown.
  - **Pipeline `ags-import` / `run-all` (not strict):** works as it does today. Files from 4.0 and 4.1 are accepted with a version WARNING, and legacy ERES results are read as ELRG with a warning. They are checked against the 4.2 rules and lists, so codes no longer in 4.2 show as warnings or errors.
  - Report which lists loaded, with their row counts.
  - Fail the tests if the CSVs are present but cannot be read.
- The built-in fallback subset stays, for running without the CSVs. The page shows which mode the checker ran in.

**B2. New page `pages/ags_viewer.py` ("AGS viewer").**
- Source: file upload (`.ags`, at most 20 MB, held in memory and never saved) or "Use example file". The example is `data/example_RIE01.ags`, copied by `refresh_data.py` from the pipeline's latest export.
- **File check** tab:
  - AGS version (TRAN_AGS), producer, groups and row counts.
  - Checker issues table (rule, group, line, message), errors first.
  - A green or red verdict line.
- **Groups** tab: pick a group and see its table with units and types shown under each heading. Includes a CSV download.
- **Borehole log** tab: pick a LOCA_ID. A Plotly strip log, depth downwards, shows:
  - geology blocks coloured by GEOL_LEG, with descriptions beside them,
  - water strike markers, with the rise shown as an arrow,
  - the well screen bar from MONG_TRZ/BRZ,
  - sample depth ticks from SAMP, with ELRG result counts on hover,
  - the header: ground level, coordinates, final depth.
  - Elevation (mOD) appears in tooltips, not as a second axis.
- **Groundwater** tab:
  - Depth to water (MOND WDEP) over time for selected wells.
  - Groundwater elevation (ground level − depth) as a separate small chart, not a second axis.
  - A location map from LOCA (BNG → WGS84 with pyproj).
- Files without GEOL, MOND or the other groups get a short notice on that tab, not an error.
- Colours: geology uses a fixed, conventional palette (made ground grey-brown, clay olive, sand yellow, gravel orange, rock blue-grey), with a hatch pattern so colour is not the only cue. Status colours as on the other pages.
- Dependencies: add `pyproj` to the hosted `requirements.txt`.

**B3. Tests (AppTest)**
- The page renders with the example file.
- A broken file (CR-only line ends, a missing parent key) shows errors.
- A file with TRAN_AGS `4.1`, or with no TRAN group, is rejected by the viewer, but still loads through `load_file` with a version warning. The existing legacy ERES test stays.
- A file using a Proposed code gives a warning, and a file using a Declined code gives an error. Small test CSVs are used, so this test does not depend on what the real lists contain.
- A third-party-style file with no GEOL or MOND shows the notices.
- The strip log has one block per GEOL row.
- The copied `lib/ags/` matches the recorded source.

## Part C: documentation
Correct the statements that are now wrong:
- `README.md` line 144: the AGS code lists are "a registered-user download, so they are not in this repo".
- `CLAUDE.md` line 217: the AGS reference files "are git-ignored (registered-user material)". Line 176 also still names ERES.
- `src/eddqc/ags/reference.py` docstring: "distributes these lists to registered users, so they are not committed". The file name `DATATYPE.csv` changes too.
- `interview_prep/Interview_QA.md` Q120 item 7: "the official AGS code lists cannot be redistributed". Also the Part 15 AGS answers and the quick reference row.
- `docs/PLAN_PHASE6.md`: add a note at the top that the code-list decision was replaced by this plan. Leave the rest as a record.

Then add the new material:
- Both READMEs: describe the new page and add a screenshot.
- `CLAUDE.md` implementation notes; `docs/ARCGIS_GUIDE.md` is unchanged.
- Portfolio HTML: add "AGS viewer and borehole log profiler" to the dashboard section.
- `interview_prep/Interview_QA.md`: GEOL/WSTG/WSTD/MOND, why the GEOL_GEOL codes are project codes, legend codes, reading a strip log, and depth vs elevation.

## Build order
1. A1 to A3, then rerun `init-db --reset`, `simulate`, `run-all` and `ags-export`, and run `pytest`.
2. B1 to B3, then `refresh_data.py`, `pytest`, and screenshots.
3. Part C. Commit in each repo, and push after the user confirms.

## Not in scope
Other AGS groups (ISPT, HDPH, lab geotechnical tests), editing or fixing AGS files in the browser, saving uploads, and cross-sections between boreholes.
