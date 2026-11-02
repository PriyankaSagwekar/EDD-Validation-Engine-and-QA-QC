"""Check an AGS 4.2 file against the CSV rules (section 4.1.1) and the AGS code lists.

Covers Rules 1-7, 9, 10a-c, 11c, 12-19 for the groups in dictionary.py. Groups outside that
subset get the structural checks only, with a warning.
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
    severity: str          # ERROR or WARNING
    group: str
    line: int
    message: str

    def __str__(self) -> str:
        return f"{self.severity} {self.rule} line {self.line} [{self.group}]: {self.message}"


def check_text(text: str, ref: Reference | None = None) -> tuple[dict[str, Group], list[Issue]]:
    groups, parse_issues = parse(text)
    issues = [Issue(p.rule, "ERROR", "", p.line, p.message) for p in parse_issues]
    return groups, issues + check_groups(groups, ref)


def check_groups(groups: dict[str, Group], ref: Reference | None = None) -> list[Issue]:
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
    if "TRAN" in groups and "TRAN_AGS" in groups["TRAN"].headings and groups["TRAN"].rows:
        version = groups["TRAN"].rows[0][groups["TRAN"].headings.index("TRAN_AGS")]
        if not version.startswith("4.2"):
            warn("TRAN_AGS", "TRAN", groups["TRAN"].line, f"File declares AGS {version}; checked against 4.2")

    dict_rows = _records(groups.get("DICT"))
    user = {(r.get("DICT_GRP"), r.get("DICT_HDNG")): r for r in dict_rows if r.get("DICT_TYPE") == "HEADING"}
    abbr = {(r.get("ABBR_HDNG"), r.get("ABBR_CODE")): r for r in _records(groups.get("ABBR"))}
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

    for (heading, code), r in abbr.items():
        if r.get("ABBR_LIST") == "AGS4" and ref.official and ref.abbr_desc(heading, code) is None:
            err("Rule 16", "ABBR", 0, f"{heading} code {code!r} is marked AGS4 but is not an approved AGS code")
    for u in units:
        if u not in ref.units:
            warn("Rule 15", "UNIT", 0, f"Unit {u!r} is not in the AGS unit list")
    return out


def _records(g: Group | None) -> list[dict]:
    return [dict(zip(g.headings, r)) for r in g.rows] if g else []


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
