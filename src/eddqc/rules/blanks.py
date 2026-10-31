"""BLK-01..03: method, field/equipment and trip blank contamination (false positives above MDL).

A blank detect is reported on the blank row. Associated field samples with a
detect below the action level (5x the blank, 10x for common lab contaminants)
are qualified B, because the result may come from contamination, not the site.
"""
from __future__ import annotations

import pandas as pd

from .base import FIELD_SAMPLES, Output, Ref, Rule

BLANKS = {
    "BLK-01": (("MB",), "lab_batch_id", "method blank"),
    "BLK-02": (("FB", "EB"), "coc_id", "field/equipment blank"),
    "BLK-03": (("TB",), "coc_id", "trip blank"),
}


class BlankRules(Rule):
    family = "Blank contamination"
    rule_ids = tuple(BLANKS)

    def run(self, d: pd.DataFrame, ref: Ref, out: Output) -> None:
        hit = d.is_trg & d.is_detect & d.result_value_n.notna() & d.mdl_n.notna() \
            & (d.result_value_n > d.mdl_n)
        samples = d.is_trg & d.is_detect & d.sample_type.isin(FIELD_SAMPLES) & d.result_value_n.notna()
        common = ref.analytes.common_lab_contaminant.astype(bool)
        for rule_id, (types, link_col, label) in BLANKS.items():
            for row in d.index[hit & d.sample_type.isin(types)]:
                b = d.loc[row]
                factor = 10 if bool(common.get(b.cas_rn, False)) else 5
                action = factor * b.result_value_n
                assoc = samples & (d[link_col] == b[link_col]) & (d.method_code == b.method_code) \
                    & (d.cas_rn == b.cas_rn) & (d.result_value_n < action)
                n = int(assoc.sum())
                out.exc(rule_id, row,
                        f"{b.chemical_name} detected in {label} {b.sys_sample_code} at {b.result_value} {b.unit} "
                        f"(MDL {b.mdl}); {n} associated result(s) below {factor}x action level qualified B",
                        observed=b.result_value, limit=f"MDL {b.mdl}")
                out.qual(rule_id, d.index[assoc], "B")
