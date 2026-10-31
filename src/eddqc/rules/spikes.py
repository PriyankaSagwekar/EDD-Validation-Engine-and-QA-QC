"""MS-01..03 and LCS-01: matrix spike and laboratory control sample recoveries."""
from __future__ import annotations

import pandas as pd

from .base import FIELD_SAMPLES, Output, Ref, Rule, q_estimate, q_for_recovery

KEY = ["parent_sample_code", "method_code", "fraction", "cas_rn"]


def rpd(a: float, b: float) -> float:
    mean = (a + b) / 2
    return 0.0 if mean == 0 else abs(a - b) / mean * 100


class SpikeRules(Rule):
    family = "Matrix spike"
    rule_ids = ("MS-01", "MS-02", "MS-03", "LCS-01")

    def run(self, d: pd.DataFrame, ref: Ref, out: Output) -> None:
        self._matrix_spikes(d, ref, out)
        self._lcs(d, ref, out)

    def _parent_rows(self, d, r):
        return d.index[(d.sys_sample_code == r.parent_sample_code) & (d.method_code == r.method_code)
                       & (d.fraction == r.fraction) & (d.cas_rn == r.cas_rn) & d.is_trg]

    def _matrix_spikes(self, d, ref, out):
        lim = ref.spike_limits
        spikes = d[d.is_trg & d.sample_type.isin(["MS", "MSD"])]
        for row, r in spikes.iterrows():
            key = (r.method_code, r.cas_rn, "MS")
            if key not in lim.index or pd.isna(r.percent_recovery_n):
                continue
            lo, hi = lim.at[key, "lower_pct"], lim.at[key, "upper_pct"]
            parents = self._parent_rows(d, r)
            p = 0.0
            if len(parents):
                pr = d.loc[parents[0]]
                p = pr.result_value_n if pr.is_detect and pd.notna(pr.result_value_n) else 0.0
            if pd.notna(r.spike_added_n) and r.spike_added_n > 0 and p > 4 * r.spike_added_n:
                if r.sample_type == "MS":
                    out.exc("MS-03", row, f"{r.chemical_name}: parent {p:g} is more than 4x spike "
                                          f"{r.spike_added}; recovery not assessable",
                            observed=f"{p:g}", limit=f"<= 4 x {r.spike_added}")
                continue
            rec = r.percent_recovery_n
            if lo <= rec <= hi:
                continue
            q_rows = list(parents)
            out.exc("MS-01", row, f"{r.sample_type} {r.chemical_name} recovery {rec:g}% outside {lo:g}-{hi:g}%; "
                                  f"parent {r.parent_sample_code} qualified",
                    observed=f"{rec:g}%", limit=f"{lo:g}-{hi:g}%", severity="CRITICAL" if rec < 10 else None)
            for x in q_rows:
                out.qual("MS-01", [x], q_for_recovery(rec, lo, hi, d.at[x, "is_detect"]))

        ms = spikes[spikes.sample_type == "MS"].reset_index().set_index(KEY)
        msd = spikes[spikes.sample_type == "MSD"].reset_index().set_index(KEY)
        for key in ms.index.intersection(msd.index):
            a, b = ms.loc[key], msd.loc[key]
            if isinstance(a, pd.DataFrame):
                a = a.iloc[0]
            if isinstance(b, pd.DataFrame):
                b = b.iloc[0]
            lk = (key[1], key[3], "MS")
            if lk not in lim.index or pd.isna(a.result_value_n) or pd.isna(b.result_value_n):
                continue
            rpd_max = lim.at[lk, "rpd_max"]
            value = rpd(a.result_value_n, b.result_value_n)
            if pd.notna(rpd_max) and value > rpd_max:
                out.exc("MS-02", int(b.source_row_no),
                        f"{b.chemical_name} MS/MSD RPD {value:.0f}% above {rpd_max:g}%",
                        observed=f"{value:.0f}%", limit=f"{rpd_max:g}%")
                parents = d.index[(d.sys_sample_code == key[0]) & (d.method_code == key[1])
                                  & (d.fraction == key[2]) & (d.cas_rn == key[3]) & d.is_trg]
                for x in parents:
                    out.qual("MS-02", [x], q_estimate(d.at[x, "is_detect"]))

    def _lcs(self, d, ref, out):
        lim = ref.spike_limits
        targets = d.is_trg & d.sample_type.isin(list(FIELD_SAMPLES) + ["MS", "MSD"])
        for row in d.index[d.is_trg & (d.sample_type == "LCS")]:
            r = d.loc[row]
            key = (r.method_code, r.cas_rn, "LCS")
            if key not in lim.index or pd.isna(r.percent_recovery_n):
                continue
            lo, hi = lim.at[key, "lower_pct"], lim.at[key, "upper_pct"]
            rec = r.percent_recovery_n
            if lo <= rec <= hi:
                continue
            assoc = d.index[targets & (d.lab_batch_id == r.lab_batch_id) & (d.method_code == r.method_code)
                            & (d.cas_rn == r.cas_rn)]
            out.exc("LCS-01", row, f"LCS {r.chemical_name} recovery {rec:g}% outside {lo:g}-{hi:g}%; "
                                   f"{len(assoc)} result(s) in lab batch {r.lab_batch_id} qualified",
                    observed=f"{rec:g}%", limit=f"{lo:g}-{hi:g}%", severity="CRITICAL" if rec < 10 else None)
            for x in assoc:
                out.qual("LCS-01", [x], q_for_recovery(rec, lo, hi, d.at[x, "is_detect"]))
