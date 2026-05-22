from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ga_reporter.meta_capture import (
    expand_debug_text_to_daily_records,
    load_captured_records,
    load_meta_capture_targets,
    make_captured_record,
    save_captured_records,
    upsert_captured_record,
)
from ga_reporter.database import ensure_schema, resolve_postgres_config, upsert_meta_captured_records


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture Meta Business Suite exports into backend storage."
    )
    parser.add_argument(
        "--config",
        default="config/meta_capture_targets.json",
        help="Path to JSON config describing Meta Business Suite targets.",
    )
    parser.add_argument(
        "--output",
        default="data/meta_business_suite_records.json",
        help="Path to JSON output file used by the dashboard.",
    )
    parser.add_argument(
        "--download-dir",
        default="data/meta_business_suite_exports",
        help="Directory where exported Meta report files are saved.",
    )
    parser.add_argument(
        "--profile-dir",
        default=".playwright/meta-business-suite-profile",
        help="Persistent browser profile directory for the logged-in Meta session.",
    )
    parser.add_argument(
        "--browser-channel",
        default="chrome",
        choices=["chrome", "msedge", "chromium"],
        help="Browser channel to launch. Defaults to installed Google Chrome.",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run headless. Omit for the safer visible-browser workflow.",
    )
    parser.add_argument(
        "--pause-on-login",
        action="store_true",
        help="Pause after opening each target so you can finish login or navigation before capture.",
    )
    parser.add_argument(
        "--use-system-profile",
        action="store_true",
        help="Use the browser's real system user-data directory instead of the isolated Playwright profile.",
    )
    parser.add_argument(
        "--terminate-existing-browser",
        action="store_true",
        help="Force-close existing browser processes for the selected installed browser before launch.",
    )
    parser.add_argument(
        "--debug-dump-dir",
        default="debug/meta_capture",
        help="Directory where raw page text dumps are written for parser tuning.",
    )
    parser.add_argument(
        "--date-preset",
        choices=["daily", "weekly", "yearly"],
        help="Optional override for all capture targets.",
    )
    parser.add_argument(
        "--start-date",
        help="Custom start date in YYYY-MM-DD for Meta capture.",
    )
    parser.add_argument(
        "--end-date",
        help="Custom end date in YYYY-MM-DD for Meta capture.",
    )
    parser.add_argument(
        "--target",
        action="append",
        default=[],
        help="Optional profile name filter. Repeat for multiple targets.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise SystemExit(
            "Missing dependency. Install with `pip install -r requirements.txt` "
            "and then `python -m playwright install chromium`."
        ) from exc

    targets = load_meta_capture_targets(str(ROOT / args.config))
    if args.target:
        requested = {value.strip().lower() for value in args.target if value.strip()}
        targets = [target for target in targets if target.profile_name.lower() in requested]
    if not targets:
        raise SystemExit("No Meta capture targets matched the requested filters.")

    custom_date_range: tuple[str, str] | None = None
    if args.start_date or args.end_date:
        if not args.start_date or not args.end_date:
            raise SystemExit("--start-date and --end-date must be used together.")
        _validate_iso_date(args.start_date)
        _validate_iso_date(args.end_date)
        custom_date_range = (args.start_date, args.end_date)
    output_path = ROOT / args.output
    download_dir = ROOT / args.download_dir
    profile_dir = _resolve_profile_dir(ROOT, args.profile_dir, args.browser_channel, args.use_system_profile)
    debug_dump_dir = ROOT / args.debug_dump_dir
    download_dir.mkdir(parents=True, exist_ok=True)
    debug_dump_dir.mkdir(parents=True, exist_ok=True)

    if args.use_system_profile and args.terminate_existing_browser:
        _terminate_existing_browser_processes(args.browser_channel)

    try:
        import streamlit as st

        streamlit_secrets = st.secrets
    except Exception:
        streamlit_secrets = {}

    postgres_config, postgres_source = resolve_postgres_config(streamlit_secrets)
    if postgres_config:
        ensure_schema(postgres_config)

    existing_records = load_captured_records(str(output_path))
    updated_records = list(existing_records)
    postgres_upserts = 0

    with sync_playwright() as playwright:
        browser_context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            accept_downloads=True,
            headless=args.headless,
            viewport={"width": 1600, "height": 1000},
            channel=None if args.browser_channel == "chromium" else args.browser_channel,
        )
        page = browser_context.new_page()

        for target in targets:
            try:
                print(f"Opening {target.profile_name}...")
                page.goto(target.insights_url, wait_until="domcontentloaded", timeout=120000)
                page.wait_for_timeout(5000)

                _prepare_results_view(
                    page,
                    platform_name=_platform_display_name(target.platform),
                    period_preset=args.date_preset or target.period_preset,
                    custom_date_range=custom_date_range,
                )

                if args.pause_on_login:
                    input(
                        f"Review the page for '{target.profile_name}', complete login if needed, "
                        "then press Enter to capture metrics..."
                    )
                else:
                    page.wait_for_timeout(5000)

                page_text = page.locator("body").inner_text()
                dump_path = debug_dump_dir / _debug_dump_name(
                    target.profile_name,
                    custom_date_range=custom_date_range,
                )
                dump_path.write_text(page_text, encoding="utf-8")
                downloaded_files = _download_exports_for_target(
                    page=page,
                    target_name=target.profile_name,
                    download_dir=download_dir,
                )
                detailed_records = expand_debug_text_to_daily_records(
                    target=target,
                    page_text=page_text,
                )
                record = make_captured_record(
                    target,
                    page_text,
                    downloaded_files=downloaded_files,
                )
                records_to_store = detailed_records or ([record] if record.metrics else [])

                if not records_to_store:
                    print(
                        f"Warning: no metrics were captured for {target.profile_name}. "
                        f"Check the page, date range, or selectors. Debug text saved to {dump_path}"
                    )
                if downloaded_files:
                    print(
                        f"Downloaded exports for {target.profile_name}: "
                        + ", ".join(Path(path).name for path in downloaded_files)
                    )
                else:
                    print(f"Warning: no export files were downloaded for {target.profile_name}.")
                for item in records_to_store:
                    updated_records = upsert_captured_record(updated_records, item)
                if postgres_config and records_to_store:
                    postgres_upserts += upsert_meta_captured_records(postgres_config, records_to_store)
                if detailed_records:
                    print(
                        f"Captured {target.profile_name}: expanded to {len(detailed_records)} daily row(s) "
                        f"from {detailed_records[0].captured_at[:10]} to {detailed_records[-1].captured_at[:10]}"
                    )
                else:
                    print(
                        f"Captured {target.profile_name}: "
                        + ", ".join(f"{key}={value:g}" for key, value in record.metrics.items())
                    )
            except Exception as exc:
                print(f"Warning: target '{target.profile_name}' failed: {exc}")
                continue

        browser_context.close()

    save_captured_records(str(output_path), updated_records)
    print(f"Saved captured records to {output_path}")
    if postgres_config:
        print(
            f"Upserted {postgres_upserts} daily social row(s) into PostgreSQL using {postgres_source}."
        )
    return 0


