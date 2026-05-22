from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
import re
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
    metric_cards_present,
    parse_visible_date_range_bounds,
    save_captured_records,
    upsert_captured_record,
    validate_tiktok_shop_context,
    visible_date_range_is_single_day,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Backfill TikTok Shop daily metrics into PostgreSQL.")
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
        help="Optional profile_name to backfill only one target.",
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
        help="Directory for daily backfill debug artifacts.",
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
        snapshot_prefix="tiktok_daily_backfill",
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
                print(f"Backfilling TikTok target: {target.profile_name}")
                page.goto(target.overview_url, wait_until="domcontentloaded", timeout=90000)
                _wait_for_overview_ready(page)
                initial_text = _page_text(page)
                auth_issue = detect_tiktok_auth_issue(initial_text, page.url)
                if auth_issue:
                    _write_day_debug_artifacts(debug_dir, target.profile_name, start_date, initial_text, page)
                    raise RuntimeError(
                        f"TikTok session for '{target.profile_name}' is not ready for daily backfill: {auth_issue}"
                    )

                cursor = start_date
                while cursor <= end_date:
                    print(f"  Day {cursor.isoformat()}")
                    before_text = _page_text(page)
                    _open_day_picker(page)
                    _navigate_day_picker_to_month(page, cursor)
                    _select_day(page, cursor)
                    page_text = _wait_for_day_refresh(page, before_text, cursor)
                    _write_day_debug_artifacts(debug_dir, target.profile_name, cursor, page_text, page)

                    auth_issue = detect_tiktok_auth_issue(page_text, page.url)
                    validation_issue = validate_tiktok_shop_context(target, page_text, page.url)
                    if auth_issue:
                        raise RuntimeError(
                            f"TikTok session for '{target.profile_name}' drifted during daily backfill: {auth_issue}"
                        )
                    if validation_issue:
                        raise RuntimeError(
                            f"TikTok page validation failed for '{target.profile_name}' on {cursor.isoformat()}: {validation_issue}"
                        )

                    record = make_captured_record(target, page_text, captured_at=datetime.now(UTC))
                    if not record.metrics:
                        raise RuntimeError(
                            f"No TikTok metrics parsed for '{target.profile_name}' on {cursor.isoformat()}."
                        )
                    if _page_is_multi_day_range(page_text):
                        raise RuntimeError(
                            f"TikTok page for '{target.profile_name}' is still showing a multi-day range on "
                            f"{cursor.isoformat()}; refusing to upsert this capture."
                        )
                    selected_day = _read_selected_day(page)
                    if selected_day == cursor and (
                        not record.visible_date_range
                        or _compare_layout_uses_previous_day_label(page_text, record.visible_date_range, cursor)
                    ):
                        record = replace(
                            record,
                            visible_date_range=selected_day.strftime("%b %d, %Y"),
                        )
                    if not record.visible_date_range or not visible_date_range_is_single_day(record.visible_date_range):
                        raise RuntimeError(
                            f"TikTok page for '{target.profile_name}' is not in a single-day view on {cursor.isoformat()}: "
                            f"{record.visible_date_range or 'blank date range'}"
                        )
                    bounds = parse_visible_date_range_bounds(record.visible_date_range)
                    if not bounds or bounds[0] != cursor:
                        raise RuntimeError(
                            f"TikTok page date mismatch for '{target.profile_name}': expected {cursor.isoformat()}, "
                            f"saw {record.visible_date_range}"
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
                                "notes": f"{target.notes} Daily backfill snapshot.",
                            }
                        ],
                        capture_source="tiktok_seller_daily_backfill",
                        notes=f"{target.notes} Daily backfill snapshot.",
                    )
                    total_upserts += inserted
                    print(f"    Upserted {inserted} row(s): {record.metrics}")
                    cursor += timedelta(days=1)
        finally:
            save_captured_records(args.data_path, existing_records)
            context.close()

    print(f"Done. Upserted {total_upserts} daily TikTok row(s) into PostgreSQL.")
    return 0


def _parse_iso_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _page_text(page) -> str:
    return page.locator("body").inner_text(timeout=30000)


def _open_day_picker(page) -> None:
    page.locator("div.arco-picker-range").first.click(force=True)
    page.wait_for_timeout(800)
    day_mode = page.locator("div.m4b-date-picker-range-mode-item", has_text="Day")
    if day_mode.count():
        day_mode.first.click(force=True)
    page.wait_for_timeout(800)


