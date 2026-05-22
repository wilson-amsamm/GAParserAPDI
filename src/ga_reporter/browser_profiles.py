from __future__ import annotations

import shutil
import subprocess
from datetime import datetime
from pathlib import Path


_LOCK_FILES = {
    "Cookies",
    "Cookies-journal",
    "LOCK",
    "LOCKFILE",
    "Safe Browsing Cookies",
    "Safe Browsing Cookies-journal",
    "SingletonCookie",
    "SingletonLock",
    "SingletonSocket",
}

_EXCLUDED_DIRS = [
    "Default\\Cache",
    "Default\\Code Cache",
    "Default\\GPUCache",
    "Default\\Service Worker\\CacheStorage",
    "GrShaderCache",
    "ShaderCache",
    "Crashpad",
    "component_crx_cache",
]


def prepare_browser_profile_dir(
    *,
    configured_profile_dir: Path,
    browser_channel: str,
    use_system_profile: bool,
    snapshot_root: Path,
    snapshot_prefix: str,
    keep_snapshots: int = 3,
) -> Path:
    if not use_system_profile:
        return configured_profile_dir

    source_dir = get_system_profile_dir(browser_channel)
    snapshot_root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    snapshot_dir = snapshot_root / f"{snapshot_prefix}_{timestamp}"
    _copy_browser_profile(source_dir, snapshot_dir)
    _cleanup_old_snapshots(snapshot_root, snapshot_prefix, keep_snapshots)
    return snapshot_dir


def get_system_profile_dir(browser_channel: str) -> Path:
    local_app_data = Path.home() / "AppData" / "Local"
    if browser_channel == "msedge":
        return local_app_data / "Microsoft" / "Edge" / "User Data"
    if browser_channel == "chrome":
        return local_app_data / "Google" / "Chrome" / "User Data"
    raise ValueError("System profile mode is only supported for installed Chrome or Edge.")


def _copy_browser_profile(source_dir: Path, destination_dir: Path) -> None:
    if not source_dir.exists():
        raise FileNotFoundError(f"Browser profile directory was not found: {source_dir}")

    if destination_dir.exists():
        shutil.rmtree(destination_dir, ignore_errors=True)
    destination_dir.mkdir(parents=True, exist_ok=True)

    if _try_robocopy(source_dir, destination_dir):
        return

    raise RuntimeError(
        "Failed to snapshot the live browser profile. Close Edge/Chrome, or use the "
        "dedicated Playwright profile after logging into TikTok there once."
    )


def _try_robocopy(source_dir: Path, destination_dir: Path) -> bool:
    command = [
        "robocopy",
        str(source_dir),
        str(destination_dir),
        "/MIR",
        "/R:1",
        "/W:1",
        "/XD",
        *_EXCLUDED_DIRS,
        "/XF",
        *_LOCK_FILES,
    ]

    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.returncode < 8


def _cleanup_old_snapshots(snapshot_root: Path, snapshot_prefix: str, keep_snapshots: int) -> None:
    snapshots = sorted(
        (
            path
            for path in snapshot_root.glob(f"{snapshot_prefix}_*")
            if path.is_dir()
        ),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for stale in snapshots[max(keep_snapshots, 1) :]:
        shutil.rmtree(stale, ignore_errors=True)
