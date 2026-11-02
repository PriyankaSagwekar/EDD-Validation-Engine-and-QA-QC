"""AGS 4.2 export / import: round trips, checker rules and the code mappings. No database needed."""
import warnings

import pandas as pd
import pytest

from eddqc import ags
from eddqc import refdata as R
from eddqc.ags.reference import load_reference
from eddqc.loader import EDDFormatError, read_edd
from eddqc.seed import reference_tables


def ref_frame(name):
    cols, rows = reference_tables()[name]
    return pd.DataFrame(rows, columns=cols)


@pytest.fixture(scope="module")
def locations():
    return ref_frame("ref_Location")


@pytest.fixture(scope="module")
def site():
    return {"geology": ref_frame("ref_Geology"), "strikes": ref_frame("ref_Water_Strike"),
            "strike_readings": ref_frame("ref_Water_Strike_Reading"), "levels": ref_frame("ref_Water_Level")}


def to_ags(df, locations, **kw):
    return ags.to_text(ags.edd_to_groups(df, locations, **kw))


def roundtrip(text):
    groups, issues = ags.check_text(text)
    assert not ags.errors(issues), ags.errors(issues)[:5]
    return ags.ags_to_edd(groups)


def group(text, name):
    return ags.parse(text)[0][name].frame()


def test_clean_edd_round_trips_exactly(clean_gw, locations, validate):
    back = roundtrip(to_ags(clean_gw, locations, include_lab_qc=True)).drop(columns="source_row_no")
    orig = clean_gw.reset_index(drop=True)[back.columns].fillna("").astype(object)
    pd.testing.assert_frame_equal(back.reset_index(drop=True).astype(object), orig)
    assert validate(back).exceptions.empty


def test_dirty_edds_give_same_exceptions_and_qualifiers(dirty_events, locations, validate):
    """Every QA/QC finding survives the trip, except flat-file defects AGS cannot represent:
    unparseable or missing key fields, duplicate rows (COMP-*) and conflicting sample headers (REF-05)."""
    key = ["rule_id", "sys_sample_code", "cas_rn", "source_row_no"]
    rules_seen = set()
    for event in dirty_events:
        df = event.df.reset_index(drop=True)
        df.insert(0, "source_row_no", range(2, len(df) + 2))
        first = validate(df).exceptions
        drop_rows = set(first[first.rule_id.str.startswith("COMP") | (first.rule_id == "REF-05")].source_row_no)
        bad_samples = set(first[first.rule_id == "REF-05"].sys_sample_code)
        src = df[~df.source_row_no.isin(drop_rows) & ~df.sys_sample_code.isin(bad_samples)].reset_index(drop=True)
        before = validate(src)
        back = roundtrip(to_ags(src, locations, include_lab_qc=True, strict=False))
        back["source_row_no"] = src.source_row_no.values          # compare row by row
        after = validate(back)
        pd.testing.assert_frame_equal(before.exceptions.sort_values(key)[key].reset_index(drop=True),
                                      after.exceptions.sort_values(key)[key].reset_index(drop=True))
        pd.testing.assert_series_equal(before.rows.validator_qualifier, after.rows.validator_qualifier)
        rules_seen |= set(before.exceptions.rule_id)
    assert len(rules_seen) >= 20, sorted(rules_seen)


