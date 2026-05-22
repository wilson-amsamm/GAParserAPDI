from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Iterable

if TYPE_CHECKING:
    from ga_reporter.dashboard_data import SocialProfileSnapshot


DEFAULT_LABEL_MAP = {
    "Views": "views",
    "Viewers": "viewers",
    "Content interactions": "content_interactions",
    "Facebook visits": "facebook_visits",
    "Follows": "follows",
    "Unfollows": "unfollows",
    "Net follows": "net_follows",
}


@dataclass(frozen=True)
class MetaCaptureTarget:
    profile_name: str
    platform: str
    insights_url: str
    label_map: dict[str, str]
    period_preset: str = "weekly"
    external_id: str = ""
    notes: str = ""


@dataclass(frozen=True)
class MetaCapturedRecord:
    profile_name: str
    platform: str
    metrics: dict[str, float]
    source: str
    captured_at: str
    visible_date_range: str = ""
    downloaded_files: tuple[str, ...] = ()
    notes: str = ""


def load_meta_capture_targets(config_path: str) -> list[MetaCaptureTarget]:
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Meta capture config file not found: {path}")

    raw = json.loads(path.read_text(encoding="utf-8"))
    targets = raw.get("targets")
    if not isinstance(targets, list) or not targets:
        raise ValueError("Meta capture config must contain a non-empty 'targets' list.")

    result: list[MetaCaptureTarget] = []
    for item in targets:
        profile_name = str(item.get("profile_name", "")).strip()
        platform = str(item.get("platform", "facebook_page")).strip()
        insights_url = str(item.get("insights_url", "")).strip()
        notes = str(item.get("notes", "")).strip()
        external_id = str(item.get("external_id", "")).strip()
        period_preset = str(item.get("period_preset", "weekly")).strip().lower() or "weekly"
        label_map_raw = item.get("label_map") or DEFAULT_LABEL_MAP

        if not profile_name or not insights_url:
            raise ValueError("Each Meta capture target must include profile_name and insights_url.")
        if period_preset not in {"daily", "weekly", "yearly"}:
            raise ValueError("Meta capture target period_preset must be one of: daily, weekly, yearly.")
        if not isinstance(label_map_raw, dict) or not label_map_raw:
            raise ValueError("Each Meta capture target must include a non-empty label_map object.")

        label_map = {
            str(label).strip(): str(metric_name).strip()
            for label, metric_name in label_map_raw.items()
            if str(label).strip() and str(metric_name).strip()
        }
        if not label_map:
            raise ValueError("Meta capture target label_map cannot be empty after normalization.")

        result.append(
            MetaCaptureTarget(
                profile_name=profile_name,
                platform=platform,
                insights_url=insights_url,
                label_map=label_map,
                period_preset=period_preset,
                external_id=external_id,
                notes=notes,
            )
        )
    return result


def parse_visible_metrics(page_text: str, label_map: dict[str, str]) -> dict[str, float]:
    metrics: dict[str, float] = {}
    for label, metric_name in label_map.items():
        value = _extract_numeric_value(page_text, label)
        if value is not None:
            metrics[metric_name] = value
    return metrics


def extract_visible_date_range(page_text: str) -> str:
    normalized = _normalize_whitespace(page_text)
    match = re.search(
        r"([A-Z][a-z]{2,8} \d{1,2}, \d{4}\s*[-–]\s*[A-Z][a-z]{2,8} \d{1,2}, \d{4})",
        normalized,
    )
    if match:
        return match.group(1).replace("–", "-")
    return ""


def record_to_social_snapshot(record: MetaCapturedRecord) -> "SocialProfileSnapshot":
    from ga_reporter.dashboard_data import SocialProfileSnapshot

    notes = record.notes
    if record.visible_date_range:
        suffix = f"Visible range: {record.visible_date_range}"
        notes = f"{notes} | {suffix}".strip(" |")
    if record.downloaded_files:
        suffix = f"Exports: {len(record.downloaded_files)} file(s)"
        notes = f"{notes} | {suffix}".strip(" |")
    return SocialProfileSnapshot(
        platform=record.platform,
        profile_name=record.profile_name,
        metrics=record.metrics,
        source=record.source,
        notes=notes,
    )


