"""The part of the AGS 4.2 data dictionary this project reads and writes.

Transcribed from "Electronic Transfer of Geotechnical and Geoenvironmental Data, AGS4,
Edition 4.2, December 2025", section 3.6. Headings are listed in dictionary order
(Rule 7) as (heading, status, unit, type). Status: "*" key, "R" required.
"""
from __future__ import annotations

SAMP_KEYS = [("LOCA_ID", "*", "", "ID"), ("SAMP_TOP", "*", "m", "2DP"), ("SAMP_REF", "*", "", "X"),
             ("SAMP_TYPE", "*", "", "PA"), ("SAMP_ID", "*", "", "ID")]

GROUPS: dict[str, list[tuple[str, str, str, str]]] = {
    "PROJ": [("PROJ_ID", "*R", "", "ID"), ("PROJ_NAME", "", "", "X"), ("PROJ_LOC", "", "", "X"),
             ("PROJ_CLNT", "", "", "X"), ("PROJ_CONT", "", "", "X"), ("PROJ_ENG", "", "", "X"),
             ("PROJ_MEMO", "", "", "X"), ("FILE_FSET", "", "", "X")],
    "TRAN": [("TRAN_ISNO", "*R", "", "X"), ("TRAN_DATE", "R", "yyyy-mm-dd", "DT"), ("TRAN_PROD", "R", "", "X"),
             ("TRAN_STAT", "R", "", "X"), ("TRAN_DESC", "", "", "X"), ("TRAN_AGS", "R", "", "X"),
             ("TRAN_RECV", "R", "", "X"), ("TRAN_DLIM", "", "", "X"), ("TRAN_RCON", "", "", "X"),
             ("TRAN_REM", "", "", "X"), ("FILE_FSET", "", "", "X")],
    "TYPE": [("TYPE_TYPE", "*R", "", "X"), ("TYPE_DESC", "R", "", "X"), ("FILE_FSET", "", "", "X")],
    "UNIT": [("UNIT_UNIT", "*R", "", "X"), ("UNIT_DESC", "R", "", "X"), ("UNIT_REM", "", "", "X"),
             ("FILE_FSET", "", "", "X")],
    "ABBR": [("ABBR_HDNG", "*R", "", "X"), ("ABBR_CODE", "*R", "", "X"), ("ABBR_DESC", "R", "", "X"),
             ("ABBR_LIST", "", "", "X"), ("ABBR_REM", "", "", "X"), ("FILE_FSET", "", "", "X")],
    "DICT": [("DICT_TYPE", "*R", "", "PA"), ("DICT_GRP", "*R", "", "X"), ("DICT_HDNG", "*", "", "X"),
             ("DICT_STAT", "", "", "PA"), ("DICT_DTYP", "", "", "PT"), ("DICT_DESC", "R", "", "X"),
             ("DICT_UNIT", "", "", "PU"), ("DICT_EXMP", "", "", "X"), ("DICT_PGRP", "", "", "X"),
             ("DICT_REM", "", "", "X"), ("FILE_FSET", "", "", "X")],
    "LOCA": [("LOCA_ID", "*", "", "ID"), ("LOCA_TYPE", "", "", "PA"), ("LOCA_STAT", "", "", "PA"),
             ("LOCA_NATE", "", "m", "2DP"), ("LOCA_NATN", "", "m", "2DP"), ("LOCA_GREF", "", "", "PA"),
             ("LOCA_GL", "", "m", "2DP"), ("LOCA_REM", "", "", "X"), ("LOCA_FDEP", "", "m", "2DP"),
             ("LOCA_STAR", "", "yyyy-mm-dd", "DT"), ("LOCA_PURP", "", "", "X"), ("LOCA_TERM", "", "", "X"),
             ("LOCA_ENDD", "", "yyyy-mm-dd", "DT"), ("LOCA_LETT", "", "", "X"), ("FILE_FSET", "", "", "X"),
             ("LOCA_NATD", "", "", "X"), ("LOCA_NSRI", "", "", "0DP")],
    "MONG": [("LOCA_ID", "*", "", "ID"), ("MONG_ID", "*", "", "X"), ("MONG_DIS", "*", "m", "2DP"),
             ("PIPE_REF", "", "", "X"), ("MONG_DATE", "", "yyyy-mm-dd", "DT"), ("MONG_TYPE", "", "", "PA"),
             ("MONG_DETL", "", "", "X"), ("MONG_TRZ", "", "m", "2DP"), ("MONG_BRZ", "", "m", "2DP"),
             ("MONG_REM", "", "", "X"), ("MONG_CONT", "", "", "X"), ("FILE_FSET", "", "", "X")],
    "MOND": [("LOCA_ID", "*", "", "ID"), ("MONG_ID", "*", "", "X"), ("MONG_DIS", "*", "m", "2DP"),
             ("MOND_DTIM", "*", "yyyy-mm-ddThh:mm", "DT"), ("MOND_TYPE", "*", "", "PA"), ("MOND_REF", "*", "", "X"),
             ("MOND_INST", "", "", "X"), ("MOND_RDNG", "", "", "XN"), ("MOND_UNIT", "R", "", "PU"),
             ("MOND_METH", "", "", "X"), ("MOND_LIM", "", "", "U"), ("MOND_ULIM", "", "", "U"),
             ("MOND_NAME", "", "", "X"), ("MOND_CRED", "", "", "X"), ("MOND_CONT", "", "", "X"),
             ("MOND_REM", "", "", "X"), ("FILE_FSET", "", "", "X")],
    "GEOL": [("LOCA_ID", "*", "", "ID"), ("GEOL_TOP", "*", "m", "2DP"), ("GEOL_BASE", "*", "m", "2DP"),
             ("GEOL_DESC", "", "", "X"), ("GEOL_LEG", "", "", "PA"), ("GEOL_GEOL", "", "", "PA"),
             ("GEOL_GEO2", "", "", "PA"), ("GEOL_STAT", "", "", "X"), ("GEOL_BGS", "", "", "PA"),
             ("GEOL_FORM", "", "", "X"), ("GEOL_REM", "", "", "X"), ("FILE_FSET", "", "", "X"),
             ("GEOL_BNDF", "", "", "PA")],
    "WSTG": [("LOCA_ID", "*", "", "ID"), ("WSTG_DPTH", "*", "m", "2DP"),
             ("WSTG_DTIM", "", "yyyy-mm-ddThh:mm", "DT"), ("WSTG_SEAL", "", "m", "2DP"),
             ("WSTG_CAS", "", "m", "2DP"), ("WSTG_REM", "", "", "X"), ("FILE_FSET", "", "", "X")],
    "WSTD": [("LOCA_ID", "*", "", "ID"), ("WSTG_DPTH", "*", "m", "2DP"), ("WSTD_NMIN", "*", "min", "0DP"),
             ("WSTD_POST", "", "m", "2DP"), ("WSTD_REM", "", "", "X"), ("FILE_FSET", "", "", "X")],
    "SAMP": [*SAMP_KEYS, ("SAMP_BASE", "", "m", "2DP"), ("SAMP_DTIM", "", "yyyy-mm-ddThh:mm", "DT"),
             ("SAMP_CONT", "", "", "X"), ("SAMP_PREP", "", "", "X"), ("SAMP_TECH", "", "", "X"),
             ("SAMP_MATX", "", "", "X"), ("SAMP_TYPC", "", "", "X"), ("SAMP_WHO", "", "", "X"),
             ("SAMP_WHY", "", "", "X"), ("SAMP_REM", "", "", "X"), ("SAMP_DESC", "", "", "X"),
             ("SAMP_LINK", "", "", "RL"), ("FILE_FSET", "", "", "X")],
    "CHOC": [*SAMP_KEYS, ("CHOC_REF", "*", "", "X"), ("CHOC_FROM", "", "", "X"), ("CHOC_TO", "", "", "X"),
             ("CHOC_DDIS", "", "yyyy-mm-dd", "DT"), ("CHOC_BTCH", "", "", "X"), ("CHOC_REM", "", "", "X"),
             ("CHOC_CONT", "", "", "0DP"), ("FILE_FSET", "", "", "X")],
    "ELRG": [*SAMP_KEYS, ("SPEC_REF", "*", "", "X"), ("SPEC_DPTH", "*", "m", "2DP"),
             ("ELRG_CODE", "*R", "", "PA"), ("ELRG_METH", "*", "", "X"), ("ELRG_MATX", "*", "", "PA"),
             ("ELRG_RTYP", "*", "", "PA"), ("ELRG_TADE", "*", "", "PA"), ("ELRG_TICN", "*", "", "X"),
             ("ELRG_RUNI", "*R", "", "PU"), ("SPEC_DESC", "", "", "X"), ("SPEC_PREP", "", "", "X"),
             ("SPEC_BASE", "", "m", "2DP"), ("ELRG_LSID", "", "", "X"), ("ELRG_RTCD", "", "", "PA"),
             ("ELRG_IQLF", "", "", "X"), ("ELRG_LQLF", "", "", "X"), ("ELRG_RVAL", "", "", "U"),
             ("ELRG_RTXT", "", "", "X"), ("ELRG_NAME", "", "", "X"), ("ELRG_TNAM", "", "", "X"),
             ("ELRG_DCAT", "", "", "X"), ("ELRG_TESN", "", "", "X"), ("ELRG_FDEV", "", "", "YN"),
             ("ELRG_DEV", "", "", "X"), ("ELRG_RRES", "", "", "YN"), ("ELRG_DETF", "", "", "YN"),
             ("ELRG_ORG", "", "", "YN"), ("ELRG_RDLM", "", "", "U"), ("ELRG_MDLM", "", "", "U"),
             ("ELRG_QLM", "", "", "U"), ("ELRG_DUNI", "", "", "PU"), ("ELRG_CASC", "", "", "X"),
             ("ELRG_TICP", "", "%", "0DP"), ("ELRG_TICT", "", "s", "0DP"),
             ("ELRG_RDAT", "", "yyyy-mm-ddThh:mm", "DT"), ("ELRG_SGRP", "", "", "X"),
             ("ELRG_DTIM", "", "yyyy-mm-ddThh:mm", "DT"), ("ELRG_TEST", "", "", "X"), ("ELRG_TORD", "", "", "X"),
             ("ELRG_LOCN", "", "", "PA"), ("ELRG_BAS", "", "", "PA"), ("ELRG_DIL", "", "", "0DP"),
             ("ELRG_LMTH", "", "", "X"), ("ELRG_LDTM", "", "yyyy-mm-ddThh:mm", "DT"), ("ELRG_IREF", "", "", "X"),
             ("ELRG_ITYP", "", "", "X"), ("ELRG_SIZE", "", "mm", "0DP"), ("ELRG_PERP", "", "%", "1DP"),
             ("ELRG_REM", "", "", "X"), ("ELRG_LAB", "", "", "X"), ("ELRG_CRED", "", "", "X"),
             ("TEST_STAT", "", "", "X"), ("FILE_FSET", "", "", "X")],
}