def _navigate_day_picker_to_month(page, target_day: date) -> None:
    target_label = target_day.strftime("%m/%Y")
    headers = page.locator("div.arco-picker-header-value")
    prev_month_button = page.locator("div.arco-picker-header-icon").nth(1)
    next_month_button = page.locator("div.arco-picker-header-icon").nth(2)

    for _ in range(36):
        header_count = headers.count()
        visible_labels = [
            headers.nth(index).inner_text(timeout=5000).strip()
            for index in range(header_count)
        ]
        if target_label in visible_labels:
            return
        current_label = visible_labels[0]
        if _month_year_key(current_label) > _month_year_key(target_label):
            prev_month_button.click(force=True)
        else:
            next_month_button.click(force=True)
        page.wait_for_timeout(300)
    raise RuntimeError(f"Failed to navigate TikTok day picker to month {target_label}.")


def _month_year_key(label: str) -> tuple[int, int]:
    month_text, year_text = label.split("/")
    return int(year_text), int(month_text)


def _select_day(page, target_day: date) -> None:
    _select_day_with_range_escape(page, target_day, escaped_range=False)


def _select_day_with_range_escape(page, target_day: date, *, escaped_range: bool) -> None:
    cells = page.locator("div.arco-picker-cell")
    cell_count = cells.count()
    matching_indexes: list[int] = []
    for index in range(cell_count):
        cell = cells.nth(index)
        class_name = cell.get_attribute("class") or ""
        if "arco-picker-cell-disabled" in class_name:
            continue
        try:
            text = cell.inner_text(timeout=1000).strip()
        except Exception:
            continue
        if text != str(target_day.day):
            continue
        matching_indexes.append(index)
    prefer_last_in_view = _target_month_is_right_calendar(page, target_day)
    ordered_indexes = sorted(
        matching_indexes,
        key=lambda idx: (
            "arco-picker-cell-in-view" not in (cells.nth(idx).get_attribute("class") or ""),
            -idx if prefer_last_in_view else idx,
        ),
    )
    for index in ordered_indexes:
        cell = cells.nth(index)
        class_name = cell.get_attribute("class") or ""
        if not escaped_range and _cell_is_part_of_existing_range(class_name):
            _click_alternate_day(page, target_day)
            _open_day_picker(page)
            _navigate_day_picker_to_month(page, target_day)
            _select_day_with_range_escape(page, target_day, escaped_range=True)
            return
        cell.click(force=True)
        page.wait_for_timeout(1200)
        if _selected_day_needs_commit(page, target_day):
            cell.click(force=True)
            page.wait_for_timeout(1200)
        return
    raise RuntimeError(f"Failed to select TikTok day {target_day.isoformat()}.")


def _cell_is_part_of_existing_range(class_name: str) -> bool:
    return any(
        marker in class_name
        for marker in (
            "arco-picker-cell-in-range",
            "arco-picker-cell-range-start",
            "arco-picker-cell-range-end",
            "arco-picker-cell-selected",
        )
    )


def _click_alternate_day(page, target_day: date) -> None:
    cells = page.locator("div.arco-picker-cell")
    cell_count = cells.count()
    for index in range(cell_count):
        cell = cells.nth(index)
        class_name = cell.get_attribute("class") or ""
        if "arco-picker-cell-disabled" in class_name or "arco-picker-cell-in-view" not in class_name:
            continue
        try:
            text = cell.inner_text(timeout=1000).strip()
        except Exception:
            continue
        if not text.isdigit() or text == str(target_day.day):
            continue
        cell.click(force=True)
        _wait_for_overview_ready(page, timeout_ms=45000)
        return
    raise RuntimeError(f"Failed to move TikTok picker off existing range for {target_day.isoformat()}.")


def _selected_day_needs_commit(page, target_day: date) -> bool:
    selected_day = _read_selected_day(page)
    if _page_uses_compare_layout(page):
        return True
    raw_values = page.evaluate(
        """
        () => Array.from(document.querySelectorAll('input'))
            .map(input => ({ value: (input.value || '').trim(), placeholder: (input.placeholder || '').trim() }))
        """
    )
    if selected_day != target_day:
        return True
    if not isinstance(raw_values, list):
        return False
    for item in raw_values:
        if not isinstance(item, dict):
            continue
        placeholder = str(item.get("placeholder", "") or "").strip().lower()
        value = str(item.get("value", "") or "").strip()
        if placeholder == "end date" and not value:
            return True
    return False


def _page_uses_compare_layout(page) -> bool:
    try:
        page_text = page.locator("body").inner_text(timeout=5000)
    except Exception:
        return False
    normalized = " ".join((page_text or "").split()).lower()
    return "compare" in normalized and "key metrics" in normalized


