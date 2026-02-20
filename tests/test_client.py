import unittest
from unittest.mock import Mock

import tests._path  # noqa: F401
from ga_reporter.client import GADataClient


class TestGADataClientLogic(unittest.TestCase):
    def test_organic_query_failure_records_warning_and_returns_zero(self) -> None:
        client = GADataClient.__new__(GADataClient)
        client._impressions_metric = "organicGoogleSearchImpressions"
        client._warnings = []

        calls = []

        def fake_fetch(property_id, metric_name, start_date, end_date, dimension_name=None):
            calls.append((metric_name, dimension_name))
            if metric_name == "activeUsers":
                return 10
            if metric_name == "organicGoogleSearchImpressions":
                raise RuntimeError("incompatible")
            raise AssertionError("unexpected metric")

        client._fetch_metric_total = Mock(side_effect=fake_fetch)  # type: ignore[attr-defined]

        visitors, impressions = client.fetch_metrics("123", "2026-02-01", "2026-02-15")

        self.assertEqual((visitors, impressions), (10, 0))
        self.assertIn(
            "Impressions query failed for property '123' in 2026-02-01 to 2026-02-15 using "
            "landingPagePlusQueryString aggregation: incompatible",
            client.get_warnings()[0],
        )
        self.assertIn(("organicGoogleSearchImpressions", "landingPagePlusQueryString"), calls)

    def test_organic_nonzero_has_no_warning(self) -> None:
        client = GADataClient.__new__(GADataClient)
        client._impressions_metric = "organicGoogleSearchImpressions"
        client._warnings = []

        def fake_fetch(property_id, metric_name, start_date, end_date, dimension_name=None):
            if metric_name == "activeUsers":
                return 5
            if metric_name == "organicGoogleSearchImpressions":
                return 15
            raise AssertionError("unexpected metric")

        client._fetch_metric_total = Mock(side_effect=fake_fetch)  # type: ignore[attr-defined]

        visitors, impressions = client.fetch_metrics("123", "2026-02-01", "2026-02-15")

        self.assertEqual((visitors, impressions), (5, 15))
        self.assertEqual(client.get_warnings(), [])

    def test_organic_zero_records_no_rows_warning(self) -> None:
        client = GADataClient.__new__(GADataClient)
        client._impressions_metric = "organicGoogleSearchImpressions"
        client._warnings = []

        def fake_fetch(property_id, metric_name, start_date, end_date, dimension_name=None):
            if metric_name == "activeUsers":
                return 7
            if metric_name == "organicGoogleSearchImpressions":
                return 0
            raise AssertionError("unexpected metric")

        client._fetch_metric_total = Mock(side_effect=fake_fetch)  # type: ignore[attr-defined]

        visitors, impressions = client.fetch_metrics("555", "2026-02-18", "2026-02-18")

        self.assertEqual((visitors, impressions), (7, 0))
        warnings = client.get_warnings()
        self.assertEqual(len(warnings), 1)
        self.assertIn("returned no rows", warnings[0])
        self.assertIn("landingPagePlusQueryString aggregation", warnings[0])


if __name__ == "__main__":
    unittest.main()
