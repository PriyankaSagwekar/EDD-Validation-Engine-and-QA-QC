"""Edge cases for individual rules, built by editing one clean EDD."""
from datetime import datetime, timedelta

from eddqc.edd_schema import DATE_FORMAT
from eddqc.rules.qualifiers import combine


def rows_of(res, rule_id):
    return res.exceptions[res.exceptions.rule_id == rule_id]


def status(res, df_index_label):
    """qc_status / qualifier for the EDD row that was df.loc[label] (source_row_no = label + 2)."""
    r = res.rows.set_index("source_row_no").loc[df_index_label + 2]
    return r.qc_status, r.validator_qualifier


def first(df, **kw):
    m = True
    for k, v in kw.items():
        m = m & (df[k] == v)
    return df.index[m][0]


# ------------------------------------------------------------------ detection boundary
def test_detect_exactly_at_mdl_is_not_det01(clean_gw, validate):
    df = clean_gw.copy()
    i = first(df, sample_type="N", result_type="TRG", detect_flag="Y", cas_rn="7440-38-2")
    df.loc[i, ["result_value", "lab_qualifier"]] = [df.at[i, "mdl"], "J"]
    res = validate(df)
    assert rows_of(res, "DET-01").empty and rows_of(res, "DET-02").empty


def test_detect_below_mdl_becomes_u(clean_gw, validate):
    df = clean_gw.copy()
    i = first(df, sample_type="N", result_type="TRG", detect_flag="Y", cas_rn="7440-38-2")
    df.loc[i, ["result_value", "lab_qualifier"]] = [str(float(df.at[i, "mdl"]) / 2), "J"]
    res = validate(df)
    assert len(rows_of(res, "DET-01")) == 1
    assert status(res, i) == ("QUALIFIED", "U")


# ------------------------------------------------------------------ thermal preservation
def _set_cooler(df, temp):
    df.loc[df.cooler_id == "C2", "cooler_temp_c"] = temp
    return df


def test_cooler_at_6c_passes(clean_gw, validate):
    res = validate(_set_cooler(clean_gw.copy(), "6.0"))
    assert rows_of(res, "PRES-01").empty


def test_cooler_just_above_6c_qualifies_organics_not_metals(clean_gw, validate):
    df = _set_cooler(clean_gw.copy(), "6.1")
    res = validate(df)
    exc = rows_of(res, "PRES-01")
    assert len(exc) and set(exc.severity) == {"WARNING"}
    assert "METALS-ICPMS" not in set(exc.method_code)   # metals have no temperature requirement
    i = first(df, cooler_id="C2", method_code="VOC-HSGCMS", result_type="TRG", detect_flag="N")
    assert status(res, i) == ("QUALIFIED", "UJ")


def test_cooler_above_10c_rejects(clean_gw, validate):
    df = _set_cooler(clean_gw.copy(), "12.0")
    res = validate(df)
    assert set(rows_of(res, "PRES-01").severity) == {"CRITICAL"}
    i = first(df, cooler_id="C2", method_code="PAH-GCMS", result_type="TRG")
    assert status(res, i) == ("HELD", "R")


# ------------------------------------------------------------------ holding time
def _analysis_after(df, sample, method, days):
    m = (df.sys_sample_code == sample) & (df.method_code == method)
    sd = datetime.strptime(df.loc[m, "sample_date"].iloc[0], DATE_FORMAT)
    df.loc[m, "analysis_date"] = (sd + timedelta(days=days)).strftime(DATE_FORMAT)
    return df.index[m & (df.result_type == "TRG")][0]


def test_holding_time_boundaries(clean_gw, validate):
    s = "MW01-2601"
    df = clean_gw.copy()
    _analysis_after(df, s, "VOC-HSGCMS", 14)          # exactly at the 14 day limit
    assert rows_of(validate(df), "HT-01").empty

    df = clean_gw.copy()
    i = _analysis_after(df, s, "VOC-HSGCMS", 15)
    res = validate(df)
    assert list(rows_of(res, "HT-01").severity) == ["WARNING"]
    assert status(res, i)[1] in ("J", "UJ")

    df = clean_gw.copy()
    i = _analysis_after(df, s, "VOC-HSGCMS", 29)      # more than 2x the limit
    res = validate(df)
    assert list(rows_of(res, "HT-01").severity) == ["CRITICAL"]
    assert status(res, i) == ("HELD", "R")


