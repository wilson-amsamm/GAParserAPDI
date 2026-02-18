import csv
import json
from pathlib import Path
from typing import Iterable

from ga_reporter.models import DateRange, MetricSummary


def format_text_summary(items: Iterable[MetricSummary], date_range: DateRange) -> str:
    lines = [
        "Website Metrics Summary:",
        f"Date Range: {date_range.start_date} to {date_range.end_date}",
        "",
    ]
    for item in items:
        lines.append(f"- {item.site_name}")
        lines.append(f"  Visitors: {item.visitors}")
        lines.append(f"  Impressions: {item.impressions}")
    return "\n".join(lines)


def export_text(path: str, content: str) -> None:
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content + "\n", encoding="utf-8")


def export_csv(path: str, items: Iterable[MetricSummary], date_range: DateRange) -> None:
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with file_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["site_name", "visitors", "impressions", "start_date", "end_date"])
        for item in items:
            writer.writerow(
                [
                    item.site_name,
                    item.visitors,
                    item.impressions,
                    date_range.start_date,
                    date_range.end_date,
                ]
            )


def export_json(path: str, items: Iterable[MetricSummary], date_range: DateRange) -> None:
    payload = {
        "start_date": date_range.start_date,
        "end_date": date_range.end_date,
        "websites": [
            {
                "site_name": item.site_name,
                "visitors": item.visitors,
                "impressions": item.impressions,
            }
            for item in items
        ],
    }

    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
