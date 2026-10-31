"""Export location QC status for ArcGIS / QGIS (British National Grid, EPSG:27700)."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from sqlalchemy.engine import Engine

from .db import read_sql


def export_locations(engine: Engine, out_dir: Path) -> tuple[Path, Path]:
    df = read_sql(engine, "SELECT * FROM dbo.vw_Location_QC_Status ORDER BY location_code")
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "location_qc_status.csv"
    df.to_csv(csv_path, index=False)

    features = []
    for r in df.to_dict("records"):
        props = {k: (None if pd.isna(v) else (str(v) if isinstance(v, pd.Timestamp) else v))
                 for k, v in r.items() if k not in ("easting", "northing")}
        for k, v in props.items():
            if hasattr(v, "item"):
                props[k] = v.item()
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [float(r["easting"]), float(r["northing"])]},
            "properties": props,
        })
    gj = {
        "type": "FeatureCollection",
        "name": "location_qc_status",
        # Legacy named CRS member: ArcGIS Pro and QGIS read it, so points land on the British National Grid.
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::27700"}},
        "features": features,
    }
    geojson_path = out_dir / "location_qc_status.geojson"
    geojson_path.write_text(json.dumps(gj, indent=2, default=str), encoding="utf-8")
    return csv_path, geojson_path
