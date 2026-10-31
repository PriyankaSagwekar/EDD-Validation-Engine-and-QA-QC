"""QA/QC Exception Report: a formatted Excel workbook per batch."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy.engine import Engine

from .db import read_sql

FILLS = {
    "CRITICAL": PatternFill("solid", start_color="F4C7C3"),
    "WARNING": PatternFill("solid", start_color="FCE8B2"),
    "INFO": PatternFill("solid", start_color="D2E3FC"),
    "HELD": PatternFill("solid", start_color="F4C7C3"),
    "QUALIFIED": PatternFill("solid", start_color="FCE8B2"),
    "PASS": PatternFill("solid", start_color="D9EAD3"),
}
HEADER_FILL = PatternFill("solid", start_color="1F4E5A")
HEADER_FONT = Font(bold=True, color="FFFFFF")
FAMILY_ORDER = ["Completeness", "Referential integrity", "Structural / depth", "Thermal preservation",
                "Holding time", "Detection boundary", "Blank contamination", "Surrogates", "Matrix spike",
                "Lab control sample", "Field duplicates", "Plausibility"]
SHEET_NAMES = {"Referential integrity": "Referential", "Structural / depth": "Structural-Depth",
               "Thermal preservation": "Preservation", "Detection boundary": "Detection",
               "Blank contamination": "Blanks", "Lab control sample": "LCS",
               "Field duplicates": "Field Duplicates"}


def decision(counts: dict, max_held_fraction: float) -> tuple[str, str]:
    rows = max(counts["rows"], 1)
    held = counts["held"] / rows
    if held > max_held_fraction:
        return ("NO-GO", f"{held:.0%} of rows are held, above the {max_held_fraction:.0%} limit. "
                         "Return the EDD to the laboratory for correction.")
    if counts["held"]:
        return ("PARTIAL", "Promote passed and qualified rows. Held rows stay in staging for review.")
    if counts["qualified"]:
        return ("GO WITH QUALIFIERS", "All rows can be promoted. Qualified results carry validator flags.")
    return ("GO", "All rows passed every check.")


def batch_counts(engine: Engine, batch_id: int) -> dict:
    st = read_sql(engine, "SELECT qc_status, COUNT(*) n FROM dbo.stg_Result WHERE batch_id = :b GROUP BY qc_status",
                  b=batch_id).set_index("qc_status").n
    sev = read_sql(engine, "SELECT severity, COUNT(*) n FROM dbo.qc_Exception WHERE batch_id = :b GROUP BY severity",
                   b=batch_id).set_index("severity").n
    return {"rows": int(st.sum()), "passed": int(st.get("PASS", 0)), "qualified": int(st.get("QUALIFIED", 0)),
            "held": int(st.get("HELD", 0)), "exceptions": int(sev.sum()), "critical": int(sev.get("CRITICAL", 0)),
            "warning": int(sev.get("WARNING", 0)), "info": int(sev.get("INFO", 0))}


def build_report(engine: Engine, batch_id: int, out_dir: Path, max_held_fraction: float = 0.10) -> Path:
    batch = read_sql(engine, "SELECT * FROM dbo.stg_Batch WHERE batch_id = :b", b=batch_id).iloc[0]
    counts = batch_counts(engine, batch_id)
    verdict, advice = decision(counts, max_held_fraction)

    exc = read_sql(engine, """
        SELECT r.family, e.severity, e.rule_id, r.rule_name, e.source_row_no AS edd_row, e.sys_sample_code,
               e.method_code, e.cas_rn, s.chemical_name, e.observed_value, e.limit_value, e.message
        FROM dbo.qc_Exception e
        JOIN dbo.qc_Rule r ON r.rule_id = e.rule_id
        LEFT JOIN dbo.stg_Result s ON s.batch_id = e.batch_id AND s.source_row_no = e.source_row_no
        WHERE e.batch_id = :b
        ORDER BY CASE e.severity WHEN 'CRITICAL' THEN 0 WHEN 'WARNING' THEN 1 ELSE 2 END, e.rule_id, e.source_row_no
    """, b=batch_id)
    summary = read_sql(engine, """
        SELECT family, rule_id, rule_name, severity, n_exceptions, n_samples
        FROM dbo.vw_Exception_Summary WHERE batch_id = :b ORDER BY rule_id
    """, b=batch_id)
    rows = read_sql(engine, """
        SELECT source_row_no AS edd_row, sys_sample_code, sample_type, location_code, method_code, fraction,
               cas_rn, chemical_name, result_value, unit, detect_flag, lab_qualifier, validator_qualifier,
               validator_reason, qc_status
        FROM dbo.stg_Result WHERE batch_id = :b ORDER BY source_row_no
    """, b=batch_id)
    rules = read_sql(engine, "SELECT rule_id, family, rule_name, severity, default_qualifier, description "
                             "FROM dbo.qc_Rule ORDER BY rule_id")

    by_sample = rows.groupby(["sys_sample_code", "sample_type", "location_code"], dropna=False).qc_status \
        .value_counts().unstack(fill_value=0)
    for c in ("PASS", "QUALIFIED", "HELD"):
        if c not in by_sample.columns:
            by_sample[c] = 0
    by_sample = by_sample[["PASS", "QUALIFIED", "HELD"]].reset_index()
    by_sample["decision"] = by_sample.apply(
        lambda r: "Held in staging" if r.HELD and not (r.PASS or r.QUALIFIED)
        else "Partly held" if r.HELD else "Promoted with qualifiers" if r.QUALIFIED else "Promoted", axis=1)
    by_sample = by_sample.sort_values(["HELD", "QUALIFIED"], ascending=False)

    out_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(str(batch.file_name)).stem
    path = out_dir / f"Batch{batch_id:03d}_{stem}_QAQC_Exception_Report.xlsx"

    meta = [
        ("QA/QC Exception Report", ""),
        ("", ""),
        ("Batch ID", batch_id),
        ("File", batch.file_name),
        ("Laboratory", batch.lab_code),
        ("Loaded (UTC)", str(batch.loaded_utc)),
        ("Validated (UTC)", str(batch.validated_utc)),
        ("", ""),
        ("Import decision", verdict),
        ("Advice", advice),
        ("", ""),
        ("Rows in EDD", counts["rows"]),
        ("Rows passed", counts["passed"]),
        ("Rows qualified", counts["qualified"]),
        ("Rows held", counts["held"]),
        ("Critical exceptions", counts["critical"]),
        ("Warning exceptions", counts["warning"]),
        ("Info exceptions", counts["info"]),
    ]
    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        pd.DataFrame(meta, columns=["Item", "Value"]).to_excel(xw, sheet_name="Summary", index=False, header=False)
        summary.to_excel(xw, sheet_name="Summary", index=False, startrow=len(meta) + 2)
        for fam in FAMILY_ORDER:
            sub = exc[exc.family == fam].drop(columns="family")
            if len(sub):
                sub.to_excel(xw, sheet_name=SHEET_NAMES.get(fam, fam)[:31], index=False)
        rows[rows.validator_qualifier.notna()].to_excel(xw, sheet_name="Qualified Results", index=False)
        by_sample.to_excel(xw, sheet_name="Promoted vs Held", index=False)
        rows[rows.qc_status == "HELD"].to_excel(xw, sheet_name="Held Rows", index=False)
        rules.to_excel(xw, sheet_name="Rule Catalogue", index=False)

    _format(path, len(meta), verdict)
    return path


def _format(path: Path, meta_rows: int, verdict: str) -> None:
    wb = load_workbook(path)
    for ws in wb.worksheets:
        header_row = meta_rows + 3 if ws.title == "Summary" else 1
        for cell in ws[header_row]:
            if cell.value is not None:
                cell.fill, cell.font = HEADER_FILL, HEADER_FONT
        if ws.title != "Summary":
            ws.freeze_panes = "A2"
            ws.auto_filter.ref = ws.dimensions
        headers = {c.value: c.column for c in ws[header_row] if c.value}
        for key in ("severity", "qc_status"):
            if key in headers:
                col = headers[key]
                for r in range(header_row + 1, ws.max_row + 1):
                    cell = ws.cell(r, col)
                    if cell.value in FILLS:
                        cell.fill = FILLS[cell.value]
        for col_cells in ws.columns:
            width = max(len(str(c.value)) if c.value is not None else 0 for c in col_cells[:200])
            ws.column_dimensions[get_column_letter(col_cells[0].column)].width = min(max(width + 2, 8), 70)
    ws = wb["Summary"]
    for r in range(2, meta_rows + 1):
        ws.cell(r, 1).font = Font(bold=True)
    ws["A1"].font = Font(bold=True, size=16)
    colour = {"GO": "D9EAD3", "GO WITH QUALIFIERS": "D9EAD3", "PARTIAL": "FCE8B2", "NO-GO": "F4C7C3"}[verdict]
    ws["B9"].fill = PatternFill("solid", start_color=colour)
    ws["B9"].font = Font(bold=True, size=12)
    ws["B10"].alignment = Alignment(wrap_text=True)
    ws.column_dimensions["B"].width = 70
    wb.save(path)
