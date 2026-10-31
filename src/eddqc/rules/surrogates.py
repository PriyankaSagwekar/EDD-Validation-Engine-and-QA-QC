"""SUR-01: surrogate recoveries outside the allowable range (e.g. 70-130%)."""
from __future__ import annotations

import pandas as pd

from .base import Output, Ref, Rule, q_for_recovery


class SurrogateRules(Rule):
    family = "Surrogates"
    rule_ids = ("SUR-01",)

    def run(self, d: pd.DataFrame, ref: Ref, out: Output) -> None:
        lim = ref.surrogate_limits
        for row in d.index[d.result_type == "SUR"]:
            r = d.loc[row]
            key = (r.method_code, r.cas_rn)
            rec = r.percent_recovery_n if pd.notna(r.percent_recovery_n) else r.result_value_n
            if key not in lim.index or pd.isna(rec):
                continue
            lo, hi = lim.at[key, "lower_pct"], lim.at[key, "upper_pct"]
            if lo <= rec <= hi:
                continue
            targets = d.index[(d.sys_sample_code == r.sys_sample_code) & (d.method_code == r.method_code) & d.is_trg]
            direction = "low" if rec < lo else "high"
            severity = "CRITICAL" if rec < 10 else None
            out.exc("SUR-01", row,
                    f"{r.chemical_name} recovery {rec:g}% {direction} (limits {lo:g}-{hi:g}%); "
                    f"{len(targets)} {r.method_code} result(s) in {r.sys_sample_code} qualified",
                    observed=f"{rec:g}%", limit=f"{lo:g}-{hi:g}%", severity=severity)
            for x in targets:
                out.qual("SUR-01", [x], q_for_recovery(rec, lo, hi, d.at[x, "is_detect"]))
