"""STR-01..05: depth integrity, date logic and duplicate sampling."""
from __future__ import annotations

from datetime import datetime

import pandas as pd

from .base import Output, Ref, Rule, first_rows

TEST_KEY = ["sys_sample_code", "method_code", "fraction"]


class StructuralRules(Rule):
    family = "Structural / depth"
    rule_ids = ("STR-01", "STR-02", "STR-03", "STR-04", "STR-05")

    def __init__(self, now: datetime | None = None):
        self.now = now

    def run(self, d: pd.DataFrame, ref: Ref, out: Output) -> None:
        samples = first_rows(d, d.sys_sample_code != "", ["sys_sample_code"])
        locs = ref.locations
        for _, r in samples.iterrows():
            rows = d.index[d.sys_sample_code == r.sys_sample_code]
            top, base = r.depth_top_m_n, r.depth_base_m_n
            if pd.notna(top) and pd.notna(base) and top > base:
                out.exc("STR-01", r.source_row_no, f"Depth top {top} m is below depth base {base} m",
                        observed=f"{top}-{base}", limit="top <= base", hold_rows=rows)
            final = locs.at[r.location_code, "final_depth_m"] if r.location_code in locs.index else None
            if (pd.notna(top) and top < 0) or (pd.notna(base) and base < 0):
                out.exc("STR-02", r.source_row_no, "Negative sample depth", observed=f"{top}-{base}",
                        limit=">= 0", hold_rows=rows)
            elif final is not None and pd.notna(base) and base > final:
                out.exc("STR-02", r.source_row_no,
                        f"Depth {base} m is deeper than {r.location_code} final depth {final} m",
                        observed=base, limit=final, hold_rows=rows)
            env = r.sample_type in ("N", "FD", "MS", "MSD")
            if env and r.matrix == "SO" and (pd.isna(top) or pd.isna(base)):
                out.exc("STR-03", r.source_row_no, "Soil sample has no depth interval", observed="blank",
                        limit="depth_top_m and depth_base_m")
            if env and r.matrix == "WG" and r.location_code in locs.index and pd.notna(top) and pd.notna(base):
                st, sb = locs.at[r.location_code, "screen_top_m"], locs.at[r.location_code, "screen_base_m"]
                if pd.notna(st) and (top < st or base > sb):
                    out.exc("STR-03", r.source_row_no,
                            f"Sample depth {top}-{base} m is outside the well screen {st}-{sb} m",
                            observed=f"{top}-{base}", limit=f"{st}-{sb}")
            if pd.notna(r.receipt_date_dt) and pd.notna(r.sample_date_dt) and r.receipt_date_dt < r.sample_date_dt:
                out.exc("STR-04", r.source_row_no, "Lab receipt is before sampling",
                        observed=r.receipt_date, limit=f">= {r.sample_date}", hold_rows=rows)
            now = self.now or datetime.now()
            if pd.notna(r.sample_date_dt) and r.sample_date_dt > now:
                out.exc("STR-04", r.source_row_no, "Sample date is in the future",
                        observed=r.sample_date, limit=f"<= {now:%Y-%m-%d}", hold_rows=rows)

        tests = first_rows(d, d.sys_sample_code != "", TEST_KEY)
        for _, r in tests.iterrows():
            problems = []
            if pd.notna(r.analysis_date_dt) and pd.notna(r.sample_date_dt) and r.analysis_date_dt < r.sample_date_dt:
                problems.append("analysis before sampling")
            if pd.notna(r.extraction_date_dt) and pd.notna(r.sample_date_dt) and r.extraction_date_dt < r.sample_date_dt:
                problems.append("extraction before sampling")
            if pd.notna(r.extraction_date_dt) and pd.notna(r.analysis_date_dt) and r.analysis_date_dt < r.extraction_date_dt:
                problems.append("analysis before extraction")
            if problems:
                rows = d.index[(d.sys_sample_code == r.sys_sample_code) & (d.method_code == r.method_code)
                               & (d.fraction == r.fraction)]
                out.exc("STR-04", r.source_row_no, f"{r.method_code}: {', '.join(problems)}",
                        observed=r.analysis_date, limit=f"after {r.sample_date or r.extraction_date}",
                        hold_rows=rows)

        normals = samples[samples.sample_type == "N"].copy()
        normals["sample_day"] = normals.sample_date_dt.dt.date
        for _, g in normals.groupby(["location_code", "depth_top_m", "sample_day"]):
            if g.sys_sample_code.nunique() > 1:
                codes = ", ".join(sorted(g.sys_sample_code))
                for _, r in g.iterrows():
                    out.exc("STR-05", r.source_row_no,
                            f"{r.location_code} at {r.depth_top_m} m sampled more than once on "
                            f"{r.sample_day}: {codes}", observed=codes, limit="one normal sample")
