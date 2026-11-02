"""EDD rows -> AGS 4.2 groups (PROJ, TRAN, TYPE, UNIT, ABBR, DICT, LOCA, MONG, SAMP, CHOC, ELRG)."""
from __future__ import annotations

import re
from datetime import date

import pandas as pd

from .. import refdata as R
from .dictionary import GROUPS, USER_HEADINGS, key_headings, spec
from .model import Group
from .reference import Reference, load_reference

AGS_VERSION = "4.2"
PROJECT_LIST = R.SITE["site_code"]           # ABBR_LIST value for project-defined codes
QC_LOCATIONS = {"FIELDQC": "Notional location for field QC samples with no sampling point",
                "LABQC": "Notional location for laboratory QC samples"}
PROJECT_ABBR = {("LOCA_TYPE", "QC"): "Notional location for QC samples (project code)",
                **{("ELRG_CODE", c): d for c, d in R.AGS_PROJECT_CODES.items()}}
LOCA_TYPE = {"BH": "CP", "MW": "CP", "TP": "TP"}
LOCA_NAME = {"BH": "Borehole", "MW": "Monitoring well", "TP": "Trial pit"}
TORD = {"T": "Total", "D": "Dissolved"}
SPIKED_SAMPLES = ("MS", "MSD", "LCS")
CAS_PATTERN = re.compile(r"^\d{2,7}-\d{2}-\d$")
SAMPLE_TYPE_TEXT = R.VALID_VALUES["sample_type"]
MATRIX_TEXT = R.VALID_VALUES["matrix"]


class AGSWriteError(ValueError):
    """The data cannot be written as valid AGS 4.2 (an unapproved code or unit)."""


def fmt(value, typ: str) -> str:
    v = "" if value is None or (isinstance(value, float) and pd.isna(value)) else str(value).strip()
    if not v:
        return ""
    m = re.fullmatch(r"(\d)DP", typ)
    if m:
        try:
            return f"{float(v):.{int(m.group(1))}f}"
        except ValueError:
            return v
    if typ == "DT":
        return v.replace(" ", "T")
    return v


def build_group(name: str, records: list[dict]) -> Group:
    """Keep key and required headings plus any heading with data, in dictionary order (Rule 7),
    with project headings appended in DICT order (Rule 9)."""
    keys = set(key_headings(name))
    standard = [h for h, status, _, _ in GROUPS[name]
                if h in keys or "R" in status or any(r.get(h) for r in records)]
    user = [h for g, h, *_ in USER_HEADINGS if g == name and any(r.get(h) for r in records)]
    headings = standard + user
    specs = [spec(name, h) for h in headings]
    rows = [[fmt(r.get(h, ""), s[2]) for h, s in zip(headings, specs)] for r in records]
    return Group(name, headings, [s[1] for s in specs], [s[2] for s in specs], rows)


