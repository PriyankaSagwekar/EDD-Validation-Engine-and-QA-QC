"""Fictional ground investigation data: geology logs, water strikes and groundwater levels.

Generated from the ground model in refdata.py with a fixed seed per location, so every run gives
the same logs. Seeded into ref_Geology, ref_Water_Strike, ref_Water_Strike_Reading and
ref_Water_Level, and exported as the AGS groups GEOL, WSTG, WSTD and MOND.
"""
from __future__ import annotations

import math
import random
from datetime import date, datetime, timedelta

from . import refdata as R

STRIKE_MINUTES = (5, 10, 15, 20)
GW = R.GROUNDWATER


def _rng(*key) -> random.Random:
    return random.Random("-".join(map(str, (R.SITE["site_code"], *key))))


def _fmt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M")


def drilling_dates() -> dict[str, date]:
    """One hole per working day, in LOCATIONS order."""
    day, out = date.fromisoformat(R.DRILLING_START), {}
    for loc, *_ in R.LOCATIONS:
        while day.weekday() >= 5:
            day += timedelta(days=1)
        out[loc] = day
        day += timedelta(days=1)
    return out


def geology() -> list[tuple]:
    """(location, depth_top_m, depth_base_m, legend_code, geology_code, description, formation)."""
    rows = []
    for loc, _type, _e, _n, _gl, final, _st, _sb in R.LOCATIONS:
        rng, top = _rng(loc, "geology"), 0.0
        for code, legend, formation, desc, base_range in R.STRATA:
            base = final if base_range is None else min(round(rng.uniform(*base_range), 2), final)
            rows.append((loc, top, base, legend, code, desc, formation))
            top = base
            if top >= final:
                break
    return rows


def _alluvium_base(loc: str) -> float:
    return next(base for l, _t, base, _leg, code, *_ in geology() if l == loc and code == "ALV")


def _rest_depth(loc: str) -> float:
    strike = round(_alluvium_base(loc) + GW["strike_below_alluvium_m"], 2)
    return round(strike - _rng(loc, "rise").uniform(*GW["rise_m"]), 2)


def water_strikes() -> tuple[list[tuple], list[tuple]]:
    """Strikes (location, depth_m, datetime, remark) and rise readings (location, depth_m, minutes, depth_m)."""
    dates = drilling_dates()
    strikes, readings = [], []
    for loc, *_ in R.LOCATIONS:
        strike = round(_alluvium_base(loc) + GW["strike_below_alluvium_m"], 2)
        rest = _rest_depth(loc)
        when = datetime.combine(dates[loc], datetime.min.time()) + timedelta(hours=11, minutes=30)
        strikes.append((loc, strike, _fmt(when),
                        "Struck in River Terrace Deposits below the Alluvium; rose (sub-artesian)"))
        for m in STRIKE_MINUTES:
            readings.append((loc, strike, m, round(rest + (strike - rest) * math.exp(-m / 6), 2)))
    return strikes, readings


def water_levels() -> list[tuple]:
    """Dip readings (location, datetime, reading_ref, depth_to_water_m, method), one per well per
    groundwater event, taken before purging on the day the well is sampled."""
    from .simulate import EVENTS
    rows = []
    for evt, kind, start in EVENTS:
        if kind != "GW":
            continue
        for i, loc in enumerate(R.MONITORING_WELLS):
            when = start + timedelta(days=i // 4, hours=8 + 2 * (i % 4), minutes=30)
            season = -math.cos(2 * math.pi * (when.timetuple().tm_yday - 45) / 365)
            noise = _rng(loc, evt, "dip").uniform(-GW["noise_m"], GW["noise_m"])
            depth = _rest_depth(loc) + GW["seasonal_amplitude_m"] * season + noise
            rows.append((loc, _fmt(when), evt, round(max(depth, 0.05), 2), GW["dip_method"]))
    return rows
