import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Iterable

from ga_reporter.models import DateRange, MetricSummary


def _format_baseline(value: float) -> str:
    rounded = round(value)
    if abs(value - rounded) < 1e-9:
        return str(int(rounded))
    return f"{value:.2f}"


def _period_label(date_range: DateRange) -> str:
    start = datetime.strptime(date_range.start_date, "%Y-%m-%d")
    end = datetime.strptime(date_range.end_date, "%Y-%m-%d")
    days = (end - start).days + 1
    if days == 1:
        return "day"
    if days == 7:
        return "week"
    if days == 30:
        return "month"
    return f"{days}-day period"


def _format_rate_line(
    change_pct: float | None,
    baseline_value: float,
    metric_name: str,
    period_name: str,
) -> str:
    baseline_text = _format_baseline(baseline_value)
    if change_pct is None:
        return f"Rate: N/A from 2025 average of {baseline_text} {metric_name} per {period_name}"
    trend = "growth" if change_pct >= 0 else "decline"
    return (
        f"Rate: {abs(change_pct):.2f}% {trend} from 2025 average of "
        f"{baseline_text} {metric_name} per {period_name}"
    )


def format_text_summary(items: Iterable[MetricSummary], date_range: DateRange) -> str:
    period_name = _period_label(date_range)
    lines = [
        "Website Metrics Summary:",
        f"Date Range: {date_range.start_date} to {date_range.end_date}",
        "",
    ]
    for item in items:
        lines.append(f"- {item.site_name}")
        lines.append(f"Visitors:{item.visitors}")
        lines.append(
            _format_rate_line(
                item.visitors_change_pct_vs_2025_avg,
                item.expected_visitors_for_period_2025,
                "visitors",
                period_name,
            )
        )
        lines.append(f"Impressions:{item.impressions}")
        lines.append(
            _format_rate_line(
                item.impressions_change_pct_vs_2025_avg,
                item.expected_impressions_for_period_2025,
                "impressions",
                period_name,
            )
        )
        lines.append("")
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
        writer.writerow(
            [
                "site_name",
                "visitors",
                "impressions",
                "avg_daily_visitors_2025",
                "avg_daily_impressions_2025",
                "expected_visitors_for_period_2025",
                "expected_impressions_for_period_2025",
                "visitors_change_pct_vs_2025_avg",
                "impressions_change_pct_vs_2025_avg",
                "start_date",
                "end_date",
            ]
        )
        for item in items:
            writer.writerow(
                [
                    item.site_name,
                    item.visitors,
                    item.impressions,
                    f"{item.avg_daily_visitors_2025:.4f}",
                    f"{item.avg_daily_impressions_2025:.4f}",
                    f"{item.expected_visitors_for_period_2025:.4f}",
                    f"{item.expected_impressions_for_period_2025:.4f}",
                    "" if item.visitors_change_pct_vs_2025_avg is None else f"{item.visitors_change_pct_vs_2025_avg:.4f}",
                    ""
                    if item.impressions_change_pct_vs_2025_avg is None
                    else f"{item.impressions_change_pct_vs_2025_avg:.4f}",
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
                "avg_daily_visitors_2025": item.avg_daily_visitors_2025,
                "avg_daily_impressions_2025": item.avg_daily_impressions_2025,
                "expected_visitors_for_period_2025": item.expected_visitors_for_period_2025,
                "expected_impressions_for_period_2025": item.expected_impressions_for_period_2025,
                "visitors_change_pct_vs_2025_avg": item.visitors_change_pct_vs_2025_avg,
                "impressions_change_pct_vs_2025_avg": item.impressions_change_pct_vs_2025_avg,
            }
            for item in items
        ],
    }

    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
