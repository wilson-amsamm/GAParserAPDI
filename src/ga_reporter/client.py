from typing import Optional, Protocol, Tuple


class AnalyticsMetricsClient(Protocol):
    def fetch_metrics(self, property_id: str, start_date: str, end_date: str) -> Tuple[int, int]:
        """Return (visitors, impressions) for a property/date range."""


class GADataClient:
    def __init__(
        self,
        service_account_path: Optional[str] = None,
        impressions_metric: str = "organicGoogleSearchImpressions",
    ) -> None:
        try:
            from google.analytics.data_v1beta import BetaAnalyticsDataClient
            from google.oauth2 import service_account
        except ImportError as exc:
            raise ImportError(
                "Missing dependency. Install with: pip install -r requirements.txt"
            ) from exc

        credentials = None
        if service_account_path:
            credentials = service_account.Credentials.from_service_account_file(
                service_account_path
            )

        self._client = BetaAnalyticsDataClient(credentials=credentials)
        if impressions_metric != "organicGoogleSearchImpressions":
            raise ValueError(
                "Only 'organicGoogleSearchImpressions' is supported for impressions."
            )
        self._impressions_metric = impressions_metric
        self._warnings: list[str] = []

    def get_warnings(self) -> list[str]:
        return list(self._warnings)

    def _record_warning(self, message: str) -> None:
        if message not in self._warnings:
            self._warnings.append(message)

    def _fetch_metric_total(
        self,
        property_id: str,
        metric_name: str,
        start_date: str,
        end_date: str,
        dimension_name: str | None = None,
    ) -> int:
        # Import lazily so tests can run without google packages.
        from google.analytics.data_v1beta.types import RunReportRequest

        request_kwargs = {
            "property": f"properties/{property_id}",
            "metrics": [{"name": metric_name}],
            "date_ranges": [{"start_date": start_date, "end_date": end_date}],
        }
        if dimension_name:
            request_kwargs["dimensions"] = [{"name": dimension_name}]
            request_kwargs["limit"] = 10000

        response = self._client.run_report(RunReportRequest(**request_kwargs))
        if not response.rows:
            return 0

        if not dimension_name:
            return int(response.rows[0].metric_values[0].value)
        return sum(int(row.metric_values[0].value) for row in response.rows)

    def fetch_metrics(self, property_id: str, start_date: str, end_date: str) -> Tuple[int, int]:
        visitors = self._fetch_metric_total(
            property_id=property_id,
            metric_name="activeUsers",
            start_date=start_date,
            end_date=end_date,
            dimension_name=None,
        )

        try:
            impressions = self._fetch_metric_total(
                property_id=property_id,
                metric_name=self._impressions_metric,
                start_date=start_date,
                end_date=end_date,
                dimension_name="landingPagePlusQueryString",
            )
            if impressions == 0:
                self._record_warning(
                    f"Impressions returned no rows for property '{property_id}' in "
                    f"{start_date} to {end_date} using landingPagePlusQueryString aggregation."
                )
        except Exception as exc:
            impressions = 0
            self._record_warning(
                f"Impressions query failed for property '{property_id}' in {start_date} to "
                f"{end_date} using landingPagePlusQueryString aggregation: {exc}"
            )

        return (visitors, impressions)
