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