def _resolve_profile_dir(
    repo_root: Path,
    configured_profile_dir: str,
    browser_channel: str,
    use_system_profile: bool,
) -> Path:
    if not use_system_profile:
        return repo_root / configured_profile_dir

    local_app_data = Path.home() / "AppData" / "Local"
    if browser_channel == "msedge":
        return local_app_data / "Microsoft" / "Edge" / "User Data"
    if browser_channel == "chrome":
        return local_app_data / "Google" / "Chrome" / "User Data"
    raise ValueError("System profile mode is only supported for installed Chrome or Edge.")


def _terminate_existing_browser_processes(browser_channel: str) -> None:
    process_name = {
        "msedge": "msedge.exe",
        "chrome": "chrome.exe",
    }.get(browser_channel)
    if not process_name:
        return
    subprocess.run(
        ["taskkill", "/F", "/IM", process_name],
        check=False,
        capture_output=True,
        text=True,
    )


def _sanitize_filename(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value)
    cleaned = cleaned.strip("_") or "capture"
    return f"{cleaned}.txt"


def _sanitize_stem(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value)
    return cleaned.strip("_") or "capture"


def _prepare_results_view(
    page,
    platform_name: str,
    period_preset: str,
    custom_date_range: tuple[str, str] | None = None,
) -> None:
    _click_first(page, ["Results"])
    page.wait_for_timeout(2000)
    if platform_name.lower() != "instagram":
        _set_platform(page, platform_name)
    _dismiss_overlays(page)
    if custom_date_range:
        _set_custom_date_range(page, custom_date_range[0], custom_date_range[1])
    else:
        _set_date_preset(page, period_preset)
    page.wait_for_timeout(2000)


