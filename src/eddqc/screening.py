"""Screening report: validated results compared with one set of (illustrative) UK criteria."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy.engine import Engine

from .db import read_sql
from .report import HEADER_FILL, HEADER_FONT

CLASS_FILLS = {
    "Exceeds": PatternFill("solid", start_color="F4C7C3"),
    "ND inconclusive": PatternFill("solid", start_color="D9D9D9"),
    "Below": PatternFill("solid", start_color="D9EAD3"),
    "ND compliant": PatternFill("solid", start_color="D9EAD3"),
}
CLASS_ORDER = ["Exceeds", "ND inconclusive", "Below", "ND compliant"]


def criteria_sets(engine: Engine) -> pd.DataFrame:
    return read_sql(engine, """
        SELECT criterion_set, MAX(criterion_name) AS criterion_name, MAX(matrix) AS matrix,
               MAX(CAST(is_primary AS int)) AS is_primary, COUNT(*) AS n_analytes
        FROM dbo.ref_Screening_Criterion GROUP BY criterion_set ORDER BY criterion_set""")


def build_screening_report(engine: Engine, criterion_set: str, out_dir: Path) -> Path:
    sets = criteria_sets(engine).set_index("criterion_set")
    if criterion_set not in sets.index:
        raise ValueError(f"Unknown criteria set {criterion_set}. Available: {', '.join(sets.index)}")
    info = sets.loc[criterion_set]

    res = read_sql(engine, """
        SELECT location_code, sys_sample_code, matrix, sample_datetime, depth_top_m, depth_base_m,
               cas_rn, chemical_name, analyte_group, result_value, detect_flag, rl, unit,
               validator_qualifier, criterion_value, exceedance_ratio, rl_ratio, screening_class
        FROM dbo.vw_Screening_Exceedance WHERE criterion_set = :s
        ORDER BY location_code, sample_datetime, cas_rn""", s=criterion_set)
    summary = read_sql(engine, """
        SELECT location_code, chemical_name, n_results, n_exceed, n_inconclusive, max_result,
               criterion_value, unit, max_ratio, worst_class
        FROM dbo.vw_Screening_Summary WHERE criterion_set = :s
        ORDER BY ISNULL(max_ratio, 0) DESC""", s=criterion_set)

    by_class = res.screening_class.value_counts().reindex(CLASS_ORDER, fill_value=0)
    by_analyte = (res.assign(exceeds=res.screening_class == "Exceeds",
                             inconclusive=res.screening_class == "ND inconclusive")
                  .groupby(["chemical_name", "unit"], as_index=False)
                  .agg(criterion_value=("criterion_value", "max"), n_results=("cas_rn", "size"),
                       n_exceed=("exceeds", "sum"), n_inconclusive=("inconclusive", "sum"),
                       max_ratio=("exceedance_ratio", "max"),
                       locations_exceeding=("location_code",
                                            lambda s: ", ".join(sorted(set(s[res.loc[s.index, "screening_class"]
                                                                              == "Exceeds"]))))))
    by_analyte = by_analyte.sort_values(["n_exceed", "max_ratio"], ascending=False)
    heat = summary.pivot_table(index="location_code", columns="chemical_name", values="max_ratio", aggfunc="max")

    meta = [
        ("Screening Report", ""),
        ("", ""),
        ("Criteria set", f"{criterion_set}: {info.criterion_name}"),
        ("Matrix", "Soil" if info.matrix == "SO" else "Groundwater"),
        ("Data screened", "Validated, usable (not R) results for primary field samples"),
        ("Generated", datetime.now().strftime("%Y-%m-%d %H:%M")),
        ("Note", "Fictional site. Criteria values are illustrative, not for real assessment."),
        ("", ""),
        *[(c, int(by_class[c])) for c in CLASS_ORDER],
    ]

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"Screening_{criterion_set}.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        pd.DataFrame(meta).to_excel(xw, sheet_name="Summary", index=False, header=False)
        by_analyte.to_excel(xw, sheet_name="Summary", index=False, startrow=len(meta) + 2)
        res[res.screening_class == "Exceeds"].to_excel(xw, sheet_name="Exceedances", index=False)
        res[res.screening_class == "ND inconclusive"].to_excel(xw, sheet_name="Inconclusive NDs", index=False)
        heat.round(2).to_excel(xw, sheet_name="Location x Analyte")
        summary.to_excel(xw, sheet_name="Location Summary", index=False)
        res.to_excel(xw, sheet_name="All Results", index=False)
    _format(path, len(meta))
    return path


def _format(path: Path, meta_rows: int) -> None:
    wb = load_workbook(path)
    for ws in wb.worksheets:
        header_row = meta_rows + 3 if ws.title == "Summary" else 1
        for cell in ws[header_row]:
            if cell.value is not None:
                cell.fill, cell.font = HEADER_FILL, HEADER_FONT
        if ws.title != "Summary":
            ws.freeze_panes = "B2" if ws.title == "Location x Analyte" else "A2"
            ws.auto_filter.ref = ws.dimensions
        headers = {c.value: c.column for c in ws[header_row] if c.value}
        for key in ("screening_class", "worst_class"):
            if key in headers:
                for r in range(header_row + 1, ws.max_row + 1):
                    cell = ws.cell(r, headers[key])
                    if cell.value in CLASS_FILLS:
                        cell.fill = CLASS_FILLS[cell.value]
        if ws.title == "Location x Analyte":
            for row in ws.iter_rows(min_row=2, min_col=2):
                for cell in row:
                    if isinstance(cell.value, (int, float)):
                        cell.fill = CLASS_FILLS["Exceeds" if cell.value > 1 else "Below"]
        for col_cells in ws.columns:
            width = max(len(str(c.value)) if c.value is not None else 0 for c in col_cells[:200])
            ws.column_dimensions[get_column_letter(col_cells[0].column)].width = min(max(width + 2, 8), 60)
    ws = wb["Summary"]
    ws["A1"].font = Font(bold=True, size=16)
    for r in range(2, meta_rows + 1):
        ws.cell(r, 1).font = Font(bold=True)
        if ws.cell(r, 1).value in CLASS_FILLS:
            ws.cell(r, 2).fill = CLASS_FILLS[ws.cell(r, 1).value]
    wb.save(path)
