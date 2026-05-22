from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ga_reporter.browser_profiles import prepare_browser_profile_dir
from ga_reporter.tiktok_capture import (
    detect_tiktok_auth_issue,
    load_tiktok_capture_targets,
    metric_cards_present,
    validate_tiktok_shop_context,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate TikTok Seller Center session health.")
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
        help="Optional profile_name to check only one target.",
    )
    parser.add_argument(
        "--debug-dir",
        default=str(ROOT / "debug" / "tiktok_capture"),
        help="Directory for session check debug artifacts.",
    )
    parser.add_argument(
        "--use-system-profile",
        action="store_true",
        help="Use the installed browser's real user-data directory instead of the Playwright profile.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    targets = load_tiktok_capture_targets(args.config)
    if args.target:
        targets = [target for target in targets if target.profile_name == args.target]
    if not targets:
        print("No TikTok targets matched the request.")
        return 1

    debug_dir = Path(args.debug_dir)
    debug_dir.mkdir(parents=True, exist_ok=True)
    profile_dir = prepare_browser_profile_dir(
        configured_profile_dir=Path(args.profile_dir),
        browser_channel=args.browser_channel,
        use_system_profile=args.use_system_profile,
        snapshot_root=ROOT / ".playwright" / "system-profile-snapshots",
        snapshot_prefix="tiktok_session_check",
    )

    from playwright.sync_api import sync_playwright

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
                page_text = _wait_for_tiktok_overview(page)
                _write_debug_artifacts(debug_dir, target.profile_name, page_text, page)

                auth_issue = detect_tiktok_auth_issue(page_text, page.url)
                if auth_issue:
                    print(f"{target.profile_name}: FAIL - {auth_issue}")
                    return 1

                validation_issue = validate_tiktok_shop_context(target, page_text, page.url)
                if validation_issue:
                    print(f"{target.profile_name}: FAIL - {validation_issue}")
                    return 1

                print(f"{target.profile_name}: OK")
        finally:
            context.close()

    return 0


def _wait_for_tiktok_overview(page) -> str:
    for _ in range(30):
        try:
            page_text = page.locator("body").inner_text(timeout=5000)
        except Exception:
            page.wait_for_timeout(1500)
            continue
        if metric_cards_present(page_text):
            page.wait_for_timeout(1500)
            return page_text
        page.wait_for_timeout(1500)
    return page.locator("body").inner_text(timeout=15000)


def _write_debug_artifacts(debug_dir: Path, target_name: str, page_text: str, page) -> None:
    safe_name = "".join(ch if ch.isalnum() else "_" for ch in target_name).strip("_") or "tiktok_target"
    (debug_dir / f"{safe_name}_session_check.txt").write_text(page_text, encoding="utf-8")
    page.screenshot(path=str(debug_dir / f"{safe_name}_session_check.png"), full_page=True)

if __name__ == "__main__":
    raise SystemExit(main())
