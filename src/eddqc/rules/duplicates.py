"""FD-01: field duplicate precision against the parent sample."""
from __future__ import annotations

import pandas as pd

from .base import Output, Ref, Rule, q_estimate
from .spikes import rpd

RPD_LIMIT = {"W": 30.0, "S": 50.0}
ABS_FACTOR = {"W": 1.0, "S": 2.0}


class DuplicateRules(Rule):
    family = "Field duplicates"
    rule_ids = ("FD-01",)

    def run(self, d: pd.DataFrame, ref: Ref, out: Output) -> None:
        fds = d[d.is_trg & (d.sample_type == "FD") & (d.parent_sample_code != "")]
        trg = d[d.is_trg]
        parent_idx = trg.reset_index().set_index(["sys_sample_code", "method_code", "fraction", "cas_rn"])
        parent_idx = parent_idx[~parent_idx.index.duplicated()]
        for row, f in fds.iterrows():
            key = (f.parent_sample_code, f.method_code, f.fraction, f.cas_rn)
            if key not in parent_idx.index:
                continue
            p = parent_idx.loc[key]
            if not f.is_detect and not p.is_detect:
                continue
            kind = "S" if f.matrix == "SO" else "W"
            rl = max(x for x in (f.rl_n, p.rl_n, 0.0) if pd.notna(x))
            a = f.result_value_n if f.is_detect else f.rl_n
            b = p.result_value_n if p.is_detect else p.rl_n
            if pd.isna(a) or pd.isna(b):
                continue
            if f.is_detect and p.is_detect and a > 5 * rl and b > 5 * rl:
                value, limit = rpd(a, b), RPD_LIMIT[kind]
                failed = value > limit
                msg = f"{f.chemical_name} FD {a:g} vs parent {b:g}: RPD {value:.0f}% above {limit:g}%"
                obs, lim_txt = f"{value:.0f}%", f"{limit:g}%"
            else:
                diff, limit = abs(a - b), ABS_FACTOR[kind] * rl
                failed = diff > limit
                msg = f"{f.chemical_name} FD {a:g} vs parent {b:g}: difference {diff:g} above {limit:g} (near RL)"
                obs, lim_txt = f"{diff:g}", f"{limit:g}"
            if failed:
                out.exc("FD-01", row, msg, observed=obs, limit=lim_txt)
                for x in (row, int(p.source_row_no)):
                    out.qual("FD-01", [x], q_estimate(d.at[x, "is_detect"]))