# Parent group of each data group (section 3.1). Child key values must exist in the parent (Rule 10c).
PARENT = {"MONG": "LOCA", "MOND": "MONG", "GEOL": "LOCA", "WSTG": "LOCA", "WSTD": "WSTG",
          "SAMP": "LOCA", "CHOC": "SAMP", "ELRG": "SAMP"}

# User-defined headings this project adds for data AGS 4.2 has no heading for (Rules 9, 18, 19).
# (group, heading, unit, type, description). An empty unit is written as UNITLESS in DICT.
USER_HEADINGS = [
    ("CHOC", "CHOC_COOL", "", "X", "Cooler identifier"),
    ("CHOC", "CHOC_CTMP", "DegC", "1DP", "Cooler temperature on receipt at the laboratory"),
    ("CHOC", "CHOC_SEAL", "", "YN", "Custody seal intact on receipt"),
    ("ELRG", "ELRG_PH", "", "1DP", "Sample pH on receipt (preservation check)"),
    ("ELRG", "ELRG_EXDT", "yyyy-mm-ddThh:mm", "DT", "Extraction or preparation date and time"),
    ("ELRG", "ELRG_SPKA", "", "U", "Spike amount added, in ELRG_RUNI units"),
    ("ELRG", "ELRG_PREC", "%", "U", "Spike or surrogate percent recovery"),
]


def key_headings(group: str) -> list[str]:
    return [h for h, status, _, _ in GROUPS.get(group, []) if "*" in status]


def spec(group: str, heading: str) -> tuple[str, str, str] | None:
    """(status, unit, type) of a standard or project heading."""
    for h, status, unit, typ in GROUPS.get(group, []):
        if h == heading:
            return status, unit, typ
    for g, h, unit, typ, _ in USER_HEADINGS:
        if g == group and h == heading:
            return "", unit, typ
    return None
