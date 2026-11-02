"""Command line: python -m eddqc <command>."""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from .config import load_settings


def _engine(settings):
    from .db import get_engine
    return get_engine(settings)


def _print_counts(prefix: str, c: dict) -> None:
    print(f"{prefix} rows={c['rows']} passed={c['passed']} qualified={c['qualified']} held={c['held']} | "
          f"exceptions={c['exceptions']} (critical={c['critical']}, warning={c['warning']}, info={c['info']})")


def cmd_init_db(args, s):
    from .db import init_db
    ran = init_db(s, reset=args.reset)
    print(f"Database {s.database} built on {s.server}: {', '.join(ran)}")


def cmd_simulate(args, s):
    from .simulate import build_events, write_events
    events = build_events(seed=args.seed, clean=args.clean, n_events=args.events)
    out = Path(args.out) if args.out else s.paths["incoming"]
    keys = None if args.clean else s.paths["answer_keys"]
    paths = write_events(events, out, keys)
    for ev, p in zip(events, paths):
        print(f"{p.name}: {len(ev.df)} rows, {len(ev.keys)} injected defects")
    if keys:
        print(f"Answer keys written to {keys}")


def cmd_load(args, s):
    from .loader import load_file
    batch_id = load_file(_engine(s), Path(args.file))
    print(f"Loaded {args.file} as batch {batch_id}")


def cmd_validate(args, s):
    from .engine import validate_batch
    res = validate_batch(_engine(s), args.batch)
    _print_counts(f"Batch {args.batch} run {res.run_id}:", res.counts)


def cmd_report(args, s):
    from .report import build_report
    path = build_report(_engine(s), args.batch, s.paths["reports"], s.max_held_fraction)
    print(f"Report written to {path}")


def cmd_promote(args, s):
    from .engine import promote_batch
    from .report import batch_counts, decision
    eng = _engine(s)
    verdict, advice = decision(batch_counts(eng, args.batch), s.max_held_fraction)
    if verdict == "NO-GO" and not args.force:
        print(f"Batch {args.batch} is NO-GO: {advice} Use --force to promote anyway.")
        return 1
    r = promote_batch(eng, args.batch)
    print(f"Batch {r['batch_id']}: {r['rows_promoted']} rows promoted, {r['rows_held']} held in staging")


def cmd_run_all(args, s):
    from .engine import promote_batch, reject_batch, validate_batch
    from .gis_export import export_locations, export_package
    from .loader import DuplicateFileError, EDDFormatError, load_file
    from .report import build_report, decision

    eng = _engine(s)
    folder = Path(args.folder) if args.folder else s.paths["incoming"]
    files = sorted(p for p in folder.iterdir() if p.suffix.lower() in (".csv", ".xlsx", ".ags"))
    if not files:
        print(f"No EDD files in {folder}")
        return 0
    for p in files:
        print(f"\n== {p.name}")
        try:
            batch_id = load_file(eng, p)
        except EDDFormatError as e:
            print(f"   rejected before load: {e}")
            shutil.move(p, s.paths["rejected"] / p.name)
            continue
        except DuplicateFileError as e:
            print(f"   skipped: {e}")
            continue
        res = validate_batch(eng, batch_id)
        _print_counts(f"   batch {batch_id}:", res.counts)
        report = build_report(eng, batch_id, s.paths["reports"], s.max_held_fraction)
        verdict, advice = decision(res.counts, s.max_held_fraction)
        print(f"   decision: {verdict}. {advice}")
        print(f"   report: {report.name}")
        if verdict == "NO-GO":
            reject_batch(eng, batch_id)
            dest = s.paths["rejected"]
        else:
            r = promote_batch(eng, batch_id)
            print(f"   promoted {r['rows_promoted']} rows, held {r['rows_held']}")
            dest = s.paths["processed"]
        dest.mkdir(parents=True, exist_ok=True)
        shutil.move(p, dest / p.name)
    csv_path, gj = export_locations(eng, s.paths["gis"])
    gpkg = export_package(eng, s.paths["gis"])
    print(f"\nGIS export: {gj} and {gpkg}")


def cmd_gis_export(args, s):
    from .gis_export import export_locations, export_package
    eng = _engine(s)
    csv_path, gj = export_locations(eng, s.paths["gis"])
    gpkg = export_package(eng, s.paths["gis"])
    print(f"Wrote {csv_path}, {gj} and {gpkg}")


