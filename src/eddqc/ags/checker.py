"""Check an AGS 4.2 file against the CSV rules (section 4.1.1) and the AGS code lists.

Covers Rules 1-7, 9, 10a-c, 11c, 12-19 for the groups in dictionary.py. Groups outside that
subset get the structural checks only, with a warning. Codes and units are also checked against
the status of each entry in the official AGS lists (reference.py).

Imports nothing else from eddqc, so the dashboard can copy it unchanged.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .dictionary import GROUPS, PARENT, key_headings, spec
from .model import Group, parse
from .reference import Reference, load_reference


@dataclass
class Issue:
    rule: str
    severity: str          # ERROR, WARNING or INFO
    group: str
    line: int
    message: str

    def __str__(self) -> str:
        return f"{self.severity} {self.rule} line {self.line} [{self.group}]: {self.message}"


# What each AGS list status means for a file that uses the code or unit.
STATUS_SEVERITY = {"Accepted": ("INFO", "is Accepted by the AGS but not yet marked Approved"),
                   "Proposed": ("WARNING", "is only Proposed, not yet approved by the AGS"),
                   "Deprecated": ("WARNING", "is Deprecated by the AGS"),
                   "Declined": ("ERROR", "was Declined by the AGS")}
VERSION_ERROR = "Only AGS 4.2 files are accepted"


def check_text(text: str, ref: Reference | None = None,
               strict_version: bool = False) -> tuple[dict[str, Group], list[Issue]]:
    """strict_version=True rejects any file that does not declare TRAN_AGS 4.2."""
    groups, parse_issues = parse(text)
    issues = [Issue(p.rule, "ERROR", "", p.line, p.message) for p in parse_issues]
    return groups, issues + check_groups(groups, ref, strict_version)


def file_version(groups: dict[str, Group]) -> str:
    tran = groups.get("TRAN")
    if tran and "TRAN_AGS" in tran.headings and tran.rows:
        return tran.rows[0][tran.headings.index("TRAN_AGS")].strip()
    return ""


def check_groups(groups: dict[str, Group], ref: Reference | None = None,
                 strict_version: bool = False) -> list[Issue]:
    ref = ref or load_reference()
    out: list[Issue] = []
    err = lambda rule, g, line, msg: out.append(Issue(rule, "ERROR", g, line, msg))
    warn = lambda rule, g, line, msg: out.append(Issue(rule, "WARNING", g, line, msg))

    for name in ("PROJ", "TRAN", "UNIT", "TYPE"):
        if name not in groups:
            err({"PROJ": "Rule 13", "TRAN": "Rule 14", "UNIT": "Rule 15", "TYPE": "Rule 17"}[name], name, 0,
                f"Required group {name} is missing")
    for name, rule in (("PROJ", "Rule 13"), ("TRAN", "Rule 14")):
        if name in groups and len(groups[name].rows) != 1:
            err(rule, name, groups[name].line, f"{name} must contain exactly one DATA row")
    version, tran_line = file_version(groups), groups["TRAN"].line if "TRAN" in groups else 0
    if not version.startswith("4.2"):
        declared = f"the file declares AGS {version}" if version else "the file does not declare its AGS version"
        if strict_version:
            err("Version", "TRAN", tran_line, f"{VERSION_ERROR}; {declared} (TRAN_AGS)")
        else:
            warn("Version", "TRAN", tran_line, f"{declared[0].upper()}{declared[1:]}; checked against AGS 4.2")

    dict_rows = _records(groups.get("DICT"))
    user = {(r.get("DICT_GRP"), r.get("DICT_HDNG")): r for r in dict_rows if r.get("DICT_TYPE") == "HEADING"}
    abbr = {(r.get("ABBR_HDNG"), r.get("ABBR_CODE")): r for r in _records(groups.get("ABBR"))}
    unit_line = {r.get("UNIT_UNIT"): r["_line"] for r in _records(groups.get("UNIT"))}
    units = {r.get("UNIT_UNIT") for r in _records(groups.get("UNIT"))}
    types = {r.get("TYPE_TYPE") for r in _records(groups.get("TYPE"))}

    for g in groups.values():
        if not re.fullmatch(r"[A-Z0-9]{1,4}", g.name):
            err("Rule 19", g.name, g.line, f"Group name {g.name!r} must be 1-4 upper-case letters or digits")
        known = g.name in GROUPS
        if not known and g.name not in {k[0] for k in user}:
            warn("Scope", g.name, g.line, "Group is not in this checker's dictionary subset; content not checked")
        order = [h for h, *_ in GROUPS.get(g.name, [])]
        positions, seen_user = [], False
        for h, u, t in zip(g.headings, g.units, g.types):
            if not re.fullmatch(r"[A-Z0-9_]{1,9}", h):
                err("Rule 19a", g.name, g.line, f"Heading {h!r} must be at most 9 characters A-Z, 0-9, _")
            if known and h in order:
                if seen_user:
                    err("Rule 9", g.name, g.line, f"Standard heading {h} appears after a user-defined heading")
                positions.append(order.index(h))
            elif known:
                seen_user = True
                if (g.name, h) not in user:
                    err("Rule 18", g.name, g.line, f"Heading {h} is not in the dictionary and not defined in DICT")
                elif not h.startswith(g.name + "_") and spec(g.name, h) is None:
                    err("Rule 19b", g.name, g.line, f"User heading {h} must start with {g.name}_")
            if u and u not in units:
                err("Rule 15", g.name, g.line, f"Unit {u!r} of {h} is not listed in the UNIT group")
            if t and t not in types:
                err("Rule 17", g.name, g.line, f"Type {t!r} of {h} is not listed in the TYPE group")
        if positions != sorted(positions):
            err("Rule 7", g.name, g.line, "Headings are not in data dictionary order")
        if not known:
            continue

        for k in key_headings(g.name):
            if k not in g.headings:
                err("Rule 10a", g.name, g.line, f"Key heading {k} is missing")
        required = [h for h, status, *_ in GROUPS[g.name] if "R" in status]
        idx = {h: i for i, h in enumerate(g.headings)}
        keys = [idx[k] for k in key_headings(g.name) if k in idx]
        seen = {}
        for row, line in zip(g.rows, g.lines):
            kv = tuple(row[i] for i in keys)
            if kv in seen:
                err("Rule 10a", g.name, line, f"Duplicate key {kv} (first at line {seen[kv]})")
            seen.setdefault(kv, line)
            for h in required:
                if h in idx and not row[idx[h]]:
                    err("Rule 10b", g.name, line, f"Required heading {h} is empty")
            for h, t in zip(g.headings, g.types):
                v = row[idx[h]]
                if not v:
                    continue
                m = re.fullmatch(r"(\d)DP", t)
                if m and not re.fullmatch(rf"-?\d+(\.\d{{{m.group(1)}}})?" if m.group(1) != "0" else r"-?\d+", v):
                    warn("Rule 8", g.name, line, f"{h} value {v!r} is not {t}")
                elif t == "YN" and v not in ("Y", "N"):
                    err("Rule 8", g.name, line, f"{h} value {v!r} must be Y or N")
                elif t == "PU" and v not in units:
                    err("Rule 15", g.name, line, f"{h} unit {v!r} is not listed in the UNIT group")
                elif t == "PT" and v not in types:
                    err("Rule 17", g.name, line, f"{h} type {v!r} is not listed in the TYPE group")
                elif t == "PA":
                    for code in v.split("+"):
                        if (h, code) not in abbr:
                            err("Rule 16", g.name, line, f"{h} code {code!r} is not defined in the ABBR group")

        parent = PARENT.get(g.name)
        if parent:
            pkeys = key_headings(parent)
            if parent not in groups:
                err("Rule 10c", g.name, g.line, f"Parent group {parent} is missing")
            else:
                pg = groups[parent]
                pidx = [pg.headings.index(k) for k in pkeys if k in pg.headings]
                parents = {tuple(r[i] for i in pidx) for r in pg.rows}
                cidx = [idx[k] for k in pkeys if k in idx]
                if len(cidx) == len(pkeys) == len(pidx):
                    for row, line in zip(g.rows, g.lines):
                        if tuple(row[i] for i in cidx) not in parents:
                            err("Rule 10c", g.name, line, f"No matching {parent} record for this row")
        for h, t in zip(g.headings, g.types):
            if t == "RL":
                for row, line in zip(g.rows, g.lines):
                    if row[idx[h]] and not _link_ok(row[idx[h]], groups):
                        err("Rule 11c", g.name, line, f"{h} {row[idx[h]]!r} does not match a record")

    if not ref.official:
        return out
    # ABBR_LIST other than AGS4 (or blank) marks a project code, which need not be in the AGS list.
    for (heading, code), r in abbr.items():
        listed = r.get("ABBR_LIST", "")
        if listed not in ("", "AGS4"):
            continue
        entry = ref.abbr_entry(heading, code)
        if entry is None:
            if listed == "AGS4":
                err("Rule 16", "ABBR", r["_line"], f"{heading} code {code!r} is marked AGS4 but is not in the AGS list")
        elif entry.status in STATUS_SEVERITY:
            sev, text = STATUS_SEVERITY[entry.status]
            out.append(Issue("Rule 16", sev, "ABBR", r["_line"],
                             f"{heading} code {code!r} ({entry.description}) {text}" + _note(entry)))
    for u in units:
        entry = ref.units.get(u)
        if entry is None:
            warn("Rule 15", "UNIT", unit_line.get(u, 0), f"Unit {u!r} is not in the AGS unit list")
        elif entry.status in STATUS_SEVERITY:
            sev, text = STATUS_SEVERITY[entry.status]
            out.append(Issue("Rule 15", sev, "UNIT", unit_line.get(u, 0), f"Unit {u!r} {text}" + _note(entry)))
    return out


def _note(entry) -> str:
    return f". AGS note: {entry.comment}" if entry.comment else ""


def _records(g: Group | None) -> list[dict]:
    return [{**dict(zip(g.headings, r)), "_line": line} for r, line in zip(g.rows, g.lines or [0] * len(g.rows))]         if g else []


def _link_ok(value: str, groups: dict[str, Group]) -> bool:
    for one in value.split("+"):
        parts = one.split("|")
        g = groups.get(parts[0])
        if g is None:
            return False
        keys = key_headings(g.name)
        idx = [g.headings.index(k) for k in keys if k in g.headings]
        if tuple(parts[1:]) not in {tuple(r[i] for i in idx) for r in g.rows}:
            return False
    return True


def errors(issues: list[Issue]) -> list[Issue]:
    return [i for i in issues if i.severity == "ERROR"]
