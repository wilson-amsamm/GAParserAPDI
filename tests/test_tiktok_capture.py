import json
import tempfile
import unittest
from pathlib import Path

from ga_reporter.tiktok_capture import (
    extract_visible_date_range,
    load_tiktok_capture_targets,
    make_captured_record,
    metric_cards_present,
    parse_visible_date_range_bounds,
    parse_visible_metrics,
    visible_date_range_is_single_day,
)


class TikTokCaptureTests(unittest.TestCase):
    def test_parse_visible_metrics_extracts_expected_fields(self) -> None:
        page_text = """
        Last 7 days: Mar 16, 2026 - Mar 22, 2026
        Gross revenue ₱746
        Items sold 6
        Page views 532
        Visitors 314
        Conversion rate 1.59%
        """
        metrics = parse_visible_metrics(page_text)
        self.assertEqual(metrics["gross_revenue"], 746.0)
        self.assertEqual(metrics["items_sold"], 6.0)
        self.assertEqual(metrics["page_views"], 532.0)
        self.assertEqual(metrics["visitors"], 314.0)
        self.assertEqual(metrics["conversion_rate"], 1.59)

    def test_extract_visible_date_range(self) -> None:
        page_text = "Last 7 days: Mar 16, 2026 - Mar 22, 2026"
        self.assertEqual(extract_visible_date_range(page_text), "Mar 16, 2026 - Mar 22, 2026")

    def test_extract_visible_date_range_single_day(self) -> None:
        page_text = "Yesterday Mar 30, 2026 Gross revenue ₱136.76"
        self.assertEqual(extract_visible_date_range(page_text), "Mar 30, 2026")

    def test_parse_visible_metrics_supports_key_metrics_layout(self) -> None:
        page_text = """
        Key metrics
        Compare Apr 30, 2026 - Apr 30, 2026
        GMV â‚± 156 .00
        Items sold 1
        SKU orders 1
        Orders 1
        Customers 1
        Visitors 86
        Product impressions 3,225
        Unique product impressions 1,691
        """
        metrics = parse_visible_metrics(page_text)
        self.assertEqual(metrics["gross_revenue"], 156.0)
        self.assertEqual(metrics["items_sold"], 1.0)
        self.assertEqual(metrics["sku_orders"], 1.0)
        self.assertEqual(metrics["orders"], 1.0)
        self.assertEqual(metrics["customers"], 1.0)
        self.assertEqual(metrics["visitors"], 86.0)
        self.assertEqual(metrics["page_views"], 3225.0)
        self.assertEqual(metrics["unique_product_impressions"], 1691.0)
        self.assertEqual(metrics["conversion_rate"], 1.16)

    def test_metric_cards_present_supports_key_metrics_layout(self) -> None:
        page_text = """
        Key metrics
        GMV â‚±156.00
        Items sold 1
        SKU orders 1
        Orders 1
        """
        self.assertTrue(metric_cards_present(page_text))

    def test_parse_visible_metrics_supports_key_metrics_no_data_layout(self) -> None:
        page_text = """
        Key metrics
        -
        Compare
        Updated on: May 14, 2026 3:40 PM
        No Data
        GMV breakdown
        By content type
        By order source
        No Data
        """
        metrics = parse_visible_metrics(page_text)
        self.assertEqual(metrics["gross_revenue"], 0.0)
        self.assertEqual(metrics["items_sold"], 0.0)
        self.assertEqual(metrics["page_views"], 0.0)
        self.assertEqual(metrics["visitors"], 0.0)
        self.assertEqual(metrics["conversion_rate"], 0.0)

    def test_metric_cards_present_supports_key_metrics_no_data_layout(self) -> None:
        page_text = """
        Key metrics
        Compare
        No Data
        GMV breakdown
        No Data
        """
        self.assertTrue(metric_cards_present(page_text))

    def test_parse_visible_date_range_bounds_single_day(self) -> None:
        start_date, end_date = parse_visible_date_range_bounds("Mar 30, 2026")
        self.assertEqual(start_date.isoformat(), "2026-03-30")
        self.assertEqual(end_date.isoformat(), "2026-03-30")
        self.assertTrue(visible_date_range_is_single_day("Mar 30, 2026"))
        self.assertFalse(visible_date_range_is_single_day("Mar 16, 2026 - Mar 22, 2026"))

    def test_parse_visible_date_range_bounds_single_day_iso_format(self) -> None:
        start_date, end_date = parse_visible_date_range_bounds("2026-05-01")
        self.assertEqual(start_date.isoformat(), "2026-05-01")
        self.assertEqual(end_date.isoformat(), "2026-05-01")
        self.assertTrue(visible_date_range_is_single_day("2026-05-01"))

    def test_load_targets(self) -> None:
        payload = {
            "targets": [
                {
                    "profile_name": "TikTok Shop PH",
                    "overview_url": "https://seller-ph.tiktok.com/compass/data-overview?shop_region=PH",
                }
            ]
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "tiktok_targets.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            targets = load_tiktok_capture_targets(str(path))
        self.assertEqual(targets[0].profile_name, "TikTok Shop PH")

    def test_make_captured_record(self) -> None:
        payload = {
            "targets": [
                {
                    "profile_name": "TikTok Shop PH",
                    "overview_url": "https://seller-ph.tiktok.com/compass/data-overview?shop_region=PH",
                }
            ]
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "tiktok_targets.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            target = load_tiktok_capture_targets(str(path))[0]
            record = make_captured_record(
                target,
                "Last 7 days: Mar 16, 2026 - Mar 22, 2026 Gross revenue ₱746 Items sold 6 Page views 532 Visitors 314 Conversion rate 1.59%",
            )
        self.assertEqual(record.profile_name, "TikTok Shop PH")
        self.assertEqual(record.visible_date_range, "Mar 16, 2026 - Mar 22, 2026")
        self.assertEqual(record.metrics["visitors"], 314.0)

    def test_make_captured_record_uses_visible_single_day_for_timestamp(self) -> None:
        payload = {
            "targets": [
                {
                    "profile_name": "TikTok Shop PH",
                    "overview_url": "https://seller-ph.tiktok.com/compass/data-overview?shop_region=PH",
                }
            ]
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "tiktok_targets.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            target = load_tiktok_capture_targets(str(path))[0]
            record = make_captured_record(
                target,
                "Mar 30, 2026 Gross revenue ₱136.76 Items sold 2 Page views 59 Visitors 33 Conversion rate 6.06%",
            )
        self.assertEqual(record.visible_date_range, "Mar 30, 2026")
        self.assertTrue(record.captured_at.startswith("2026-03-30T12:00:00"))


if __name__ == "__main__":
    unittest.main()