def test_codes_units_and_locations_follow_ags_lists(clean_gw, locations):
    text = to_ags(clean_gw, locations)
    elrg = group(text, "ELRG")
    assert set(elrg.ELRG_RUNI) == {"ug/l", "%"}                       # AGS units are case-sensitive
    assert "P1374" in set(elrg.ELRG_CODE) and "179601-23-1" not in set(elrg.ELRG_CODE)
    assert set(elrg.ELRG_RTCD) <= {"TRG", "SUR", "IC"}
    assert set(elrg.ELRG_MATX) == {"LIQUID"}
    abbr = group(text, "ABBR").set_index(["ABBR_HDNG", "ABBR_CODE"])
    assert abbr.loc[("ELRG_CODE", "84-15-1"), "ABBR_LIST"] == "RIE01"   # o-terphenyl: project code
    assert abbr.loc[("ELRG_CODE", "71-43-2"), "ABBR_LIST"] == "AGS4"
    loca = group(text, "LOCA").set_index("LOCA_ID")
    assert loca.loc["MW01", "LOCA_TYPE"] == "CP" and loca.loc["MW01", "LOCA_NSRI"] == "27700"
    assert loca.loc["MW01", "LOCA_NATE"] == "430120.00" and loca.loc["FIELDQC", "LOCA_TYPE"] == "QC"
    assert set(group(text, "MONG").MONG_TYPE) == {"GWMP"}
    samp = group(text, "SAMP").set_index("SAMP_ID")
    fd = samp[samp.SAMP_TYPC == "Field duplicate"].iloc[0]
    assert fd.SAMP_LINK.startswith("SAMP|") and fd.SAMP_LINK.split("|")[-1] in samp.index
    assert "LABQC" not in set(loca.index)                                # lab QC only on request


def test_writer_refuses_unapproved_codes(clean_gw, locations):
    bad = clean_gw.copy()
    bad.loc[bad.index[0], "cas_rn"] = "99-99-9"
    with pytest.raises(ags.AGSWriteError):
        ags.edd_to_groups(bad, locations)
    bad = clean_gw.copy()
    bad["unit"] = bad.unit.replace("ug/L", "ug/L ")
    with pytest.raises(ags.AGSWriteError):
        ags.edd_to_groups(bad.assign(unit=bad.unit.str.replace("ug/L ", "ugL")), locations)


@pytest.mark.parametrize("change, rule", [
    (lambda t: t.replace("\r\n", "\n"), "Rule 2a"),
    (lambda t: t.replace("Fictional client", "Fictional cliént"), "Rule 1"),
    (lambda t: t.replace('"ug/l"', '"ug/L"', 5).replace('"UNIT_UNIT","UNIT_DESC"', '"UNIT_UNIT","UNIT_DESC"'),
     "Rule 15"),
    (lambda t: t.replace('"LIQUID"', '"WATER"'), "Rule 16"),
    (lambda t: t.replace('"GROUP","LOCA"', '"GROUP","LOCX"'), "Rule 10c"),
])
def test_checker_catches_broken_files(clean_gw, locations, change, rule):
    _, issues = ags.check_text(change(to_ags(clean_gw, locations)))
    assert rule in {i.rule for i in ags.errors(issues)}


def test_checker_catches_duplicate_keys(clean_gw, locations):
    text = to_ags(clean_gw, locations)
    lines = text.split("\r\n")
    first_elrg = next(i for i, ln in enumerate(lines) if ln.startswith('"DATA"') and '"INITIAL"' in ln)
    lines.insert(first_elrg + 1, lines[first_elrg])
    _, issues = ags.check_text("\r\n".join(lines))
    assert any(i.rule == "Rule 10a" and "Duplicate key" in i.message for i in issues)


def test_third_party_file_without_receipt_data_is_flagged(clean_gw, locations, validate):
    """A lab file with only the standard headings (no CHOC, no project DICT headings) still loads,
    and the preservation rules then report the missing receipt data."""
    groups = [g for g in ags.edd_to_groups(clean_gw, locations) if g.name not in ("CHOC", "DICT")]
    for g in groups:
        if g.name == "ELRG":
            keep = [i for i, h in enumerate(g.headings) if h not in ("ELRG_PH", "ELRG_EXDT", "ELRG_SPKA", "ELRG_PREC")]
            g.headings, g.units, g.types = ([x[i] for i in keep] for x in (g.headings, g.units, g.types))
            g.rows = [[r[i] for i in keep] for r in g.rows]
    edd = roundtrip(ags.to_text(groups))
    assert (edd.coc_id == "").all()
    assert "PRES-03" in set(validate(edd).exceptions.rule_id)


