"""Official AGS code lists (ABBR, UNITS, DATATYPES, ELRG) and the built-in fallback.

The lists are downloaded unchanged from the AGS website (see SOURCE.md beside them) and
committed with credit to the AGS. Each entry keeps its AGS status (Approved, Accepted,
Proposed, Deprecated, Declined); only rows valid for AGS 4.2 are read. Without the files
a small built-in set of the codes this project writes is used instead.

This module imports nothing else from eddqc, so the dashboard can copy it unchanged.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

AGS_VERSION = "4.2"
LIST_FILES = {"ABBR": ("ABBR.csv",), "UNITS": ("UNITS.csv",), "ELRG": ("ELRG.csv",),
              "DATATYPES": ("DATATYPES.csv", "DATATYPE.csv")}
# Where the lists are looked for: next to this module (the dashboard's copy), then the
# pipeline repo's docs/reference/ags.
SEARCH_DIRS = [Path(__file__).resolve().parent / "reference",
               Path(__file__).resolve().parents[3] / "docs" / "reference" / "ags"]
STATUS_ORDER = ["Approved", "Accepted", "Proposed", "Deprecated", "Declined"]

# Descriptions copied from the AGS lists for the codes this project uses.
FALLBACK_ABBR = {
    ("LOCA_TYPE", "CP"): "Cable percussion (shell and auger)",
    ("LOCA_TYPE", "TP"): "Trial pit/trench",
    ("LOCA_GREF", "OSGB"): "Ordnance Survey Great Britain National Grid",
    ("MONG_TYPE", "GWMP"): "Groundwater monitoring point",
    ("MOND_TYPE", "WDEP"): "Depth to water from LOCA_ID datum",
    ("GEOL_LEG", "102"): "MADE GROUND",
    ("GEOL_LEG", "202"): "Silty CLAY",
    ("GEOL_LEG", "501"): "GRAVEL",
    ("GEOL_LEG", "801"): "MUDSTONE",
    ("SAMP_TYPE", "ES"): "Soil sample for environmental testing",
    ("SAMP_TYPE", "EW"): "Water sample for environmental testing",
    ("ELRG_MATX", "SOLID"): "Solid",
    ("ELRG_MATX", "LIQUID"): "Liquid",
    ("ELRG_RTYP", "INITIAL"): "Initial",
    ("ELRG_RTCD", "TRG"): "Target",
    ("ELRG_RTCD", "SUR"): "Surrogate",
    ("ELRG_RTCD", "IC"): "Spiked compound",
    ("DICT_TYPE", "HEADING"): "Flag to indicate definition is a HEADING",
    ("DICT_STAT", "OTHER"): "Other field",
}
FALLBACK_UNITS = {
    "m": "metre", "mm": "millimetre", "s": "second", "min": "minute", "%": "percentage",
    "DegC": "degree Celsius", "ug/l": "micrograms per litre", "mg/l": "milligrams per litre",
    "mg/kg": "milligrams per kilogram", "UNITLESS": "No unit", "yyyy-mm-dd": "year month day",
    "yyyy-mm-ddThh:mm": "year month day hours minutes",
}
FALLBACK_TYPES = {
    "ID": "Unique Identifier", "X": "Text", "XN": "Text / numeric", "PA": "Text listed in ABBR Group",
    "PT": "Text listed in TYPE Group", "PU": "Text listed in UNIT Group",
    "DT": "Date time in international format", "U": "Value with a variable format", "YN": "Yes or No",
    "RL": "Record Link", "T": "Elapsed Time",
    **{f"{n}DP": f"Value; required number of decimal places, {n}" for n in range(5)},
}


@dataclass(frozen=True)
class Entry:
    description: str
    status: str = "Approved"
    comment: str = ""


@dataclass
class Reference:
    """AGS code lists. official=False means only the built-in subset is known."""
    abbr: dict[tuple[str, str], Entry]
    units: dict[str, Entry]
    types: dict[str, str]
    elrg: dict[str, Entry] = field(default_factory=dict)
    official: bool = False
    source: str = "built-in subset"

    def abbr_entry(self, heading: str, code: str) -> Entry | None:
        return self.elrg.get(code) if heading == "ELRG_CODE" else self.abbr.get((heading, code))

    def abbr_desc(self, heading: str, code: str) -> str | None:
        """Description of an Approved code, else None."""
        e = self.abbr_entry(heading, code)
        return e.description if e and e.status == "Approved" else None

    def unit_desc(self, unit: str) -> str | None:
        e = self.units.get(unit)
        return e.description if e and e.status == "Approved" else None

    def type_desc(self, typ: str) -> str | None:
        if typ in self.types:
            return self.types[typ]
        for suffix, word in (("DP", "decimal places"), ("SF", "significant figures"), ("SCI", "decimal places")):
            n = typ[:-len(suffix)]
            if typ.endswith(suffix) and n.isdigit():
                return f"Value; required number of {word}, {n}"
        return None

    def summary(self) -> str:
        if not self.official:
            return "Checked against a built-in subset of AGS codes; official AGS code lists not found."
        return (f"Checked against the official AGS code lists for AGS {AGS_VERSION} ({self.source}): "
                f"{len(self.abbr):,} abbreviations, {len(self.units):,} units, {len(self.elrg):,} ELRG codes, "
                f"{len(self.types):,} data types.")


def _rows(path: Path) -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.reader(fh)
        header = [h.strip() for h in next(reader)]
        return [{h: v.strip() for h, v in zip(header, r)} for r in reader]


def _for_version(row: dict[str, str]) -> bool:
    versions = row.get("Version", "")
    return not versions or AGS_VERSION in [v.strip() for v in versions.split(",")]


def _keep(table: dict, key, entry: Entry) -> None:
    """Where a code is listed twice, keep the entry with the best status."""
    old = table.get(key)
    rank = lambda e: STATUS_ORDER.index(e.status) if e.status in STATUS_ORDER else len(STATUS_ORDER)
    if old is None or rank(entry) < rank(old):
        table[key] = entry


def _find(folder: Path) -> dict[str, Path | None]:
    return {name: next((folder / n for n in names if (folder / n).exists()), None)
            for name, names in LIST_FILES.items()}


def reference_dir() -> Path | None:
    """First folder holding any of the list files."""
    return next((d for d in SEARCH_DIRS if any(_find(d).values())), None)


@lru_cache(maxsize=4)
def load_reference(folder: Path | None = None) -> Reference:
    folder = folder or reference_dir()
    files = _find(folder) if folder else {}
    if not folder or not any(files.values()):
        return Reference({k: Entry(v) for k, v in FALLBACK_ABBR.items()},
                         {k: Entry(v) for k, v in FALLBACK_UNITS.items()}, dict(FALLBACK_TYPES))
    missing = [n for n, p in files.items() if p is None]
    if missing:
        raise FileNotFoundError(f"AGS code lists in {folder} are incomplete; missing {', '.join(missing)}")

    abbr, heading = {}, None
    for r in _rows(files["ABBR"]):
        code, desc = r.get("Code", ""), r.get("Description", "")
        if code and not any(v for k, v in r.items() if k != "Code"):
            heading = code                                # a heading line, e.g. "LOCA_TYPE,,,,,"
        elif heading and code and _for_version(r):
            _keep(abbr, (heading, code), Entry(desc, r.get("Status", ""), r.get("Comments", "")))
    units = {}
    for r in _rows(files["UNITS"]):
        if r.get("Unit") and _for_version(r):
            _keep(units, r["Unit"], Entry(r.get("Description", ""), r.get("Status", ""), r.get("Comments", "")))
    elrg = {}
    for r in _rows(files["ELRG"]):
        if r.get("Code") and _for_version(r):
            _keep(elrg, r["Code"], Entry(r.get("Description", ""), r.get("Status", ""), r.get("AGS Comments", "")))
    types = {r["Type"]: r.get("Desc", "") for r in _rows(files["DATATYPES"]) if r.get("Type") and _for_version(r)}
    if not (abbr and units and elrg and types):
        raise ValueError(f"AGS code lists in {folder} could not be read (an empty list or unexpected columns)")
    return Reference(abbr, units, types, elrg, official=True, source=folder.name)
