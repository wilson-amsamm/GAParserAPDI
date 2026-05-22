import unittest

import tests._path  # noqa: F401
from ga_reporter.dashboard_ui import _build_tiktok_detail_dataframe_from_postgres


class TestDashboardUiTikTok(unittest.TestCase):
    def test_postgres_detail_skips_multi_day_rows(self) -> None:
        rows = [
            {
                "profile_name": "TikTok Shop PH",
                "metric_date": "2025-01-19",
                "gross_revenue": 1530.0,
                "items_sold": 11.0,
                "page_views": 435.0,
                "visitors": 251.0,
                "conversion_rate": 3.59,
                "capture_source": "tiktok_seller_weekly_backfill",
                "visible_date_range": "Jan 13, 2025 - Jan 19, 2025",
            },
            {
                "profile_name": "TikTok Shop PH",
                "metric_date": "2026-04-20",
                "gross_revenue": 0.0,
                "items_sold": 0.0,
                "page_views": 81.0,
                "visitors": 62.0,
                "conversion_rate": 0.0,
                "capture_source": "tiktok_seller_daily_backfill",
                "visible_date_range": "Apr 20, 2026",
            },
        ]

        detail_df = _build_tiktok_detail_dataframe_from_postgres(rows)

        self.assertEqual(len(detail_df), 1)
        self.assertEqual(detail_df.iloc[0]["Date"], "Apr 20, 2026")
        self.assertEqual(int(detail_df.iloc[0]["Visitors"]), 62)


if __name__ == "__main__":
    unittest.main()
