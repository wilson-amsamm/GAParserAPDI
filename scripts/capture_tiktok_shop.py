from __future__ import annotations

import argparse
import shutil
import sys
from datetime import UTC, datetime
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
    parser = argparse.ArgumentParser(description="Capture TikTok Seller Center overview metrics.")
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
        "--pause-on-login",
        action="store_true",
        help="Pause after the page opens so you can log in manually.",
    )
    parser.add_argument(
        "--target",
        default="",
        help="Optional profile_name to capture only one target.",
    )
    parser.add_argument(
        "--debug-dir",
        default=str(ROOT / "debug" / "tiktok_capture"),
        help="Directory for raw TikTok page text and screenshots.",
    )
    parser.add_argument(
        "--use-system-profile",
        action="store_true",
        help="Use the installed browser's real user-data directory instead of the Playwright profile.",
    )
    parser.add_argument(
        "--profile-backup-dir",
        default=str(ROOT / ".playwright" / "tiktok-seller-profile-backups"),
        help="Directory where known-good TikTok profile snapshots are stored.",
    )
    parser.add_argument(
        "--skip-profile-backup",
        action="store_true",
        help="Skip writing a profile snapshot after a successful capture session.",
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
    parser = build_parser()
    args = parser.parse_args()

    targets = load_tiktok_capture_targets(args.config)
    if args.target:
        targets = [target for target in targets if target.profile_name == args.target]
    if not targets:
        print("No TikTok targets matched the request.")
        return 1

    existing_records = load_captured_records(args.data_path)
    postgres_config, _ = resolve_postgres_config(_load_local_streamlit_secrets())
    profile_dir = prepare_browser_profile_dir(
        configured_profile_dir=Path(args.profile_dir),
        browser_channel=args.browser_channel,
        use_system_profile=args.use_system_profile,
        snapshot_root=ROOT / ".playwright" / "system-profile-snapshots",
        snapshot_prefix="tiktok_capture",
    )
    profile_backup_dir = Path(args.profile_backup_dir)

    from playwright.sync_api import sync_playwright

    successful_targets = 0
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

                page_text = page.locator("body").inner_text(timeout=15000)
                auth_issue = detect_tiktok_auth_issue(page_text, page.url)

                if args.pause_on_login or auth_issue:
                    if auth_issue:
                        print(
                            f"TikTok auth challenge detected for '{target.profile_name}': {auth_issue}. "
                            "Finish logging in or clearing the challenge in the browser window, then press Enter here to continue."
                        )
                    input(
                        f"Log in to TikTok Seller Center if needed, make sure the right date range is visible for "
                        f"'{target.profile_name}', then press Enter to capture."
                    )
                    page.wait_for_timeout(3000)
                    _wait_for_tiktok_metric_cards(page)
                    page_text = page.locator("body").inner_text(timeout=15000)
                else:
                    _wait_for_tiktok_metric_cards(page)
                    page_text = page.locator("body").inner_text(timeout=15000)

                auth_issue = detect_tiktok_auth_issue(page_text, page.url)
                validation_issue = validate_tiktok_shop_context(target, page_text, page.url)
                _write_debug_artifacts(
                    debug_dir=Path(args.debug_dir),
                    target_name=target.profile_name,
                    page_text=page_text,
                    page=page,
                )
                if auth_issue:
                    raise RuntimeError(
                        f"TikTok session for '{target.profile_name}' is not ready: {auth_issue}"
                    )
                if validation_issue:
                    raise RuntimeError(
                        f"TikTok page validation failed for '{target.profile_name}': {validation_issue}"
                    )
                record = make_captured_record(target, page_text, captured_at=datetime.now(UTC))
                if not record.metrics:
                    raise RuntimeError(
                        f"TikTok capture for '{target.profile_name}' parsed no metrics after validation."
                    )
                if not record.visible_date_range:
                    raise RuntimeError(
                        f"TikTok capture for '{target.profile_name}' is missing a visible date range. "
                        "Open a single-day date in Seller Center before capturing."
                    )
                if not visible_date_range_is_single_day(record.visible_date_range):
                    raise RuntimeError(
                        f"TikTok capture for '{target.profile_name}' is not a single-day view: "
                        f"{record.visible_date_range}. Open exactly one day before capturing."
                    )
                visible_bounds = parse_visible_date_range_bounds(record.visible_date_range)
                if not visible_bounds:
                    raise RuntimeError(
                        f"TikTok capture for '{target.profile_name}' has an unreadable date range: "
                        f"{record.visible_date_range}"
                    )
                existing_records = upsert_captured_record(existing_records, record)
                successful_targets += 1

                if postgres_config and record.metrics:
                    ensure_schema(postgres_config)
                    metric_date = visible_bounds[0].isoformat()
                    upsert_tiktok_daily_metrics(
                        postgres_config,
                        profile_name=record.profile_name,
                        external_id=target.external_id,
                        daily_rows=[
                            {
                                "metric_date": metric_date,
                                "gross_revenue": record.metrics.get("gross_revenue", 0),
                                "items_sold": record.metrics.get("items_sold", 0),
                                "page_views": record.metrics.get("page_views", 0),
                                "visitors": record.metrics.get("visitors", 0),
                                "conversion_rate": record.metrics.get("conversion_rate", 0),
                                "visible_date_range": record.visible_date_range,
                                "notes": record.notes,
                            }
                        ],
                        capture_source=record.source,
                        notes=record.notes,
                    )
                print(f"Captured {record.profile_name}: {record.metrics}")
        finally:
            save_captured_records(args.data_path, existing_records)
            context.close()

    if successful_targets and not args.skip_profile_backup and not args.use_system_profile:
        backup_path = _snapshot_profile(
            source_profile_dir=profile_dir,
            backup_root=profile_backup_dir,
        )
        print(f"Saved TikTok profile snapshot to {backup_path}")

    return 0


def _write_debug_artifacts(*, debug_dir: Path, target_name: str, page_text: str, page) -> None:
    debug_dir.mkdir(parents=True, exist_ok=True)
    safe_name = "".join(ch if ch.isalnum() else "_" for ch in target_name).strip("_") or "tiktok_target"
    text_path = debug_dir / f"{safe_name}.txt"
    screenshot_path = debug_dir / f"{safe_name}.png"
    text_path.write_text(page_text, encoding="utf-8")
    page.screenshot(path=str(screenshot_path), full_page=True)


def _wait_for_tiktok_metric_cards(page) -> None:
    for _ in range(20):
        try:
            page_text = page.locator("body").inner_text(timeout=5000)
        except Exception:
            page.wait_for_timeout(1500)
            continue
        if metric_cards_present(page_text):
            page.wait_for_timeout(1500)
            return
        page.wait_for_timeout(1500)
    page.wait_for_timeout(8000)


def _snapshot_profile(*, source_profile_dir: Path, backup_root: Path) -> Path:
    if not source_profile_dir.exists():
        raise FileNotFoundError(f"TikTok profile directory was not found: {source_profile_dir}")

    backup_root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target_dir = backup_root / f"profile_snapshot_{timestamp}"
    ignored_names = {
        "SingletonCookie",
        "SingletonLock",
        "SingletonSocket",
        "lockfile",
    }
    shutil.copytree(
        source_profile_dir,
        target_dir,
        ignore=shutil.ignore_patterns(*ignored_names),
    )
    return target_dir


if __name__ == "__main__":
    raise SystemExit(main())