def _download_exports_for_target(page, target_name: str, download_dir: Path) -> list[str]:
    saved_paths: list[str] = []
    export_buttons = page.get_by_role("button", name=re.compile(r"^Export$", re.I))
    count = export_buttons.count()
    for index in range(count):
        button = export_buttons.nth(index)
        if not button.is_visible():
            continue
        try:
            saved_paths.append(
                _download_from_export_button(
                    page=page,
                    button=button,
                    target_name=target_name,
                    button_index=index + 1,
                    download_dir=download_dir,
                )
            )
        except Exception:
            continue
    return saved_paths


def _download_from_export_button(page, button, target_name: str, button_index: int, download_dir: Path) -> str:
    with page.expect_download(timeout=15000) as download_info:
        button.click(timeout=10000)
        _click_first(page, ["Export", "Download", "CSV", "Excel", "Export data"])

    download = download_info.value
    suggested = download.suggested_filename or f"export_{button_index}.dat"
    target_path = download_dir / f"{_sanitize_stem(target_name)}_{button_index}_{suggested}"
    download.save_as(str(target_path))
    page.wait_for_timeout(1000)
    return str(target_path)


def _set_platform(page, platform_name: str) -> None:
    if platform_name.lower() == "instagram" and "platform=Instagram" in page.url:
        return
    switcher = page.get_by_role("button", name=re.compile(r"Facebook|Instagram", re.I)).first
    current_label = ""
    try:
        current_label = switcher.inner_text(timeout=3000).strip()
    except Exception:
        current_label = ""
    if not current_label and _page_appears_to_be_in_platform(page, platform_name):
        return
    if platform_name.lower() in current_label.lower():
        return
    switcher.click(timeout=10000)
    for locator in (
        page.get_by_role("radio", name=re.compile(re.escape(platform_name), re.I)),
        page.get_by_role("menuitemradio", name=re.compile(re.escape(platform_name), re.I)),
        page.get_by_role("option", name=re.compile(re.escape(platform_name), re.I)),
    ):
        if locator.count():
            _click_locator(locator.first)
            page.wait_for_timeout(1500)
            return
    if _page_appears_to_be_in_platform(page, platform_name):
        return
    _click_first(page, [platform_name])
    page.wait_for_timeout(1500)


def _set_date_preset(page, period_preset: str) -> None:
    _dismiss_overlays(page)
    desired_label = {
        "daily": "Yesterday",
        "weekly": "Last 7 days",
        "yearly": "This year",
    }[period_preset]
    date_button = page.get_by_role(
        "button",
        name=re.compile(
            r"Yesterday|Last 7 days|Last 28 days|Last 90 days|This week|This month|This year|Custom",
            re.I,
        ),
    ).first
    try:
        current_label = date_button.inner_text(timeout=3000).strip()
        if desired_label.lower() in current_label.lower():
            return
    except Exception:
        pass
    try:
        _click_locator(date_button)
        _click_first(page, [desired_label])
        try:
            _click_first(page, ["Update"])
        except Exception:
            pass
        page.wait_for_timeout(1500)
    except Exception:
        # Meta sometimes renders the visible date control inside a disabled wrapper.
        # In that case we keep the current page range instead of failing the whole capture.
        pass


