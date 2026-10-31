"""HT-01 / HT-02: analysis and extraction holding times (Sampling_Date vs Analysis_Date)."""
from __future__ import annotations

import pandas as pd

from .base import FIELD_TYPES, Output, Ref, Rule, first_rows, q_estimate

TEST_KEY = ["sys_sample_code", "method_code", "fraction"]


class HoldingTimeRules(Rule):
    family = "Holding time"
    rule_ids = ("HT-01", "HT-02")

    def run(self, d: pd.DataFrame, ref: Ref, out: Output) -> None:
        tests = first_rows(d, d.sample_type.isin(FIELD_TYPES), TEST_KEY)
        for _, r in tests.iterrows():
            key = (r.method_code, r.matrix)
            if key not in ref.methods.index or pd.isna(r.sample_date_dt):
                continue
            m = ref.methods.loc[key]
            rows = d.index[(d.sys_sample_code == r.sys_sample_code) & (d.method_code == r.method_code)
                           & (d.fraction == r.fraction)]
            ext_limit = m.extraction_holding_days
            if pd.notna(ext_limit) and pd.notna(r.extraction_date_dt):
                days = (r.extraction_date_dt - r.sample_date_dt).total_seconds() / 86400
                self._check(d, out, "HT-02", r, rows, days, ext_limit, "sampling to extraction")
                start, label = r.extraction_date_dt, "extraction to analysis"
            else:
                start, label = r.sample_date_dt, "sampling to analysis"
            if pd.notna(r.analysis_date_dt):
                days = (r.analysis_date_dt - start).total_seconds() / 86400
                self._check(d, out, "HT-01", r, rows, days, m.holding_time_days, label)

    @staticmethod
    def _check(d, out, rule_id, r, rows, days, limit, label):
        if days < 0 or days <= limit:
            return  # negative intervals are reported by STR-04
        trg = [x for x in rows if d.at[x, "is_trg"]]
        msg = f"{r.method_code}: {days:.1f} days {label}, holding time {limit:g} days"
        if days > 2 * limit:
            out.exc(rule_id, r.source_row_no, msg + " (more than 2x, rejected)",
                    observed=f"{days:.1f} d", limit=f"{limit:g} d", severity="CRITICAL")
            out.qual(rule_id, trg, "R")
        else:
            out.exc(rule_id, r.source_row_no, msg, observed=f"{days:.1f} d", limit=f"{limit:g} d")
            for x in trg:
                out.qual(rule_id, [x], q_estimate(d.at[x, "is_detect"]))
