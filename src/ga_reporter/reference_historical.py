from __future__ import annotations

import csv
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ga_reporter.meta_capture import MetaCapturedRecord


SOURCE_MAP = {
    "Harmony&HomesFB": ("Harmony & Homes Facebook", "facebook_page"),
    "QuadroDecorPhilippinesFB": ("Quadro Decor Philippines Facebook", "facebook_page"),
    "QuadroDecorPhilippinesIG": ("Quadro Decor Philippines Instagram", "instagram_business"),
}

METRIC_MAP = {
    "Views": "views",
    "Viewers": "viewers",
    "Reach": "reach",
    "Interactions": "content_interactions",
    "Content interactions": "content_interactions",
    "Link clicks": "link_clicks",
    "Visits": "visits",
    "Facebook visits": "visits",
    "Follows": "follows",
}


@dataclass(frozen=True)
class HistoricalSeriesFile:
    path: Path
    source_key: str
    profile_name: str
    platform: str
    metric_label: str
    metric_name: str
    year: int


def discover_historical_series(directory: str | Path) -> list[HistoricalSeriesFile]:
    base_path = Path(directory)
    result: list[HistoricalSeriesFile] = []
    for path in sorted(base_path.glob("*.csv")):
        match = re.fullmatch(r"(.+?)_(.+?)(\d{4})\.csv", path.name)
        if not match:
            continue
        source_key, metric_label, year_raw = match.groups()
        source_info = SOURCE_MAP.get(source_key)
        metric_name = METRIC_MAP.get(metric_label.strip())
        if not source_info or not metric_name:
            continue
        result.append(
            HistoricalSeriesFile(
                path=path,
                source_key=source_key,
                profile_name=source_info[0],
                platform=source_info[1],
                metric_label=metric_label.strip(),
                metric_name=metric_name,
                year=int(year_raw),
            )
        )
    return result


def load_historical_metric_series(series_file: HistoricalSeriesFile) -> dict[str, float]:
    rows = _read_text_with_fallbacks(series_file.path).splitlines()
    if len(rows) < 4:
        return {}

    csv_rows = csv.reader(rows[2:])
    next(csv_rows, None)
    result: dict[str, float] = {}
    for row in csv_rows:
        if len(row) < 2:
            continue
        metric_date = row[0][:10]
        value_raw = row[1].replace(",", "").strip()
        if not metric_date:
            continue
        try:
            value = float(value_raw or "0")
        except ValueError:
            continue
        result[metric_date] = value
    return result


def build_historical_records(directory: str | Path) -> list[MetaCapturedRecord]:
    grouped_metrics: dict[tuple[str, str, str], dict[str, float]] = defaultdict(dict)
    for series_file in discover_historical_series(directory):
        series = load_historical_metric_series(series_file)
        for metric_date, value in series.items():
            grouped_metrics[(series_file.profile_name, series_file.platform, metric_date)][
                series_file.metric_name
            ] = value

    records: list[MetaCapturedRecord] = []
    for (profile_name, platform, metric_date), metrics in sorted(grouped_metrics.items()):
        start_of_day = datetime.fromisoformat(f"{metric_date}T00:00:00")
        records.append(
            MetaCapturedRecord(
                profile_name=profile_name,
                platform=platform,
                metrics=dict(metrics),
                source="meta_historical_reference_csv",
                captured_at=start_of_day.isoformat(timespec="seconds"),
                visible_date_range=str(start_of_day.year),
                notes="Imported from reference_historical CSV exports.",
            )
        )
    return records


def _read_text_with_fallbacks(path: Path) -> str:
    for encoding in ("utf-8", "utf-8-sig", "utf-16", "utf-16-le", "utf-16-be"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="latin-1")
