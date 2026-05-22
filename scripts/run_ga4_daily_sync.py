from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "logs" / "ga4_daily_sync"


def main() -> int:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = LOG_DIR / f"ga4_daily_sync_{timestamp}.log"
    latest_path = LOG_DIR / "latest.log"

    command = [
        sys.executable,
        "-u",
        str(ROOT / "scripts" / "sync_ga4_to_postgres.py"),
    ]

    with log_path.open("w", encoding="utf-8") as handle:
        handle.write(f"GA4 daily sync started at {datetime.now().isoformat()}\n")
        handle.write(f"Project root: {ROOT}\n")
        handle.write(f"Command: {' '.join(command)}\n\n")
        handle.flush()

        completed = subprocess.run(
            command,
            cwd=ROOT,
            stdout=handle,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )

        handle.write(f"\nGA4 daily sync finished at {datetime.now().isoformat()} with exit code {completed.returncode}\n")

    latest_path.write_text(log_path.read_text(encoding="utf-8"), encoding="utf-8")
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