def test_legacy_eres_is_read_with_a_warning(clean_gw, locations):
    text = to_ags(clean_gw, locations).replace('"GROUP","ELRG"', '"GROUP","ERES"').replace('"ELRG_', '"ERES_')
    groups, _ = ags.check_text(text)
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        edd = ags.ags_to_edd(groups)
    field = clean_gw[~clean_gw.sample_type.isin(R.LAB_QC_TYPES)]
    assert len(edd) == len(field) and any("ERES" in str(x.message) for x in w)


def test_loader_reads_ags_and_rejects_broken_files(clean_gw, locations, tmp_path):
    good = tmp_path / "good.ags"
    good.write_bytes(to_ags(clean_gw, locations).encode("ascii"))
    df, _ = read_edd(good)
    assert len(df) == len(clean_gw[~clean_gw.sample_type.isin(R.LAB_QC_TYPES)])
    assert df.source_row_no.min() > 20                         # AGS file line numbers, not 2, 3, ...
    bad = tmp_path / "bad.ags"
    bad.write_bytes(good.read_bytes().replace(b'"GROUP","LOCA"', b'"GROUP","LOCX"'))
    with pytest.raises(EDDFormatError, match="AGS check"):
        read_edd(bad)


def test_mapped_codes_are_approved_in_the_official_list():
    ref = load_reference()
    assert ref.official, "the AGS code lists are committed in docs/reference/ags and must load"
    for ours, code in R.AGS_ELRG_CODE.items():
        assert ref.abbr_desc("ELRG_CODE", code), (ours, code)
    standard = [cas for cas, *_ in R.ANALYTES if cas not in R.AGS_ELRG_CODE and cas not in R.AGS_PROJECT_CODES]
    assert [c for c in standard if not ref.abbr_desc("ELRG_CODE", c)] == []
    assert all(c not in ref.elrg for c in R.AGS_PROJECT_CODES)
    assert all(ref.unit_desc(u) for u in R.AGS_UNIT.values())
    assert all(ref.abbr_desc("GEOL_LEG", leg) for _, leg, *_ in R.STRATA)


def test_ground_investigation_groups_are_written_and_pass_strict_check(clean_gw, locations, site):
    text = to_ags(clean_gw, locations, site=site)
    _, issues = ags.check_text(text, strict_version=True)
    assert not ags.errors(issues), ags.errors(issues)[:5]
    groups = ags.parse(text)[0]
    wells = set(groups["MONG"].frame().LOCA_ID)
    assert set(groups["GEOL"].frame().LOCA_ID) == set(groups["WSTG"].frame().LOCA_ID) == wells
    mond = groups["MOND"].frame()
    assert set(mond.MOND_TYPE) == {"WDEP"} and set(mond.MOND_UNIT) == {"m"} and len(mond) == 4 * len(wells)
    abbr = group(text, "ABBR").set_index(["ABBR_HDNG", "ABBR_CODE"])
    assert abbr.loc[("GEOL_GEOL", "RTD"), "ABBR_LIST"] == "RIE01"         # no approved list: project codes
    assert abbr.loc[("GEOL_LEG", "501"), "ABBR_LIST"] == "AGS4"
    assert len(roundtrip(text)) == len(clean_gw[~clean_gw.sample_type.isin(R.LAB_QC_TYPES)])


def test_only_ags_42_passes_the_strict_version_check(clean_gw, locations, tmp_path):
    text = to_ags(clean_gw, locations).replace('"4.2","Portfolio', '"4.1","Portfolio')
    _, strict = ags.check_text(text, strict_version=True)
    assert any(i.rule == "Version" and "Only AGS 4.2" in i.message for i in ags.errors(strict))
    _, lenient = ags.check_text(text)
    assert not ags.errors(lenient) and any(i.rule == "Version" for i in lenient)
    no_tran = "\r\n".join(ln for ln in text.split("\r\n") if "TRAN" not in ln)
    assert any(i.rule == "Version" for i in ags.errors(ags.check_text(no_tran, strict_version=True)[1]))
    path = tmp_path / "old.ags"                                  # the pipeline still loads it
    path.write_bytes(text.encode("ascii"))
    assert len(read_edd(path)[0]) > 0


