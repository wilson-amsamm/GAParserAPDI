from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ga_reporter.database import ensure_schema, resolve_postgres_config, upsert_meta_captured_records
from ga_reporter.meta_capture import load_captured_records


def main() -> int:
    try:
        import streamlit as st

        secrets = st.secrets
    except Exception:
        secrets = {}

    config, source = resolve_postgres_config(secrets)
    if not config:
        raise SystemExit("Postgres config not found. Configure .streamlit/secrets.toml or PG* env vars.")

    records = load_captured_records(str(ROOT / "data" / "meta_business_suite_records.json"))
    ensure_schema(config)
    inserted = upsert_meta_captured_records(config, records)
    print(f"Migrated {inserted} social metric record(s) to PostgreSQL using {source}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
