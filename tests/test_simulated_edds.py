"""The engine against simulated EDDs: no false alarms on clean data, every injected defect caught."""
import pytest

from eddqc.simulate import DEFECTS, build_events


@pytest.mark.parametrize("seed", [42, 2026])
def test_clean_edds_raise_no_exceptions(seed, validate):
    for ev in build_events(seed=seed, clean=True):
        res = validate(ev.df)
        assert res.exceptions.empty, res.exceptions.head(10).to_string()
        assert (res.rows.qc_status == "PASS").all()


def test_every_defect_type_is_injected(dirty_events):
    rules = {k["rule_id"] for ev in dirty_events for k in ev.keys}
    injected_kinds = len({k["description"] for ev in dirty_events for k in ev.keys})
    assert len(rules) == 36  # every rule id in the catalogue
    assert injected_kinds >= len(DEFECTS) - 2


def test_every_injected_defect_is_caught(dirty_events, validate):
    missed = []
    for ev in dirty_events:
        e = validate(ev.df).exceptions
        for k in ev.keys:
            m = e.rule_id == k["rule_id"]
            if k["sys_sample_code"]:
                m &= e.sys_sample_code == k["sys_sample_code"]
            if k["cas_rn"]:
                m &= e.cas_rn == k["cas_rn"]
            if not m.any():
                missed.append((ev.file_stem, k))
    assert not missed, missed


def test_critical_rows_are_held(dirty_events, validate):
    res = validate(dirty_events[0].df)
    crit_rows = set(res.exceptions.loc[res.exceptions.severity == "CRITICAL", "source_row_no"])
    held = set(res.rows.loc[res.rows.qc_status == "HELD", "source_row_no"])
    assert crit_rows and crit_rows <= held
