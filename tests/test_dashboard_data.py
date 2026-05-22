import json
import tempfile
import unittest
from pathlib import Path

import tests._path  # noqa: F401
from ga_reporter.dashboard_data import (
    load_meta_accounts_config,
    load_social_config,
    merge_social_profiles,
    metric_summaries_to_rows,
    social_profiles_to_rows,
    total_social_metric,
)
from ga_reporter.models import MetricSummary


class TestDashboardData(unittest.TestCase):
    def test_load_social_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "social_profiles.json"
            config_path.write_text(
                json.dumps(
                    {
                        "profiles": [
                            {
                                "platform": "meta_page_insights",
                                "profile_name": "Brand Page",
                                "source": "manual_export",
                                "metrics": {"page_followers": 123, "reach": 456},
                                "notes": "snapshot",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            profiles = load_social_config(str(config_path))
            self.assertEqual(len(profiles), 1)
            self.assertEqual(profiles[0].platform, "meta_page_insights")
            self.assertEqual(profiles[0].metrics["reach"], 456.0)

    def test_transformers(self) -> None:
        summaries = [
            MetricSummary(
                site_name="Site A",
                visitors=10,
                impressions=20,
                avg_daily_visitors_2025=1.0,
                avg_daily_impressions_2025=2.0,
                expected_visitors_for_period_2025=7.0,
                expected_impressions_for_period_2025=14.0,
                visitors_change_pct_vs_2025_avg=42.857,
                impressions_change_pct_vs_2025_avg=42.857,
            )
        ]
        ga_rows = metric_summaries_to_rows(summaries)
        self.assertEqual(ga_rows[0]["Site"], "Site A")
        self.assertEqual(ga_rows[0]["Visitors"], 10)

        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "social_profiles.json"
            config_path.write_text(
                json.dumps(
                    {
                        "profiles": [
                            {
                                "platform": "linkedin_company",
                                "profile_name": "Brand LinkedIn",
                                "metrics": {"followers": 200, "impressions": 500},
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            profiles = load_social_config(str(config_path))

        social_rows = social_profiles_to_rows(profiles)
        self.assertEqual(social_rows[0]["Platform"], "linkedin_company")
        self.assertEqual(total_social_metric(profiles, ["followers"]), 200.0)
        merged = merge_social_profiles(profiles, profiles)
        self.assertEqual(len(merged), 2)

    def test_load_meta_accounts_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "meta_accounts.json"
            config_path.write_text(
                json.dumps(
                    {
                        "accounts": [
                            {
                                "platform": "facebook_page",
                                "account_id": "123",
                                "profile_name": "Page A",
                                "metrics": ["page_impressions", "page_reach"],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            accounts = load_meta_accounts_config(str(config_path))
            self.assertEqual(len(accounts), 1)
            self.assertEqual(accounts[0].account_id, "123")
            self.assertEqual(accounts[0].metrics[0], "page_impressions")


if __name__ == "__main__":
    unittest.main()