def edd_to_groups(df: pd.DataFrame, locations: pd.DataFrame, include_lab_qc: bool = False,
                  strict: bool = True, ref: Reference | None = None) -> list[Group]:
    """df: EDD rows as text (edd_schema columns, optionally validator_qualifier / validator_reason).
    locations: ref_Location rows. strict=False declares unknown codes as project codes instead of failing."""
    ref = ref or load_reference()
    df = df.fillna("").astype(str)
    if not include_lab_qc:
        df = df[~df.sample_type.isin(R.LAB_QC_TYPES)]
    if df.empty:
        raise AGSWriteError("No results to export")
    for col in ("validator_qualifier", "validator_reason"):
        if col not in df:
            df[col] = ""

    loc_of = lambda r: r.location_code or ("LABQC" if r.sample_type in R.LAB_QC_TYPES else "FIELDQC")
    samples = df.drop_duplicates("sys_sample_code")
    samp_key = {s.sys_sample_code: {"LOCA_ID": loc_of(s), "SAMP_TOP": s.depth_top_m, "SAMP_REF": "",
                                    "SAMP_TYPE": "ES" if s.matrix == "SO" else "EW", "SAMP_ID": s.sys_sample_code}
                for s in samples.itertuples()}

    locs = locations.set_index("location_code") if len(locations) else pd.DataFrame()
    loca, mong = [], []
    for loc_id in dict.fromkeys(k["LOCA_ID"] for k in samp_key.values()):
        if loc_id in QC_LOCATIONS:
            loca.append({"LOCA_ID": loc_id, "LOCA_TYPE": "QC", "LOCA_REM": QC_LOCATIONS[loc_id]})
        elif loc_id in locs.index:
            l = locs.loc[loc_id]
            loca.append({"LOCA_ID": loc_id, "LOCA_TYPE": LOCA_TYPE.get(l.location_type, ""),
                         "LOCA_NATE": l.easting, "LOCA_NATN": l.northing, "LOCA_GREF": "OSGB",
                         "LOCA_GL": l.ground_level_mod, "LOCA_REM": f"{LOCA_NAME.get(l.location_type, '')} "
                         f"(fictional site)", "LOCA_FDEP": l.final_depth_m, "LOCA_NSRI": "27700"})
            if l.location_type == "MW" and pd.notna(l.screen_top_m):
                mong.append({"LOCA_ID": loc_id, "MONG_ID": "P1", "MONG_DIS": "0", "MONG_TYPE": "GWMP",
                             "MONG_DETL": "Groundwater monitoring well, slotted screen",
                             "MONG_TRZ": l.screen_top_m, "MONG_BRZ": l.screen_base_m})
        else:
            loca.append({"LOCA_ID": loc_id, "LOCA_REM": "Not in the project location register"})

    def link(code: str) -> str:
        k = samp_key[code]
        return "|".join(["SAMP", *(fmt(k[h], t) for h, _, _, t in GROUPS["SAMP"][:5])])

    samp, choc = [], []
    for s in samples.itertuples():
        rec = {**samp_key[s.sys_sample_code], "SAMP_BASE": s.depth_base_m, "SAMP_DTIM": s.sample_date,
               "SAMP_MATX": MATRIX_TEXT.get(s.matrix, s.matrix),
               "SAMP_TYPC": SAMPLE_TYPE_TEXT.get(s.sample_type, s.sample_type)}
        if s.parent_sample_code in samp_key:
            rec["SAMP_LINK"] = link(s.parent_sample_code)
        elif s.parent_sample_code:
            rec["SAMP_REM"] = f"Parent sample: {s.parent_sample_code} (not in this file)"
        samp.append(rec)
        if s.coc_id:
            choc.append({**samp_key[s.sys_sample_code], "CHOC_REF": s.coc_id, "CHOC_TO": s.lab_code,
                         "CHOC_COOL": s.cooler_id, "CHOC_CTMP": s.cooler_temp_c, "CHOC_SEAL": s.custody_seal_intact})

    elrg = []
    for r in df.itertuples():
        unit = R.AGS_UNIT.get(r.unit, r.unit)
        group = R.ANALYTE_GROUP.get(r.cas_rn, "")
        held_ht = "HT-" in r.validator_reason
        rtcd = ("SUR" if r.result_type == "SUR" else
                "IC" if r.sample_type in SPIKED_SAMPLES and r.spike_added else
                "TRG" if r.result_type == "TRG" else r.result_type)
        elrg.append({**samp_key[r.sys_sample_code], "SPEC_REF": r.fraction, "SPEC_DPTH": r.depth_top_m,
                     "ELRG_CODE": R.AGS_ELRG_CODE.get(r.cas_rn, r.cas_rn), "ELRG_METH": r.method_code,
                     "ELRG_MATX": "SOLID" if r.matrix == "SO" else "LIQUID", "ELRG_RTYP": "INITIAL",
                     "ELRG_RUNI": unit, "ELRG_LSID": r.lab_sample_id, "ELRG_RTCD": rtcd,
                     "ELRG_IQLF": r.validator_qualifier, "ELRG_LQLF": r.lab_qualifier,
                     "ELRG_RVAL": r.result_value,
                     "ELRG_RTXT": f"<{r.rl}" if r.detect_flag == "N" and r.rl else r.result_value,
                     "ELRG_NAME": r.chemical_name, "ELRG_DCAT": group,
                     "ELRG_FDEV": "Y" if held_ht else "", "ELRG_DEV": "Holding time" if held_ht else "",
                     "ELRG_DETF": r.detect_flag, "ELRG_ORG": ("N" if group == "METALS" else "Y") if group else "",
                     "ELRG_RDLM": r.rl, "ELRG_MDLM": r.mdl, "ELRG_DUNI": unit if (r.rl or r.mdl) else "",
                     "ELRG_CASC": r.cas_rn if CAS_PATTERN.match(r.cas_rn) else "",
                     "ELRG_RDAT": r.receipt_date, "ELRG_SGRP": r.lab_batch_id, "ELRG_DTIM": r.analysis_date,
                     "ELRG_TORD": TORD.get(r.fraction, ""), "ELRG_DIL": r.dilution_factor,
                     "ELRG_REM": r.validator_reason, "ELRG_LAB": r.lab_code,
                     "ELRG_PH": r.sample_ph, "ELRG_EXDT": r.extraction_date,
                     "ELRG_SPKA": r.spike_added, "ELRG_PREC": r.percent_recovery})

    data = [build_group(n, recs) for n, recs in
            (("LOCA", loca), ("MONG", mong), ("SAMP", samp), ("CHOC", choc), ("ELRG", elrg)) if recs]
    used_user = {(g.name, h) for g in data for h in g.headings if spec(g.name, h) and
                 (g.name, h) in {(ug, uh) for ug, uh, *_ in USER_HEADINGS}}
    dict_rows = [{"DICT_TYPE": "HEADING", "DICT_GRP": g, "DICT_HDNG": h, "DICT_STAT": "OTHER",
                  "DICT_DTYP": t, "DICT_DESC": d, "DICT_UNIT": u or "UNITLESS"}
                 for g, h, u, t, d in USER_HEADINGS if (g, h) in used_user]
    proj = build_group("PROJ", [{"PROJ_ID": R.SITE["site_code"], "PROJ_NAME": R.SITE["site_name"],
                                 "PROJ_LOC": R.SITE["county"], "PROJ_CLNT": "Fictional client",
                                 "PROJ_ENG": "Fictional consultant",
                                 "PROJ_MEMO": "Fictional site and simulated laboratory data, for demonstration only"}])
    tran = build_group("TRAN", [{"TRAN_ISNO": "1", "TRAN_DATE": date.today().isoformat(),
                                 "TRAN_PROD": "eddqc QA/QC engine", "TRAN_STAT": "Validated",
                                 "TRAN_DESC": "Validated laboratory results with validator qualifiers (ELRG_IQLF)",
                                 "TRAN_AGS": AGS_VERSION, "TRAN_RECV": "Portfolio demonstration",
                                 "TRAN_DLIM": "|", "TRAN_RCON": "+"}])
    groups = [proj, tran, *([build_group("DICT", dict_rows)] if dict_rows else []), *data]
    abbr = _abbr_group(groups, ref, strict)
    unit = _unit_group([*groups, abbr], ref, strict)
    typ = _type_group([*groups, abbr, unit], ref)
    return [proj, tran, typ, unit, abbr, *groups[2:]]


