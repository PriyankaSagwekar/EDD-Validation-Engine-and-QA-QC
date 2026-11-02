"""In-memory AGS file: groups of HEADING / UNIT / TYPE / DATA rows, and the CSV form (section 4.1)."""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field

import pandas as pd


@dataclass
class Group:
    name: str
    headings: list[str]
    units: list[str]
    types: list[str]
    rows: list[list[str]] = field(default_factory=list)
    lines: list[int] = field(default_factory=list)     # file line of each DATA row (1-based)
    line: int = 0                                      # file line of the GROUP row

    def frame(self) -> pd.DataFrame:
        df = pd.DataFrame(self.rows, columns=self.headings, dtype=str)
        df.insert(0, "_line", self.lines or [0] * len(self.rows))
        return df


@dataclass
class ParseIssue:
    rule: str
    line: int
    message: str


def _quote(v: str) -> str:
    return '"' + str(v).replace('"', '""') + '"'


def to_text(groups: list[Group]) -> str:
    """Serialise groups in AGS CSV form: every item quoted, CRLF line ends, blank line between groups."""
    out = []
    for g in groups:
        out.append(",".join(map(_quote, ["GROUP", g.name])))
        out.append(",".join(map(_quote, ["HEADING", *g.headings])))
        out.append(",".join(map(_quote, ["UNIT", *g.units])))
        out.append(",".join(map(_quote, ["TYPE", *g.types])))
        out.extend(",".join(map(_quote, ["DATA", *r])) for r in g.rows)
        out.append("")
    return "\r\n".join(out) + "\r\n"


def parse(text: str) -> tuple[dict[str, Group], list[ParseIssue]]:
    """Read AGS CSV text. Structural problems (Rules 1-6) are returned, not raised."""
    issues: list[ParseIssue] = []
    if any(ord(ch) > 127 for ch in text):
        bad = next(i for i, ln in enumerate(text.split("\n"), 1) if any(ord(c) > 127 for c in ln))
        issues.append(ParseIssue("Rule 1", bad, "File contains non-ASCII characters"))
    groups: dict[str, Group] = {}
    current: Group | None = None
    expected = None
    raw_lines = text.split("\n")
    for no, raw in enumerate(raw_lines, 1):
        if raw == "" and no == len(raw_lines):
            break
        if not raw.endswith("\r"):
            issues.append(ParseIssue("Rule 2a", no, "Line does not end with CR+LF"))
        line = raw.rstrip("\r")
        if not line.strip():
            continue
        if not line.startswith('"'):
            issues.append(ParseIssue("Rule 5", no, "Line does not start with a quoted data descriptor"))
        items = next(csv.reader(io.StringIO(line)))
        desc, values = items[0], items[1:]
        if desc == "GROUP":
            if len(values) != 1:
                issues.append(ParseIssue("Rule 4", no, "GROUP row must hold exactly one group name"))
            name = values[0] if values else ""
            if name in groups:
                issues.append(ParseIssue("Rule 2", no, f"Group {name} appears more than once"))
            current = Group(name, [], [], [], line=no)
            groups[name] = current
            expected = "HEADING"
            continue
        if current is None:
            issues.append(ParseIssue("Rule 3", no, f"{desc} row before any GROUP row"))
            continue
        if desc in ("HEADING", "UNIT", "TYPE"):
            if desc != expected:
                issues.append(ParseIssue("Rule 2b", no, f"{desc} row out of order in {current.name}"))
            setattr(current, {"HEADING": "headings", "UNIT": "units", "TYPE": "types"}[desc], values)
            expected = {"HEADING": "UNIT", "UNIT": "TYPE", "TYPE": "DATA"}[desc]
        elif desc == "DATA":
            if expected != "DATA":
                issues.append(ParseIssue("Rule 2b", no, f"DATA row before HEADING/UNIT/TYPE in {current.name}"))
            current.rows.append(values)
            current.lines.append(no)
        else:
            issues.append(ParseIssue("Rule 3", no, f"Unknown data descriptor {desc!r}"))
            continue
        if current.headings and len(values) != len(current.headings):
            issues.append(ParseIssue("Rule 4", no, f"{desc} row has {len(values)} fields; "
                                                    f"{current.name} HEADING has {len(current.headings)}"))
    for g in groups.values():
        if not g.rows:
            issues.append(ParseIssue("Rule 2", g.line, f"Group {g.name} has no DATA rows"))
        g.rows = [r + [""] * (len(g.headings) - len(r)) if len(r) < len(g.headings) else r[:len(g.headings)]
                  for r in g.rows]
    return groups, issues
