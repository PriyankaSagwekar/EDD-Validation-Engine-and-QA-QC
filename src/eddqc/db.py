"""Database helpers: SQLAlchemy engine, script runner and database initialisation."""
from __future__ import annotations

import subprocess
import urllib.parse
from pathlib import Path

import pandas as pd
import pyodbc
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from .config import Settings
from . import seed

SCRIPT_ORDER = [
    "01_create_database.sql",
    "02_reference.sql",
    "03_staging.sql",
    "04_master.sql",
    "05_qc.sql",
    "06_seed_reference.sql",
    "07_views.sql",
    "08_sp_promote_batch.sql",
]


def get_engine(settings: Settings) -> Engine:
    params = urllib.parse.quote_plus(settings.odbc_string())
    return create_engine(f"mssql+pyodbc:///?odbc_connect={params}", fast_executemany=True)


def read_sql(engine: Engine, sql: str, **params) -> pd.DataFrame:
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn, params=params)


def database_exists(settings: Settings) -> bool:
    with pyodbc.connect(settings.odbc_string("master"), autocommit=True) as conn:
        row = conn.execute("SELECT DB_ID(?)", settings.database).fetchone()
        return row[0] is not None


def drop_database(settings: Settings) -> None:
    with pyodbc.connect(settings.odbc_string("master"), autocommit=True) as conn:
        conn.execute(
            f"IF DB_ID(N'{settings.database}') IS NOT NULL BEGIN "
            f"ALTER DATABASE [{settings.database}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE; "
            f"DROP DATABASE [{settings.database}]; END"
        )


def run_sql_script(settings: Settings, script: Path, database: str) -> None:
    """Run a .sql file through sqlcmd so GO batch separators work."""
    cmd = ["sqlcmd", "-S", settings.server, "-d", database, "-b", "-I", "-f", "65001",
           "-v", f"DbName={settings.database}", "-i", str(script)]
    if settings.trusted_connection:
        cmd.insert(1, "-E")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"{script.name} failed:\n{result.stdout}\n{result.stderr}")


def init_db(settings: Settings, reset: bool = False) -> list[str]:
    if database_exists(settings):
        if not reset:
            raise RuntimeError(
                f"Database {settings.database} already exists. Use --reset to drop and rebuild it."
            )
        drop_database(settings)
    sql_dir = settings.paths["sql"]
    seed.write_seed_sql(sql_dir / "06_seed_reference.sql")
    ran = []
    for name in SCRIPT_ORDER:
        db = "master" if name.startswith("01_") else settings.database
        run_sql_script(settings, sql_dir / name, db)
        ran.append(name)
    return ran
