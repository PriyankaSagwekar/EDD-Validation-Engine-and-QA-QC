# ArcGIS guide: maps from `site_qc.gpkg`

How to turn the pipeline's GIS package into ArcGIS Pro figures and ArcGIS Online maps that the dashboard can embed. The site and data are fictional; say so on every map.

## 1. Produce the package

```powershell
.\.venv\Scripts\python.exe -m eddqc run-all        # or, after a run: python -m eddqc gis-export
```

`data/gis/site_qc.gpkg` (British National Grid, EPSG:27700) contains:

| Item | Type | Key fields | Use |
|---|---|---|---|
| `location_qc_status` | points | `qc_rag`, `n_held`, `n_qualified`, `n_critical_exceptions` | QC status map |
| `location_screening_summary` | points | `ratio_band`, `worst_analyte`, `max_ratio`, `n_analytes_exceeding` | Screening map |
| `results_timeseries` | table | `location_code`, `sample_datetime`, `chemical_name`, `plot_value`, `point_class`, `criterion_value` | Time-series charts |
| `screening_results` | table | `location_code`, `chemical_name`, `criterion_set`, `max_ratio`, `worst_class` | Heat chart, pop-up detail |

CSV copies of each item sit next to the GeoPackage.

## 2. ArcGIS Pro: check the data and make the report figure

1. New project (Map template). Set the map's coordinate system to **British National Grid (EPSG:27700)**.
2. **Add Data** > `site_qc.gpkg` > add both point layers and both tables.
3. Check the points fall at the site (central Leeds, around 430300 E, 433300 N). This closes the outstanding GIS check in `CLAUDE.md`.
4. Symbolise `location_qc_status` with **Unique Values** on `qc_rag`:

   | Value | Colour | Label |
   |---|---|---|
   | RED | `#d03b3b` | Some results held |
   | AMBER | `#fab219` | Some results qualified |
   | GREEN | `#0ca30c` | All results passed |
   | GREY | `#898781` | No data |

   Label points with `location_code`. Save the symbology: right-click the layer > **Sharing > Save As Layer File** > `gis/location_qc_status.lyrx`.
5. Symbolise `location_screening_summary` by `ratio_band` (`>10x` `#d03b3b`, `1-10x` `#ec835a`, `Inconclusive` `#898781`, `Below criterion` `#0ca30c`). Save as `gis/location_screening_summary.lyrx`.
6. **Relates** (Joins and Relates > Add Relate) from each point layer to `results_timeseries` and `screening_results` on `location_code`.
7. Charts: on `results_timeseries` create a **Line Chart** (date `sample_datetime`, number `plot_value`, split by `point_class`, filter one location and analyte); add a guide line at `criterion_value`. On `screening_results` create a **Matrix Heat Chart** (x `chemical_name`, y `location_code`, colour `max_ratio`).
8. Layout (A4 landscape): map frame, title "Riverside Industrial Estate (fictional): QC status", legend, scale bar, north arrow, BNG grid or coordinate note, and the text "Fictional site and simulated data. Screening criteria are illustrative." **Export Layout** to `docs/images/site_qc_layout.png` (and PDF) for the README.

## 3. ArcGIS Online: maps for the dashboard

Check first that your account can create hosted feature layers and share publicly (an ArcGIS Online organisational account, or the ArcGIS Location Platform free tier).

1. **Content > New item** > upload `site_qc.gpkg` > create a hosted feature layer.
2. **Web map "Site QC"**: add `location_qc_status`, style by `qc_rag` (colours above), pop-up showing location type, samples, results held/qualified and critical exceptions. Add a text note that the site is fictional. Save.
3. **Web map "Screening"**: add `location_screening_summary`, style by `ratio_band`, pop-up showing worst analyte, worst result, criterion and ratio. Save.
4. **ArcGIS Dashboard "Results explorer"**: map (Site QC) + category selectors for location and analyte + **Serial chart** on `results_timeseries` (x `sample_datetime`, y `plot_value`, split by `point_class`) with a reference line at the criterion. ArcGIS Dashboards have no matrix heat chart; the Streamlit Screening page provides the heatmap.
5. Share all three items with **Everyone (public)**. Copy each item's URL into the dashboard repo's `config/maps.toml`:

   ```toml
   [maps]
   site_qc = "https://<org>.maps.arcgis.com/apps/mapviewer/index.html?webmap=<id>"
   screening = "https://<org>.maps.arcgis.com/apps/mapviewer/index.html?webmap=<id>"
   results = "https://<org>.maps.arcgis.com/apps/dashboards/<id>"
   ```

   Commit and push the dashboard repo; the pages switch from the built-in map to the ArcGIS map.

## 4. Updating after new data

Run the pipeline, then on the hosted feature layer use **Update Data > Overwrite entire layer** with the new `site_qc.gpkg`. The item id stays the same, so the web maps, the ArcGIS Dashboard and the Streamlit embeds keep working.

## Live alternative (ArcGIS Pro only)

On the same laptop, ArcGIS Pro can read the views directly: **Insert > Connections > New Database Connection** (SQL Server, instance `.\SQLEXPRESS`, operating system authentication, database `EnvDataQC`), then add `vw_Location_QC_Status` and use **XY Table To Point** on `easting`/`northing` (EPSG:27700). This is live but only works on this machine.
