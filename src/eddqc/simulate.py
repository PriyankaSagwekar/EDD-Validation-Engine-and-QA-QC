"""Simulate laboratory EDDs for a fictional UK site, with known injected defects.

Each sampling event becomes one EDD file (one row per result), the way a lab
would deliver it. The data are generated clean first: every value respects the
reference limits, so a clean file must pass validation with zero exceptions.
Defects are then injected and each one is written to an answer key, so tests
can prove that the validation engine catches every one of them.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from . import refdata as R
from .edd_schema import DATE_FORMAT, EDD_COLUMNS

METHOD_ABBR = {"METALS-ICPMS": "MET", "VOC-HSGCMS": "VOC", "PAH-GCMS": "PAH", "TPH-CWG-GC": "TPH"}
METHODS = list(METHOD_ABBR)
ORGANIC_METHODS = ("VOC-HSGCMS", "PAH-GCMS", "TPH-CWG-GC")
EXTRACTED_METHODS = ("PAH-GCMS", "TPH-CWG-GC")

# event code, event kind, first sampling day
EVENTS = [
    ("2601", "GW", datetime(2026, 1, 13)),
    ("2602", "SO", datetime(2026, 2, 23)),
    ("2604", "GW", datetime(2026, 4, 14)),
    ("2606", "SO", datetime(2026, 6, 8)),
    ("2607", "GW", datetime(2026, 7, 14)),
    ("2609", "GW", datetime(2026, 9, 22)),
]

CAS_BY_METHOD = {m: [cas for (mm, cas) in R.METHOD_ANALYTE_LIMITS if mm == m] for m in METHODS}
TOTALS = {"BTEX-TOT", "TPH-TOT-C10C40"}
COMPONENTS = {t: [a[0] for a in R.ANALYTES if a[5] == t] for t in TOTALS}
LOC_INFO = {l[0]: l for l in R.LOCATIONS}

# ---------------------------------------------------------------- concentration model
# (median, probability of detection). Water ug/L, soil mg/kg.
WATER_BASE = {
    "7440-38-2": (2.0, 0.95), "7440-43-9": (0.06, 0.5), "7440-47-3": (1.2, 0.8),
    "7440-50-8": (2.5, 0.9), "7439-92-1": (0.8, 0.8), "7440-02-0": (3.0, 0.9),
    "7440-66-6": (12.0, 0.95), "91-20-3": (0.02, 0.3),
}
WATER_GROUP_DEFAULT = {"VOC": (0.5, 0.04), "PAH": (0.008, 0.15), "TPH": (15.0, 0.08)}
SOIL_BASE = {
    "7440-38-2": (18, 1), "7440-43-9": (0.6, 0.9), "7440-47-3": (35, 1), "7440-50-8": (45, 1),
    "7439-92-1": (150, 1), "7440-02-0": (28, 1), "7440-66-6": (180, 1),
    "91-20-3": (0.3, 0.9), "208-96-8": (0.2, 0.9), "83-32-9": (0.15, 0.9), "86-73-7": (0.2, 0.9),
    "85-01-8": (1.5, 0.9), "120-12-7": (0.5, 0.9), "206-44-0": (3.0, 0.9), "129-00-0": (2.5, 0.9),
    "56-55-3": (1.4, 0.9), "218-01-9": (1.5, 0.9), "205-99-2": (1.8, 0.9), "207-08-9": (0.7, 0.9),
    "50-32-8": (1.3, 0.9), "193-39-5": (0.8, 0.9), "53-70-3": (0.2, 0.9), "191-24-2": (0.9, 0.9),
}
SOIL_GROUP_DEFAULT = {"VOC": (0.002, 0.1), "PAH": (0.1, 0.5), "TPH": (5.0, 0.5)}
DEEP_FACTOR = {"METALS": 0.5, "PAH": 0.05, "TPH": 0.2, "VOC": 1.0}

_PLUME = {"71-43-2": 60, "108-88-3": 35, "100-41-4": 20, "179601-23-1": 45, "95-47-6": 15,
          "TPH-ALI-C10C12": 300, "TPH-ALI-C12C16": 250, "TPH-ALI-C16C21": 120, "TPH-ALI-C21C35": 40,
          "TPH-ARO-C10C12": 400, "TPH-ARO-C12C16": 200, "TPH-ARO-C16C21": 80, "TPH-ARO-C21C35": 20,
          "91-20-3": 25, "83-32-9": 2, "86-73-7": 1.5, "85-01-8": 1.0}
_SOLVENT = {"79-01-6": 120, "127-18-4": 30, "75-01-4": 4}
WATER_HOTSPOTS = [
    ({"MW03": 1.0, "MW04": 0.3, "MW05": 0.05}, _PLUME),
    ({"MW07": 1.0, "MW08": 0.35, "MW09": 0.05}, _SOLVENT),
]
SOIL_HOTSPOTS = [
    ({"BH02": 1.0}, {"71-43-2": 0.5, "108-88-3": 1.2, "100-41-4": 0.8, "179601-23-1": 2.0, "95-47-6": 0.7,
                     "TPH-ALI-C10C12": 150, "TPH-ALI-C12C16": 220, "TPH-ALI-C16C21": 180, "TPH-ALI-C21C35": 90,
                     "TPH-ARO-C10C12": 120, "TPH-ARO-C12C16": 160, "TPH-ARO-C16C21": 110, "TPH-ARO-C21C35": 60}),
    ({"BH03": 1.0}, {"79-01-6": 0.05, "127-18-4": 0.3}),
]


def sig(v: float, n: int = 3) -> float:
    if v == 0 or v is None:
        return 0.0
    return round(v, -int(math.floor(math.log10(abs(v)))) + (n - 1))


def fnum(v) -> str:
    if v is None or v == "":
        return ""
    return f"{v:.6g}"


def fdate(d: datetime | None) -> str:
    return "" if d is None else d.strftime(DATE_FORMAT)


def limits(method: str, cas: str, kind: str, dilution: float = 1.0) -> tuple[float, float]:
    mdl, rl = R.METHOD_ANALYTE_LIMITS[(method, cas)][kind]
    return sig(mdl * dilution), sig(rl * dilution)


# ---------------------------------------------------------------- data structures
@dataclass
class Sample:
    code: str
    sample_type: str
    matrix: str
    lab_id: str
    location: str | None = None
    dt: datetime | None = None
    top: float | None = None
    base: float | None = None
    parent: str | None = None
    cooler: str | None = None
    methods: tuple = tuple(METHODS)


@dataclass
class EventData:
    evt: str
    kind_code: str
    file_stem: str
    df: pd.DataFrame
    keys: list = field(default_factory=list)


class Simulator:
    def __init__(self, seed: int = 42):
        self.rng = np.random.default_rng(seed)
        self.lab_seq = 0

    # ------------------------------------------------------------ helpers
    def _lab_id(self, evt: str) -> str:
        self.lab_seq += 1
        return f"FAL{evt}-{self.lab_seq:04d}"

    def _true_value(self, cas: str, kind: str, loc: str, depth: float | None) -> float:
        grp = R.ANALYTE_GROUP[cas]
        if kind == "W":
            med, p = WATER_BASE.get(cas, WATER_GROUP_DEFAULT.get(grp, (0, 0)))
            for locs, meds in WATER_HOTSPOTS:
                if loc in locs and cas in meds:
                    med, p = meds[cas] * locs[loc], 1.0
        else:
            med, p = SOIL_BASE.get(cas, SOIL_GROUP_DEFAULT.get(grp, (0, 0)))
            if depth is not None and depth > 1.5:
                med *= DEEP_FACTOR[grp]
                if grp in ("PAH", "TPH"):
                    p *= 0.6
            for locs, meds in SOIL_HOTSPOTS:
                if loc in locs and cas in meds:
                    med, p = meds[cas] * locs[loc], 1.0
        if med <= 0 or self.rng.random() >= p:
            return 0.0
        return float(med * math.exp(self.rng.normal(0, 0.5)))

    @staticmethod
    def _report(value: float, mdl: float, rl: float) -> tuple[str, str, str]:
        """Return result_value, detect_flag, lab_qualifier as a lab would report them."""
        v = sig(value)
        if v < mdl or v == 0:
            return "", "N", ""
        return fnum(v), "Y", ("J" if v < rl else "")

    # ------------------------------------------------------------ event
    def build_event(self, evt: str, kind_code: str, start: datetime) -> EventData:
        rng = self.rng
        field_matrix = "WG" if kind_code == "GW" else "SO"
        kind = R.matrix_kind(field_matrix)
        lab_qc_matrix = "WQ" if kind == "W" else "SO"
        coc = f"COC-{evt}"

        normals: list[Sample] = []
        if kind_code == "GW":
            for i, loc in enumerate(R.MONITORING_WELLS):
                day = i // 4
                info = LOC_INFO[loc]
                normals.append(Sample(
                    code=f"{loc}-{evt}", sample_type="N", matrix="WG", lab_id=self._lab_id(evt),
                    location=loc, dt=start + timedelta(days=day, hours=9 + 2 * (i % 4), minutes=int(rng.integers(0, 50))),
                    top=info[6] + 0.5, base=info[7] - 0.5, cooler="C1" if day == 0 else "C2"))
        else:
            i = 0
            for loc, depths in R.SOIL_LOCATIONS.items():
                for d in depths:
                    day = i // 5
                    normals.append(Sample(
                        code=f"{loc}-{d:.1f}-{evt}", sample_type="N", matrix="SO", lab_id=self._lab_id(evt),
                        location=loc, dt=start + timedelta(days=day, hours=9 + (i % 5), minutes=int(rng.integers(0, 50))),
                        top=d, base=round(d + 0.3, 2), cooler="C1" if day == 0 else "C2"))
                    i += 1

        idx = rng.choice(len(normals), 2, replace=False)
        fd_parent, ms_parent = normals[idx[0]], normals[idx[1]]
        fd = Sample(code=f"FD01-{evt}", sample_type="FD", matrix=field_matrix, lab_id=self._lab_id(evt),
                    location=fd_parent.location, dt=fd_parent.dt, top=fd_parent.top, base=fd_parent.base,
                    parent=fd_parent.code, cooler=fd_parent.cooler)
        blank_type = "FB" if kind_code == "GW" else "EB"
        fb = Sample(code=f"{blank_type}01-{evt}", sample_type=blank_type, matrix="WQ", lab_id=self._lab_id(evt),
                    dt=start + timedelta(hours=16), cooler="C1")
        tb = Sample(code=f"TB01-{evt}", sample_type="TB", matrix="WQ", lab_id=self._lab_id(evt),
                    dt=start + timedelta(hours=8), cooler="C1", methods=("VOC-HSGCMS",))
        ms = Sample(code=f"{ms_parent.code}-MS", sample_type="MS", matrix=field_matrix,
                    lab_id=f"{ms_parent.lab_id}-MS", location=ms_parent.location, dt=ms_parent.dt,
                    top=ms_parent.top, base=ms_parent.base, parent=ms_parent.code, cooler=ms_parent.cooler)
        msd = Sample(code=f"{ms_parent.code}-MSD", sample_type="MSD", matrix=field_matrix,
                     lab_id=f"{ms_parent.lab_id}-MSD", location=ms_parent.location, dt=ms_parent.dt,
                     top=ms_parent.top, base=ms_parent.base, parent=ms_parent.code, cooler=ms_parent.cooler)
        field_samples = normals + [fd, fb, tb]

        # receipt per cooler
        coolers = {}
        for c in ("C1", "C2"):
            dts = [s.dt for s in field_samples if s.cooler == c]
            last = max(dts)
            coolers[c] = {
                "receipt": datetime(last.year, last.month, last.day, 10, 0) + timedelta(days=1),
                "temp": round(float(rng.uniform(2.0, 5.5)), 1),
            }
        last_receipt = max(v["receipt"] for v in coolers.values())

        # lab batch dates per method
        batches = {}
        for m in METHODS:
            ext = None
            if m in EXTRACTED_METHODS:
                ext = last_receipt + timedelta(days=int(rng.integers(1, 3)), hours=-1)
                anl = ext + timedelta(days=int(rng.integers(2, 10)))
            elif m == "METALS-ICPMS":
                anl = last_receipt + timedelta(days=int(rng.integers(5, 12)))
            else:
                anl = last_receipt + timedelta(days=int(rng.integers(1, 4)))
            batches[m] = {"lab_batch": f"LB{evt}-{METHOD_ABBR[m]}", "ext": ext, "anl": anl}

        rows: list[dict] = []
        true_vals: dict[tuple, float] = {}
        reported: dict[tuple, tuple] = {}

        def header(s: Sample) -> dict:
            is_lab = s.sample_type in R.LAB_QC_TYPES
            c = coolers.get(s.cooler) if s.cooler else None
            return {
                "sys_sample_code": s.code, "lab_sample_id": s.lab_id, "sample_type": s.sample_type,
                "parent_sample_code": s.parent or "", "location_code": s.location or "",
                "matrix": s.matrix, "sample_date": fdate(s.dt),
                "depth_top_m": "" if s.top is None else f"{s.top:.2f}",
                "depth_base_m": "" if s.base is None else f"{s.base:.2f}",
                "coc_id": "" if is_lab else coc, "cooler_id": "" if is_lab else (s.cooler or ""),
                "receipt_date": "" if is_lab else fdate(c["receipt"]),
                "cooler_temp_c": "" if is_lab else f"{c['temp']:.1f}",
                "custody_seal_intact": "" if is_lab else "Y",
                "lab_code": R.LAB["lab_code"],
            }

        def test_fields(s: Sample, m: str, fraction: str, seq: int) -> dict:
            b = batches[m]
            jitter = timedelta(minutes=17 * seq)
            ph = ""
            if R.matrix_kind(s.matrix) == "W" and m in ("METALS-ICPMS", "VOC-HSGCMS") \
                    and s.sample_type not in R.LAB_QC_TYPES:
                ph = f"{rng.uniform(1.4, 1.9):.1f}"
            return {"method_code": m, "fraction": fraction, "lab_batch_id": b["lab_batch"],
                    "extraction_date": fdate(b["ext"] + jitter) if b["ext"] else "",
                    "analysis_date": fdate(b["anl"] + jitter), "dilution_factor": "1", "sample_ph": ph}

        def add_row(h: dict, t: dict, cas: str, value: str, detect: str, mdl, rl, unit: str,
                    rtype: str = "TRG", spike="", rec="", q=""):
            row = {**h, **t, "cas_rn": cas, "chemical_name": R.ANALYTE_NAME[cas], "result_value": value,
                   "detect_flag": detect, "mdl": fnum(mdl) if mdl != "" else "", "rl": fnum(rl) if rl != "" else "",
                   "unit": unit, "result_type": rtype, "spike_added": spike, "percent_recovery": rec,
                   "lab_qualifier": q}
            rows.append(row)

        def surrogate_rows(h, t, m):
            for cas, _lo, _hi in R.SURROGATES.get(m, []):
                rec = round(float(rng.uniform(85, 115)), 1)
                add_row(h, t, cas, fnum(rec), "Y", "", "", "%", rtype="SUR", rec=fnum(rec))

        def target_rows(s: Sample, h: dict, t: dict, m: str, fraction: str, values: dict[str, float]):
            k = R.matrix_kind(s.matrix)
            unit = R.UNITS[k]
            comp_reported = {}
            for cas in CAS_BY_METHOD[m]:
                if cas in TOTALS:
                    continue
                mdl, rl = limits(m, cas, k)
                val, det, q = self._report(values.get(cas, 0.0), mdl, rl)
                comp_reported[cas] = float(val) if det == "Y" else 0.0
                reported[(s.code, m, fraction, cas)] = (val, det)
                add_row(h, t, cas, val, det, mdl, rl, unit, q=q)
            for tot in TOTALS:
                if tot in CAS_BY_METHOD[m]:
                    total = sum(comp_reported.get(c, 0.0) for c in COMPONENTS[tot])
                    if tot == "TPH-TOT-C10C40" and total > 0:
                        total *= float(rng.uniform(1.05, 1.4))
                    mdl, rl = limits(m, tot, k)
                    val, det, q = self._report(total, mdl, rl)
                    reported[(s.code, m, fraction, tot)] = (val, det)
                    add_row(h, t, tot, val, det, mdl, rl, unit, q=q)

        def fractions(s: Sample, m: str) -> list[str]:
            if m != "METALS-ICPMS":
                return ["N"]
            if R.matrix_kind(s.matrix) == "W" and s.sample_type not in ("MB", "LCS", "MS", "MSD"):
                return ["T", "D"]
            return ["T"]

        seq = 0
        # normal samples
        for s in normals:
            h = header(s)
            depth = s.top
            for m in s.methods:
                for fr in fractions(s, m):
                    seq += 1
                    if fr == "D":
                        vals = {c: true_vals[(s.code, m, "T", c)] * float(rng.uniform(0.4, 0.9))
                                for c in CAS_BY_METHOD[m]}
                    else:
                        vals = {c: self._true_value(c, kind, s.location, depth) for c in CAS_BY_METHOD[m]
                                if c not in TOTALS}
                    for c, v in vals.items():
                        true_vals[(s.code, m, fr, c)] = v
                    t = test_fields(s, m, fr, seq)
                    target_rows(s, h, t, m, fr, vals)
                    if m in ORGANIC_METHODS:
                        surrogate_rows(h, t, m)

        # field duplicate: close to its parent, same detect status
        h = header(fd)
        for m in fd.methods:
            for fr in fractions(fd, m):
                seq += 1
                vals = {}
                for c in CAS_BY_METHOD[m]:
                    if c in TOTALS:
                        continue
                    pv = true_vals[(fd_parent.code, m, fr, c)]
                    pval, pdet = reported[(fd_parent.code, m, fr, c)]
                    if pdet == "N":
                        vals[c] = 0.0
                        continue
                    v = float(pval) * float(rng.uniform(0.93, 1.07))
                    mdl, _ = limits(m, c, kind)
                    vals[c] = v if sig(v) >= mdl else float(pval)
                if fr == "D":  # keep dissolved <= total for the duplicate too
                    for c in vals:
                        tot_val, tot_det = reported.get((fd.code, m, "T", c), ("", "N"))
                        if tot_det == "Y":
                            vals[c] = min(vals[c], float(tot_val))
                        else:
                            vals[c] = 0.0
                t = test_fields(fd, m, fr, seq)
                target_rows(fd, h, t, m, fr, vals)
                if m in ORGANIC_METHODS:
                    surrogate_rows(h, t, m)

        # field / equipment / trip blanks: clean
        for s in (fb, tb):
            h = header(s)
            for m in s.methods:
                for fr in fractions(s, m):
                    seq += 1
                    t = test_fields(s, m, fr, seq)
                    target_rows(s, h, t, m, fr, {})
                    if m in ORGANIC_METHODS:
                        surrogate_rows(h, t, m)

        # matrix spike and duplicate on the chosen parent
        ms_recs = {}
        for s in (ms, msd):
            h = header(s)
            for m in s.methods:
                seq += 1
                t = test_fields(s, m, "T" if m == "METALS-ICPMS" else "N", seq)
                t["sample_ph"] = ""
                unit = R.UNITS[kind]
                for c in CAS_BY_METHOD[m]:
                    if c in TOTALS:
                        continue
                    mdl, rl = limits(m, c, kind)
                    fr = "T" if m == "METALS-ICPMS" else "N"
                    pval, pdet = reported[(ms_parent.code, m, fr, c)]
                    p = float(pval) if pdet == "Y" else 0.0
                    spike = sig(max(10 * rl, p))
                    if s.sample_type == "MS":
                        rec = float(rng.uniform(88, 112))
                        ms_recs[(m, c)] = rec
                    else:
                        rec = ms_recs[(m, c)] + float(rng.uniform(-4, 4))
                    measured = sig(p + spike * rec / 100)
                    add_row(h, t, c, fnum(measured), "Y", mdl, rl, unit, spike=fnum(spike), rec=f"{rec:.1f}")

        # lab QC: method blank and LCS per lab batch
        for m in METHODS:
            abbr = METHOD_ABBR[m]
            mb = Sample(code=f"MB-{evt}-{abbr}", sample_type="MB", matrix=lab_qc_matrix,
                        lab_id=f"MB{evt}{abbr}", methods=(m,))
            lcs = Sample(code=f"LCS-{evt}-{abbr}", sample_type="LCS", matrix=lab_qc_matrix,
                         lab_id=f"LCS{evt}{abbr}", methods=(m,))
            fr = "T" if m == "METALS-ICPMS" else "N"
            h = header(mb)
            t = test_fields(mb, m, fr, 0)
            target_rows(mb, h, t, m, fr, {})
            if m in ORGANIC_METHODS:
                surrogate_rows(h, t, m)
            h = header(lcs)
            t = test_fields(lcs, m, fr, 0)
            k = R.matrix_kind(lab_qc_matrix)
            for c in CAS_BY_METHOD[m]:
                if c in TOTALS:
                    continue
                mdl, rl = limits(m, c, k)
                spike = sig(10 * rl)
                rec = float(rng.uniform(88, 112))
                add_row(h, t, c, fnum(sig(spike * rec / 100)), "Y", mdl, rl, R.UNITS[k],
                        spike=fnum(spike), rec=f"{rec:.1f}")

        df = pd.DataFrame(rows, columns=EDD_COLUMNS).fillna("").astype(str)
        stem = f"FAL_EDD_{evt}_{kind_code}"
        return EventData(evt=evt, kind_code=kind_code, file_stem=stem, df=df)


# ==================================================================== defect injection
class Ctx:
    """Holds one event's DataFrame while defects are injected into it."""

    def __init__(self, ev: EventData, rng: np.random.Generator):
        self.ev = ev
        self.rng = rng
        self.touched: set[str] = set()

    @property
    def df(self) -> pd.DataFrame:
        return self.ev.df

    def free(self) -> pd.Series:
        df = self.df
        return ~df.sys_sample_code.isin(self.touched) & ~df.parent_sample_code.isin(self.touched)

    def pick(self, mask: pd.Series):
        idx = self.df.index[mask & self.free()]
        if len(idx) == 0:
            return None
        return idx[int(self.rng.integers(0, len(idx)))]

    def pick_sample(self, mask: pd.Series):
        i = self.pick(mask)
        return None if i is None else self.df.at[i, "sys_sample_code"]

    def touch(self, *codes):
        self.touched.update(c for c in codes if c)

    def key(self, rule, sample="", cas="", note=""):
        return {"file": self.ev.file_stem, "rule_id": rule, "sys_sample_code": sample or "",
                "cas_rn": cas or "", "description": note}


