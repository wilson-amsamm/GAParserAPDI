import time
from datetime import datetime
from typing import Iterable, List

from ga_reporter.client import AnalyticsMetricsClient
from ga_reporter.models import MetricSummary, PropertyConfig


LAST_YEAR_START = "2025-01-01"
LAST_YEAR_END = "2025-12-31"
LAST_YEAR_DAYS = 365


def _days_inclusive(start_date: str, end_date: str) -> int:
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    return (end - start).days + 1


def _pct_change(current_value: float, baseline_value: float) -> float | None:
    if baseline_value == 0:
        if current_value == 0:
            return 0.0
        return None
    return ((current_value - baseline_value) / baseline_value) * 100.0


def build_summary(
    client: AnalyticsMetricsClient,
    properties: Iterable[PropertyConfig],
    start_date: str,
    end_date: str,
    retries: int = 2,
    retry_delay_seconds: float = 1.0,
    continue_on_error: bool = False,
) -> List[MetricSummary]:
    summaries: List[MetricSummary] = []
    period_days = _days_inclusive(start_date, end_date)

    for item in properties:
        attempt = 0
        while True:
            try:
                visitors, impressions = client.fetch_metrics(
                    property_id=item.property_id,
                    start_date=start_date,
                    end_date=end_date,
                )
                visitors_2025, impressions_2025 = client.fetch_metrics(
                    property_id=item.property_id,
                    start_date=LAST_YEAR_START,
                    end_date=LAST_YEAR_END,
                )

                avg_daily_visitors_2025 = visitors_2025 / LAST_YEAR_DAYS
                avg_daily_impressions_2025 = impressions_2025 / LAST_YEAR_DAYS

                expected_visitors_for_period_2025 = avg_daily_visitors_2025 * period_days
                expected_impressions_for_period_2025 = avg_daily_impressions_2025 * period_days

                visitors_change_pct_vs_2025_avg = _pct_change(
                    visitors, expected_visitors_for_period_2025
                )
                impressions_change_pct_vs_2025_avg = _pct_change(
                    impressions, expected_impressions_for_period_2025
                )

                summaries.append(
                    MetricSummary(
                        site_name=item.site_name,
                        visitors=visitors,
                        impressions=impressions,
                        avg_daily_visitors_2025=avg_daily_visitors_2025,
                        avg_daily_impressions_2025=avg_daily_impressions_2025,
                        expected_visitors_for_period_2025=expected_visitors_for_period_2025,
                        expected_impressions_for_period_2025=expected_impressions_for_period_2025,
                        visitors_change_pct_vs_2025_avg=visitors_change_pct_vs_2025_avg,
                        impressions_change_pct_vs_2025_avg=impressions_change_pct_vs_2025_avg,
                    )
                )
                break
            except Exception as exc:
                last_error = (
                    f"site='{item.site_name}', property_id='{item.property_id}'"
                )
                attempt += 1
                if attempt > retries:
                    if continue_on_error:
                        summaries.append(
                            MetricSummary(
                                site_name=item.site_name,
                                visitors=0,
                                impressions=0,
                                avg_daily_visitors_2025=0.0,
                                avg_daily_impressions_2025=0.0,
                                expected_visitors_for_period_2025=0.0,
                                expected_impressions_for_period_2025=0.0,
                                visitors_change_pct_vs_2025_avg=0.0,
                                impressions_change_pct_vs_2025_avg=0.0,
                            )
                        )
                        break
                    raise RuntimeError(
                        f"Failed to fetch metrics for {last_error} after {attempt} attempts."
                    ) from exc
                time.sleep(retry_delay_seconds)
    return summaries
