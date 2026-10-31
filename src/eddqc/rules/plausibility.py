"""PLB-01 / PLB-02: chemically implausible combinations of results."""
from __future__ import annotations

import pandas as pd

from .base import Output, Ref, Rule

TOLERANCE = 1.10


class PlausibilityRules(Rule):
    family = "Plausibility"
    rule_ids = ("PLB-01", "PLB-02")

    def run(self, d: pd.DataFrame, ref: Ref, out: Output) -> None:
        trg = d[d.is_trg]
        # PLB-01 dissolved vs total metals
        tot = trg[trg.fraction == "T"].reset_index().set_index(["sys_sample_code", "method_code", "cas_rn"])
        tot = tot[~tot.index.duplicated()]
        for row, r in trg[(trg.fraction == "D") & trg.is_detect].iterrows():
            key = (r.sys_sample_code, r.method_code, r.cas_rn)
            if key not in tot.index or pd.isna(r.result_value_n):
                continue
            t = tot.loc[key]
            ref_val = t.result_value_n if t.is_detect else t.rl_n
            if pd.notna(ref_val) and r.result_value_n > TOLERANCE * ref_val:
                label = "total" if t.is_detect else "total RL"
                out.exc("PLB-01", row, f"Dissolved {r.chemical_name} {r.result_value} exceeds {label} "
                                       f"{ref_val:g} by more than 10%",
                        observed=r.result_value, limit=f"<= {ref_val * TOLERANCE:.3g}")

        # PLB-02 components vs reported totals
        parents = ref.analytes.sum_into_cas.dropna()
        if parents.empty:
            return
        comp = trg[trg.cas_rn.isin(parents.index) & trg.is_detect].copy()
        comp["total_cas"] = comp.cas_rn.map(parents)
        sums = comp.groupby(["sys_sample_code", "method_code", "fraction", "total_cas"]).result_value_n.sum()
        totals = trg[trg.cas_rn.isin(set(parents.values))]
        for row, r in totals.iterrows():
            key = (r.sys_sample_code, r.method_code, r.fraction, r.cas_rn)
            s = sums.get(key, 0.0)
            ref_val = r.result_value_n if r.is_detect else r.rl_n
            if s > 0 and pd.notna(ref_val) and s > TOLERANCE * ref_val:
                label = "reported total" if r.is_detect else "total RL (total not detected)"
                out.exc("PLB-02", row, f"Sum of components {s:.3g} exceeds {label} {ref_val:g} "
                                       f"for {r.chemical_name}", observed=f"{s:.3g}", limit=f"<= {ref_val * TOLERANCE:.3g}")
