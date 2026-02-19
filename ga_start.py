from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional


def _repo_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


ROOT = _repo_root()
SRC = ROOT / "src"
if SRC.exists() and str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ga_reporter.cli import main as cli_main  # noqa: E402


def _is_service_account_json(path: Path) -> bool:
    if not path.exists() or not path.is_file() or path.suffix.lower() != ".json":
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return False
    return payload.get("type") == "service_account"


def _load_saved_service_account(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None
    value = payload.get("service_account")
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _save_service_account(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"service_account": value}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _resolve_service_account(runtime_config: Path) -> Optional[str]:
    env_value = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if env_value:
        return env_value

    saved_value = _load_saved_service_account(runtime_config)
    if saved_value:
        return saved_value

    local_default = ROOT / "service_account.json"
    if _is_service_account_json(local_default):
        resolved = str(local_default)
        _save_service_account(runtime_config, resolved)
        return resolved

    candidates = [p for p in ROOT.glob("*.json") if _is_service_account_json(p)]
    if len(candidates) == 1:
        resolved = str(candidates[0].resolve())
        _save_service_account(runtime_config, resolved)
        return resolved

    prompt = "Enter full path to service_account JSON (leave blank to skip): "
    value = input(prompt).strip()
    if not value:
        return None
    _save_service_account(runtime_config, value)
    return value


def _resolve_config_path(config_dir: Path) -> Path:
    main_path = config_dir / "properties.json"
    if main_path.exists():
        return main_path
    example_path = config_dir / "properties.example.json"
    if example_path.exists():
        return example_path
    return main_path


def main() -> int:
    config_dir = ROOT / "config"
    runtime_config = config_dir / "runtime.json"
    config_path = _resolve_config_path(config_dir)
    service_account = _resolve_service_account(runtime_config)
    out_dir = ROOT / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    export_txt_path = out_dir / f"website_summary_{stamp}.txt"

    args = [
        "--menu",
        "--config",
        str(config_path),
        "--export-txt",
        str(export_txt_path),
    ]
    if service_account:
        args.extend(["--service-account", service_account])

    exit_code = cli_main(args)
    if getattr(sys, "frozen", False):
        if exit_code == 0:
            print(f"\nSaved report to: {export_txt_path}")
        try:
            input("\nPress Enter to exit...")
        except EOFError:
            pass
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
