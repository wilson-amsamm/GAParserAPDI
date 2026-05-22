from __future__ import annotations

import argparse
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ga_reporter.browser_profiles import prepare_browser_profile_dir
from ga_reporter.database import ensure_schema, resolve_postgres_config, upsert_tiktok_daily_metrics
from ga_reporter.tiktok_capture import (
    detect_tiktok_auth_issue,
    extract_visible_date_range,
    load_captured_records,
    load_tiktok_capture_targets,
    make_captured_record,
    parse_visible_date_range_bounds,
    save_captured_records,
    upsert_captured_record,
    validate_tiktok_shop_context,
    visible_date_range_is_single_day,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manual-assisted TikTok Shop daily recapture into PostgreSQL."
    )
    parser.add_argument(
        "--config",
        default=str(ROOT / "config" / "tiktok_targets.json"),
        help="Path to TikTok capture target config JSON.",
    )
    parser.add_argument(
        "--data-path",
        default=str(ROOT / "data" / "tiktok_shop_records.json"),
        help="Path to captured TikTok JSON data file.",
    )
    parser.add_argument(
        "--profile-dir",
        default=str(ROOT / ".playwright" / "tiktok-seller-profile"),
        help="Persistent browser profile directory.",
    )
    parser.add_argument(
        "--browser-channel",
        default="msedge",
        choices=["msedge", "chrome", "chromium"],
        help="Browser channel to use.",
    )
    parser.add_argument(
        "--target",
        default="",
        help="Optional profile_name to recapture only one target.",
    )
    parser.add_argument(
        "--start-date",
        required=True,
        help="Start date in YYYY-MM-DD.",
    )
    parser.add_argument(
        "--end-date",
        required=True,
        help="End date in YYYY-MM-DD.",
    )
    parser.add_argument(
        "--debug-dir",
        default=str(ROOT / "debug" / "tiktok_capture"),
        help="Directory for debug artifacts.",
    )
    parser.add_argument(
        "--use-system-profile",
        action="store_true",
        help="Use the installed browser's real user-data directory instead of the Playwright profile.",
    )
    parser.add_argument(
        "--pause-on-login",
        action="store_true",
        help="Pause after the page opens so you can log in manually.",
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


def main() -> int:
    args = build_parser().parse_args()
    start_date = _parse_iso_date(args.start_date)
    end_date = _parse_iso_date(args.end_date)
    if end_date < start_date:
        raise ValueError("--end-date must be on or after --start-date.")

    targets = load_tiktok_capture_targets(args.config)
    if args.target:
        targets = [target for target in targets if target.profile_name == args.target]
    if not targets:
        print("No TikTok targets matched the request.")
        return 1

    postgres_config, postgres_source = resolve_postgres_config(_load_local_streamlit_secrets())
    if not postgres_config:
        print(f"PostgreSQL is not configured ({postgres_source}).")
        return 1
    ensure_schema(postgres_config)

    existing_records = load_captured_records(args.data_path)
    profile_dir = prepare_browser_profile_dir(
        configured_profile_dir=Path(args.profile_dir),
        browser_channel=args.browser_channel,
        use_system_profile=args.use_system_profile,
        snapshot_root=ROOT / ".playwright" / "system-profile-snapshots",
        snapshot_prefix="tiktok_manual_recapture",
    )
    debug_dir = Path(args.debug_dir)
    debug_dir.mkdir(parents=True, exist_ok=True)

    from playwright.sync_api import sync_playwright

    total_upserts = 0
    with sync_playwright() as p:
        browser_launcher = getattr(p, "chromium")
        context = browser_launcher.launch_persistent_context(
            user_data_dir=str(profile_dir),
            channel=None if args.browser_channel == "chromium" else args.browser_channel,
            headless=False,
            viewport={"width": 1440, "height": 980},
        )
        page = context.new_page()

        try:
            for target in targets:
                page.goto(target.overview_url, wait_until="domcontentloaded", timeout=90000)
                page.wait_for_timeout(5000)

                page_text = _page_text(page)
                auth_issue = detect_tiktok_auth_issue(page_text, page.url)
                if args.pause_on_login or auth_issue:
                    if auth_issue:
                        print(
                            f"TikTok auth challenge detected for '{target.profile_name}': {auth_issue}."
                        )
                    input(
                        "Log in if needed, navigate to TikTok Shop analytics, then press Enter to begin manual recapture."
                    )
                    page.wait_for_timeout(2000)

                cursor = start_date
                while cursor <= end_date:
                    print(f"\nTarget day: {cursor.isoformat()}")
                    record = _capture_verified_day(
                        page=page,
                        target=target,
                        target_day=cursor,
                        debug_dir=debug_dir,
                    )
                    existing_records = upsert_captured_record(existing_records, record)
                    inserted = upsert_tiktok_daily_metrics(
                        postgres_config,
                        profile_name=record.profile_name,
                        external_id=target.external_id,
                        daily_rows=[
                            {
                                "metric_date": cursor.isoformat(),
                                "gross_revenue": record.metrics.get("gross_revenue", 0),
                                "items_sold": record.metrics.get("items_sold", 0),
                                "page_views": record.metrics.get("page_views", 0),
                                "visitors": record.metrics.get("visitors", 0),
                                "conversion_rate": record.metrics.get("conversion_rate", 0),
                                "visible_date_range": record.visible_date_range,
                                "notes": f"{target.notes} Manual verified daily recapture.",
                            }
                        ],
                        capture_source="tiktok_seller_manual_verified_recapture",
                        notes=f"{target.notes} Manual verified daily recapture.",
                    )
                    total_upserts += inserted
                    print(f"Upserted {inserted} row(s): {record.metrics}")
                    cursor += timedelta(days=1)
        finally:
            save_captured_records(args.data_path, existing_records)
            context.close()

    print(f"Done. Upserted {total_upserts} manually verified TikTok row(s) into PostgreSQL.")
    return 0


def _capture_verified_day(*, page, target, target_day: date, debug_dir: Path):
    while True:
        page_text = _page_text(page)
        visible_range = extract_visible_date_range(page_text)
        print(
            "Visible page state:"
            f" visible_range={visible_range or 'blank'}"
        )
        input(
            "Manually set the Seller Center page to the exact target day, wait for the cards to refresh, then press Enter."
        )
        page.wait_for_timeout(1500)
        page_text = _page_text(page)
        _write_day_debug_artifacts(debug_dir, target.profile_name, target_day, page_text, page)

        auth_issue = detect_tiktok_auth_issue(page_text, page.url)
        validation_issue = validate_tiktok_shop_context(target, page_text, page.url)
        if auth_issue:
            print(f"Still blocked by auth: {auth_issue}")
            continue
        if validation_issue:
            print(f"Page still not valid: {validation_issue}")
            continue

        record = make_captured_record(target, page_text, captured_at=datetime.now(UTC))
        if not record.metrics:
            print("No metrics were parsed from the current page. Try refreshing the cards and press Enter again.")
            continue
        if not record.visible_date_range or not visible_date_range_is_single_day(record.visible_date_range):
            print(
                "The page is not showing a single-day visible range yet: "
                f"{record.visible_date_range or 'blank'}"
            )
            continue
        bounds = parse_visible_date_range_bounds(record.visible_date_range)
        if not bounds or bounds[0] != target_day:
            print(
                "The on-screen visible range still does not match the target day. "
                f"Expected {target_day.isoformat()}, saw {record.visible_date_range}."
            )
            continue
        return record


def _write_day_debug_artifacts(debug_dir: Path, target_name: str, target_day: date, page_text: str, page) -> None:
    safe_name = "".join(ch if ch.isalnum() else "_" for ch in target_name).strip("_") or "tiktok_target"
    day_key = target_day.isoformat()
    (debug_dir / f"{safe_name}_{day_key}.txt").write_text(page_text, encoding="utf-8")
    page.screenshot(path=str(debug_dir / f"{safe_name}_{day_key}.png"), full_page=True)


def _parse_iso_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _page_text(page) -> str:
    return page.locator("body").inner_text(timeout=30000)


if __name__ == "__main__":
    raise SystemExit(main())
