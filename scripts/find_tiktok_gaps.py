from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ga_reporter.database import resolve_postgres_config, load_tiktok_daily_metrics


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Find missing TikTok daily dates in PostgreSQL.")
    parser.add_argument("--start-date", required=True, help="Start date in YYYY-MM-DD.")
    parser.add_argument("--end-date", required=True, help="End date in YYYY-MM-DD.")
    parser.add_argument("--profile-name", default="TikTok Shop PH", help="TikTok profile name to inspect.")
    return parser


def _load_local_streamlit_secrets() -> dict[str, object]:
    secrets_path = ROOT / ".streamlit" / "secrets.toml"
    if not secrets_path.exists():
        return {}
    try:
        return tomllib.loads(secrets_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def main() -> int:
    args = build_parser().parse_args()
    start_date = datetime.strptime(args.start_date, "%Y-%m-%d").date()
    end_date = datetime.strptime(args.end_date, "%Y-%m-%d").date()
    if end_date < start_date:
        raise ValueError("--end-date must be on or after --start-date.")

    postgres_config, postgres_source = resolve_postgres_config(_load_local_streamlit_secrets())
    if not postgres_config:
        print(f"PostgreSQL is not configured ({postgres_source}).")
        return 1

    rows = load_tiktok_daily_metrics(
        postgres_config,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
    )
    existing_dates = {
        row["metric_date"]
        for row in rows
        if str(row.get("profile_name", "")).strip() == args.profile_name
    }

    missing: list[date] = []
    cursor = start_date
    while cursor <= end_date:
        if cursor not in existing_dates:
            missing.append(cursor)
        cursor += timedelta(days=1)

    print(f"profile={args.profile_name}")
    print(f"window={start_date.isoformat()}..{end_date.isoformat()}")
    print(f"existing_rows={len(existing_dates)}")
    print(f"missing_rows={len(missing)}")
    for item in missing:
        print(item.isoformat())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