def _m(df, **kw) -> pd.Series:
    mask = pd.Series(True, index=df.index)
    for col, val in kw.items():
        if isinstance(val, (list, tuple, set)):
            mask &= df[col].isin(val)
        else:
            mask &= df[col] == val
    return mask


def _trg(df):
    return (df.result_type == "TRG") & ~df.cas_rn.isin(TOTALS)


def _water(df):
    return df.matrix.isin(R.WATER_MATRICES)


def _shift_date(text: str, days: float) -> str:
    return fdate(datetime.strptime(text, DATE_FORMAT) + timedelta(days=days))


def _set_recovery(df, i, rec):
    spike = float(df.at[i, "spike_added"])
    old_rec = float(df.at[i, "percent_recovery"])
    measured = float(df.at[i, "result_value"]) - spike * (old_rec - rec) / 100
    df.at[i, "result_value"] = fnum(sig(max(measured, 0.0)))
    df.at[i, "percent_recovery"] = f"{rec:.1f}"


def _parent_row(df, i):
    r = df.loc[i]
    m = _m(df, sys_sample_code=r.parent_sample_code, method_code=r.method_code,
           fraction=r.fraction, cas_rn=r.cas_rn, result_type="TRG")
    idx = df.index[m]
    return None if len(idx) == 0 else idx[0]