def _write_lists(folder, datatype_name="DATATYPES.csv"):
    folder.mkdir()
    (folder / "ABBR.csv").write_text(
        "Code ,Description,Status,Comments,Date,Version\n"
        "ELRG_MATX,,,,,\nLIQUID,Liquid,Approved,,,\"4.0,4.1,4.2\"\nSOLID,Solid,Approved,,,4.2\n"
        "WATER,Water,Declined,Use LIQUID,,\"4.1,4.2\"\nGAS,Gas,Proposed,,,4.2\nSLUDGE,Sludge,Approved,,,4.0\n")
    (folder / "UNITS.csv").write_text('"Type","Unit","Description","Date","Comments","Status","Version"\n'
                                      '"Conc","ug/l","micrograms per litre","","","Approved","4.2"\n'
                                      '"Density","g/cm3","grams per cubic centimetre","","","Deprecated","4.2"\n')
    (folder / "ELRG.csv").write_text('"Code","Date Last Reviewed","Status","Description","AGS Comments"\n'
                                     '"71-43-2","","Approved","Benzene",""\n'
                                     '"11-82-7","","Deprecated","Old","Use 110-82-7"\n'
                                     '"999-99-9","","Accepted","New",""\n')
    (folder / datatype_name).write_text('"Type","Desc","Notes","Version"\n"X","Text","","4.2"\n')


def test_code_list_statuses_and_versions(tmp_path):
    from eddqc.ags.model import Group
    _write_lists(tmp_path / "lists")
    ref = load_reference(tmp_path / "lists")
    assert ref.official and ref.abbr_desc("ELRG_MATX", "LIQUID") == "Liquid"
    assert ref.abbr_entry("ELRG_MATX", "SLUDGE") is None                 # AGS 4.0 only: not read
    assert ref.abbr_desc("ELRG_MATX", "WATER") is None
    assert ref.abbr_entry("ELRG_MATX", "WATER").status == "Declined"
    abbr = Group("ABBR", ["ABBR_HDNG", "ABBR_CODE", "ABBR_DESC", "ABBR_LIST"], [""] * 4, ["X"] * 4,
                 [["ELRG_MATX", c, c, "AGS4"] for c in ("LIQUID", "WATER", "GAS", "UNKNOWN")] +
                 [["ELRG_CODE", c, c, "AGS4"] for c in ("11-82-7", "999-99-9")], lines=list(range(10, 16)))
    unit = Group("UNIT", ["UNIT_UNIT", "UNIT_DESC"], ["", ""], ["X", "X"],
                 [["ug/l", "u"], ["g/cm3", "g"], ["furlong", "f"]], lines=[20, 21, 22])
    issues = ags.check_groups({"ABBR": abbr, "UNIT": unit}, ref)
    found = {(i.severity, i.line) for i in issues if i.rule in ("Rule 15", "Rule 16")}
    assert found == {("ERROR", 11), ("WARNING", 12), ("ERROR", 13), ("WARNING", 14), ("INFO", 15),
                     ("WARNING", 21), ("WARNING", 22)}
    assert "Use LIQUID" in next(i.message for i in issues if i.line == 11)


def test_code_list_loader_accepts_old_file_name_and_rejects_partial_folders(tmp_path):
    _write_lists(tmp_path / "old", "DATATYPE.csv")
    assert load_reference(tmp_path / "old").official
    _write_lists(tmp_path / "partial")
    (tmp_path / "partial" / "ELRG.csv").unlink()
    with pytest.raises(FileNotFoundError, match="ELRG"):
        load_reference(tmp_path / "partial")
