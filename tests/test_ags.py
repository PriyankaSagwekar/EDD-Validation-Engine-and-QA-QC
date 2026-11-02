"""AGS 4.2 export / import: round trips, checker rules and the code mappings. No database needed."""
import warnings

import pandas as pd
import pytest

from eddqc import ags
from eddqc import refdata as R
from eddqc.ags.reference import load_reference
from eddqc.loader import EDDFormatError, read_edd
from eddqc.seed import reference_tables


@pytest.fixture(scope="module")
def locations():
    cols, rows = reference_tables()["ref_Location"]
    return pd.DataFrame(rows, columns=cols)


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
    if not ref.official:
        pytest.skip("Official AGS code lists not present in docs/reference/ags")
    for ours, code in R.AGS_ELRG_CODE.items():
        assert code in ref.elrg, (ours, code)
    standard = [cas for cas, *_ in R.ANALYTES if cas not in R.AGS_ELRG_CODE and cas not in R.AGS_PROJECT_CODES]
    assert [c for c in standard if c not in ref.elrg] == []
    assert all(c not in ref.elrg for c in R.AGS_PROJECT_CODES)
    assert all(u in ref.units for u in R.AGS_UNIT.values())
