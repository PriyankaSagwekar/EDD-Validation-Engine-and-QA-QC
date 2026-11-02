"""End-to-end test against SQL Server, in a throwaway database (EnvDataQC_Test).

Skipped automatically when SQL Server is not reachable.
"""
import os

import pyodbc
import pytest

from eddqc import db
from eddqc.config import load_settings
from eddqc.engine import promote_batch, validate_batch
from eddqc.loader import DuplicateFileError, load_file
from eddqc.report import build_report
from eddqc.simulate import build_events, write_events

TEST_DB = "EnvDataQC_Test"


@pytest.fixture(scope="module")
def settings():
    os.environ["EDDQC_DATABASE"] = TEST_DB
    s = load_settings()
    try:
        pyodbc.connect(s.odbc_string("master"), timeout=3).close()
    except pyodbc.Error:
        pytest.skip("SQL Server not reachable")
    db.init_db(s, reset=True)
    yield s
    db.drop_database(s)
    os.environ.pop("EDDQC_DATABASE", None)


def test_load_validate_promote(settings, tmp_path):
    engine = db.get_engine(settings)
    events = build_events(seed=11, n_events=2)
    paths = write_events(events, tmp_path / "in", tmp_path / "keys")

    for ev, path in zip(events, paths):
        batch_id = load_file(engine, path)
        with pytest.raises(DuplicateFileError):
            load_file(engine, path)

        res = validate_batch(engine, batch_id)
        exc = db.read_sql(engine, "SELECT rule_id, sys_sample_code, cas_rn FROM dbo.qc_Exception "
                                  "WHERE batch_id = :b", b=batch_id)
        for k in ev.keys:
            m = exc.rule_id == k["rule_id"]
            if k["sys_sample_code"]:
                m &= exc.sys_sample_code == k["sys_sample_code"]
            if k["cas_rn"]:
                m &= exc.cas_rn == k["cas_rn"]
            assert m.any(), k

        report = build_report(engine, batch_id, tmp_path / "reports")
        assert report.exists()

        out = promote_batch(engine, batch_id)
        assert out["rows_held"] == res.counts["held"]
        assert out["rows_promoted"] == res.counts["rows"] - res.counts["held"]

    check = db.read_sql(engine, """
        SELECT (SELECT COUNT(*) FROM dbo.dt_Result) AS master,
               (SELECT SUM(rows_promoted) FROM dbo.stg_Batch) AS promoted,
               (SELECT COUNT(*) FROM dbo.dt_Result r JOIN dbo.stg_Result s
                  ON s.batch_id = r.batch_id AND s.source_row_no = r.source_row_no
                WHERE ISNULL(r.validator_qualifier, '') <> ISNULL(s.validator_qualifier, '')) AS mismatches
    """).iloc[0]
    assert check.master == check.promoted
    assert check.mismatches == 0


def test_reporting_views_and_gis_package(settings, tmp_path):
    """Runs after test_load_validate_promote, on the batches it loaded."""
    import geopandas as gpd
    import pyogrio

    from eddqc.gis_export import PACKAGE_ITEMS, export_package

    engine = db.get_engine(settings)
    q = lambda sql: db.read_sql(engine, sql)
    summary = q("SELECT * FROM dbo.vw_Batch_Summary")
    assert len(summary) == 2

    held = q("SELECT COUNT(*) AS n FROM dbo.stg_Result WHERE qc_status = 'HELD'").n.iloc[0]
    assert summary.rows_held.sum() == held
    assert len(q("SELECT * FROM dbo.vw_Held_Rows")) == held
    assert (summary.rows_passed + summary.rows_qualified + summary.rows_held == summary.row_count).all()
    n_exc = q("SELECT COUNT(*) AS n FROM dbo.qc_Exception").n.iloc[0]
    assert summary.n_exceptions.sum() == n_exc
    assert len(q("SELECT * FROM dbo.vw_Exception_Detail")) == n_exc

    quals = q("SELECT SUM(n_results) AS n FROM dbo.vw_Qualifier_Summary").n.iloc[0]
    assert quals == q("SELECT COUNT(*) AS n FROM dbo.dt_Result").n.iloc[0]

    ts = q("SELECT * FROM dbo.vw_Result_Timeseries")
    nd = ts[ts.detect_flag == "N"]
    assert len(nd) and (nd.plot_value == nd.rl).all()
    assert set(ts.point_class) <= {"Detect", "Non-detect", "Qualified"}

    scr = q("SELECT * FROM dbo.vw_Screening_Exceedance")
    det = scr[scr.detect_flag == "Y"]
    assert ((det.result_value > det.criterion_value) == (det.screening_class == "Exceeds")).all()
    nds = scr[scr.detect_flag == "N"]
    assert ((nds.rl > nds.criterion_value) == (nds.screening_class == "ND inconclusive")).all()
    assert len(q("SELECT * FROM dbo.vw_Screening_Location")) == 15

    from eddqc.screening import CLASS_ORDER, build_screening_report
    import pandas as pd
    for crit_set in ("DWS", "EQS-FW"):
        path = build_screening_report(engine, crit_set, tmp_path / "reports")
        meta = pd.read_excel(path, sheet_name="Summary", header=None, nrows=12).dropna(subset=[0])
        counts = dict(zip(meta[0], meta[1]))
        expected = scr[scr.criterion_set == crit_set].screening_class.value_counts()
        assert all(counts[c] == expected.get(c, 0) for c in CLASS_ORDER)
    with pytest.raises(ValueError):
        build_screening_report(engine, "NOPE", tmp_path / "reports")

    from eddqc.ags.export import export_from_db
    ags_path, ags_issues = export_from_db(engine, tmp_path / "ags", include_lab_qc=True)
    assert not ags_issues
    promoted = q("SELECT COUNT(*) AS n FROM dbo.dt_Result").n.iloc[0]
    ags_batch = load_file(engine, ags_path)
    staged = q(f"SELECT source_row_no FROM dbo.stg_Result WHERE batch_id = {ags_batch}")
    assert len(staged) == promoted and staged.source_row_no.min() > 20   # AGS line numbers
    reval = validate_batch(engine, ags_batch)
    assert reval.counts["critical"] == 0 and reval.counts["held"] == 0
    with pytest.raises(DuplicateFileError):
        load_file(engine, ags_path)

    gpkg = export_package(engine, tmp_path / "gis")
    layers = dict(pyogrio.list_layers(gpkg))
    assert set(layers) == set(PACKAGE_ITEMS)
    for layer, (sql, is_points) in PACKAGE_ITEMS.items():
        assert len(pyogrio.read_dataframe(gpkg, layer=layer)) == len(q(sql))
        if is_points:
            assert gpd.read_file(gpkg, layer=layer).crs.to_epsg() == 27700
