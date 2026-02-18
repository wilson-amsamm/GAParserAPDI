import time
from typing import Iterable, List

from ga_reporter.client import AnalyticsMetricsClient
from ga_reporter.models import MetricSummary, PropertyConfig


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
    for item in properties:
        attempt = 0
        while True:
            try:
                visitors, impressions = client.fetch_metrics(
                    property_id=item.property_id,
                    start_date=start_date,
                    end_date=end_date,
                )
                summaries.append(
                    MetricSummary(
                        site_name=item.site_name,
                        visitors=visitors,
                        impressions=impressions,
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
                            MetricSummary(site_name=item.site_name, visitors=0, impressions=0)
                        )
                        break
                    raise RuntimeError(
                        f"Failed to fetch metrics for {last_error} after {attempt} attempts."
                    ) from exc
                time.sleep(retry_delay_seconds)
    return summaries
