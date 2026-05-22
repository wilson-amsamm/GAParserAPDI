from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Iterable


DEFAULT_LABEL_MAP = {
    "GMV": "gross_revenue",
    "Gross revenue": "gross_revenue",
    "Items sold": "items_sold",
    "SKU orders": "sku_orders",
    "Orders": "orders",
    "Customers": "customers",
    "Page views": "page_views",
    "Product impressions": "page_views",
    "Unique product impressions": "unique_product_impressions",
    "Visitors": "visitors",
    "Conversion rate": "conversion_rate",
}


@dataclass(frozen=True)
class TikTokCaptureTarget:
    profile_name: str
    overview_url: str
    external_id: str = ""
    region: str = "PH"
    notes: str = ""
    label_map: dict[str, str | list[str]] | None = None
    expected_markers: tuple[str, ...] = ()


@dataclass(frozen=True)
class TikTokCapturedRecord:
    profile_name: str
    metrics: dict[str, float]
    source: str
    captured_at: str
    visible_date_range: str = ""
    notes: str = ""


def load_tiktok_capture_targets(config_path: str) -> list[TikTokCaptureTarget]:
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"TikTok capture config file not found: {path}")

    raw = json.loads(path.read_text(encoding="utf-8"))
    targets = raw.get("targets")
    if not isinstance(targets, list) or not targets:
        raise ValueError("TikTok capture config must contain a non-empty 'targets' list.")

    result: list[TikTokCaptureTarget] = []
    for item in targets:
        profile_name = str(item.get("profile_name", "")).strip()
        overview_url = str(item.get("overview_url", "")).strip()
        external_id = str(item.get("external_id", "")).strip()
        region = str(item.get("region", "PH")).strip() or "PH"
        notes = str(item.get("notes", "")).strip()
        expected_markers_raw = item.get("expected_markers", [])
        label_map_raw = item.get("label_map") or DEFAULT_LABEL_MAP
        if not profile_name or not overview_url:
            raise ValueError("Each TikTok capture target must include profile_name and overview_url.")
        if not isinstance(label_map_raw, dict) or not label_map_raw:
            raise ValueError("Each TikTok capture target must include a non-empty label_map object.")

        label_map: dict[str, str | list[str]] = dict(DEFAULT_LABEL_MAP)
        for label, metric_name in label_map_raw.items():
            clean_label = str(label).strip()
            if not clean_label:
                continue
            if isinstance(metric_name, list):
                aliases = [str(item).strip() for item in metric_name if str(item).strip()]
                if aliases:
                    label_map[clean_label] = aliases
            else:
                clean_metric = str(metric_name).strip()
                if clean_metric:
                    label_map[clean_label] = clean_metric

        expected_markers: list[str] = []
        if isinstance(expected_markers_raw, str):
            expected_markers_raw = [expected_markers_raw]
        if isinstance(expected_markers_raw, list):
            expected_markers = [
                str(marker).strip()
                for marker in expected_markers_raw
                if str(marker).strip()
            ]

        result.append(
            TikTokCaptureTarget(
                profile_name=profile_name,
                overview_url=overview_url,
                external_id=external_id,
                region=region,
                notes=notes,
                label_map=label_map,
                expected_markers=tuple(expected_markers),
            )
        )
    return result


def parse_visible_metrics(page_text: str, label_map: dict[str, str | list[str]] | None = None) -> dict[str, float]:
    mapping = label_map or DEFAULT_LABEL_MAP
    metrics: dict[str, float] = {}
    normalized = _normalize_whitespace(page_text)
    for label, metric_name in mapping.items():
        value = _extract_metric_value(normalized, label)
        if value is None:
            continue
        if isinstance(metric_name, list):
            for alias_metric_name in metric_name:
                metrics[alias_metric_name] = value
        else:
            metrics[metric_name] = value
    if not metrics and tiktok_no_data_present(page_text):
        metrics = {
            "gross_revenue": 0.0,
            "items_sold": 0.0,
            "sku_orders": 0.0,
            "orders": 0.0,
            "customers": 0.0,
            "page_views": 0.0,
            "unique_product_impressions": 0.0,
            "visitors": 0.0,
        }
    if "conversion_rate" not in metrics:
        items_sold = float(metrics.get("items_sold", 0) or 0)
        visitors = float(metrics.get("visitors", 0) or 0)
        metrics["conversion_rate"] = 0.0 if visitors == 0 else round((items_sold / visitors) * 100, 2)
    return metrics


