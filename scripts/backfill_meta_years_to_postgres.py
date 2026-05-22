from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ga_reporter.database import ensure_schema, resolve_postgres_config, upsert_meta_captured_records
from ga_reporter.meta_capture import expand_debug_text_to_daily_records, load_meta_capture_targets


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill Meta Business Suite history year by year into PostgreSQL."
    )
    parser.add_argument("--config", default="config/meta_capture_targets.json")
    parser.add_argument("--browser-channel", default="msedge", choices=["chrome", "msedge", "chromium"])
    parser.add_argument("--use-system-profile", action="store_true")
    parser.add_argument("--terminate-existing-browser", action="store_true")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--year-start", type=int, required=True)
    parser.add_argument("--year-end", type=int, required=True)
    parser.add_argument("--target", action="append", default=[])
    parser.add_argument("--debug-dump-dir", default="debug/meta_capture")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.year_end < args.year_start:
        raise SystemExit("--year-end must be on or after --year-start.")

    try:
        import streamlit as st

        secrets = st.secrets
    except Exception:
        secrets = {}

    postgres_config, postgres_source = resolve_postgres_config(secrets)
    if not postgres_config:
        raise SystemExit("Postgres config not found. Configure .streamlit/secrets.toml or PG* env vars.")

    ensure_schema(postgres_config)
    targets = load_meta_capture_targets(str(ROOT / args.config))
    if args.target:
        requested = {value.strip().lower() for value in args.target if value.strip()}
        targets = [target for target in targets if target.profile_name.lower() in requested]
    if not targets:
        raise SystemExit("No Meta capture targets matched the requested filters.")

    imported_records = 0
    for target in targets:
        for year in range(args.year_start, args.year_end + 1):
            start_date = date(year, 1, 1)
            end_date = date(year, 12, 31)
            if end_date > date.today():
                end_date = date.today()
            if start_date > end_date:
                continue
            dump_path = ROOT / args.debug_dump_dir / _dump_filename(target.profile_name, year)
            run_args = [
                str(ROOT / "scripts" / "capture_meta_business_suite.py"),
                "--config",
                args.config,
                "--browser-channel",
                args.browser_channel,
                "--target",
                target.profile_name,
                "--start-date",
                start_date.isoformat(),
                "--end-date",
                end_date.isoformat(),
                "--debug-dump-dir",
                args.debug_dump_dir,
            ]
            if args.use_system_profile:
                run_args.append("--use-system-profile")
            if args.terminate_existing_browser:
                run_args.append("--terminate-existing-browser")
            if args.headless:
                run_args.append("--headless")

            _run_python(run_args)

            if not dump_path.exists():
                print(f"Warning: no debug dump found for {target.profile_name} {year}.")
                continue

            page_text = dump_path.read_text(encoding="utf-8")
            records = expand_debug_text_to_daily_records(target=target, page_text=page_text)
            if not records:
                print(f"Warning: no daily records parsed for {target.profile_name} {year}.")
                continue

            imported_records += upsert_meta_captured_records(postgres_config, records)
            print(f"Imported {len(records)} rows for {target.profile_name} {year} using {postgres_source}.")

    print(f"Backfill complete. Imported or updated {imported_records} daily rows.")
    return 0


def _run_python(args: list[str]) -> None:
    import subprocess

    subprocess.run([sys.executable, *args], check=True, cwd=str(ROOT))


def _dump_filename(profile_name: str, year: int) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in profile_name)
    cleaned = cleaned.strip("_") or "capture"
    return f"{cleaned}_{year}.txt"


if __name__ == "__main__":
    raise SystemExit(main())