def inj_comp01(c: Ctx):
    i = c.pick(_m(c.df, sample_type="N") & _trg(c.df))
    if i is None:
        return []
    c.df.at[i, "unit"] = ""
    c.touch(c.df.at[i, "sys_sample_code"])
    return [c.key("COMP-01", c.df.at[i, "sys_sample_code"], c.df.at[i, "cas_rn"], "unit left blank")]


def inj_comp02(c: Ctx):
    i = c.pick(_m(c.df, sample_type="N") & _trg(c.df))
    if i is None:
        return []
    c.df.at[i, "detect_flag"] = "P"
    c.touch(c.df.at[i, "sys_sample_code"])
    return [c.key("COMP-02", c.df.at[i, "sys_sample_code"], c.df.at[i, "cas_rn"], "detect_flag 'P' is not a valid code")]


def inj_comp03(c: Ctx):
    i = c.pick(_m(c.df, sample_type="N", detect_flag="Y") & _trg(c.df))
    if i is None:
        return []
    c.df.at[i, "result_value"] = "<" + c.df.at[i, "rl"]
    c.touch(c.df.at[i, "sys_sample_code"])
    return [c.key("COMP-03", c.df.at[i, "sys_sample_code"], c.df.at[i, "cas_rn"], "text '<RL' in a numeric result")]