def load_captured_records(data_path: str) -> list[MetaCapturedRecord]:
    path = Path(data_path)
    if not path.exists():
        return []

    raw = json.loads(path.read_text(encoding="utf-8"))
    records_raw = raw.get("records")
    if not isinstance(records_raw, list):
        raise ValueError("Captured Meta data file must contain a 'records' list.")

    records: list[MetaCapturedRecord] = []
    for item in records_raw:
        metrics_raw = item.get("metrics")
        downloaded_files_raw = item.get("downloaded_files", [])
        if not isinstance(metrics_raw, dict):
            continue
        metrics = {
            str(name).strip(): float(value)
            for name, value in metrics_raw.items()
            if str(name).strip() and isinstance(value, (int, float))
        }
        downloaded_files = tuple(
            str(path).strip()
            for path in downloaded_files_raw
            if isinstance(path, str) and str(path).strip()
        )
        records.append(
            MetaCapturedRecord(
                profile_name=str(item.get("profile_name", "")).strip(),
                platform=str(item.get("platform", "")).strip(),
                metrics=metrics,
                source=str(item.get("source", "meta_business_suite_automation")).strip(),
                captured_at=str(item.get("captured_at", "")).strip(),
                visible_date_range=str(item.get("visible_date_range", "")).strip(),
                downloaded_files=downloaded_files,
                notes=str(item.get("notes", "")).strip(),
            )
        )
    return records