def _values(groups: list[Group], kind: str) -> list[tuple[str, str]]:
    found = {}
    for g in groups:
        for i, (h, t) in enumerate(zip(g.headings, g.types)):
            if t == kind:
                for row in g.rows:
                    for v in filter(None, row[i].split("+") if kind == "PA" else [row[i]]):
                        found[(h, v)] = None
    return list(found)


def _abbr_group(groups: list[Group], ref: Reference, strict: bool) -> Group:
    rows = []
    for heading, code in _values(groups, "PA"):
        desc, source = ref.abbr_desc(heading, code), "AGS4"
        if desc is None and (heading, code) in PROJECT_ABBR:
            desc, source = PROJECT_ABBR[(heading, code)], PROJECT_LIST
        if desc is None:
            if strict:
                raise AGSWriteError(f"{heading} code {code!r} is not an approved AGS code")
            desc, source = f"Project code {code}", PROJECT_LIST
        rows.append({"ABBR_HDNG": heading, "ABBR_CODE": code, "ABBR_DESC": desc, "ABBR_LIST": source})
    return build_group("ABBR", rows)


def _unit_group(groups: list[Group], ref: Reference, strict: bool) -> Group:
    units = dict.fromkeys(u for g in groups for u in g.units if u)
    units.update(dict.fromkeys(v for _, v in _values(groups, "PU")))
    rows = []
    for u in units:
        desc = ref.units.get(u)
        if desc is None:
            if strict:
                raise AGSWriteError(f"Unit {u!r} is not in the AGS unit list (units are case-sensitive)")
            desc = f"Project unit {u}"
        rows.append({"UNIT_UNIT": u, "UNIT_DESC": desc})
    return build_group("UNIT", rows)


def _type_group(groups: list[Group], ref: Reference) -> Group:
    types = dict.fromkeys(t for g in groups for t in g.types if t)
    types.update(dict.fromkeys(v for _, v in _values(groups, "PT")))
    types["X"] = None                                       # the TYPE group itself uses X
    return build_group("TYPE", [{"TYPE_TYPE": t, "TYPE_DESC": ref.type_desc(t) or t} for t in types])