def inj_comp04(c: Ctx):
    i = c.pick(_m(c.df, sample_type="N") & _trg(c.df))
    if i is None:
        return []
    c.ev.df = pd.concat([c.df, c.df.loc[[i]]], ignore_index=True)
    s, cas = c.df.iloc[-1]["sys_sample_code"], c.df.iloc[-1]["cas_rn"]
    c.touch(s)
    return [c.key("COMP-04", s, cas, "result row repeated")]


def inj_comp05(c: Ctx):
    i = c.pick(_m(c.df, sample_type="N") & _trg(c.df))
    if i is None:
        return []
    c.df.at[i, "unit"] = "mg/kg" if c.df.at[i, "unit"] == "ug/L" else "ug/L"
    c.touch(c.df.at[i, "sys_sample_code"])
    return [c.key("COMP-05", c.df.at[i, "sys_sample_code"], c.df.at[i, "cas_rn"], "unit swapped between water and soil")]


def _normal_not_parent(c: Ctx):
    parents = set(c.df.parent_sample_code)
    return _m(c.df, sample_type="N") & ~c.df.sys_sample_code.isin(parents)


def inj_ref01(c: Ctx):
    s = c.pick_sample(_normal_not_parent(c))
    if s is None:
        return []
    c.df.loc[c.df.sys_sample_code == s, "location_code"] = "MW99"
    c.touch(s)
    return [c.key("REF-01", s, note="location MW99 does not exist")]


