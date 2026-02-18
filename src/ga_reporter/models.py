from dataclasses import dataclass


@dataclass(frozen=True)
class PropertyConfig:
    site_name: str
    property_id: str


@dataclass(frozen=True)
class DateRange:
    start_date: str
    end_date: str


@dataclass(frozen=True)
class MetricSummary:
    site_name: str
    visitors: int
    impressions: int
    avg_daily_visitors_2025: float
    avg_daily_impressions_2025: float
    expected_visitors_for_period_2025: float
    expected_impressions_for_period_2025: float
    visitors_change_pct_vs_2025_avg: float | None
    impressions_change_pct_vs_2025_avg: float | None
