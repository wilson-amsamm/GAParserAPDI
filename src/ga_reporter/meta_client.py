from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests


@dataclass(frozen=True)
class MetaAccountConfig:
    platform: str
    account_id: str
    profile_name: str
    metrics: tuple[str, ...]
    notes: str = ""


@dataclass(frozen=True)
class MetaAccountSnapshot:
    platform: str
    account_id: str
    profile_name: str
    metrics: dict[str, float]
    source: str
    notes: str = ""


class MetaInsightsClient:
    def __init__(
        self,
        access_token: str,
        graph_version: str = "v23.0",
        session: requests.Session | None = None,
    ) -> None:
        if not access_token.strip():
            raise ValueError("Meta access token is required.")
        self._access_token = access_token.strip()
        self._graph_version = graph_version.strip() or "v23.0"
        self._session = session or requests.Session()

    def fetch_account_snapshot(
        self,
        account: MetaAccountConfig,
        *,
        since: str,
        until: str,
    ) -> MetaAccountSnapshot:
        endpoint = self._resolve_endpoint(account.platform, account.account_id)
        payload = self._get_json(
            endpoint,
            {
                "metric": ",".join(account.metrics),
                "period": "day",
                "since": since,
                "until": until,
            },
        )

        data = payload.get("data")
        if not isinstance(data, list):
            raise RuntimeError(
                f"Meta insights response for '{account.profile_name}' did not include a valid data array."
            )

        metrics: dict[str, float] = {}
        for item in data:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            values = item.get("values", [])
            if not name:
                continue
            metrics[name] = self._aggregate_metric(name, values)

        return MetaAccountSnapshot(
            platform=account.platform,
            account_id=account.account_id,
            profile_name=account.profile_name,
            metrics=metrics,
            source="meta_graph_api",
            notes=account.notes,
        )

    def _resolve_endpoint(self, platform: str, account_id: str) -> str:
        normalized = platform.strip().lower()
        if normalized in {"meta_page_insights", "facebook_page", "facebook_page_insights"}:
            return f"/{account_id}/insights"
        if normalized in {"instagram_business", "instagram_business_insights", "instagram_user"}:
            return f"/{account_id}/insights"
        raise ValueError(f"Unsupported Meta platform: {platform}")

    def _get_json(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        url = f"https://graph.facebook.com/{self._graph_version}{path}"
        response = self._session.get(
            url,
            params={**params, "access_token": self._access_token},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict) and "error" in payload:
            message = payload["error"].get("message", "Unknown Meta API error")
            raise RuntimeError(message)
        if not isinstance(payload, dict):
            raise RuntimeError("Unexpected Meta API payload.")
        return payload

    def _aggregate_metric(self, metric_name: str, values: Any) -> float:
        if not isinstance(values, list) or not values:
            return 0.0

        extracted: list[float] = []
        for item in values:
            if not isinstance(item, dict):
                continue
            value = item.get("value")
            if isinstance(value, (int, float)):
                extracted.append(float(value))

        if not extracted:
            return 0.0

        if metric_name in {"page_fans", "followers_count", "follower_count"}:
            return extracted[-1]
        return sum(extracted)
