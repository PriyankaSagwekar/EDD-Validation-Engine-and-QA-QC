"""Official AGS code lists (ELRG, ABBR, UNITS, DATATYPE) and the built-in fallback.

The AGS distributes these lists to registered users, so they are not committed. Put the
CSV downloads in docs/reference/ags/ and they are used automatically. Without them, the
small set of codes this project writes (below) is used instead.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from ..config import PROJECT_ROOT

REFERENCE_DIR = PROJECT_ROOT / "docs" / "reference" / "ags"

# Descriptions copied from the AGS lists for the codes this project uses.
FALLBACK_ABBR = {
    ("LOCA_TYPE", "CP"): "Cable percussion (shell and auger)",
    ("LOCA_TYPE", "TP"): "Trial pit/trench",
    ("LOCA_GREF", "OSGB"): "Ordnance Survey Great Britain National Grid",
    ("MONG_TYPE", "GWMP"): "Groundwater monitoring point",
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
    "m": "metre", "mm": "millimetre", "s": "second", "%": "percentage", "DegC": "degree Celsius",
    "ug/l": "micrograms per litre", "mg/l": "milligrams per litre", "mg/kg": "milligrams per kilogram",
    "UNITLESS": "No unit", "yyyy-mm-dd": "year month day",
    "yyyy-mm-ddThh:mm": "year month day hours minutes",
}
FALLBACK_TYPES = {
    "ID": "Unique Identifier", "X": "Text", "XN": "Text / numeric", "PA": "Text listed in ABBR Group",
    "PT": "Text listed in TYPE Group", "PU": "Text listed in UNIT Group",
    "DT": "Date time in international format", "U": "Value with a variable format", "YN": "Yes or No",
    "RL": "Record Link", "T": "Elapsed Time",
    **{f"{n}DP": f"Value; required number of decimal places, {n}" for n in range(5)},
}


@dataclass
class Reference:
    """Codes the AGS approves. official=False means only the built-in subset is known."""
    abbr: dict[tuple[str, str], str]
    units: dict[str, str]
    types: dict[str, str]
    elrg: dict[str, str] = field(default_factory=dict)
    official: bool = False

    def abbr_desc(self, heading: str, code: str) -> str | None:
        if heading == "ELRG_CODE":
            return self.elrg.get(code)
        return self.abbr.get((heading, code))

    def type_desc(self, typ: str) -> str | None:
        if typ in self.types:
            return self.types[typ]
        for suffix, word in (("DP", "decimal places"), ("SF", "significant figures"), ("SCI", "decimal places")):
            n = typ[:-len(suffix)]
            if typ.endswith(suffix) and n.isdigit():
                return f"Value; required number of {word}, {n}"
        return None


def _rows(path: Path) -> list[list[str]]:
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return [r for r in csv.reader(fh)][1:]


@lru_cache(maxsize=1)
def load_reference(folder: Path = REFERENCE_DIR) -> Reference:
    files = {name: folder / f"{name}.csv" for name in ("ELRG", "ABBR", "UNITS", "DATATYPE")}
    if not all(p.exists() for p in files.values()):
        from .. import refdata as R
        elrg = {cas: name for cas, name, *_ in R.ANALYTES
                if cas not in R.AGS_ELRG_CODE and cas not in R.AGS_PROJECT_CODES}
        elrg.update({code: our for our, code in R.AGS_ELRG_CODE.items()})
        return Reference(dict(FALLBACK_ABBR), dict(FALLBACK_UNITS), dict(FALLBACK_TYPES), elrg, official=False)

    elrg = {r[0].strip(): r[3].strip() for r in _rows(files["ELRG"]) if len(r) > 3 and r[2].strip() == "Approved"}
    abbr, heading = {}, None
    for r in _rows(files["ABBR"]):
        if len(r) < 3:
            continue
        if r[0].strip() and not any(c.strip() for c in r[1:]):
            heading = r[0].strip()                      # a heading line, e.g. "LOCA_TYPE,,,,,"
        elif heading and r[2].strip() == "Approved":
            abbr[(heading, r[0].strip())] = r[1].strip()
    units = {r[1]: r[2] for r in _rows(files["UNITS"]) if len(r) > 5 and r[5].strip() == "Approved"}
    types = {r[0].strip(): r[1].strip() for r in _rows(files["DATATYPE"]) if r and r[0].strip()}
    return Reference(abbr, units, types, elrg, official=True)