def cmd_screen(args, s):
    from .screening import build_screening_report, criteria_sets
    eng = _engine(s)
    sets = [args.set] if args.set else list(criteria_sets(eng).criterion_set)
    for code in sets:
        print(f"Wrote {build_screening_report(eng, code, s.paths['reports'])}")


def cmd_ags_export(args, s):
    from .ags.export import export_from_db
    out = Path(args.out) if args.out else s.paths["ags"]
    path, issues = export_from_db(_engine(s), out, batch=args.batch, include_lab_qc=args.include_lab_qc)
    print(f"Wrote {path} (AGS 4.2, {len(issues)} checker warning(s))")
    for i in issues:
        print(f"  {i}")


def cmd_ags_check(args, s):
    from .ags import check_text, errors
    from .ags.reference import load_reference
    print(load_reference().summary())
    _, issues = check_text(Path(args.file).read_bytes().decode("utf-8", errors="replace"),
                           strict_version=args.strict)
    for i in issues:
        print(i)
    n = len(errors(issues))
    print(f"{args.file}: {n} error(s), {len(issues) - n} warning(s) or note(s)")
    return 1 if n else 0


def cmd_status(args, s):
    from .db import read_sql
    df = read_sql(_engine(s), "SELECT batch_id, file_name, status, row_count, rows_promoted, rows_held, "
                              "loaded_utc FROM dbo.stg_Batch ORDER BY batch_id")
    print(df.to_string(index=False) if len(df) else "No batches loaded")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="eddqc", description="Environmental EDD QA/QC validation engine")
    sub = p.add_subparsers(dest="command", required=True)

    x = sub.add_parser("init-db", help="create the database, tables, reference data, views and procedures")
    x.add_argument("--reset", action="store_true", help="drop and rebuild the database if it exists")
    x.set_defaults(func=cmd_init_db)

    x = sub.add_parser("simulate", help="generate lab EDDs with injected defects and answer keys")
    x.add_argument("--seed", type=int, default=42)
    x.add_argument("--events", type=int, default=None, help="number of sampling events (max 6)")
    x.add_argument("--clean", action="store_true", help="generate defect-free EDDs")
    x.add_argument("--out", help="output folder (default data/incoming)")
    x.set_defaults(func=cmd_simulate)

    x = sub.add_parser("load", help="load one EDD file into staging")
    x.add_argument("file")
    x.set_defaults(func=cmd_load)

    for name, func, helptext in (("validate", cmd_validate, "run all QA/QC rules on a staged batch"),
                                 ("report", cmd_report, "write the Excel QA/QC Exception Report"),
                                 ("promote", cmd_promote, "move passed and qualified rows to master")):
        x = sub.add_parser(name, help=helptext)
        x.add_argument("--batch", type=int, required=True)
        if name == "promote":
            x.add_argument("--force", action="store_true", help="promote even if the batch is NO-GO")
        x.set_defaults(func=func)

    x = sub.add_parser("run-all", help="load, validate, report and promote every EDD in a folder")
    x.add_argument("folder", nargs="?")
    x.set_defaults(func=cmd_run_all)

    sub.add_parser("gis-export", help="write location QC status (CSV, GeoJSON) and the ArcGIS GeoPackage"
                   ).set_defaults(func=cmd_gis_export)
    x = sub.add_parser("screen", help="write the screening report against UK criteria (illustrative values)")
    x.add_argument("--set", help="criteria set code, e.g. DWS, EQS-FW, GAC-RES (default: all sets)")
    x.set_defaults(func=cmd_screen)

    x = sub.add_parser("ags-export", help="export promoted results as an AGS 4.2 file")
    x.add_argument("--batch", type=int, help="one batch only (default: all promoted data)")
    x.add_argument("--include-lab-qc", action="store_true", help="also export method blanks and LCS")
    x.add_argument("--out", help="output folder (default data/ags)")
    x.set_defaults(func=cmd_ags_export)

    x = sub.add_parser("ags-check", help="check an AGS file against the AGS 4.2 rules and code lists")
    x.add_argument("file")
    x.add_argument("--strict", action="store_true", help="reject files that are not AGS 4.2")
    x.set_defaults(func=cmd_ags_check)

    x = sub.add_parser("ags-import", help="load an AGS file into staging (same as load)")
    x.add_argument("file")
    x.set_defaults(func=cmd_load)

    sub.add_parser("status", help="list loaded batches").set_defaults(func=cmd_status)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = load_settings()
    try:
        return args.func(args, settings) or 0
    except (ValueError, RuntimeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
