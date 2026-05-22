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

from ga_reporter.browser_profiles import prepare_browser_profile_dir
from ga_reporter.database import ensure_schema, resolve_postgres_config, upsert_tiktok_daily_metrics
from ga_reporter.tiktok_capture import (
    detect_tiktok_auth_issue,
    load_tiktok_capture_targets,
    parse_visible_metrics,
    validate_tiktok_shop_context,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Backfill TikTok Shop weekly metrics into PostgreSQL.")
    parser.add_argument(
        "--config",
        default=str(ROOT / "config" / "tiktok_targets.json"),
        help="Path to TikTok capture target config JSON.",
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
        help="Optional profile_name to backfill only one target.",
    )
    parser.add_argument(
        "--start-date",
        default="",
        help="Optional start date in YYYY-MM-DD. Defaults to first full week of last year.",
    )
    parser.add_argument(
        "--end-date",
        default="",
        help="Optional end date in YYYY-MM-DD. Defaults to last completed Sunday.",
    )
    parser.add_argument(
        "--limit-weeks",
        type=int,
        default=0,
        help="Optional limit for the number of weeks to process, useful for testing.",
    )
    parser.add_argument(
        "--debug-dir",
        default=str(ROOT / "debug" / "tiktok_capture"),
        help="Directory for weekly backfill debug artifacts.",
    )
    parser.add_argument(
        "--use-system-profile",
        action="store_true",
        help="Use the installed browser's real user-data directory instead of the Playwright profile.",
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

    targets = load_tiktok_capture_targets(args.config)
    if args.target:
        targets = [target for target in targets if target.profile_name == args.target]
    if not targets:
        print("No TikTok targets matched the request.")
        return 1

    start_date, end_date = _resolve_backfill_window(args.start_date, args.end_date)
    weeks = _generate_week_ranges(start_date, end_date)
    if args.limit_weeks > 0:
        weeks = weeks[: args.limit_weeks]
    if not weeks:
        print("No weekly TikTok ranges to backfill.")
        return 0

    postgres_config, postgres_source = resolve_postgres_config(_load_local_streamlit_secrets())
    if not postgres_config:
        print(f"PostgreSQL is not configured ({postgres_source}).")
        return 1
    ensure_schema(postgres_config)

    from playwright.sync_api import sync_playwright

    debug_dir = Path(args.debug_dir)
    debug_dir.mkdir(parents=True, exist_ok=True)
    profile_dir = prepare_browser_profile_dir(
        configured_profile_dir=Path(args.profile_dir),
        browser_channel=args.browser_channel,
        use_system_profile=args.use_system_profile,
        snapshot_root=ROOT / ".playwright" / "system-profile-snapshots",
        snapshot_prefix="tiktok_weekly_backfill",
    )

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
                print(f"Backfilling TikTok target: {target.profile_name}")
                page.goto(target.overview_url, wait_until="domcontentloaded", timeout=90000)
                page.wait_for_timeout(5000)
                initial_text = _page_text(page)
                auth_issue = detect_tiktok_auth_issue(initial_text, page.url)
                if auth_issue:
                    _write_week_debug_artifacts(debug_dir, target.profile_name, start_date, initial_text, page)
                    raise RuntimeError(
                        f"TikTok session for '{target.profile_name}' is not ready for backfill: {auth_issue}"
                    )
                _ensure_tiktok_metric_cards(page)
                current_text = _page_text(page)
                validation_issue = validate_tiktok_shop_context(target, current_text, page.url)
                if validation_issue:
                    _write_week_debug_artifacts(debug_dir, target.profile_name, start_date, current_text, page)
                    raise RuntimeError(
                        f"TikTok page validation failed for '{target.profile_name}' before backfill: {validation_issue}"
                    )

                for week_start, week_end in weeks:
                    print(f"  Week {week_start.isoformat()} -> {week_end.isoformat()}")
                    before_text = _page_text(page)
                    _open_week_picker(page)
                    _navigate_week_picker_to_month(page, week_start)
                    _select_week_start(page, week_start)
                    _wait_for_week_refresh(page, before_text)
                    _ensure_tiktok_metric_cards(page)

                    page_text = _page_text(page)
                    auth_issue = detect_tiktok_auth_issue(page_text, page.url)
                    validation_issue = validate_tiktok_shop_context(target, page_text, page.url)
                    if auth_issue:
                        _write_week_debug_artifacts(debug_dir, target.profile_name, week_start, page_text, page)
                        raise RuntimeError(
                            f"TikTok session for '{target.profile_name}' drifted during backfill: {auth_issue}"
                        )
                    if validation_issue:
                        _write_week_debug_artifacts(debug_dir, target.profile_name, week_start, page_text, page)
                        raise RuntimeError(
                            f"TikTok page validation failed for '{target.profile_name}' during backfill: {validation_issue}"
                        )
                    metrics = parse_visible_metrics(page_text, target.label_map)
                    if not metrics:
                        _write_week_debug_artifacts(debug_dir, target.profile_name, week_start, page_text, page)
                        raise RuntimeError(
                            f"No TikTok metrics parsed for '{target.profile_name}' in week {week_start.isoformat()}."
                        )

                    visible_date_range = f"{week_start:%b %d, %Y} - {week_end:%b %d, %Y}"
                    inserted = upsert_tiktok_daily_metrics(
                        postgres_config,
                        profile_name=target.profile_name,
                        external_id=target.external_id,
                        daily_rows=[
                            {
                                "metric_date": week_end.isoformat(),
                                "gross_revenue": metrics.get("gross_revenue", 0),
                                "items_sold": metrics.get("items_sold", 0),
                                "page_views": metrics.get("page_views", 0),
                                "visitors": metrics.get("visitors", 0),
                                "conversion_rate": metrics.get("conversion_rate", 0),
                                "visible_date_range": visible_date_range,
                                "notes": f"{target.notes} Weekly backfill snapshot.",
                            }
                        ],
                        capture_source="tiktok_seller_weekly_backfill",
                        notes=f"{target.notes} Weekly backfill snapshot.",
                    )
                    total_upserts += inserted
                    print(f"    Upserted {inserted} row(s): {metrics}")
        finally:
            context.close()

    print(f"Done. Upserted {total_upserts} weekly TikTok row(s) into PostgreSQL.")
    return 0


def _resolve_backfill_window(start_date_raw: str, end_date_raw: str) -> tuple[date, date]:
    today = date.today()
    default_start = date(today.year - 1, 1, 1)
    default_end = today - timedelta(days=1)

    start_candidate = _parse_iso_date(start_date_raw) if start_date_raw else default_start
    end_candidate = _parse_iso_date(end_date_raw) if end_date_raw else default_end

    start = _first_monday_on_or_after(start_candidate)
    end = _last_sunday_on_or_before(end_candidate)
    if end < start:
        raise ValueError("Backfill window is empty after aligning to full weeks.")
    return start, end


def _parse_iso_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _first_monday_on_or_after(value: date) -> date:
    return value + timedelta(days=(7 - value.weekday()) % 7)


def _last_sunday_on_or_before(value: date) -> date:
    return value - timedelta(days=(value.weekday() + 1) % 7)


def _generate_week_ranges(start: date, end: date) -> list[tuple[date, date]]:
    weeks: list[tuple[date, date]] = []
    cursor = start
    while cursor <= end:
        weeks.append((cursor, cursor + timedelta(days=6)))
        cursor += timedelta(days=7)
    return weeks


def _page_text(page) -> str:
    return page.locator("body").inner_text(timeout=15000)


def _ensure_tiktok_metric_cards(page) -> None:
    try:
        page.wait_for_function(
            """
            () => {
                const text = (document.body?.innerText || '').replace(/\\s+/g, ' ');
                return (
                    text.includes('Gross revenue') &&
                    text.includes('Items sold') &&
                    text.includes('Page views') &&
                    text.includes('Visitors') &&
                    text.includes('Conversion rate')
                );
            }
            """,
            timeout=30000,
        )
        page.wait_for_timeout(1500)
    except Exception:
        page.wait_for_timeout(8000)


def _open_week_picker(page) -> None:
    page.locator("div.arco-picker-range").first.click(force=True)
    page.wait_for_timeout(800)
    page.locator("div.m4b-date-picker-range-mode-item", has_text="Week").click(force=True)
    page.wait_for_timeout(800)


def _navigate_week_picker_to_month(page, target_week_start: date) -> None:
    target_label = target_week_start.strftime("%m/%Y")
    header = page.locator("div.arco-picker-container.mode-week div.arco-picker-header-value").first
    prev_month_button = page.locator("div.arco-picker-container.mode-week div.arco-picker-header-icon").nth(1)
    next_month_button = page.locator("div.arco-picker-container.mode-week div.arco-picker-header-icon").nth(2)

    for _ in range(36):
        current_label = header.inner_text(timeout=5000).strip()
        if current_label == target_label:
            return
        if _month_year_key(current_label) > _month_year_key(target_label):
            prev_month_button.click(force=True)
        else:
            next_month_button.click(force=True)
        page.wait_for_timeout(300)
    raise RuntimeError(f"Failed to navigate TikTok week picker to month {target_label}.")


def _month_year_key(label: str) -> tuple[int, int]:
    month_text, year_text = label.split("/")
    return int(year_text), int(month_text)


def _select_week_start(page, week_start: date) -> None:
    rows = page.locator("div.arco-panel-week .arco-picker-row-week")
    row_count = rows.count()
    for index in range(row_count):
        row = rows.nth(index)
        first_visible_cell = row.locator("div.arco-picker-cell:not(.arco-picker-cell-week)").first
        if not first_visible_cell.is_visible():
            continue
        day_text = first_visible_cell.inner_text(timeout=3000).strip()
        if day_text == str(week_start.day):
            first_visible_cell.click(force=True)
            page.wait_for_timeout(1200)
            return
    raise RuntimeError(f"Failed to select TikTok week starting {week_start.isoformat()}.")


def _wait_for_week_refresh(page, previous_text: str) -> None:
    try:
        page.wait_for_function(
            """
            prevText => {
                const text = (document.body?.innerText || '').replace(/\\s+/g, ' ');
                return text !== prevText && text.includes('Gross revenue') && text.includes('Visitors');
            }
            """,
            arg=" ".join((previous_text or "").split()),
            timeout=30000,
        )
        page.wait_for_timeout(1500)
    except Exception:
        page.wait_for_timeout(6000)


def _write_week_debug_artifacts(debug_dir: Path, target_name: str, week_start: date, page_text: str, page) -> None:
    safe_name = "".join(ch if ch.isalnum() else "_" for ch in target_name).strip("_") or "tiktok_target"
    week_key = week_start.isoformat()
    (debug_dir / f"{safe_name}_{week_key}.txt").write_text(page_text, encoding="utf-8")
    page.screenshot(path=str(debug_dir / f"{safe_name}_{week_key}.png"), full_page=True)


def _resolve_profile_dir(configured_profile_dir: Path, browser_channel: str, use_system_profile: bool) -> Path:
    if not use_system_profile:
        return configured_profile_dir

    local_app_data = Path.home() / "AppData" / "Local"
    if browser_channel == "msedge":
        return local_app_data / "Microsoft" / "Edge" / "User Data"
    if browser_channel == "chrome":
        return local_app_data / "Google" / "Chrome" / "User Data"
    raise ValueError("System profile mode is only supported for installed Chrome or Edge.")


if __name__ == "__main__":
    raise SystemExit(main())
