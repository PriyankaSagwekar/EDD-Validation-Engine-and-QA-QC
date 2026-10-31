"""COMP-01..05: required fields, valid codes, parseable values, duplicates, units."""
from __future__ import annotations

import pandas as pd

from .base import DATE_COLS, FIELD_TYPES, NUMERIC_COLS, Output, Ref, Rule

ALWAYS_REQUIRED = ["sys_sample_code", "sample_type", "matrix", "lab_code", "method_code", "fraction",
                   "lab_batch_id", "analysis_date", "cas_rn", "result_type", "detect_flag", "unit"]
CODED = {"sample_type": "sample_type", "matrix": "matrix", "result_type": "result_type",
         "detect_flag": "detect_flag", "fraction": "fraction", "unit": "unit",
         "custody_seal_intact": "yes_no"}
DUP_KEY = ["sys_sample_code", "method_code", "fraction", "cas_rn", "result_type"]


class CompletenessRules(Rule):
    family = "Completeness"
    rule_ids = ("COMP-01", "COMP-02", "COMP-03", "COMP-04", "COMP-05")

    def run(self, d: pd.DataFrame, ref: Ref, out: Output) -> None:
        self._required(d, out)
        self._codes(d, ref, out)
        self._parse(d, out)
        self._duplicates(d, out)
        self._units(d, ref, out)

    def _required(self, d, out):
        req = {c: pd.Series(True, index=d.index) for c in ALWAYS_REQUIRED}
        req["mdl"] = d.is_trg
        req["rl"] = d.is_trg
        field = d.sample_type.isin(FIELD_TYPES)
        for c in ("sample_date", "coc_id", "receipt_date"):
            req[c] = field
        req["location_code"] = d.sample_type.isin(["N", "FD", "MS", "MSD"])
        req["result_value"] = d.is_detect
        spiked = d.is_trg & d.sample_type.isin(["LCS", "MS", "MSD"])
        req["percent_recovery"] = spiked | (d.result_type == "SUR")
        req["spike_added"] = spiked
        missing = pd.DataFrame({c: m & (d[c] == "") for c, m in req.items()})
        for row, flags in missing[missing.any(axis=1)].iterrows():
            cols = [c for c, v in flags.items() if v]
            out.exc("COMP-01", row, f"Required field(s) blank: {', '.join(cols)}", observed="blank",
                    limit=", ".join(cols))

    def _codes(self, d, ref, out):
        for col, domain in CODED.items():
            valid = ref.valid_values.get(domain, set())
            bad = (d[col] != "") & ~d[col].isin(valid)
            for row in d.index[bad]:
                out.exc("COMP-02", row, f"{col} value '{d.at[row, col]}' is not a valid code",
                        observed=d.at[row, col], limit=f"{domain} list")

    def _parse(self, d, out):
        for col in NUMERIC_COLS:
            bad = (d[col] != "") & d[col + "_n"].isna()
            for row in d.index[bad]:
                out.exc("COMP-03", row, f"{col} '{d.at[row, col]}' is not a number",
                        observed=d.at[row, col], limit="numeric")
        for col in DATE_COLS:
            bad = (d[col] != "") & d[col + "_dt"].isna()
            for row in d.index[bad]:
                out.exc("COMP-03", row, f"{col} '{d.at[row, col]}' is not a valid date",
                        observed=d.at[row, col], limit="YYYY-MM-DD HH:MM")

    def _duplicates(self, d, out):
        dup = d.duplicated(DUP_KEY, keep="first")
        for row in d.index[dup]:
            out.exc("COMP-04", row, "Duplicate of an earlier row for the same sample, method, fraction, "
                                    "analyte and result type", observed="duplicate")

    def _units(self, d, ref, out):
        ma = ref.method_analytes
        for row in d.index[d.is_trg & (d.unit != "")]:
            r = d.loc[row]
            key = (r.method_code, r.matrix, r.cas_rn)
            if key in ma.index:
                expected = ma.at[key, "unit"]
                if r.unit != expected:
                    out.exc("COMP-05", row, f"Unit {r.unit} does not match method unit {expected}",
                            observed=r.unit, limit=expected)
        sur = (d.result_type == "SUR") & (d.unit != "") & (d.unit != "%")
        for row in d.index[sur]:
            out.exc("COMP-05", row, f"Surrogate unit {d.at[row, 'unit']} should be %",
                    observed=d.at[row, "unit"], limit="%")