def extract_visible_date_range(page_text: str) -> str:
    normalized = _normalize_whitespace(page_text)
    match = re.search(
        r"([A-Z][a-z]{2,8} \d{1,2}, \d{4}\s*-\s*[A-Z][a-z]{2,8} \d{1,2}, \d{4})",
        normalized,
    )
    if match:
        return match.group(1)
    single_match = re.search(r"([A-Z][a-z]{2,8} \d{1,2}, \d{4})", normalized)
    if single_match:
        return single_match.group(1)
    return ""


def load_captured_records(data_path: str) -> list[TikTokCapturedRecord]:
    path = Path(data_path)
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    records_raw = raw.get("records")
    if not isinstance(records_raw, list):
        raise ValueError("Captured TikTok data file must contain a 'records' list.")
    records: list[TikTokCapturedRecord] = []
    for item in records_raw:
        metrics_raw = item.get("metrics")
        if not isinstance(metrics_raw, dict):
            continue
        metrics = {
            str(name).strip(): float(value)
            for name, value in metrics_raw.items()
            if str(name).strip() and isinstance(value, (int, float))
        }
        records.append(
            TikTokCapturedRecord(
                profile_name=str(item.get("profile_name", "")).strip(),
                metrics=metrics,
                source=str(item.get("source", "tiktok_seller_capture")).strip(),
                captured_at=str(item.get("captured_at", "")).strip(),
                visible_date_range=str(item.get("visible_date_range", "")).strip(),
                notes=str(item.get("notes", "")).strip(),
            )
        )
    return records


