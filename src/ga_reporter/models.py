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
