"""Shared pieces for validation rules: reference data, parsed EDD frame, output collector."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ..edd_schema import EDD_COLUMNS

FIELD_TYPES = ("N", "FD", "FB", "EB", "TB", "MS", "MSD")
FIELD_SAMPLES = ("N", "FD")          # environmental samples that receive qualifiers from batch QC
LAB_QC_TYPES = ("MB", "LCS")
NUMERIC_COLS = ["result_value", "mdl", "rl", "depth_top_m", "depth_base_m", "cooler_temp_c",
                "sample_ph", "dilution_factor", "spike_added", "percent_recovery"]
DATE_COLS = ["sample_date", "receipt_date", "extraction_date", "analysis_date"]


# --------------------------------------------------------------------------- reference data
@dataclass
class Ref:
    locations: pd.DataFrame        # index location_code
    analytes: pd.DataFrame         # index cas_rn
    methods: pd.DataFrame          # index (method_code, matrix)
    method_analytes: pd.DataFrame  # index (method_code, matrix, cas_rn)
    surrogate_limits: pd.DataFrame # index (method_code, cas_rn)
    spike_limits: pd.DataFrame     # index (method_code, cas_rn, qc_type)
    criteria: pd.DataFrame         # columns cas_rn, matrix, criterion_name, criterion_value
    valid_values: dict[str, set]
    rules: pd.DataFrame            # index rule_id
    master_samples: set = field(default_factory=set)

    @classmethod
    def from_tables(cls, t: dict[str, pd.DataFrame], master_samples: set | None = None) -> "Ref":
        vv: dict[str, set] = {}
        for d, c in zip(t["ref_Valid_Value"].domain, t["ref_Valid_Value"].code):
            vv.setdefault(d, set()).add(c)
        num = lambda df, cols: df.astype({c: float for c in cols})
        return cls(
            locations=num(t["ref_Location"], ["final_depth_m", "screen_top_m", "screen_base_m"]
                          ).set_index("location_code"),
            analytes=t["ref_Analyte"].set_index("cas_rn"),
            methods=num(t["ref_Method"], ["holding_time_days", "extraction_holding_days", "temp_min_c",
                                          "temp_max_c", "ph_max"]).set_index(["method_code", "matrix"]),
            method_analytes=num(t["ref_Method_Analyte"], ["mdl", "rl"]
                                ).set_index(["method_code", "matrix", "cas_rn"]),
            surrogate_limits=num(t["ref_Surrogate_Limit"], ["lower_pct", "upper_pct"]
                                 ).set_index(["method_code", "cas_rn"]),
            spike_limits=num(t["ref_Spike_Limit"], ["lower_pct", "upper_pct", "rpd_max"]
                             ).set_index(["method_code", "cas_rn", "qc_type"]),
            criteria=num(t["ref_Screening_Criterion"], ["criterion_value"]),
            valid_values=vv,
            rules=t["qc_Rule"].set_index("rule_id"),
            master_samples=set(master_samples or ()),
        )

    @classmethod
    def from_refdata(cls) -> "Ref":
        """Build reference data straight from refdata.py (no database needed)."""
        from ..seed import reference_tables
        tables = {name: pd.DataFrame(rows, columns=cols) for name, (cols, rows) in reference_tables().items()}
        return cls.from_tables(tables)

    @classmethod
    def from_db(cls, engine) -> "Ref":
        from ..db import read_sql
        names = ["ref_Location", "ref_Analyte", "ref_Method", "ref_Method_Analyte", "ref_Surrogate_Limit",
                 "ref_Spike_Limit", "ref_Screening_Criterion", "ref_Valid_Value", "qc_Rule"]
        tables = {n: read_sql(engine, f"SELECT * FROM dbo.{n}") for n in names}
        tables["qc_Rule"] = tables["qc_Rule"][tables["qc_Rule"].active.astype(bool)]
        master = set(read_sql(engine, "SELECT sys_sample_code FROM dbo.dt_Sample").sys_sample_code)
        return cls.from_tables(tables, master)


# --------------------------------------------------------------------------- parsed EDD
def parse_edd(raw: pd.DataFrame) -> pd.DataFrame:
    """Return a frame indexed by source_row_no with text columns plus typed *_n and *_dt copies."""
    d = raw.copy()
    if "source_row_no" not in d.columns:
        d["source_row_no"] = np.arange(2, len(d) + 2)
    d = d.set_index("source_row_no")
    for c in EDD_COLUMNS:
        if c not in d.columns:
            d[c] = ""
        d[c] = d[c].astype(object).where(d[c].notna(), "").astype(str).str.strip()
    for c in NUMERIC_COLS:
        d[c + "_n"] = pd.to_numeric(d[c].where(d[c] != ""), errors="coerce")
    for c in DATE_COLS:
        d[c + "_dt"] = pd.to_datetime(d[c].where(d[c] != ""), errors="coerce", format="ISO8601")
    d["dilution_n"] = d["dilution_factor_n"].fillna(1.0)
    d["is_trg"] = d.result_type == "TRG"
    d["is_detect"] = d.detect_flag == "Y"
    return d


def first_rows(d: pd.DataFrame, mask: pd.Series, keys: list[str]) -> pd.DataFrame:
    """First row of each group, keeping source_row_no as a column."""
    sub = d[mask].reset_index()
    return sub.drop_duplicates(keys, keep="first")


# --------------------------------------------------------------------------- qualifiers
def q_estimate(detect: bool) -> str:
    return "J" if detect else "UJ"


def q_low(detect: bool) -> str:
    return "J-" if detect else "UJ"


def q_high(detect: bool) -> str | None:
    return "J+" if detect else None


def q_for_recovery(rec: float, lower: float, upper: float, detect: bool) -> str | None:
    if rec < 10:
        return "R"
    if rec < lower:
        return q_low(detect)
    if rec > upper:
        return q_high(detect)
    return None


# --------------------------------------------------------------------------- output collector
class Output:
    def __init__(self, d: pd.DataFrame, ref: Ref):
        self.d = d
        self.ref = ref
        self.exceptions: list[dict] = []
        self.qualifiers: list[tuple[int, str, str]] = []

    def exc(self, rule_id: str, row: int | None, message: str, observed=None, limit=None,
            severity: str | None = None, hold_rows=None) -> None:
        if rule_id not in self.ref.rules.index:
            return  # rule switched off in qc_Rule
        sev = severity or self.ref.rules.at[rule_id, "severity"]
        rec = {"rule_id": rule_id, "severity": sev, "source_row_no": row,
               "sys_sample_code": None, "method_code": None, "cas_rn": None,
               "observed_value": None if observed is None else str(observed)[:100],
               "limit_value": None if limit is None else str(limit)[:100],
               "message": message[:400]}
        if row is not None and row in self.d.index:
            r = self.d.loc[row]
            rec.update(sys_sample_code=r.sys_sample_code or None, method_code=r.method_code or None,
                       cas_rn=r.cas_rn or None)
        self.exceptions.append(rec)
        if sev == "CRITICAL":
            self.hold(rule_id, [row] if row is not None else [])
            if hold_rows is not None:
                self.hold(rule_id, hold_rows)

    def qual(self, rule_id: str, rows, qualifier: str | None) -> None:
        if qualifier is None or rule_id not in self.ref.rules.index:
            return
        for r in rows:
            self.qualifiers.append((int(r), rule_id, qualifier))

    def hold(self, rule_id: str, rows) -> None:
        self.qual(rule_id, rows, "HOLD")


class Rule:
    """A family of checks. Subclasses implement run()."""
    family = ""
    rule_ids: tuple[str, ...] = ()

    def run(self, d: pd.DataFrame, ref: Ref, out: Output) -> None:  # pragma: no cover
        raise NotImplementedError

    def active(self, ref: Ref, rule_id: str) -> bool:
        return rule_id in ref.rules.index
