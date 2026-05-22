from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ga_reporter.client import GADataClient
from ga_reporter.config import load_property_config
from ga_reporter.credentials import resolve_service_account_path
from ga_reporter.database import ensure_schema, resolve_postgres_config, upsert_website_daily_metrics
from ga_reporter.date_utils import resolve_meta_date_range

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
    postgres_config, postgres_source = resolve_postgres_config(secrets)
    if not postgres_config:
        print("PostgreSQL config is not available.")
        return 1

    service_account_path, credential_source = resolve_service_account_path(repo_root=ROOT, streamlit_secrets=secrets)
    if not service_account_path:
        print("GA4 service account path is not available.")
        return 1

    ensure_schema(postgres_config)
    properties = load_property_config(str(ROOT / "config" / "properties.json"))
    client = GADataClient(service_account_path=service_account_path)

    sync_range = resolve_meta_date_range("last_28_days", None, None)
    print(
        f"Syncing GA4 daily website metrics for {sync_range.start_date} to {sync_range.end_date} "
        f"using {credential_source} and {postgres_source}."
    )

    total_rows = 0
    for item in properties:
        daily_rows = client.fetch_daily_metrics(
            property_id=item.property_id,
            start_date=sync_range.start_date,
            end_date=sync_range.end_date,
        )
        inserted = upsert_website_daily_metrics(
            postgres_config,
            site_name=item.site_name,
            property_id=item.property_id,
            daily_rows=daily_rows,
            capture_source="ga4_api_daily_sync",
            notes=f"Synced from GA4 for {sync_range.start_date} to {sync_range.end_date}.",
        )
        total_rows += inserted
        print(f"{item.site_name}: upserted {inserted} daily row(s).")

    warnings = client.get_warnings()
    if warnings:
        print("Warnings:")
        for warning in warnings:
            print(f"- {warning}")

    print(f"Done. Upserted {total_rows} daily website row(s) into PostgreSQL.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
