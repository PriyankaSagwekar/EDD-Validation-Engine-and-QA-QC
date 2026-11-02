"""AGS groups -> EDD rows, so an AGS file goes through the same loader and QA/QC rules as a CSV EDD."""
from __future__ import annotations

import re
import warnings

import pandas as pd

from .. import refdata as R
from ..edd_schema import EDD_COLUMNS
from .model import Group
from .writer import QC_LOCATIONS

REVERSE_CODE = {ags: ours for ours, ags in R.AGS_ELRG_CODE.items()}
REVERSE_UNIT = {ags: ours for ours, ags in R.AGS_UNIT.items()}
SAMPLE_TYPE_CODE = {text: code for code, text in R.VALID_VALUES["sample_type"].items()}
MATRIX_CODE = {text: code for code, text in R.VALID_VALUES["matrix"].items()}
SAMP_KEYS = ["LOCA_ID", "SAMP_TOP", "SAMP_REF", "SAMP_TYPE", "SAMP_ID"]


def _date(v: str) -> str:
    return v.replace("T", " ") if v else v


def ags_to_edd(groups: dict[str, Group]) -> pd.DataFrame:
    """One EDD row per ELRG (or legacy ERES) row. source_row_no is the line of that row in the AGS file."""
    if "ELRG" in groups:
        res = groups["ELRG"].frame()
    elif "ERES" in groups:
        warnings.warn("ERES was removed in AGS 4.2; reading it as ELRG")
        res = groups["ERES"].frame()
        res.columns = [re.sub(r"^ERES_", "ELRG_", c) for c in res.columns]
    else:
        raise ValueError("The file has no ELRG (or ERES) group of laboratory results")

    def col(df: pd.DataFrame, name: str) -> pd.Series:
        return df[name] if name in df else pd.Series("", index=df.index)

    for k in SAMP_KEYS:
        if k not in res:
            res[k] = ""
    if "SAMP" in groups:
        samp = groups["SAMP"].frame().drop(columns="_line")
        samp = samp.loc[:, ~samp.columns.isin(res.columns) | samp.columns.isin(SAMP_KEYS)]
        res = res.merge(samp, on=SAMP_KEYS, how="left")
    if "CHOC" in groups:
        choc = groups["CHOC"].frame().drop(columns="_line").drop_duplicates(SAMP_KEYS)
        res = res.merge(choc[[c for c in choc.columns if c in SAMP_KEYS or c.startswith("CHOC_")]],
                        on=SAMP_KEYS, how="left")
    res = res.fillna("")

    parent = col(res, "SAMP_LINK").str.split("|").str[-1].where(col(res, "SAMP_LINK") != "", "")
    from_rem = col(res, "SAMP_REM").str.extract(r"Parent sample: (\S+)", expand=False).fillna("")
    code = col(res, "ELRG_CODE")
    cas = code.map(REVERSE_CODE).fillna(code)
    casc = col(res, "ELRG_CASC")
    cas = cas.where((cas != "") | (casc == ""), casc)
    matrix = col(res, "SAMP_MATX").map(MATRIX_CODE)
    matrix = matrix.fillna(col(res, "SAMP_MATX")).where(col(res, "SAMP_MATX") != "",
                                                         col(res, "ELRG_MATX").map({"SOLID": "SO", "LIQUID": "WG"}))
    fraction = col(res, "SPEC_REF").where(col(res, "SPEC_REF").isin(["T", "D", "N"]),
                                          col(res, "ELRG_TORD").map({"Total": "T", "Dissolved": "D"}))
    loc = col(res, "LOCA_ID")

    edd = pd.DataFrame({
        "sys_sample_code": col(res, "SAMP_ID"),
        "lab_sample_id": col(res, "ELRG_LSID"),
        "sample_type": col(res, "SAMP_TYPC").map(SAMPLE_TYPE_CODE).fillna(col(res, "SAMP_TYPC"))
                       .replace("", "N"),
        "parent_sample_code": parent.where(parent != "", from_rem),
        "location_code": loc.where(~loc.isin(list(QC_LOCATIONS)), ""),
        "matrix": matrix,
        "sample_date": col(res, "SAMP_DTIM").map(_date),
        "depth_top_m": col(res, "SAMP_TOP"),
        "depth_base_m": col(res, "SAMP_BASE"),
        "coc_id": col(res, "CHOC_REF"),
        "cooler_id": col(res, "CHOC_COOL"),
        "receipt_date": col(res, "ELRG_RDAT").map(_date),
        "cooler_temp_c": col(res, "CHOC_CTMP"),
        "custody_seal_intact": col(res, "CHOC_SEAL"),
        "sample_ph": col(res, "ELRG_PH"),
        "lab_code": col(res, "ELRG_LAB"),
        "method_code": col(res, "ELRG_METH"),
        "fraction": fraction,
        "lab_batch_id": col(res, "ELRG_SGRP"),
        "extraction_date": col(res, "ELRG_EXDT").map(_date),
        "analysis_date": col(res, "ELRG_DTIM").map(_date),
        "dilution_factor": col(res, "ELRG_DIL"),
        "cas_rn": cas,
        "chemical_name": col(res, "ELRG_NAME"),
        "result_value": col(res, "ELRG_RVAL"),
        "detect_flag": col(res, "ELRG_DETF"),
        "mdl": col(res, "ELRG_MDLM"),
        "rl": col(res, "ELRG_RDLM"),
        "unit": col(res, "ELRG_RUNI").map(REVERSE_UNIT).fillna(col(res, "ELRG_RUNI")).replace("UNITLESS", ""),
        "result_type": col(res, "ELRG_RTCD").replace({"IC": "TRG", "": "TRG"}),
        "spike_added": col(res, "ELRG_SPKA"),
        "percent_recovery": col(res, "ELRG_PREC"),
        "lab_qualifier": col(res, "ELRG_LQLF"),
    }).fillna("")
    edd.insert(0, "source_row_no", res["_line"].values)
    return edd[["source_row_no", *EDD_COLUMNS]]
