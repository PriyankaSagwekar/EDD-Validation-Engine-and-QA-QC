"""Read a lab EDD (CSV or Excel), normalise its headers and load it to staging."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from .edd_schema import ALIASES, EDD_COLUMNS, REQUIRED_COLUMNS


class EDDFormatError(ValueError):
    """The file cannot be loaded at all (wrong layout)."""


class DuplicateFileError(ValueError):
    def __init__(self, path: Path, batch_id: int):
        super().__init__(f"{path.name} was already loaded as batch {batch_id}")
        self.batch_id = batch_id


def _norm(col: str) -> str:
    c = re.sub(r"[^0-9a-z]+", "_", str(col).strip().lower()).strip("_")
    return ALIASES.get(c, c)


def read_ags(path: Path) -> pd.DataFrame:
    """An AGS file as EDD rows. Files that fail the AGS checks are rejected before load. Files from
    AGS 4.0 and 4.1 are accepted with a version warning (the dashboard viewer accepts 4.2 only)."""
    from .ags import ags_to_edd, check_text, errors
    groups, issues = check_text(path.read_bytes().decode("utf-8", errors="replace"))
    if errors(issues):
        listed = "; ".join(str(i) for i in errors(issues)[:5])
        raise EDDFormatError(f"{path.name} fails {len(errors(issues))} AGS check(s): {listed}")
    try:
        return ags_to_edd(groups)
    except ValueError as e:
        raise EDDFormatError(f"{path.name}: {e}") from e


def read_edd(path: Path) -> tuple[pd.DataFrame, list[str]]:
    """Return the EDD as text columns in canonical order, plus a list of ignored columns."""
    suffix = path.suffix.lower()
    if suffix == ".ags":
        df = read_ags(path)
        rows = df.pop("source_row_no").astype(int)
        df = df.astype(str).apply(lambda s: s.str.strip())
        df.insert(0, "source_row_no", rows)               # line of the ELRG row in the AGS file
        return df.reset_index(drop=True), []
    if suffix == ".csv":
        df = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    elif suffix in (".xlsx", ".xls"):
        df = pd.read_excel(path, dtype=str, keep_default_na=False)
    else:
        raise EDDFormatError(f"Unsupported file type {suffix}; expected .csv, .xlsx or .ags")
    df.columns = [_norm(c) for c in df.columns]
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise EDDFormatError(f"{path.name} is missing required columns: {', '.join(missing)}")
    ignored = [c for c in df.columns if c not in EDD_COLUMNS]
    for c in EDD_COLUMNS:
        if c not in df.columns:
            df[c] = ""
    df = df[EDD_COLUMNS].fillna("").astype(str)
    df = df.apply(lambda s: s.str.strip())
    df = df[(df != "").any(axis=1)]                     # drop fully blank lines
    df.insert(0, "source_row_no", df.index + 2)          # line number in the file (header = 1)
    return df.reset_index(drop=True), ignored


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_file(engine: Engine, path: Path) -> int:
    """Load one EDD into stg_Batch / stg_Result. Returns the new batch_id."""
    path = Path(path)
    digest = file_hash(path)
    with engine.connect() as conn:
        existing = conn.execute(text("SELECT batch_id FROM dbo.stg_Batch WHERE file_hash = :h"),
                                {"h": digest}).scalar()
    if existing is not None:
        raise DuplicateFileError(path, existing)

    df, _ignored = read_edd(path)
    lab_codes = df.lab_code[df.lab_code != ""]
    lab = lab_codes.mode().iloc[0] if len(lab_codes) else None
    staged = df.astype(object).where(df != "", None)

    with engine.begin() as conn:
        batch_id = conn.execute(text(
            "INSERT INTO dbo.stg_Batch (file_name, file_hash, lab_code, row_count) OUTPUT INSERTED.batch_id "
            "VALUES (:f, :h, :l, :n)"), {"f": path.name, "h": digest, "l": lab, "n": len(df)}).scalar()
        staged.insert(0, "batch_id", batch_id)
        staged.to_sql("stg_Result", conn, schema="dbo", if_exists="append", index=False, chunksize=1000)
    return int(batch_id)
