"""Run every rule family over an EDD and record the outcome."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from .edd_schema import EDD_COLUMNS
from .rules import RULE_FAMILIES, Output, Ref, parse_edd
from .rules.qualifiers import finalize
from .rules.structural import StructuralRules

EXC_COLS = ["rule_id", "severity", "source_row_no", "sys_sample_code", "method_code", "cas_rn",
            "observed_value", "limit_value", "message"]


@dataclass
class ValidationResult:
    exceptions: pd.DataFrame   # one row per finding
    qualifiers: pd.DataFrame   # one row per qualifier applied to a result
    rows: pd.DataFrame         # final status per EDD row
    run_id: int | None = None

    @property
    def counts(self) -> dict:
        sev = self.exceptions.severity.value_counts() if len(self.exceptions) else pd.Series(dtype=int)
        st = self.rows.qc_status.value_counts()
        return {
            "rows": len(self.rows),
            "exceptions": len(self.exceptions),
            "critical": int(sev.get("CRITICAL", 0)),
            "warning": int(sev.get("WARNING", 0)),
            "info": int(sev.get("INFO", 0)),
            "held": int(st.get("HELD", 0)),
            "qualified": int(st.get("QUALIFIED", 0)),
            "passed": int(st.get("PASS", 0)),
        }


def validate_frame(raw: pd.DataFrame, ref: Ref, now: datetime | None = None) -> ValidationResult:
    """Validate an EDD held in a DataFrame. No database needed."""
    d = parse_edd(raw)
    out = Output(d, ref)
    for family in RULE_FAMILIES:
        rule = family(now) if family is StructuralRules else family()
        rule.run(d, ref, out)
    exceptions = pd.DataFrame(out.exceptions, columns=EXC_COLS)
    qualifiers = pd.DataFrame(out.qualifiers, columns=["source_row_no", "rule_id", "qualifier"])
    rows = finalize(d, out.qualifiers)
    return ValidationResult(exceptions, qualifiers, rows)


def read_batch(engine: Engine, batch_id: int) -> pd.DataFrame:
    cols = ", ".join(["source_row_no"] + EDD_COLUMNS)
    with engine.connect() as conn:
        df = pd.read_sql(text(f"SELECT {cols} FROM dbo.stg_Result WHERE batch_id = :b ORDER BY source_row_no"),
                         conn, params={"b": batch_id})
    return df


def _none(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    return v


def validate_batch(engine: Engine, batch_id: int, now: datetime | None = None) -> ValidationResult:
    with engine.connect() as conn:
        status = conn.execute(text("SELECT status FROM dbo.stg_Batch WHERE batch_id = :b"),
                              {"b": batch_id}).scalar()
    if status is None:
        raise ValueError(f"Batch {batch_id} does not exist")
    if status == "PROMOTED":
        raise ValueError(f"Batch {batch_id} is already promoted; load a corrected EDD as a new batch")

    started = datetime.now(timezone.utc).replace(tzinfo=None)
    raw = read_batch(engine, batch_id)
    ref = Ref.from_db(engine)
    result = validate_frame(raw, ref, now)
    c = result.counts

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM dbo.qc_Exception WHERE batch_id = :b"), {"b": batch_id})
        conn.execute(text("DELETE FROM dbo.qc_Result_Qualifier WHERE batch_id = :b"), {"b": batch_id})
        run_id = conn.execute(text(
            "INSERT INTO dbo.qc_Run (batch_id, started_utc, finished_utc, rows_checked, n_exceptions, "
            "n_critical, n_warning, n_info, rows_held, rows_qualified) OUTPUT INSERTED.run_id "
            "VALUES (:b, :s, SYSUTCDATETIME(), :r, :e, :c, :w, :i, :h, :q)"),
            {"b": batch_id, "s": started, "r": c["rows"], "e": c["exceptions"], "c": c["critical"],
             "w": c["warning"], "i": c["info"], "h": c["held"], "q": c["qualified"]}).scalar()

        if len(result.exceptions):
            recs = [{k: _none(v) for k, v in r.items()} | {"run_id": run_id, "batch_id": batch_id}
                    for r in result.exceptions.to_dict("records")]
            for r in recs:
                if r["source_row_no"] is not None:
                    r["source_row_no"] = int(r["source_row_no"])
            conn.execute(text(
                "INSERT INTO dbo.qc_Exception (run_id, batch_id, source_row_no, rule_id, severity, sys_sample_code, "
                "method_code, cas_rn, observed_value, limit_value, message) VALUES (:run_id, :batch_id, "
                ":source_row_no, :rule_id, :severity, :sys_sample_code, :method_code, :cas_rn, :observed_value, "
                ":limit_value, :message)"), recs)
        if len(result.qualifiers):
            recs = [{"run_id": run_id, "batch_id": batch_id, "row": int(r.source_row_no), "rule": r.rule_id,
                     "q": r.qualifier} for r in result.qualifiers.itertuples()]
            conn.execute(text(
                "INSERT INTO dbo.qc_Result_Qualifier (run_id, batch_id, source_row_no, rule_id, qualifier) "
                "VALUES (:run_id, :batch_id, :row, :rule, :q)"), recs)

        conn.execute(text("CREATE TABLE #status (source_row_no int PRIMARY KEY, q varchar(5) NULL, "
                          "reason varchar(200) NULL, st varchar(10) NOT NULL)"))
        recs = [{"r": int(r.source_row_no), "q": _none(r.validator_qualifier), "reason": _none(r.validator_reason),
                 "st": r.qc_status} for r in result.rows.itertuples()]
        conn.execute(text("INSERT INTO #status VALUES (:r, :q, :reason, :st)"), recs)
        conn.execute(text(
            "UPDATE s SET validator_qualifier = t.q, validator_reason = t.reason, qc_status = t.st "
            "FROM dbo.stg_Result s JOIN #status t ON t.source_row_no = s.source_row_no WHERE s.batch_id = :b"),
            {"b": batch_id})
        conn.execute(text("DROP TABLE #status"))
        conn.execute(text("UPDATE dbo.stg_Batch SET status = 'VALIDATED', validated_utc = SYSUTCDATETIME() "
                          "WHERE batch_id = :b"), {"b": batch_id})
    result.run_id = run_id
    return result


def promote_batch(engine: Engine, batch_id: int) -> dict:
    with engine.begin() as conn:
        row = conn.execute(text("EXEC dbo.usp_Promote_Batch @batch_id = :b"), {"b": batch_id}).mappings().first()
    return dict(row)


def reject_batch(engine: Engine, batch_id: int) -> None:
    with engine.begin() as conn:
        conn.execute(text("UPDATE dbo.stg_Batch SET status = 'REJECTED' WHERE batch_id = :b"), {"b": batch_id})
