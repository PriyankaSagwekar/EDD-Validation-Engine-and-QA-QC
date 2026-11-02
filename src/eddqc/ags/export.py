"""Export promoted (validated) master data from SQL Server as an AGS 4.2 file, with the
ground investigation data (geology, water strikes, water levels) of the locations in it."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy.engine import Engine

from ..db import read_sql
from .checker import check_text, errors
from .model import to_text
from .writer import edd_to_groups

MASTER_AS_EDD = """
SELECT s.sys_sample_code, t.lab_sample_id, s.sample_type, s.parent_sample_code, s.location_code, s.matrix,
       s.sample_datetime AS sample_date, s.depth_top_m, s.depth_base_m, s.coc_id, s.cooler_id,
       rc.receipt_datetime AS receipt_date, rc.cooler_temp_c, rc.custody_seal_intact, t.sample_ph, t.lab_code,
       t.method_code, t.fraction, t.lab_batch_id, t.extraction_datetime AS extraction_date,
       t.analysis_datetime AS analysis_date, t.dilution_factor, r.cas_rn, a.chemical_name, r.result_value,
       r.detect_flag, r.mdl, r.rl, r.unit, r.result_type, r.spike_added, r.percent_recovery, r.lab_qualifier,
       r.validator_qualifier, r.validator_reason
FROM dbo.dt_Result r
JOIN dbo.dt_Test t     ON t.test_id = r.test_id
JOIN dbo.dt_Sample s   ON s.sample_id = t.sample_id
JOIN dbo.ref_Analyte a ON a.cas_rn = r.cas_rn
LEFT JOIN dbo.dt_Receipt rc ON rc.coc_id = s.coc_id AND rc.cooler_id = s.cooler_id
WHERE (:batch IS NULL OR r.batch_id = :batch)
ORDER BY r.batch_id, r.source_row_no
"""
SITE_QUERIES = {
    "geology": "SELECT * FROM dbo.ref_Geology ORDER BY location_code, depth_top_m",
    "strikes": "SELECT * FROM dbo.ref_Water_Strike ORDER BY location_code, strike_depth_m",
    "strike_readings": "SELECT * FROM dbo.ref_Water_Strike_Reading ORDER BY location_code, strike_depth_m, "
                       "minutes_after",
    "levels": "SELECT * FROM dbo.ref_Water_Level ORDER BY location_code, reading_datetime",
}


def _text(v) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)) or v is pd.NaT:
        return ""
    if isinstance(v, pd.Timestamp):
        return v.strftime("%Y-%m-%d %H:%M")
    if isinstance(v, float):
        return np.format_float_positional(v, trim="-")
    return str(v)


def export_from_db(engine: Engine, out_dir: Path, batch: int | None = None,
                   include_lab_qc: bool = False) -> tuple[Path, list]:
    df = read_sql(engine, MASTER_AS_EDD, batch=batch)
    if df.empty:
        raise ValueError("No promoted results to export" + (f" for batch {batch}" if batch else ""))
    df = df.astype(object).apply(lambda s: s.map(_text))
    locations = read_sql(engine, "SELECT * FROM dbo.ref_Location")
    site = {name: read_sql(engine, sql).astype(object).apply(lambda s: s.map(_text))
            for name, sql in SITE_QUERIES.items()}
    text = to_text(edd_to_groups(df, locations, include_lab_qc=include_lab_qc, site=site))
    _, issues = check_text(text)
    if errors(issues):
        raise ValueError("Export failed the AGS checks:\n" + "\n".join(map(str, errors(issues)[:10])))
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = f"_batch{batch:03d}" if batch else ""
    path = out_dir / f"RIE01_{date.today():%Y%m%d}{suffix}.ags"
    path.write_bytes(text.encode("ascii"))
    return path, issues