def _target_month_is_right_calendar(page, target_day: date) -> bool:
    headers = page.locator("div.arco-picker-header-value")
    labels: list[str] = []
    for index in range(headers.count()):
        try:
            labels.append(headers.nth(index).inner_text(timeout=1000).strip())
        except Exception:
            continue
    target_label = target_day.strftime("%m/%Y")
    if len(labels) >= 2 and labels[1] == target_label:
        return True
    return False


def _wait_for_day_refresh(page, previous_text: str, target_day: date) -> str:
    try:
        page.wait_for_function(
            """
            prevText => {
                const text = (document.body?.innerText || '').replace(/\\s+/g, ' ');
                const hasOldMetrics = text.includes('Gross revenue') && text.includes('Visitors');
                const hasNewMetrics = text.includes('Key metrics') && text.includes('GMV') && text.includes('Items sold');
                return text !== prevText && (hasOldMetrics || hasNewMetrics);
            }
            """,
            arg=" ".join((previous_text or "").split()),
            timeout=45000,
        )
    except Exception:
        pass
    _wait_for_overview_ready(page, timeout_ms=45000)

    for _ in range(20):
        page_text = _page_text(page)
        selected_day = _read_selected_day(page)
        visible_range = extract_visible_date_range(page_text)
        bounds = parse_visible_date_range_bounds(visible_range) if visible_range else None
        if (
            metric_cards_present(page_text)
            and
            selected_day == target_day
            and (
                (bounds and bounds[0] == target_day and bounds[1] == target_day)
                or _compare_layout_uses_previous_day_label(page_text, visible_range, target_day)
            )
        ):
            return page_text
        page.wait_for_timeout(1500)

    final_text = _page_text(page)
    selected_day = _read_selected_day(page)
    visible_range = extract_visible_date_range(final_text)
    raise RuntimeError(
        "TikTok page did not finish refreshing to the requested day. "
        f"Expected {target_day.isoformat()}, selected={selected_day}, visible={visible_range or 'blank'}."
    )


def _wait_for_overview_ready(page, timeout_ms: int = 60000) -> None:
    attempts = max(timeout_ms // 1500, 1)
    for _ in range(attempts):
        try:
            page_text = page.locator("body").inner_text(timeout=5000)
        except Exception:
            page.wait_for_timeout(1500)
            continue
        if metric_cards_present(page_text):
            page.wait_for_timeout(1500)
            return
        page.wait_for_timeout(1500)
    page.wait_for_timeout(10000)


def _read_selected_day(page) -> date | None:
    raw_values = page.evaluate(
        """
        () => Array.from(document.querySelectorAll('input'))
            .map(input => (input.value || '').trim())
            .filter(Boolean)
        """
    )
    if not isinstance(raw_values, list):
        return None

    for raw in raw_values:
        parsed = _parse_input_date(str(raw))
        if parsed:
            return parsed
    return None


def _parse_input_date(value: str) -> date | None:
    cleaned = value.strip()
    if not cleaned:
        return None

    iso_match = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", cleaned)
    if iso_match:
        year, month, day = iso_match.groups()
        return date(int(year), int(month), int(day))

    for fmt in ("%b %d, %Y", "%B %d, %Y", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    return None


def _page_is_multi_day_range(page_text: str) -> bool:
    normalized = " ".join((page_text or "").split()).lower()
    multi_day_markers = [
        "last 7 days:",
        "last 28 days:",
        "custom:",
        "week:",
        "month:",
    ]
    return any(marker in normalized for marker in multi_day_markers)


def _compare_layout_uses_previous_day_label(page_text: str, visible_range: str, target_day: date) -> bool:
    normalized = " ".join((page_text or "").split()).lower()
    if "compare" not in normalized:
        return False
    if not visible_range:
        return False
    bounds = parse_visible_date_range_bounds(visible_range)
    if not bounds or bounds[0] != bounds[1]:
        return False
    previous_day = target_day - timedelta(days=1)
    return bounds[0] == previous_day


def _write_day_debug_artifacts(debug_dir: Path, target_name: str, target_day: date, page_text: str, page) -> None:
    safe_name = "".join(ch if ch.isalnum() else "_" for ch in target_name).strip("_") or "tiktok_target"
    day_key = target_day.isoformat()
    (debug_dir / f"{safe_name}_{day_key}.txt").write_text(page_text, encoding="utf-8")
    page.screenshot(path=str(debug_dir / f"{safe_name}_{day_key}.png"), full_page=True)


if __name__ == "__main__":
    raise SystemExit(main())