# ------------------------------------------------------------------ surrogates and spikes
def test_surrogate_below_10_percent_rejects_sample(clean_gw, validate):
    df = clean_gw.copy()
    i = first(df, sys_sample_code="MW02-2601", result_type="SUR", method_code="PAH-GCMS")
    df.loc[i, ["result_value", "percent_recovery"]] = ["5.0", "5.0"]
    res = validate(df)
    assert list(rows_of(res, "SUR-01").severity) == ["CRITICAL"]
    t = first(df, sys_sample_code="MW02-2601", method_code="PAH-GCMS", result_type="TRG")
    assert status(res, t) == ("HELD", "R")


def test_surrogate_high_only_qualifies_detects(clean_gw, validate):
    df = clean_gw.copy()
    i = first(df, sys_sample_code="MW03-2601", result_type="SUR", method_code="VOC-HSGCMS")
    df.loc[i, ["result_value", "percent_recovery"]] = ["140", "140"]
    res = validate(df)
    det = first(df, sys_sample_code="MW03-2601", method_code="VOC-HSGCMS", result_type="TRG", detect_flag="Y")
    nd = first(df, sys_sample_code="MW03-2601", method_code="VOC-HSGCMS", result_type="TRG", detect_flag="N")
    assert status(res, det) == ("QUALIFIED", "J+")
    assert status(res, nd) == ("PASS", None)   # high bias cannot hide a non-detect


def test_matrix_spike_not_assessable_when_parent_high(clean_gw, validate):
    df = clean_gw.copy()
    i = first(df, sample_type="MS", result_type="TRG")
    parent = first(df, sys_sample_code=df.at[i, "parent_sample_code"], method_code=df.at[i, "method_code"],
                   fraction=df.at[i, "fraction"], cas_rn=df.at[i, "cas_rn"])
    df.loc[parent, ["result_value", "detect_flag", "lab_qualifier"]] = [str(float(df.at[i, "spike_added"]) * 5), "Y", ""]
    df.loc[i, "percent_recovery"] = "40"                 # would fail MS-01 if it were assessable
    res = validate(df)
    assert len(rows_of(res, "MS-03")) == 1
    assert rows_of(res, "MS-01").empty


# ------------------------------------------------------------------ blanks
def test_method_blank_action_level(clean_gw, validate):
    df = clean_gw.copy()
    mb = first(df, sample_type="MB", cas_rn="7440-66-6")
    df.loc[mb, ["result_value", "detect_flag"]] = ["2.0", "Y"]       # zinc in the method blank
    low = first(df, sample_type="N", cas_rn="7440-66-6", fraction="T")
    high = df.index[(df.sample_type == "N") & (df.cas_rn == "7440-66-6") & (df.fraction == "D")][0]
    df.loc[low, ["result_value", "detect_flag", "lab_qualifier"]] = ["9.5", "Y", ""]   # < 5 x 2.0
    df.loc[high, ["result_value", "detect_flag", "lab_qualifier"]] = ["10.5", "Y", ""]  # >= action level
    res = validate(df)
    assert len(rows_of(res, "BLK-01")) == 1
    assert status(res, low)[1] == "B"
    assert status(res, high)[1] != "B"


# ------------------------------------------------------------------ qualifier precedence
def test_qualifier_precedence():
    assert combine({"B", "J"}, True) == "J"
    assert combine({"J+", "J-"}, True) == "J"
    assert combine({"J", "J-"}, True) == "J-"
    assert combine({"U", "J"}, True) == "UJ"
    assert combine({"J"}, False) == "UJ"
    assert combine({"B", "R", "J"}, True) == "R"
    assert combine({"HOLD"}, True) is None
    assert combine({"B"}, True) == "B"
