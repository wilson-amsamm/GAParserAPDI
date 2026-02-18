import unittest

import tests._path  # noqa: F401
from ga_reporter.models import PropertyConfig
from ga_reporter.reporter import build_summary


class FakeClient:
    def __init__(self) -> None:
        self.calls = 0

    def fetch_metrics(self, property_id: str, start_date: str, end_date: str) -> tuple[int, int]:
        self.calls += 1
        if start_date == "2025-01-01" and end_date == "2025-12-31":
            # Yearly baseline totals.
            return (365, 730)
        # Current range totals.
        return (10, 20)


class FlakyClient:
    def __init__(self, fail_count: int) -> None:
        self.fail_count = fail_count
        self.calls = 0

    def fetch_metrics(self, property_id: str, start_date: str, end_date: str) -> tuple[int, int]:
        self.calls += 1
        if self.calls <= self.fail_count:
            raise RuntimeError("temporary failure")
        if start_date == "2025-01-01" and end_date == "2025-12-31":
            return (365, 730)
        return (5, 15)


class AlwaysFailClient:
    def fetch_metrics(self, property_id: str, start_date: str, end_date: str) -> tuple[int, int]:
        raise RuntimeError("permanent failure")


class TestReporter(unittest.TestCase):
    def test_build_summary_success(self) -> None:
        client = FakeClient()
        properties = [
            PropertyConfig(site_name="A", property_id="1"),
            PropertyConfig(site_name="B", property_id="2"),
        ]

        result = build_summary(client, properties, "2026-02-01", "2026-02-15")
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].visitors, 10)
        self.assertEqual(result[1].impressions, 20)
        self.assertAlmostEqual(result[0].avg_daily_visitors_2025, 1.0)
        self.assertAlmostEqual(result[0].expected_visitors_for_period_2025, 15.0)
        self.assertAlmostEqual(result[0].visitors_change_pct_vs_2025_avg, -33.3333, places=3)
        self.assertEqual(client.calls, 4)

    def test_retry_then_success(self) -> None:
        client = FlakyClient(fail_count=1)
        properties = [PropertyConfig(site_name="A", property_id="1")]

        result = build_summary(
            client,
            properties,
            "2026-02-01",
            "2026-02-15",
            retries=2,
            retry_delay_seconds=0,
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].visitors, 5)
        self.assertEqual(client.calls, 3)

    def test_continue_on_error_outputs_zeroes(self) -> None:
        client = AlwaysFailClient()
        properties = [PropertyConfig(site_name="A", property_id="1")]

        result = build_summary(
            client,
            properties,
            "2026-02-01",
            "2026-02-15",
            retries=1,
            retry_delay_seconds=0,
            continue_on_error=True,
        )
        self.assertEqual(result[0].visitors, 0)
        self.assertEqual(result[0].impressions, 0)
        self.assertEqual(result[0].visitors_change_pct_vs_2025_avg, 0.0)


if __name__ == "__main__":
    unittest.main()
