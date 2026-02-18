import unittest

import tests._path  # noqa: F401
from ga_reporter.models import PropertyConfig
from ga_reporter.reporter import build_summary


class FakeClient:
    def __init__(self) -> None:
        self.calls = 0

    def fetch_metrics(self, property_id: str, start_date: str, end_date: str) -> tuple[int, int]:
        self.calls += 1
        return (int(property_id), int(property_id) + 10)


class FlakyClient:
    def __init__(self, fail_count: int) -> None:
        self.fail_count = fail_count
        self.calls = 0

    def fetch_metrics(self, property_id: str, start_date: str, end_date: str) -> tuple[int, int]:
        self.calls += 1
        if self.calls <= self.fail_count:
            raise RuntimeError("temporary failure")
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
        self.assertEqual(result[0].visitors, 1)
        self.assertEqual(result[1].impressions, 12)
        self.assertEqual(client.calls, 2)

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
        self.assertEqual(client.calls, 2)

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


if __name__ == "__main__":
    unittest.main()
