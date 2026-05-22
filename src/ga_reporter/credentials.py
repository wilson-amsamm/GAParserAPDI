import json
import os
import tempfile
from pathlib import Path
from typing import Any


def resolve_service_account_path(
    *,
    repo_root: Path,
    streamlit_secrets: Any | None = None,
) -> tuple[str | None, str]:
    env_value = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if env_value:
        return env_value, "environment variable"

    secret_path = _read_secret_value(streamlit_secrets, "google_service_account_path")
    if secret_path:
        return str(secret_path), "streamlit secrets path"

    secret_info = _read_secret_mapping(streamlit_secrets, "google_service_account")
    if secret_info:
        return _write_temp_service_account(secret_info), "streamlit secrets payload"

    local_candidates = [
        repo_root / "service_account.json",
        *sorted(repo_root.glob("*service*.json")),
        *sorted(repo_root.glob("cool2025-*.json")),
        *sorted(repo_root.glob("*.json")),
    ]
    for candidate in local_candidates:
        if _is_service_account_json(candidate):
            return str(candidate), "local ignored file"

    return None, "not configured"


def resolve_meta_access_token(streamlit_secrets: Any | None = None) -> tuple[str | None, str]:
    env_value = os.getenv("META_ACCESS_TOKEN")
    if env_value and env_value.strip():
        return env_value.strip(), "environment variable"

    secret_value = _read_secret_value(streamlit_secrets, "meta_access_token")
    if secret_value:
        return secret_value, "streamlit secrets"

    return None, "not configured"


def _read_secret_value(streamlit_secrets: Any | None, key: str) -> str | None:
    if streamlit_secrets is None:
        return None
    try:
        value = streamlit_secrets.get(key)
    except Exception:
        return None
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _read_secret_mapping(streamlit_secrets: Any | None, key: str) -> dict[str, Any] | None:
    if streamlit_secrets is None:
        return None
    try:
        value = streamlit_secrets.get(key)
    except Exception:
        return None
    if hasattr(value, "to_dict"):
        value = value.to_dict()
    if isinstance(value, dict) and value.get("type") == "service_account":
        return value
    return None


def _write_temp_service_account(payload: dict[str, Any]) -> str:
    temp_dir = Path(tempfile.gettempdir()) / "online_platform_analytics"
    temp_dir.mkdir(parents=True, exist_ok=True)
    target = temp_dir / "service_account.runtime.json"
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return str(target)


def _is_service_account_json(path: Path) -> bool:
    if not path.exists() or not path.is_file() or path.suffix.lower() != ".json":
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return payload.get("type") == "service_account"
