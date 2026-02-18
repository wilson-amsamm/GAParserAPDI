from typing import Optional, Protocol, Tuple


class AnalyticsMetricsClient(Protocol):
    def fetch_metrics(self, property_id: str, start_date: str, end_date: str) -> Tuple[int, int]:
        """Return (visitors, impressions) for a property/date range."""


class GADataClient:
    def __init__(
        self,
        service_account_path: Optional[str] = None,
        impressions_metric: str = "screenPageViews",
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
        self._impressions_metric = impressions_metric

    def fetch_metrics(self, property_id: str, start_date: str, end_date: str) -> Tuple[int, int]:
        # Import lazily so tests can run without google packages.
        from google.analytics.data_v1beta.types import RunReportRequest

        users_request = RunReportRequest(
            property=f"properties/{property_id}",
            metrics=[{"name": "activeUsers"}],
            date_ranges=[{"start_date": start_date, "end_date": end_date}],
        )
        impressions_request = RunReportRequest(
            property=f"properties/{property_id}",
            metrics=[{"name": self._impressions_metric}],
            date_ranges=[{"start_date": start_date, "end_date": end_date}],
        )

        users_response = self._client.run_report(users_request)
        impressions_response = self._client.run_report(impressions_request)

        visitors_raw = "0"
        if users_response.rows:
            visitors_raw = users_response.rows[0].metric_values[0].value

        impressions_raw = "0"
        if impressions_response.rows:
            impressions_raw = impressions_response.rows[0].metric_values[0].value

        return (int(visitors_raw), int(impressions_raw))