def inj_ref02(c: Ctx):
    i = c.pick(_m(c.df, sample_type="N") & _trg(c.df))
    if i is None:
        return []
    bad = c.df.at[i, "cas_rn"] + "9"
    c.df.at[i, "cas_rn"] = bad
    c.touch(c.df.at[i, "sys_sample_code"])
    return [c.key("REF-02", c.df.at[i, "sys_sample_code"], bad, "mistyped CAS number")]


def inj_ref03(c: Ctx):
    s = c.pick_sample(_m(c.df, sample_type="FD"))
    if s is None:
        return []
    c.df.loc[c.df.sys_sample_code == s, "parent_sample_code"] = f"MW11-{c.ev.evt}"
    c.touch(s)
    return [c.key("REF-03", s, note="FD points to a parent that was never sampled")]


def inj_ref04(c: Ctx):
    s = c.pick_sample(_m(c.df, sample_type="MB"))
    if s is None:
        return []
    c.ev.df = c.df[c.df.sys_sample_code != s].reset_index(drop=True)
    c.touch(s)
    return [c.key("REF-04", note=f"method blank {s} missing from EDD")]


def inj_ref05(c: Ctx):
    s = c.pick_sample(_normal_not_parent(c))
    if s is None:
        return []
    rows = c.df.index[c.df.sys_sample_code == s]
    loc = c.df.at[rows[0], "location_code"]
    other = next(l[0] for l in R.LOCATIONS if l[0] != loc)
    c.df.at[rows[len(rows) // 2], "location_code"] = other
    c.touch(s)
    return [c.key("REF-05", s, note="one row carries a different location")]


def _soil_normal(c: Ctx):
    return _normal_not_parent(c) & (c.df.matrix == "SO")


def inj_str01(c: Ctx):
    s = c.pick_sample(_soil_normal(c))
    if s is None:
        return []
    m = c.df.sys_sample_code == s
    top, base = c.df.loc[m, "depth_top_m"].copy(), c.df.loc[m, "depth_base_m"].copy()
    c.df.loc[m, "depth_top_m"], c.df.loc[m, "depth_base_m"] = base, top
    c.touch(s)
    return [c.key("STR-01", s, note="depth top and base swapped")]


def inj_str02(c: Ctx):
    s = c.pick_sample(_soil_normal(c))
    if s is None:
        return []
    m = c.df.sys_sample_code == s
    loc = c.df.loc[m, "location_code"].iloc[0]
    final = LOC_INFO[loc][5]
    c.df.loc[m, "depth_top_m"] = f"{final + 1:.2f}"
    c.df.loc[m, "depth_base_m"] = f"{final + 1.3:.2f}"
    c.touch(s)
    return [c.key("STR-02", s, note=f"depth below final depth {final} m")]


def inj_str03(c: Ctx):
    s = c.pick_sample(_soil_normal(c))
    if s is None:
        return []
    m = c.df.sys_sample_code == s
    c.df.loc[m, ["depth_top_m", "depth_base_m"]] = ""
    c.touch(s)
    return [c.key("STR-03", s, note="soil sample without depths")]


def inj_str04(c: Ctx):
    s = c.pick_sample(_normal_not_parent(c))
    if s is None:
        return []
    m = (c.df.sys_sample_code == s) & (c.df.method_code == "METALS-ICPMS")
    sd = c.df.loc[m, "sample_date"].iloc[0]
    c.df.loc[m, "analysis_date"] = _shift_date(sd, -2)
    c.touch(s)
    return [c.key("STR-04", s, note="metals analysed two days before sampling")]


def inj_str05(c: Ctx):
    s = c.pick_sample(_normal_not_parent(c))
    if s is None:
        return []
    copy = c.df[c.df.sys_sample_code == s].copy()
    copy["sys_sample_code"] = s + "A"
    copy["lab_sample_id"] = copy["lab_sample_id"] + "A"
    c.ev.df = pd.concat([c.df, copy], ignore_index=True)
    c.touch(s, s + "A")
    return [c.key("STR-05", s, note="same location, depth and date sampled under two codes")]


def inj_pres01(c: Ctx):
    m = c.df.cooler_id == "C2"
    if not m.any():
        return []
    c.df.loc[m, "cooler_temp_c"] = "8.5"
    return [c.key("PRES-01", note="cooler C2 received at 8.5 C")]


def inj_pres02(c: Ctx):
    s = c.pick_sample(_normal_not_parent(c) & (c.df.matrix == "WG"))
    if s is None:
        return []
    m = (c.df.sys_sample_code == s) & (c.df.method_code == "METALS-ICPMS")
    c.df.loc[m, "sample_ph"] = "6.8"
    c.touch(s)
    return [c.key("PRES-02", s, note="metals bottle not acidified (pH 6.8)")]


def inj_pres03(c: Ctx):
    m = c.df.cooler_id == "C1"
    if not m.any():
        return []
    c.df.loc[m, "custody_seal_intact"] = "N"
    return [c.key("PRES-03", note="cooler C1 custody seal broken")]


def inj_ht01(c: Ctx):
    s = c.pick_sample(_normal_not_parent(c))
    if s is None:
        return []
    m = (c.df.sys_sample_code == s) & (c.df.method_code == "VOC-HSGCMS")
    sd = c.df.loc[m, "sample_date"].iloc[0]
    c.df.loc[m, "analysis_date"] = _shift_date(sd, 20)
    c.touch(s)
    return [c.key("HT-01", s, note="VOCs analysed 20 days after sampling (limit 14)")]


def inj_ht02(c: Ctx):
    s = c.pick_sample(_normal_not_parent(c))
    if s is None:
        return []
    m = (c.df.sys_sample_code == s) & (c.df.method_code == "PAH-GCMS")
    sd = c.df.loc[m, "sample_date"].iloc[0]
    limit = 7 if c.df.loc[m, "matrix"].iloc[0] != "SO" else 14
    c.df.loc[m, "extraction_date"] = _shift_date(sd, limit + 3)
    c.df.loc[m, "analysis_date"] = _shift_date(sd, limit + 8)
    c.touch(s)
    return [c.key("HT-02", s, note=f"PAH extracted {limit + 3} days after sampling (limit {limit})")]


def inj_det01(c: Ctx):
    i = c.pick(_m(c.df, sample_type="N", detect_flag="Y") & _trg(c.df))
    if i is None:
        return []
    c.df.at[i, "result_value"] = fnum(sig(float(c.df.at[i, "mdl"]) * 0.5))
    c.df.at[i, "lab_qualifier"] = "J"
    c.touch(c.df.at[i, "sys_sample_code"])
    return [c.key("DET-01", c.df.at[i, "sys_sample_code"], c.df.at[i, "cas_rn"], "detect at half the MDL")]


def inj_det02(c: Ctx):
    m = _m(c.df, sample_type="N", detect_flag="Y", lab_qualifier="") & _trg(c.df)
    i = c.pick(m)
    if i is None:
        return []
    mdl, rl = float(c.df.at[i, "mdl"]), float(c.df.at[i, "rl"])
    c.df.at[i, "result_value"] = fnum(sig((mdl + rl) / 2))
    c.touch(c.df.at[i, "sys_sample_code"])
    return [c.key("DET-02", c.df.at[i, "sys_sample_code"], c.df.at[i, "cas_rn"], "value below RL without J flag")]


def inj_det03(c: Ctx):
    i = c.pick(_m(c.df, sample_type="N", detect_flag="N") & _trg(c.df))
    if i is None:
        return []
    c.df.at[i, "result_value"] = fnum(sig(float(c.df.at[i, "rl"]) * 0.5))
    c.touch(c.df.at[i, "sys_sample_code"])
    return [c.key("DET-03", c.df.at[i, "sys_sample_code"], c.df.at[i, "cas_rn"], "non-detect carries half the RL")]


def inj_det04(c: Ctx):
    plume = {"MW03", "MW04", "MW05", "MW07", "MW08", "MW09"}
    s = c.pick_sample(_normal_not_parent(c) & (c.df.matrix == "WG") & ~c.df.location_code.isin(plume))
    if s is None:
        return []
    m = (c.df.sys_sample_code == s) & (c.df.method_code == "VOC-HSGCMS") & (c.df.result_type == "TRG")
    for i in c.df.index[m]:
        mdl, rl = float(c.df.at[i, "mdl"]) * 10, float(c.df.at[i, "rl"]) * 10
        c.df.at[i, "mdl"], c.df.at[i, "rl"] = fnum(sig(mdl)), fnum(sig(rl))
        if c.df.at[i, "detect_flag"] == "Y" and float(c.df.at[i, "result_value"]) < rl:
            c.df.at[i, "result_value"], c.df.at[i, "detect_flag"], c.df.at[i, "lab_qualifier"] = "", "N", ""
    c.df.loc[(c.df.sys_sample_code == s) & (c.df.method_code == "VOC-HSGCMS"), "dilution_factor"] = "10"
    c.touch(s)
    return [c.key("DET-04", s, note="VOCs diluted x10, raised RLs above screening criteria")]


def inj_det05(c: Ctx):
    i = c.pick(_m(c.df, sample_type="N", detect_flag="N") & _trg(c.df))
    if i is None:
        return []
    c.df.at[i, "mdl"], c.df.at[i, "rl"] = c.df.at[i, "rl"], c.df.at[i, "mdl"]
    c.touch(c.df.at[i, "sys_sample_code"])
    return [c.key("DET-05", c.df.at[i, "sys_sample_code"], c.df.at[i, "cas_rn"], "MDL and RL swapped")]


def _blank_hit(c: Ctx, sample_types, prefer_cas, rule, factor, note):
    m = _m(c.df, sample_type=sample_types, result_type="TRG") & c.df.cas_rn.isin(prefer_cas)
    i = c.pick(m)
    if i is None:
        return []
    c.df.at[i, "result_value"] = fnum(sig(float(c.df.at[i, "rl"]) * factor))
    c.df.at[i, "detect_flag"], c.df.at[i, "lab_qualifier"] = "Y", ""
    c.touch(c.df.at[i, "sys_sample_code"])
    return [c.key(rule, c.df.at[i, "sys_sample_code"], c.df.at[i, "cas_rn"], note)]


def inj_blk01(c: Ctx):
    return _blank_hit(c, ["MB"], ["75-09-2", "7440-66-6", "7440-50-8"], "BLK-01", 3, "method blank detect")


def inj_blk02(c: Ctx):
    return _blank_hit(c, ["FB", "EB"], ["7440-66-6", "7440-50-8"], "BLK-02", 5, "field/equipment blank detect")


def inj_blk03(c: Ctx):
    return _blank_hit(c, ["TB"], ["108-88-3", "75-09-2"], "BLK-03", 2, "trip blank detect")


def _surrogate(c: Ctx, rec, note):
    i = c.pick(_m(c.df, sample_type="N", result_type="SUR"))
    if i is None:
        return []
    c.df.at[i, "result_value"] = c.df.at[i, "percent_recovery"] = f"{rec:.1f}"
    c.touch(c.df.at[i, "sys_sample_code"])
    return [c.key("SUR-01", c.df.at[i, "sys_sample_code"], c.df.at[i, "cas_rn"], note)]


def inj_sur_low(c: Ctx):
    return _surrogate(c, 52.0, "surrogate recovery 52%")


def inj_sur_high(c: Ctx):
    return _surrogate(c, 148.0, "surrogate recovery 148%")


def _ms_pair(c: Ctx, parent_detect: str | None):
    m = _m(c.df, sample_type="MS")
    cand = []
    for i in c.df.index[m & c.free()]:
        p = _parent_row(c.df, i)
        if p is None:
            continue
        if parent_detect is None or c.df.at[p, "detect_flag"] == parent_detect:
            cand.append((i, p))
    if not cand:
        return None
    i, p = cand[int(c.rng.integers(0, len(cand)))]
    r = c.df.loc[i]
    j = c.df.index[_m(c.df, sample_type="MSD", parent_sample_code=r.parent_sample_code,
                      method_code=r.method_code, cas_rn=r.cas_rn)]
    if len(j) == 0:
        return None
    return i, j[0], p


def inj_ms01(c: Ctx):
    pair = _ms_pair(c, None)
    if pair is None:
        return []
    i, j, p = pair
    _set_recovery(c.df, i, 45.0)
    _set_recovery(c.df, j, 48.0)
    c.touch(c.df.at[i, "sys_sample_code"], c.df.at[j, "sys_sample_code"], c.df.at[p, "sys_sample_code"])
    return [c.key("MS-01", c.df.at[i, "sys_sample_code"], c.df.at[i, "cas_rn"], "MS/MSD recovery 45/48%")]


def inj_ms02(c: Ctx):
    pair = _ms_pair(c, "N")
    if pair is None:
        return []
    i, j, p = pair
    _set_recovery(c.df, i, 75.0)
    _set_recovery(c.df, j, 125.0)
    c.touch(c.df.at[i, "sys_sample_code"], c.df.at[j, "sys_sample_code"], c.df.at[p, "sys_sample_code"])
    return [c.key("MS-02", c.df.at[j, "sys_sample_code"], c.df.at[j, "cas_rn"], "MS 75% vs MSD 125%")]


def inj_ms03(c: Ctx):
    pair = _ms_pair(c, "Y")
    if pair is None:
        return []
    i, j, p = pair
    pv = float(c.df.at[p, "result_value"])
    spike = sig(pv / 10)
    for k in (i, j):
        rec = float(c.df.at[k, "percent_recovery"])
        c.df.at[k, "spike_added"] = fnum(spike)
        c.df.at[k, "result_value"] = fnum(sig(pv + spike * rec / 100))
    c.touch(c.df.at[i, "sys_sample_code"], c.df.at[j, "sys_sample_code"], c.df.at[p, "sys_sample_code"])
    return [c.key("MS-03", c.df.at[i, "sys_sample_code"], c.df.at[i, "cas_rn"], "spike only 10% of parent result")]


def inj_lcs01(c: Ctx):
    i = c.pick(_m(c.df, sample_type="LCS"))
    if i is None:
        return []
    _set_recovery(c.df, i, 65.0)
    c.touch(c.df.at[i, "sys_sample_code"])
    return [c.key("LCS-01", c.df.at[i, "sys_sample_code"], c.df.at[i, "cas_rn"], "LCS recovery 65%")]


def inj_fd01(c: Ctx):
    cand = []
    for i in c.df.index[_m(c.df, sample_type="FD", detect_flag="Y") & _trg(c.df) & c.free()]:
        p = _parent_row(c.df, i)
        if p is not None and c.df.at[p, "detect_flag"] == "Y" \
                and float(c.df.at[p, "result_value"]) > 5 * float(c.df.at[p, "rl"]) \
                and c.df.at[i, "fraction"] != "D":
            cand.append((i, p))
    if not cand:
        return []
    i, p = cand[int(c.rng.integers(0, len(cand)))]
    c.df.at[i, "result_value"] = fnum(sig(float(c.df.at[p, "result_value"]) * 2.5))
    c.touch(c.df.at[i, "sys_sample_code"], c.df.at[p, "sys_sample_code"])
    return [c.key("FD-01", c.df.at[i, "sys_sample_code"], c.df.at[i, "cas_rn"], "duplicate 2.5x parent")]


def inj_plb01(c: Ctx):
    m = _m(c.df, sample_type="N", fraction="T", detect_flag="Y", method_code="METALS-ICPMS") & _water(c.df)
    i = c.pick(m)
    if i is None:
        return []
    r = c.df.loc[i]
    d = c.df.index[_m(c.df, sys_sample_code=r.sys_sample_code, fraction="D", cas_rn=r.cas_rn)]
    if len(d) == 0:
        return []
    c.df.at[d[0], "result_value"] = fnum(sig(float(r.result_value) * 1.5))
    c.df.at[d[0], "detect_flag"], c.df.at[d[0], "lab_qualifier"] = "Y", ""
    c.touch(r.sys_sample_code)
    return [c.key("PLB-01", r.sys_sample_code, r.cas_rn, "dissolved 1.5x total")]


def inj_plb02(c: Ctx):
    i = c.pick(_m(c.df, sample_type="N", detect_flag="Y") & c.df.cas_rn.isin(TOTALS)
               & (c.df.result_type == "TRG"))
    if i is None:
        return []
    val = float(c.df.at[i, "result_value"])
    rl = float(c.df.at[i, "rl"])
    if val / 2 < rl:
        return []
    c.df.at[i, "result_value"] = fnum(sig(val / 2))
    c.touch(c.df.at[i, "sys_sample_code"])
    return [c.key("PLB-02", c.df.at[i, "sys_sample_code"], c.df.at[i, "cas_rn"], "total halved below sum of components")]


DEFECTS = [
    inj_comp01, inj_comp02, inj_comp03, inj_comp04, inj_comp05,
    inj_ref01, inj_ref02, inj_ref03, inj_ref04, inj_ref05,
    inj_str01, inj_str02, inj_str03, inj_str04, inj_str05,
    inj_pres01, inj_pres02, inj_pres03,
    inj_ht01, inj_ht02,
    inj_det01, inj_det02, inj_det03, inj_det04, inj_det05,
    inj_blk01, inj_blk02, inj_blk03,
    inj_sur_low, inj_sur_high,
    inj_ms01, inj_ms02, inj_ms03, inj_lcs01,
    inj_fd01, inj_plb01, inj_plb02,
]


# ==================================================================== orchestration
def build_events(seed: int = 42, clean: bool = False, n_events: int | None = None,
                 extra_defects: int = 3) -> list[EventData]:
    sim = Simulator(seed)
    events = [sim.build_event(e, k, d) for e, k, d in EVENTS[: n_events or len(EVENTS)]]
    if clean:
        return events
    rng = np.random.default_rng(seed + 1)
    ctxs = [Ctx(ev, rng) for ev in events]
    order = list(DEFECTS)
    rng.shuffle(order)
    # every defect type lands in at least one file
    for k, inj in enumerate(order):
        for step in range(len(ctxs)):
            ctx = ctxs[(k + step) % len(ctxs)]
            keys = inj(ctx)
            if keys:
                ctx.ev.keys.extend(keys)
                break
    # plus a few random extras per file
    for ctx in ctxs:
        for inj in rng.choice(DEFECTS, extra_defects, replace=False):
            if inj in (inj_pres01, inj_pres03):
                continue
            ctx.ev.keys.extend(inj(ctx))
    return events


def write_events(events: list[EventData], out_dir: Path, key_dir: Path | None,
                 excel_kinds: tuple = ("SO",)) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for ev in events:
        if ev.kind_code in excel_kinds:
            path = out_dir / f"{ev.file_stem}.xlsx"
            ev.df.to_excel(path, index=False, sheet_name="EDD")
        else:
            path = out_dir / f"{ev.file_stem}.csv"
            ev.df.to_csv(path, index=False)
        paths.append(path)
        if key_dir is not None:
            key_dir.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(ev.keys, columns=["file", "rule_id", "sys_sample_code", "cas_rn", "description"]) \
                .to_csv(key_dir / f"{ev.file_stem}_answer_key.csv", index=False)
    return paths
