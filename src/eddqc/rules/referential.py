"""REF-01..05: links to reference data, QC parents, associated blanks, header consistency."""
from __future__ import annotations

import pandas as pd

from .base import FIELD_SAMPLES, Output, Ref, Rule, first_rows

HEADER_COLS = ["location_code", "sample_type", "matrix", "sample_date", "depth_top_m",
               "depth_base_m", "parent_sample_code"]


class ReferentialRules(Rule):
    family = "Referential integrity"
    rule_ids = ("REF-01", "REF-02", "REF-03", "REF-04", "REF-05")

    def run(self, d: pd.DataFrame, ref: Ref, out: Output) -> None:
        self._locations(d, ref, out)
        self._methods_analytes(d, ref, out)
        self._parents(d, ref, out)
        self._blanks_present(d, out)
        self._headers(d, out)

    def _locations(self, d, ref, out):
        bad = (d.location_code != "") & ~d.location_code.isin(ref.locations.index)
        for _, r in first_rows(d, bad, ["sys_sample_code"]).iterrows():
            rows = d.index[d.sys_sample_code == r.sys_sample_code]
            out.exc("REF-01", r.source_row_no, f"Location {r.location_code} is not in ref_Location",
                    observed=r.location_code, limit="ref_Location", hold_rows=rows)

    def _methods_analytes(self, d, ref, out):
        for row, r in d.iterrows():
            if not r.method_code or not r.cas_rn or not r.matrix:
                continue
            if (r.method_code, r.matrix) not in ref.methods.index:
                out.exc("REF-02", row, f"Method {r.method_code} for matrix {r.matrix} is not in ref_Method",
                        observed=r.method_code, limit="ref_Method")
            elif r.cas_rn not in ref.analytes.index:
                out.exc("REF-02", row, f"CAS {r.cas_rn} is not in ref_Analyte",
                        observed=r.cas_rn, limit="ref_Analyte")
            elif r.result_type == "SUR":
                if (r.method_code, r.cas_rn) not in ref.surrogate_limits.index:
                    out.exc("REF-02", row, f"{r.cas_rn} is not a surrogate for {r.method_code}",
                            observed=r.cas_rn, limit="ref_Surrogate_Limit")
            elif (r.method_code, r.matrix, r.cas_rn) not in ref.method_analytes.index:
                out.exc("REF-02", row, f"{r.cas_rn} is not reported by {r.method_code} ({r.matrix})",
                        observed=r.cas_rn, limit="ref_Method_Analyte")

    def _parents(self, d, ref, out):
        known = set(d.sys_sample_code) | ref.master_samples
        qc = d.sample_type.isin(["FD", "MS", "MSD"])
        for _, r in first_rows(d, qc, ["sys_sample_code"]).iterrows():
            if not r.parent_sample_code or r.parent_sample_code not in known:
                out.exc("REF-03", r.source_row_no,
                        f"{r.sample_type} parent '{r.parent_sample_code or '(blank)'}' not found in batch or master",
                        observed=r.parent_sample_code or "blank", limit="existing sample")

    def _blanks_present(self, d, out):
        mb_batches = set(d.loc[d.sample_type == "MB", "lab_batch_id"])
        env = d.sample_type.isin(FIELD_SAMPLES) & (d.lab_batch_id != "")
        no_mb = env & ~d.lab_batch_id.isin(mb_batches)
        for _, r in first_rows(d, no_mb, ["sys_sample_code", "method_code"]).iterrows():
            out.exc("REF-04", r.source_row_no, f"No method blank reported for lab batch {r.lab_batch_id}",
                    observed=r.lab_batch_id, limit="MB in lab batch")
        tb_cocs = set(d.loc[(d.sample_type == "TB") & (d.method_code == "VOC-HSGCMS"), "coc_id"])
        voc = env & (d.method_code == "VOC-HSGCMS") & (d.coc_id != "") & ~d.coc_id.isin(tb_cocs)
        for _, r in first_rows(d, voc, ["sys_sample_code"]).iterrows():
            out.exc("REF-04", r.source_row_no, f"No trip blank for VOC samples on {r.coc_id}",
                    observed=r.coc_id, limit="TB per chain of custody")

    def _headers(self, d, out):
        for code, g in d[d.sys_sample_code != ""].groupby("sys_sample_code"):
            if len(g) < 2:
                continue
            for col in HEADER_COLS:
                counts = g[col].value_counts()
                if len(counts) > 1:
                    mode = counts.index[0]
                    for row in g.index[g[col] != mode]:
                        out.exc("REF-05", row, f"{col} '{g.at[row, col]}' conflicts with '{mode}' on other "
                                               f"rows of {code}", observed=g.at[row, col], limit=mode)
        lab = d[d.lab_sample_id != ""].groupby("lab_sample_id").sys_sample_code.nunique()
        for lab_id in lab[lab > 1].index:
            rows = d.index[d.lab_sample_id == lab_id]
            out.exc("REF-05", rows[0], f"Lab sample id {lab_id} is used for several samples",
                    observed=lab_id, limit="one sample per lab id", hold_rows=rows)
