"""Combine every qualifier applied to a result into one final validator qualifier.

Precedence: R > UJ > J+/J- > J > U > B. J+ with J- gives J (bias unknown).
A non-detect, or a detect re-classified U, that is also estimated becomes UJ.
"""
from __future__ import annotations

import pandas as pd

ESTIMATED = {"J", "J+", "J-", "UJ"}


def combine(quals: set[str], detect: bool) -> str | None:
    quals = set(quals) - {"HOLD"}
    if not quals:
        return None
    if "R" in quals:
        return "R"
    est = quals & ESTIMATED
    if est:
        if "UJ" in est or "U" in quals or not detect:
            return "UJ"
        if "J+" in est and "J-" in est:
            return "J"
        if "J-" in est:
            return "J-"
        if "J+" in est:
            return "J+"
        return "J"
    if "U" in quals:
        return "U"
    if "B" in quals:
        return "B"
    return None


def finalize(d: pd.DataFrame, qualifiers: list[tuple[int, str, str]]) -> pd.DataFrame:
    """Return one row per EDD row: validator_qualifier, validator_reason, qc_status."""
    q = pd.DataFrame(qualifiers, columns=["source_row_no", "rule_id", "qualifier"])
    status = pd.DataFrame(index=d.index)
    status["validator_qualifier"] = None
    status["validator_reason"] = None
    status["qc_status"] = "PASS"
    if q.empty:
        return status.reset_index()
    for row, g in q.groupby("source_row_no"):
        if row not in status.index:
            continue
        quals = set(g.qualifier)
        final = combine(quals, bool(d.at[row, "is_detect"]))
        status.at[row, "validator_qualifier"] = final
        status.at[row, "validator_reason"] = ";".join(sorted(set(g.rule_id)))[:200]
        if "HOLD" in quals or final == "R":
            status.at[row, "qc_status"] = "HELD"
        elif final:
            status.at[row, "qc_status"] = "QUALIFIED"
    return status.reset_index()
