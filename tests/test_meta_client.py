import unittest

import tests._path  # noqa: F401
from ga_reporter.meta_client import MetaAccountConfig, MetaInsightsClient


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get(self, url, params, timeout):
        self.calls.append((url, params, timeout))
        return FakeResponse(self.payload)


class TestMetaClient(unittest.TestCase):
    def test_fetch_page_snapshot(self) -> None:
        session = FakeSession(
            {
                "data": [
                    {
                        "name": "page_impressions",
                        "values": [{"value": 10}, {"value": 15}],
                    },
                    {
                        "name": "page_fans",
                        "values": [{"value": 100}, {"value": 120}],
                    },
                ]
            }
        )
        client = MetaInsightsClient("token-123", session=session)
        account = MetaAccountConfig(
            platform="facebook_page",
            account_id="12345",
            profile_name="Page A",
            metrics=("page_impressions", "page_fans"),
        )

        snapshot = client.fetch_account_snapshot(
            account,
            since="2026-03-01",
            until="2026-03-07",
        )

        self.assertEqual(snapshot.metrics["page_impressions"], 25.0)
        self.assertEqual(snapshot.metrics["page_fans"], 120.0)
        self.assertIn("/12345/insights", session.calls[0][0])

    def test_error_payload_raises(self) -> None:
        session = FakeSession({"error": {"message": "Bad token"}})
        client = MetaInsightsClient("token-123", session=session)
        account = MetaAccountConfig(
            platform="instagram_business",
            account_id="67890",
            profile_name="IG A",
            metrics=("impressions",),
        )

        with self.assertRaises(RuntimeError):
            client.fetch_account_snapshot(
                account,
                since="2026-03-01",
                until="2026-03-07",
            )


if __name__ == "__main__":
    unittest.main()