def save_captured_records(data_path: str, records: Iterable[MetaCapturedRecord]) -> None:
    path = Path(data_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "records": [
            {
                "profile_name": record.profile_name,
                "platform": record.platform,
                "metrics": record.metrics,
                "source": record.source,
                "captured_at": record.captured_at,
                "visible_date_range": record.visible_date_range,
                "downloaded_files": list(record.downloaded_files),
                "notes": record.notes,
            }
            for record in records
        ]
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def upsert_captured_record(
    existing: Iterable[MetaCapturedRecord], new_record: MetaCapturedRecord
) -> list[MetaCapturedRecord]:
    records = list(existing)
    replaced = False
    for index, record in enumerate(records):
        if (
            record.profile_name == new_record.profile_name
            and record.platform == new_record.platform
            and _record_day_key(record.captured_at) == _record_day_key(new_record.captured_at)
        ):
            records[index] = new_record
            replaced = True
            break
    if not replaced:
        records.append(new_record)
    return records


def make_captured_record(
    target: MetaCaptureTarget,
    page_text: str,
    downloaded_files: Iterable[str] = (),
    captured_at: datetime | None = None,
) -> MetaCapturedRecord:
    metrics = parse_visible_metrics(page_text, target.label_map)
    return MetaCapturedRecord(
        profile_name=target.profile_name,
        platform=target.platform,
        metrics=metrics,
        source="meta_business_suite_automation",
        captured_at=(captured_at or datetime.utcnow()).isoformat(timespec="seconds"),
        visible_date_range=extract_visible_date_range(page_text),
        downloaded_files=tuple(downloaded_files),
        notes=target.notes,
    )


def expand_debug_text_to_daily_records(
    *,
    target: MetaCaptureTarget,
    page_text: str,
    captured_at: datetime | None = None,
) -> list[MetaCapturedRecord]:
    visible_range = extract_visible_date_range(page_text)
    if not visible_range:
        return []

    start_date, end_date = _parse_visible_date_range_bounds(visible_range)
    labels = _extract_series_labels(page_text)
    rows = re.findall(r"Primary\t([0-9\t]+)", page_text)
    if not rows:
        return []
    if not labels or len(labels) != len(rows):
        labels = _extract_series_labels_from_primary_rows(page_text)
    if not labels:
        return []

    series_by_metric: dict[str, list[float]] = {}
    for label, row in zip(labels, rows):
        metric_name = target.label_map.get(label)
        if not metric_name:
            continue
        values = [float(part) for part in row.split("\t") if part.strip()]
        series_by_metric[metric_name] = values

    if not series_by_metric:
        return []

    days = (end_date - start_date).days + 1
    days = min(days, max(len(values) for values in series_by_metric.values()))
    records: list[MetaCapturedRecord] = []
    for offset in range(days):
        day = start_date + timedelta(days=offset)
        metrics = {
            metric_name: values[offset]
            for metric_name, values in series_by_metric.items()
            if offset < len(values)
        }
        records.append(
            MetaCapturedRecord(
                profile_name=target.profile_name,
                platform=target.platform,
                metrics=metrics,
                source="meta_business_suite_automation",
                captured_at=(captured_at or datetime.combine(day, datetime.min.time())).replace(
                    hour=12,
                    minute=0,
                    second=0,
                ).isoformat(timespec="seconds"),
                visible_date_range=visible_range,
                downloaded_files=(),
                notes=target.notes,
            )
        )
    return records


def _extract_numeric_value(text: str, label: str) -> float | None:
    patterns = [
        rf"{re.escape(label)}[\s\S]{{0,80}}?Export[\s\S]{{0,40}}?([0-9][0-9,]*(?:\.\d+)?)",
        rf"{re.escape(label)}[\s\S]{{0,40}}?([0-9][0-9,]*(?:\.\d+)?)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return float(match.group(1).replace(",", ""))
    return None


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _record_day_key(timestamp: str) -> str:
    try:
        parsed = datetime.fromisoformat(timestamp)
        return parsed.date().isoformat()
    except ValueError:
        return timestamp[:10]


def _parse_visible_date_range_bounds(visible_range: str) -> tuple[datetime.date, datetime.date]:
    start_raw, end_raw = [part.strip() for part in visible_range.split("-")]
    start_date = _parse_meta_date(start_raw)
    end_date = _parse_meta_date(end_raw)
    return start_date, end_date


def _extract_series_labels(page_text: str) -> list[str]:
    labels: list[str] = []
    candidates = {
        "views": "Views",
        "viewers": "Viewers",
        "content interactions": "Content interactions",
        "link clicks": "Link clicks",
        "visits": "Visits",
        "follows": "Follows",
        "unfollows": "Unfollows",
        "net follows": "Net follows",
        "facebook visits": "Visits",
        "facebook follows": "Follows",
        "facebook link clicks": "Link clicks",
    }
    lines = [
        line.replace("\u200b", "").replace("â€‹", "").strip()
        for line in page_text.splitlines()
    ]
    for index, line in enumerate(lines):
        if line.lower() != "export":
            continue
        probe_index = index - 1
        while probe_index >= 0:
            probe = lines[probe_index]
            if not probe:
                probe_index -= 1
                continue
            candidate = candidates.get(probe.lower())
            if candidate:
                labels.append(candidate)
            break
    return labels


def _extract_series_labels_from_primary_rows(page_text: str) -> list[str]:
    labels: list[str] = []
    candidates = _metric_label_candidates()
    lines = [
        line.replace("\u200b", "").replace("â€‹", "").strip()
        for line in page_text.splitlines()
    ]
    for index, line in enumerate(lines):
        if not line.startswith("Primary\t"):
            continue
        probe_index = index - 1
        chosen_label: str | None = None
        while probe_index >= 0 and index - probe_index <= 18:
            probe = lines[probe_index]
            normalized_probe = probe.lower()
            if normalized_probe in candidates:
                chosen_label = candidates[normalized_probe]
                break
            probe_index -= 1
        if chosen_label:
            labels.append(chosen_label)
    return labels


def _parse_meta_date(value: str):
    for fmt in ("%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Unsupported Meta date format: {value}")


def _metric_label_candidates() -> dict[str, str]:
    return {
        "views": "Views",
        "viewers": "Viewers",
        "reach": "Reach",
        "instagram reach": "Reach",
        "content interactions": "Content interactions",
        "link clicks": "Link clicks",
        "instagram link clicks": "Link clicks",
        "facebook link clicks": "Link clicks",
        "visits": "Visits",
        "facebook visits": "Visits",
        "profile visits": "Visits",
        "follows": "Follows",
        "unfollows": "Unfollows",
        "net follows": "Net follows",
    }
