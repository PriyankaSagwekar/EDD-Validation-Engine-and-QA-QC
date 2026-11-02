"""The fictional ground investigation data: logs are continuous, screens sit in the aquifer,
water strikes rise and water levels stay inside each well."""
from collections import defaultdict

from eddqc import refdata as R
from eddqc import site_investigation as SI

LOC = {loc[0]: loc for loc in R.LOCATIONS}


def test_geology_is_continuous_from_ground_level_to_final_depth():
    logs = defaultdict(list)
    for loc, top, base, *_ in SI.geology():
        logs[loc].append((top, base))
    assert set(logs) == set(LOC)
    for loc, layers in logs.items():
        assert layers[0][0] == 0 and layers[-1][1] == LOC[loc][5], loc
        assert all(a[1] == b[0] for a, b in zip(layers, layers[1:])), loc       # no gaps or overlaps
        assert all(top < base for top, base in layers), loc


def test_well_screens_sit_below_the_alluvium():
    for loc, top, base, _leg, code, *_ in SI.geology():
        st, sb = LOC[loc][6], LOC[loc][7]
        if st is not None and code in ("MG", "ALV"):
            assert base <= st, (loc, code, base, st)
            assert sb <= LOC[loc][5]


def test_water_strikes_rise_and_levels_stay_in_the_well():
    strikes, readings = SI.water_strikes()
    by_strike = defaultdict(list)
    for loc, depth, minutes, level in readings:
        by_strike[(loc, depth)].append((minutes, level))
    for loc, depth, *_ in strikes:
        levels = [lv for _, lv in sorted(by_strike[(loc, depth)])]
        assert depth < LOC[loc][5]
        assert all(a >= b for a, b in zip([depth, *levels], levels)), loc          # water rises
    dips = SI.water_levels()
    assert {d[0] for d in dips} == set(R.MONITORING_WELLS)
    assert all(0 < depth < LOC[loc][7] for loc, _, _, depth, _ in dips)
    assert SI.geology() == SI.geology() and dips == SI.water_levels()            # reproducible
