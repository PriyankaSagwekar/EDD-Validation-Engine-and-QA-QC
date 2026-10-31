"""PRES-01..03: cooler temperature, chemical preservation (pH) and custody."""
from __future__ import annotations

import pandas as pd

from .base import FIELD_TYPES, Output, Ref, Rule, first_rows, q_estimate, q_low

TEST_KEY = ["sys_sample_code", "method_code", "fraction"]
SEVERE_TEMP_C = 10.0


def _test_rows(d, r):
    return d.index[(d.sys_sample_code == r.sys_sample_code) & (d.method_code == r.method_code)
                   & (d.fraction == r.fraction)]


class PreservationRules(Rule):
    family = "Thermal preservation"
    rule_ids = ("PRES-01", "PRES-02", "PRES-03")

    def run(self, d: pd.DataFrame, ref: Ref, out: Output) -> None:
        field = d.sample_type.isin(FIELD_TYPES)
        tests = first_rows(d, field, TEST_KEY)
        for _, r in tests.iterrows():
            key = (r.method_code, r.matrix)
            if key not in ref.methods.index:
                continue
            m = ref.methods.loc[key]
            rows = _test_rows(d, r)
            trg = [x for x in rows if d.at[x, "is_trg"]]
            temp = r.cooler_temp_c_n
            if pd.notna(temp) and pd.notna(m.temp_max_c) and (temp > m.temp_max_c or temp < m.temp_min_c):
                limit = f"{m.temp_min_c:g}-{m.temp_max_c:g} C"
                if temp > SEVERE_TEMP_C:
                    out.exc("PRES-01", r.source_row_no,
                            f"Cooler {r.cooler_id} at {temp:g} C (above {SEVERE_TEMP_C:g} C): {r.method_code} rejected",
                            observed=f"{temp:g} C", limit=limit, severity="CRITICAL")
                    out.qual("PRES-01", trg, "R")
                else:
                    out.exc("PRES-01", r.source_row_no,
                            f"Cooler {r.cooler_id} at {temp:g} C, outside {limit} for {r.method_code}",
                            observed=f"{temp:g} C", limit=limit)
                    for x in trg:
                        out.qual("PRES-01", [x], q_estimate(d.at[x, "is_detect"]))
            ph = r.sample_ph_n
            if pd.notna(ph) and pd.notna(m.ph_max) and ph > m.ph_max:
                out.exc("PRES-02", r.source_row_no,
                        f"{r.method_code} bottle pH {ph:g}, method requires pH <= {m.ph_max:g}",
                        observed=ph, limit=f"<= {m.ph_max:g}")
                for x in trg:
                    out.qual("PRES-02", [x], q_low(d.at[x, "is_detect"]))

        samples = first_rows(d, field, ["sys_sample_code"])
        for _, r in samples.iterrows():
            problems = []
            if r.custody_seal_intact == "N":
                problems.append(f"custody seal broken on cooler {r.cooler_id}")
            if r.receipt_date == "":
                problems.append("receipt date missing")
            if r.cooler_temp_c == "":
                problems.append("receipt temperature missing")
            if problems:
                out.exc("PRES-03", r.source_row_no, "; ".join(problems).capitalize(),
                        observed=r.custody_seal_intact or "blank", limit="seal intact, receipt recorded")
