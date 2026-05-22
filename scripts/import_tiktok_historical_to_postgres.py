from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
import tomllib


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ga_reporter.database import ensure_schema, resolve_postgres_config, upsert_tiktok_daily_metrics
from ga_reporter.tiktok_capture import load_tiktok_capture_targets


COLUMN_ALIASES = {
    "week": "week",
    "month": "month",
    "date": "metric_date",
    "gross revenue": "gross_revenue",
    "gmv": "gross_revenue",
    "items sold": "items_sold",
    "page views": "page_views",
    "visitors": "visitors",
    "conversion rate": "conversion_rate",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import TikTok historical spreadsheet data into PostgreSQL.")
    parser.add_argument(
        "--input",
        default=str(ROOT / "TiktokWeeklyUpsert.xlsx"),
        help="Path to TikTok historical CSV/XLSX file.",
    )
    parser.add_argument(
        "--config",
        default=str(ROOT / "config" / "tiktok_targets.json"),
        help="Path to TikTok target config JSON.",
    )
    parser.add_argument(
        "--target",
        default="",
        help="Optional TikTok profile_name to import into. Defaults to the first configured target.",
    )
    return parser


def _load_local_streamlit_secrets() -> dict[str, object]:
    secrets_path = ROOT / ".streamlit" / "secrets.toml"
    if not secrets_path.exists():
        return {}
    try:
        return tomllib.loads(secrets_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _read_input(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xlsm", ".xls"}:
        return pd.read_excel(path)
    if suffix == ".csv":
        return pd.read_csv(path)
    raise ValueError(f"Unsupported file type: {path.suffix}")


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    rename_map: dict[str, str] = {}
    for column in df.columns:
        key = str(column).strip().lower()
        if key in COLUMN_ALIASES:
            rename_map[column] = COLUMN_ALIASES[key]
    return df.rename(columns=rename_map)


def _coerce_number(value) -> float:
    if pd.isna(value):
        return 0.0
    if isinstance(value, str):
        cleaned = value.replace(",", "").replace("₱", "").replace("%", "").strip()
        if cleaned in {"", "-", "--"}:
            return 0.0
        return float(cleaned)
    return float(value)


def build_daily_rows(df: pd.DataFrame) -> list[dict[str, object]]:
    normalized = _normalize_columns(df)
    required = {"metric_date", "gross_revenue", "items_sold", "page_views", "visitors", "conversion_rate"}
    missing = required - set(normalized.columns)
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(sorted(missing))}")

    rows: list[dict[str, object]] = []
    for _, row in normalized.iterrows():
        metric_date = row.get("metric_date")
        if pd.isna(metric_date):
            continue

        gross_revenue = _coerce_number(row.get("gross_revenue"))
        items_sold = _coerce_number(row.get("items_sold"))
        page_views = _coerce_number(row.get("page_views"))
        visitors = _coerce_number(row.get("visitors"))
        conversion_rate = _coerce_number(row.get("conversion_rate"))

        # Skip separator/header-like rows that only carry week or month labels.
        if gross_revenue == items_sold == page_views == visitors == conversion_rate == 0.0:
            continue

        metric_date_ts = pd.Timestamp(metric_date)
        week_label = str(row.get("week", "") or "").strip()
        month_value = row.get("month", "")
        month_label = ""
        if pd.notna(month_value) and str(month_value).strip():
            month_label = pd.Timestamp(month_value).strftime("%B %Y")

        notes_parts = ["Imported from TikTok historical spreadsheet."]
        if week_label:
            notes_parts.append(f"Week: {week_label}")
        if month_label:
            notes_parts.append(f"Month: {month_label}")

        rows.append(
            {
                "metric_date": metric_date_ts.date().isoformat(),
                "gross_revenue": gross_revenue,
                "items_sold": items_sold,
                "page_views": page_views,
                "visitors": visitors,
                "conversion_rate": conversion_rate,
                "visible_date_range": metric_date_ts.strftime("%b %d, %Y"),
                "notes": " ".join(notes_parts),
            }
        )
    return rows


def main() -> int:
    args = build_parser().parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        raise SystemExit(f"Input file not found: {input_path}")

    targets = load_tiktok_capture_targets(args.config)
    if not targets:
        raise SystemExit(f"No TikTok targets found in {args.config}")

    target = next((item for item in targets if item.profile_name == args.target), targets[0])

    postgres_config, source = resolve_postgres_config(_load_local_streamlit_secrets())
    if not postgres_config:
        raise SystemExit(f"PostgreSQL is not configured ({source}).")

    ensure_schema(postgres_config)
    df = _read_input(input_path)
    daily_rows = build_daily_rows(df)
    inserted = upsert_tiktok_daily_metrics(
        postgres_config,
        profile_name=target.profile_name,
        external_id=target.external_id,
        daily_rows=daily_rows,
        capture_source="tiktok_manual_historical_import",
        notes=f"{target.notes} Imported from historical spreadsheet.",
    )
    print(
        f"Imported {inserted} TikTok historical row(s) into PostgreSQL for "
        f"{target.profile_name} from {input_path.name}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
