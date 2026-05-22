from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ga_reporter.database import ensure_schema, resolve_postgres_config, upsert_meta_captured_records
from ga_reporter.reference_historical import build_historical_records


def main() -> int:
    try:
        import streamlit as st

        secrets = st.secrets
    except Exception:
        secrets = {}

    config, source = resolve_postgres_config(secrets)
    if not config:
        raise SystemExit("Postgres config not found. Configure .streamlit/secrets.toml or PG* env vars.")

    records = build_historical_records(ROOT / "reference_historical")
    ensure_schema(config)
    inserted = upsert_meta_captured_records(config, records)
    print(f"Imported {inserted} historical social row(s) to PostgreSQL using {source}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
