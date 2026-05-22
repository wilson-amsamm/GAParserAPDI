import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from ga_reporter.config import load_property_config
from ga_reporter.meta_capture import load_captured_records, record_to_social_snapshot
from ga_reporter.meta_client import MetaAccountConfig, MetaAccountSnapshot, MetaInsightsClient
from ga_reporter.models import DateRange, MetricSummary
from ga_reporter.reporter import build_summary


@dataclass(frozen=True)
class SocialProfileSnapshot:
    platform: str
    profile_name: str
    metrics: dict[str, float]
    source: str = "manual"
    notes: str = ""


def load_meta_accounts_config(config_path: str) -> list[MetaAccountConfig]:
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Meta config file not found: {path}")

    raw = json.loads(path.read_text(encoding="utf-8"))
    accounts = raw.get("accounts")
    if not isinstance(accounts, list) or not accounts:
        raise ValueError("Meta config must contain a non-empty 'accounts' list.")

    result: list[MetaAccountConfig] = []
    for item in accounts:
        platform = str(item.get("platform", "")).strip()
        account_id = str(item.get("account_id", "")).strip()
        profile_name = str(item.get("profile_name", "")).strip()
        notes = str(item.get("notes", "")).strip()
        metrics_raw = item.get("metrics")

        if not platform or not account_id or not profile_name:
            raise ValueError(
                "Each Meta account must include non-empty platform, account_id, and profile_name."
            )
        if not isinstance(metrics_raw, list) or not metrics_raw:
            raise ValueError("Each Meta account must include a non-empty metrics list.")

        metrics = tuple(str(metric).strip() for metric in metrics_raw if str(metric).strip())
        if not metrics:
            raise ValueError("Meta metrics list cannot be empty after normalization.")

        result.append(
            MetaAccountConfig(
                platform=platform,
                account_id=account_id,
                profile_name=profile_name,
                metrics=metrics,
                notes=notes,
            )
        )
    return result


def load_social_config(config_path: str) -> list[SocialProfileSnapshot]:
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Social config file not found: {path}")

    raw = json.loads(path.read_text(encoding="utf-8"))
    profiles = raw.get("profiles")
    if not isinstance(profiles, list) or not profiles:
        raise ValueError("Social config must contain a non-empty 'profiles' list.")

    snapshots: list[SocialProfileSnapshot] = []
    for item in profiles:
        platform = str(item.get("platform", "")).strip()
        profile_name = str(item.get("profile_name", "")).strip()
        notes = str(item.get("notes", "")).strip()
        source = str(item.get("source", "manual")).strip() or "manual"
        metrics_raw = item.get("metrics")

        if not platform or not profile_name:
            raise ValueError("Each social profile must include non-empty platform and profile_name.")
        if not isinstance(metrics_raw, dict) or not metrics_raw:
            raise ValueError("Each social profile must include a non-empty metrics object.")

        metrics: dict[str, float] = {}
        for key, value in metrics_raw.items():
            metric_name = str(key).strip()
            if not metric_name:
                raise ValueError("Social metric names must be non-empty.")
            if not isinstance(value, (int, float)):
                raise ValueError("Social metric values must be numeric.")
            metrics[metric_name] = float(value)

        snapshots.append(
            SocialProfileSnapshot(
                platform=platform,
                profile_name=profile_name,
                metrics=metrics,
                source=source,
                notes=notes,
            )
        )
    return snapshots


def load_ga4_summary(
    *,
    config_path: str,
    service_account_path: str | None,
    date_range: DateRange,
    impressions_metric: str = "organicGoogleSearchImpressions",
    retries: int = 2,
    retry_delay_seconds: float = 1.0,
    continue_on_error: bool = True,
) -> tuple[list[MetricSummary], list[str]]:
    from ga_reporter.client import GADataClient

    properties = load_property_config(config_path)
    client = GADataClient(
        service_account_path=service_account_path,
        impressions_metric=impressions_metric,
    )
    summaries = build_summary(
        client=client,
        properties=properties,
        start_date=date_range.start_date,
        end_date=date_range.end_date,
        retries=retries,
        retry_delay_seconds=retry_delay_seconds,
        continue_on_error=continue_on_error,
    )
    warnings = client.get_warnings() if hasattr(client, "get_warnings") else []
    return summaries, warnings


def load_meta_summary(
    *,
    config_path: str,
    access_token: str,
    date_range: DateRange,
    graph_version: str = "v23.0",
) -> tuple[list[SocialProfileSnapshot], list[str]]:
    accounts = load_meta_accounts_config(config_path)
    client = MetaInsightsClient(access_token=access_token, graph_version=graph_version)

    snapshots: list[SocialProfileSnapshot] = []
    warnings: list[str] = []
    for account in accounts:
        try:
            snapshot = client.fetch_account_snapshot(
                account,
                since=date_range.start_date,
                until=date_range.end_date,
            )
            snapshots.append(_meta_snapshot_to_social(snapshot))
        except Exception as exc:
            warnings.append(f"{account.profile_name}: {exc}")
    return snapshots, warnings


def load_meta_captured_summary(data_path: str) -> list[SocialProfileSnapshot]:
    return [record_to_social_snapshot(record) for record in load_captured_records(data_path)]


def metric_summaries_to_rows(items: Iterable[MetricSummary]) -> list[dict[str, float | int | str | None]]:
    rows: list[dict[str, float | int | str | None]] = []
    for item in items:
        rows.append(
            {
                "Site": item.site_name,
                "Visitors": item.visitors,
                "Impressions": item.impressions,
                "2025 Avg Daily Visitors": round(item.avg_daily_visitors_2025, 2),
                "2025 Avg Daily Impressions": round(item.avg_daily_impressions_2025, 2),
                "Expected Visitors For Period": round(item.expected_visitors_for_period_2025, 2),
                "Expected Impressions For Period": round(
                    item.expected_impressions_for_period_2025, 2
                ),
                "Visitors Change % vs 2025 Avg": _round_optional(
                    item.visitors_change_pct_vs_2025_avg
                ),
                "Impressions Change % vs 2025 Avg": _round_optional(
                    item.impressions_change_pct_vs_2025_avg
                ),
            }
        )
    return rows


def social_profiles_to_rows(
    profiles: Iterable[SocialProfileSnapshot],
) -> list[dict[str, float | str]]:
    rows: list[dict[str, float | str]] = []
    for profile in profiles:
        row: dict[str, float | str] = {
            "Platform": profile.platform,
            "Profile": profile.profile_name,
            "Source": profile.source,
            "Notes": profile.notes,
        }
        row.update({metric_name: value for metric_name, value in profile.metrics.items()})
        rows.append(row)
    return rows


def total_social_metric(
    profiles: Iterable[SocialProfileSnapshot], metric_names: Iterable[str]
) -> float:
    candidates = {name.lower() for name in metric_names}
    total = 0.0
    for profile in profiles:
        for metric_name, value in profile.metrics.items():
            if metric_name.lower() in candidates:
                total += value
    return total


def merge_social_profiles(
    *groups: Iterable[SocialProfileSnapshot],
) -> list[SocialProfileSnapshot]:
    merged: list[SocialProfileSnapshot] = []
    for group in groups:
        merged.extend(group)
    return merged


def _round_optional(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 2)


def _meta_snapshot_to_social(snapshot: MetaAccountSnapshot) -> SocialProfileSnapshot:
    return SocialProfileSnapshot(
        platform=snapshot.platform,
        profile_name=snapshot.profile_name,
        metrics=snapshot.metrics,
        source=snapshot.source,
        notes=snapshot.notes,
    )
