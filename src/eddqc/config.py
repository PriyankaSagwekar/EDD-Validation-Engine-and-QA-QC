"""Settings loaded from config/settings.toml, with environment overrides."""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    server: str
    database: str
    driver: str
    trusted_connection: bool
    paths: dict[str, Path]
    max_held_fraction: float

    def odbc_string(self, database: str | None = None) -> str:
        db = database or self.database
        auth = "Trusted_Connection=yes;" if self.trusted_connection else ""
        return f"DRIVER={{{self.driver}}};SERVER={self.server};DATABASE={db};{auth}"


def load_settings(path: Path | None = None) -> Settings:
    path = path or PROJECT_ROOT / "config" / "settings.toml"
    with open(path, "rb") as fh:
        cfg = tomllib.load(fh)
    db = cfg["database"]
    paths = {k: (PROJECT_ROOT / v) for k, v in cfg["paths"].items()}
    return Settings(
        server=os.environ.get("EDDQC_SERVER", db["server"]),
        database=os.environ.get("EDDQC_DATABASE", db["database"]),
        driver=db["driver"],
        trusted_connection=db.get("trusted_connection", True),
        paths=paths,
        max_held_fraction=cfg.get("validation", {}).get("max_held_fraction", 0.10),
    )
