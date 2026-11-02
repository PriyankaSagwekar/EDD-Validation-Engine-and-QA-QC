"""DET-01..05: results near the detection boundary and detection limit consistency."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .base import FIELD_SAMPLES, Output, Ref, Rule

REL_TOL = 0.02


class DetectionRules(Rule):
    family = "Detection boundary"
    rule_ids = ("DET-01", "DET-02", "DET-03", "DET-04", "DET-05")

    def run(self, d: pd.DataFrame, ref: Ref, out: Output) -> None:
        trg = d.is_trg
        det = trg & d.is_detect & d.result_value_n.notna() & d.mdl_n.notna()

        for row in d.index[det & (d.result_value_n < d.mdl_n)]:
            r = d.loc[row]
            out.exc("DET-01", row, f"Detected value {r.result_value} is below the MDL {r.mdl}",
                    observed=r.result_value, limit=f"MDL {r.mdl}")
            out.qual("DET-01", [row], "U")

        between = det & d.rl_n.notna() & (d.result_value_n >= d.mdl_n) & (d.result_value_n < d.rl_n) \
            & ~d.lab_qualifier.str.contains("J", na=False)
        for row in d.index[between]:
            r = d.loc[row]
            out.exc("DET-02", row, f"Value {r.result_value} is between MDL {r.mdl} and RL {r.rl} "
                                   f"but has no J flag", observed=r.result_value, limit=f"RL {r.rl}")
            out.qual("DET-02", [row], "J")

        nd_val = trg & (d.detect_flag == "N") & d.result_value_n.notna()
        nd_bad = nd_val & ~np.isclose(d.result_value_n.fillna(-1), d.rl_n.fillna(-2), rtol=REL_TOL)
        for row in d.index[nd_bad]:
            r = d.loc[row]
            out.exc("DET-03", row, f"Non-detect carries value {r.result_value}; expected blank or RL {r.rl}",
                    observed=r.result_value, limit=f"blank or {r.rl}")

        primary = ref.criteria[ref.criteria.is_primary.astype(int) == 1]
        crit = primary.set_index(["cas_rn", "matrix"]).criterion_value
        nd = trg & (d.detect_flag == "N") & d.sample_type.isin(FIELD_SAMPLES) & d.rl_n.notna()
        for row in d.index[nd]:
            r = d.loc[row]
            key = (r.cas_rn, r.matrix)
            if key in crit.index and r.rl_n > crit[key]:
                out.exc("DET-04", row, f"RL {r.rl} {r.unit} is above the screening criterion {crit[key]:g}; "
                                       "non-detect cannot show compliance",
                        observed=f"RL {r.rl}", limit=f"{crit[key]:g}")

        ma = ref.method_analytes
        lim = trg & d.mdl_n.notna() & d.rl_n.notna()
        for row in d.index[lim]:
            r = d.loc[row]
            if r.rl_n < r.mdl_n:
                out.exc("DET-05", row, f"RL {r.rl} is lower than MDL {r.mdl}", observed=f"RL {r.rl}",
                        limit=f">= MDL {r.mdl}")
                continue
            key = (r.method_code, r.matrix, r.cas_rn)
            if key not in ma.index:
                continue
            exp_mdl, exp_rl = ma.at[key, "mdl"] * r.dilution_n, ma.at[key, "rl"] * r.dilution_n
            if not (np.isclose(r.mdl_n, exp_mdl, rtol=REL_TOL) and np.isclose(r.rl_n, exp_rl, rtol=REL_TOL)):
                out.exc("DET-05", row, f"MDL/RL {r.mdl}/{r.rl} differ from reference {exp_mdl:g}/{exp_rl:g} "
                                       f"at dilution {r.dilution_n:g}",
                        observed=f"{r.mdl}/{r.rl}", limit=f"{exp_mdl:g}/{exp_rl:g}")
