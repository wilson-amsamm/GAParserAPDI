from datetime import datetime
import json
import tempfile
import unittest
from pathlib import Path

import tests._path  # noqa: F401
from ga_reporter.meta_capture import (
    expand_debug_text_to_daily_records,
    extract_visible_date_range,
    load_captured_records,
    load_meta_capture_targets,
    make_captured_record,
    parse_visible_metrics,
    save_captured_records,
    upsert_captured_record,
)


SAMPLE_TEXT = """
Performance February 18, 2026 - March 17, 2026
Views
518
Viewers
176
Content interactions
1
Facebook visits
252
Follows
5
Unfollows
3
Net follows
2
"""


class TestMetaCapture(unittest.TestCase):
    def test_parse_visible_metrics(self) -> None:
        metrics = parse_visible_metrics(
            SAMPLE_TEXT,
            {
                "Views": "views",
                "Viewers": "viewers",
                "Facebook visits": "facebook_visits",
                "Net follows": "net_follows",
            },
        )
        self.assertEqual(metrics["views"], 518.0)
        self.assertEqual(metrics["viewers"], 176.0)
        self.assertEqual(metrics["facebook_visits"], 252.0)
        self.assertEqual(metrics["net_follows"], 2.0)

    def test_make_record_and_date_range(self) -> None:
        target_payload = {
            "targets": [
                {
                    "profile_name": "Page A",
                    "platform": "facebook_page",
                    "insights_url": "https://business.facebook.com/latest/insights/overview/",
                    "label_map": {"Views": "views"},
                }
            ]
        }
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "targets.json"
            config_path.write_text(json.dumps(target_payload), encoding="utf-8")
            targets = load_meta_capture_targets(str(config_path))

        record = make_captured_record(
            targets[0],
            SAMPLE_TEXT,
            downloaded_files=["data/meta_business_suite_exports/page_a_export.csv"],
            captured_at=datetime(2026, 3, 18, 16, 0, 0),
        )
        self.assertEqual(targets[0].period_preset, "weekly")
        self.assertEqual(record.metrics["views"], 518.0)
        self.assertEqual(record.visible_date_range, "February 18, 2026 - March 17, 2026")
        self.assertEqual(record.downloaded_files[0], "data/meta_business_suite_exports/page_a_export.csv")
        self.assertEqual(extract_visible_date_range(SAMPLE_TEXT), record.visible_date_range)

    def test_save_load_and_upsert(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "records.json"
            first = make_captured_record(
                load_meta_capture_targets_from_memory(),
                SAMPLE_TEXT,
                captured_at=datetime(2026, 3, 18, 16, 0, 0),
            )
            records = upsert_captured_record([], first)
            save_captured_records(str(output_path), records)
            loaded = load_captured_records(str(output_path))
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0].metrics["views"], 518.0)
            self.assertEqual(len(loaded[0].downloaded_files), 0)

    def test_expand_debug_text_to_daily_records(self) -> None:
        debug_text = """
Insights
Facebook
Last 7 days: Mar 12, 2026 - Mar 18, 2026
Views
â€‹
Export
431
Primary\t217\t69\t14\t40\t72\t12\t7
Viewers
â€‹
Export
60
Primary\t35\t7\t8\t3\t10\t5\t3
Content interactions
â€‹
Export
7
Primary\t3\t1\t1\t0\t2\t0\t0
Link clicks
â€‹
Export
1
Primary\t0\t0\t0\t0\t1\t0\t0
Visits
â€‹
Export
74
Primary\t23\t6\t0\t8\t24\t8\t5
Follows
â€‹
Export
0
Primary\t0\t0\t0\t0\t0\t0\t0
"""
        records = expand_debug_text_to_daily_records(
            target=load_meta_capture_targets_from_memory(),
            page_text=debug_text,
        )
        self.assertEqual(len(records), 7)
        self.assertEqual(records[0].metrics["views"], 217.0)
        self.assertEqual(records[0].metrics["facebook_visits"], 23.0)
        self.assertEqual(records[-1].metrics["views"], 7.0)


def load_meta_capture_targets_from_memory():
    from ga_reporter.meta_capture import MetaCaptureTarget

    return MetaCaptureTarget(
        profile_name="Page A",
        platform="facebook_page",
        insights_url="https://business.facebook.com/latest/insights/overview/",
        label_map={
            "Views": "views",
            "Viewers": "viewers",
            "Content interactions": "content_interactions",
            "Link clicks": "link_clicks",
            "Visits": "facebook_visits",
            "Follows": "follows",
        },
    )


if __name__ == "__main__":
    unittest.main()