def _set_custom_date_range(page, start_date: str, end_date: str) -> None:
    _dismiss_overlays(page)
    date_button = page.get_by_role(
        "button",
        name=re.compile(
            r"Yesterday|Last 7 days|Last 28 days|Last 90 days|This week|This month|This year|Custom",
            re.I,
        ),
    ).first
    _click_locator(date_button)
    _click_first(page, ["Custom"])
    page.wait_for_timeout(1000)

    start_label = _display_date(start_date)
    end_label = _display_date(end_date)

    editable_inputs = page.locator("input")
    filled = False
    count = editable_inputs.count()
    if count >= 2:
        try:
            editable_inputs.nth(0).fill(start_label, timeout=5000)
            editable_inputs.nth(1).fill(end_label, timeout=5000)
            filled = True
        except Exception:
            filled = False

    if not filled:
        buttons = page.get_by_role("button", name=re.compile(r"[A-Z][a-z]{2} \d{1,2}, \d{4}", re.I))
        if buttons.count() >= 2:
            try:
                buttons.nth(0).click(timeout=5000)
                page.keyboard.press("Control+A")
                page.keyboard.type(start_label)
                buttons.nth(1).click(timeout=5000)
                page.keyboard.press("Control+A")
                page.keyboard.type(end_label)
                filled = True
            except Exception:
                filled = False

    if not filled:
        raise RuntimeError("Unable to fill Meta custom date range inputs.")

    _click_first(page, ["Update"])
    page.wait_for_timeout(1500)


def _click_first(page, labels: list[str]) -> None:
    for label in labels:
        exact = page.get_by_text(label, exact=True)
        if exact.count():
            _click_locator(exact.first)
            return

        locator = page.get_by_role("button", name=re.compile(re.escape(label), re.I))
        if locator.count():
            _click_locator(locator.first)
            return

        locator = page.get_by_role("link", name=re.compile(re.escape(label), re.I))
        if locator.count():
            _click_locator(locator.first)
            return

        locator = page.get_by_text(re.compile(re.escape(label), re.I))
        if locator.count():
            _click_locator(locator.first)
            return

    raise RuntimeError(f"Unable to find any clickable element for labels: {labels}")


def _platform_display_name(platform: str) -> str:
    return "Instagram" if "instagram" in platform.lower() else "Facebook"


def _click_locator(locator) -> None:
    try:
        locator.click(timeout=10000)
        return
    except Exception:
        pass

    try:
        locator.click(timeout=10000, force=True)
        return
    except Exception:
        pass

    locator.evaluate("(element) => element.click()")


def _dismiss_overlays(page) -> None:
    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
    except Exception:
        pass

    close_patterns = [
        re.compile(r"close", re.I),
        re.compile(r"not now", re.I),
        re.compile(r"got it", re.I),
        re.compile(r"dismiss", re.I),
        re.compile(r"skip", re.I),
    ]
    for pattern in close_patterns:
        for locator in (
            page.get_by_role("button", name=pattern),
            page.get_by_role("link", name=pattern),
        ):
            try:
                if locator.count():
                    _click_locator(locator.first)
                    page.wait_for_timeout(300)
            except Exception:
                continue


def _validate_iso_date(value: str) -> None:
    datetime.strptime(value, "%Y-%m-%d")


def _display_date(value: str) -> str:
    return datetime.strptime(value, "%Y-%m-%d").strftime("%b %d, %Y")


def _debug_dump_name(profile_name: str, custom_date_range: tuple[str, str] | None = None) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in profile_name)
    cleaned = cleaned.strip("_") or "capture"
    if custom_date_range:
        start_year = custom_date_range[0][:4]
        end_year = custom_date_range[1][:4]
        if start_year == end_year:
            return f"{cleaned}_{start_year}.txt"
        return f"{cleaned}_{custom_date_range[0]}_{custom_date_range[1]}.txt"
    return f"{cleaned}.txt"


def _page_appears_to_be_in_platform(page, platform_name: str) -> bool:
    try:
        body_text = page.locator("body").inner_text(timeout=3000)
    except Exception:
        return False
    lines = [line.replace("\u200b", "").replace("â€‹", "").strip() for line in body_text.splitlines()]
    head = [line for line in lines[:12] if line]
    normalized_head = " | ".join(head).lower()
    return platform_name.lower() in normalized_head


if __name__ == "__main__":
    raise SystemExit(main())
