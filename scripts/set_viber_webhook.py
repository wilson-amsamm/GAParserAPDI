from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ga_reporter.viber_bot import resolve_viber_config, set_viber_webhook

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib


def _load_streamlit_secrets() -> dict:
    secrets_path = ROOT / ".streamlit" / "secrets.toml"
    if not secrets_path.exists():
        return {}
    with secrets_path.open("rb") as handle:
        return tomllib.load(handle)


def main() -> int:
    secrets = _load_streamlit_secrets()
    viber_config, viber_source = resolve_viber_config(secrets)
    if not viber_config:
        print("Viber config is not available.")
        return 1
    response = set_viber_webhook(viber_config)
    print(f"Configured Viber webhook using {viber_source}.")
    print(response)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