def save_captured_records(data_path: str, records: Iterable[TikTokCapturedRecord]) -> None:
    path = Path(data_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "records": [
            {
                "profile_name": record.profile_name,
                "metrics": record.metrics,
                "source": record.source,
                "captured_at": record.captured_at,
                "visible_date_range": record.visible_date_range,
                "notes": record.notes,
            }
            for record in records
        ]
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def upsert_captured_record(
    existing: Iterable[TikTokCapturedRecord],
    new_record: TikTokCapturedRecord,
) -> list[TikTokCapturedRecord]:
    records = list(existing)
    replaced = False
    for index, record in enumerate(records):
        if record.profile_name == new_record.profile_name and _record_day_key(record.captured_at) == _record_day_key(
            new_record.captured_at
        ):
            records[index] = new_record
            replaced = True
            break
    if not replaced:
        records.append(new_record)
    return records


def make_captured_record(
    target: TikTokCaptureTarget,
    page_text: str,
    captured_at: datetime | None = None,
) -> TikTokCapturedRecord:
    visible_date_range = extract_visible_date_range(page_text)
    record_timestamp = captured_at or datetime.now(UTC)
    bounds = parse_visible_date_range_bounds(visible_date_range)
    if bounds and bounds[0] == bounds[1]:
        record_timestamp = datetime.combine(bounds[0], time(hour=12), tzinfo=UTC)
    return TikTokCapturedRecord(
        profile_name=target.profile_name,
        metrics=parse_visible_metrics(page_text, target.label_map),
        source="tiktok_seller_capture",
        captured_at=record_timestamp.isoformat(timespec="seconds"),
        visible_date_range=visible_date_range,
        notes=target.notes,
    )


def _extract_metric_value(page_text: str, label: str) -> float | None:
    label_pattern = re.escape(label)
    currency_markers = ("â‚±", "₱", "PHP", "P")
    currency_group = "|".join(re.escape(marker) for marker in currency_markers)
    patterns = [
        rf"{label_pattern}\s*[?]?\s*(?:{currency_group})?\s*([0-9,]+(?:\s*\.\s*\d+)?%?)",
        rf"{label_pattern}\s*(?:{currency_group})?\s*([0-9,]+(?:\s*\.\s*\d+)?%?)",
    ]
    for pattern in patterns:
        match = re.search(pattern, page_text, flags=re.IGNORECASE)
        if not match:
            continue
        raw = match.group(1).strip().replace(" ", "").replace(",", "")
        for marker in currency_markers:
            raw = raw.replace(marker, "")
        is_percent = raw.endswith("%")
        raw = raw.rstrip("%").strip()
        try:
            value = float(raw)
        except ValueError:
            continue
        return value if is_percent else value
    return None


def _normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _record_day_key(captured_at: str) -> str:
    return captured_at[:10]


def parse_visible_date_range_bounds(visible_date_range: str) -> tuple[date, date] | None:
    cleaned = _normalize_whitespace(visible_date_range)
    if not cleaned:
        return None
    if " - " in cleaned:
        start_raw, end_raw = [part.strip() for part in cleaned.split(" - ", 1)]
        return _parse_tiktok_date(start_raw), _parse_tiktok_date(end_raw)
    parsed = _parse_tiktok_date(cleaned)
    return parsed, parsed


def visible_date_range_is_single_day(visible_date_range: str) -> bool:
    bounds = parse_visible_date_range_bounds(visible_date_range)
    return bool(bounds and bounds[0] == bounds[1])


def normalize_tiktok_page_text(value: str) -> str:
    return _normalize_whitespace(value).lower()


def metric_cards_present(page_text: str) -> bool:
    normalized = normalize_tiktok_page_text(page_text)
    old_layout_labels = [
        "gross revenue",
        "items sold",
        "page views",
        "visitors",
        "conversion rate",
    ]
    if all(label in normalized for label in old_layout_labels):
        return True
    new_layout_labels = [
        "gmv",
        "items sold",
        "product impressions",
        "unique product impressions",
        "visitors",
        "sku orders",
        "orders",
        "customers",
    ]
    if "key metrics" not in normalized:
        return False
    if "gmv" not in normalized or "items sold" not in normalized:
        return tiktok_no_data_present(page_text)
    matched_labels = sum(label in normalized for label in new_layout_labels)
    return matched_labels >= 4


def tiktok_no_data_present(page_text: str) -> bool:
    normalized = normalize_tiktok_page_text(page_text)
    return "key metrics" in normalized and "no data" in normalized


def detect_tiktok_auth_issue(page_text: str, page_url: str) -> str | None:
    normalized = normalize_tiktok_page_text(page_text)
    normalized_url = (page_url or "").strip().lower()

    url_markers = [
        "login",
        "signin",
        "passport",
        "account",
        "verification",
        "challenge",
    ]
    if any(marker in normalized_url for marker in url_markers):
        return f"login-style URL detected: {page_url}"

    marker_groups = [
        (
            "login form visible",
            ["seller center", "log in"],
        ),
        (
            "credentials prompt visible",
            ["phone number", "password"],
        ),
        (
            "verification challenge visible",
            ["verification", "security check"],
        ),
        (
            "suspicious-activity challenge visible",
            ["suspicious activity", "try again later"],
        ),
        (
            "qr login challenge visible",
            ["qr code", "scan"],
        ),
        (
            "session expired prompt visible",
            ["session expired", "log in again"],
        ),
        (
            "account chooser visible",
            ["choose account", "switch account"],
        ),
        (
            "access denied prompt visible",
            ["access denied", "permission denied"],
        ),
        (
            "region mismatch prompt visible",
            ["not available in your region"],
        ),
    ]
    for reason, markers in marker_groups:
        if all(marker in normalized for marker in markers):
            return reason
    return None


def build_expected_tiktok_markers(target: TikTokCaptureTarget) -> tuple[str, ...]:
    explicit = [marker.strip() for marker in target.expected_markers if marker.strip()]
    if explicit:
        return tuple(explicit)

    region_markers = {
        "PH": ("philippines", "seller-ph.tiktok.com", "shop region"),
        "SG": ("singapore", "seller-sg.tiktok.com", "shop region"),
        "MY": ("malaysia", "seller-my.tiktok.com", "shop region"),
    }
    return region_markers.get(target.region.upper(), ())


def validate_tiktok_shop_context(target: TikTokCaptureTarget, page_text: str, page_url: str) -> str | None:
    if not metric_cards_present(page_text):
        return "overview metric cards are missing"

    expected_markers = build_expected_tiktok_markers(target)
    combined = normalize_tiktok_page_text(f"{page_url}\n{page_text}")
    if expected_markers and not any(marker.lower() in combined for marker in expected_markers):
        return (
            "expected shop/region markers were not found: "
            + ", ".join(expected_markers)
        )

    return None


def _parse_tiktok_date(value: str) -> date:
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Unsupported TikTok date format: {value}")
