from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
import time


ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "logs" / "tiktok_daily_sync"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the daily TikTok Shop sync into PostgreSQL."
    )
    parser.add_argument(
        "--browser-channel",
        default="msedge",
        choices=["chrome", "msedge", "chromium"],
        help="Browser channel used for the automated TikTok capture.",
    )
    parser.add_argument(
        "--profile-dir",
        default=".playwright/tiktok-seller-profile",
        help="Dedicated persistent browser profile for TikTok session reuse.",
    )
    parser.add_argument(
        "--target",
        default="TikTok Shop PH",
        help="Optional TikTok profile_name to sync.",
    )
    parser.add_argument(
        "--window-days",
        type=int,
        default=5,
        help="How many recent completed days to re-sync on each run.",
    )
    parser.add_argument(
        "--end-offset-days",
        type=int,
        default=2,
        help="How many days behind today the sync should stop. 2 avoids TikTok's freshest incomplete day.",
    )
    parser.add_argument(
        "--timeout-minutes",
        type=int,
        default=90,
        help="Maximum runtime for the sync job before the wrapper exits with an error.",
    )
    parser.add_argument(
        "--use-system-profile",
        action="store_true",
        help="Use the installed browser's real user-data directory instead of the Playwright profile.",
    )
    parser.add_argument(
        "--retry-count",
        type=int,
        default=2,
        help="How many attempts to make when the TikTok sync exits non-zero.",
    )
    parser.add_argument(
        "--retry-delay-seconds",
        type=int,
        default=15,
        help="Delay between retry attempts after a failed run.",
    )
    return parser.parse_args(argv)


def _resolve_window(today: date, *, window_days: int, end_offset_days: int) -> tuple[date, date]:
    safe_window = max(window_days, 1)
    safe_offset = max(end_offset_days, 0)
    end_date = today - timedelta(days=safe_offset)
    start_date = end_date - timedelta(days=safe_window - 1)
    return start_date, end_date


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = LOG_DIR / f"tiktok_daily_sync_{timestamp}.log"
    latest_path = LOG_DIR / "latest.log"

    start_date, end_date = _resolve_window(
        date.today(),
        window_days=args.window_days,
        end_offset_days=args.end_offset_days,
    )
    command = [
        sys.executable,
        "-u",
        str(ROOT / "scripts" / "backfill_tiktok_days_to_postgres.py"),
        "--target",
        args.target,
        "--start-date",
        start_date.isoformat(),
        "--end-date",
        end_date.isoformat(),
        "--browser-channel",
        args.browser_channel,
        "--profile-dir",
        args.profile_dir,
    ]
    if args.use_system_profile:
        command.append("--use-system-profile")

    with log_path.open("w", encoding="utf-8") as handle:
        handle.write(f"TikTok daily sync started at {datetime.now().isoformat()}\n")
        handle.write(f"Project root: {ROOT}\n")
        handle.write(f"Command: {' '.join(command)}\n")
        handle.write(f"Window: {start_date.isoformat()} to {end_date.isoformat()}\n\n")
        handle.flush()

        total_attempts = max(args.retry_count, 1)
        completed = subprocess.CompletedProcess(command, returncode=1)
        for attempt in range(1, total_attempts + 1):
            handle.write(f"Attempt {attempt} of {total_attempts}\n")
            if args.use_system_profile:
                running_count = _running_browser_process_count(args.browser_channel)
                if running_count:
                    handle.write(
                        f"Detected {running_count} running {args.browser_channel} process(es) while using the live system profile.\n"
                    )
            handle.flush()

            try:
                completed = subprocess.run(
                    command,
                    cwd=ROOT,
                    stdout=handle,
                    stderr=subprocess.STDOUT,
                    text=True,
                    check=False,
                    timeout=max(args.timeout_minutes, 1) * 60,
                )
            except subprocess.TimeoutExpired:
                handle.write(
                    f"\nTikTok daily sync exceeded {args.timeout_minutes} minute(s) and was terminated.\n"
                )
                completed = subprocess.CompletedProcess(command, returncode=124)

            if completed.returncode == 0:
                break
            if attempt < total_attempts:
                handle.write(
                    f"Attempt {attempt} failed with exit code {completed.returncode}. "
                    f"Retrying in {max(args.retry_delay_seconds, 0)} second(s).\n\n"
                )
                handle.flush()
                time.sleep(max(args.retry_delay_seconds, 0))

        handle.write(
            f"\nTikTok daily sync finished at {datetime.now().isoformat()} "
            f"with exit code {completed.returncode}\n"
        )
        gap_completed = _run_gap_check(
            handle=handle,
            target=args.target,
            start_date=start_date,
            end_date=end_date,
        )
        if completed.returncode == 0 and gap_completed.returncode != 0:
            completed = subprocess.CompletedProcess(command, returncode=gap_completed.returncode)

    latest_path.write_text(log_path.read_text(encoding="utf-8"), encoding="utf-8")

    if completed.returncode != 0:
        raise SystemExit(completed.returncode)
    return completed.returncode


def _run_gap_check(*, handle, target: str, start_date: date, end_date: date) -> subprocess.CompletedProcess:
    command = [
        sys.executable,
        "-u",
        str(ROOT / "scripts" / "find_tiktok_gaps.py"),
        "--profile-name",
        target,
        "--start-date",
        start_date.isoformat(),
        "--end-date",
        end_date.isoformat(),
    ]
    handle.write("\nTikTok post-run gap check started.\n")
    handle.write(f"Command: {' '.join(command)}\n")
    handle.flush()
    completed = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.stdout:
        handle.write(completed.stdout)
    if completed.stderr:
        handle.write(completed.stderr)

    missing_count = _parse_missing_rows(completed.stdout)
    if completed.returncode == 0 and missing_count == 0:
        handle.write("TikTok gap check passed: no missing rows.\n")
        return completed
    if completed.returncode == 0 and missing_count > 0:
        handle.write(f"TikTok gap check failed: {missing_count} missing row(s) remain.\n")
        return subprocess.CompletedProcess(command, returncode=2)

    handle.write(f"TikTok gap check failed with exit code {completed.returncode}.\n")
    return completed


def _parse_missing_rows(output: str) -> int:
    for line in (output or "").splitlines():
        if not line.startswith("missing_rows="):
            continue
        try:
            return int(line.split("=", 1)[1].strip())
        except ValueError:
            return -1
    return -1


def _running_browser_process_count(browser_channel: str) -> int:
    process_map = {
        "msedge": "msedge.exe",
        "chrome": "chrome.exe",
        "chromium": "chromium.exe",
    }
    image_name = process_map.get(browser_channel)
    if not image_name:
        return 0

    completed = subprocess.run(
        ["tasklist", "/FI", f"IMAGENAME eq {image_name}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return 0

    rows = [line for line in completed.stdout.splitlines() if line.strip()]
    matches = [line for line in rows if line.lower().startswith(os.path.splitext(image_name)[0])]
    return len(matches)


if __name__ == "__main__":
    raise SystemExit(main())
