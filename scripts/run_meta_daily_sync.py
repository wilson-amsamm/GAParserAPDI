from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "logs" / "meta_daily_sync"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the daily Meta Business Suite sync into backend storage."
    )
    parser.add_argument(
        "--browser-channel",
        default="msedge",
        choices=["chrome", "msedge", "chromium"],
        help="Browser channel used for the automated Meta capture.",
    )
    parser.add_argument(
        "--profile-dir",
        default=".playwright/meta-business-suite-profile",
        help="Dedicated persistent browser profile for automated Meta login/session reuse.",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run the Meta capture in headless mode.",
    )
    parser.add_argument(
        "--timeout-minutes",
        type=int,
        default=60,
        help="Maximum runtime for the capture job before the wrapper exits with an error.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = LOG_DIR / f"meta_daily_sync_{timestamp}.log"
    latest_log_path = LOG_DIR / "latest.log"
    command = [
        sys.executable,
        "-u",
        str(ROOT / "scripts" / "capture_meta_business_suite.py"),
        "--date-preset",
        "daily",
        "--browser-channel",
        args.browser_channel,
        "--profile-dir",
        args.profile_dir,
    ]
    if args.headless:
        command.append("--headless")

    with log_path.open("w", encoding="utf-8") as log_file:
        log_file.write(f"Meta daily sync started at {datetime.now().isoformat()}\n")
        log_file.write(f"Project root: {ROOT}\n")
        log_file.write(f"Command: {' '.join(command)}\n\n")
        log_file.flush()
        try:
            completed = subprocess.run(
                command,
                check=False,
                cwd=str(ROOT),
                stdout=log_file,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=max(args.timeout_minutes, 1) * 60,
            )
        except subprocess.TimeoutExpired:
            log_file.write(
                f"\nMeta daily sync exceeded {args.timeout_minutes} minute(s) and was terminated.\n"
            )
            completed = subprocess.CompletedProcess(command, returncode=124)
        log_file.write(
            f"\nMeta daily sync finished at {datetime.now().isoformat()} "
            f"with exit code {completed.returncode}\n"
        )

    latest_log_path.write_text(log_path.read_text(encoding="utf-8"), encoding="utf-8")

    if completed.returncode != 0:
        raise SystemExit(completed.returncode)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
