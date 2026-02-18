import csv
import json
import tempfile
import unittest
from pathlib import Path

import tests._path  # noqa: F401
from ga_reporter.models import DateRange, MetricSummary
from ga_reporter.output import export_csv, export_json, export_text, format_text_summary


class TestOutput(unittest.TestCase):
    def setUp(self) -> None:
        self.items = [
            MetricSummary(site_name="Site A", visitors=10, impressions=20),
            MetricSummary(site_name="Site B", visitors=30, impressions=40),
        ]
        self.date_range = DateRange(start_date="2026-02-01", end_date="2026-02-15")

    def test_format_text_summary(self) -> None:
        text = format_text_summary(self.items, self.date_range)
        self.assertIn("Website Metrics Summary:", text)
        self.assertIn("Date Range: 2026-02-01 to 2026-02-15", text)
        self.assertIn("Visitors: 10", text)
        self.assertIn("Impressions: 40", text)

    def test_export_text_csv_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            txt_path = Path(tmp) / "report.txt"
            csv_path = Path(tmp) / "report.csv"
            json_path = Path(tmp) / "report.json"

            export_text(str(txt_path), "sample")
            export_csv(str(csv_path), self.items, self.date_range)
            export_json(str(json_path), self.items, self.date_range)

            self.assertTrue(txt_path.exists())
            self.assertTrue(csv_path.exists())
            self.assertTrue(json_path.exists())

            text_content = txt_path.read_text(encoding="utf-8")
            self.assertIn("sample", text_content)

            with csv_path.open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.reader(handle))
            self.assertEqual(rows[0], ["site_name", "visitors", "impressions", "start_date", "end_date"])
            self.assertEqual(rows[1][0], "Site A")

            payload = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["start_date"], "2026-02-01")
            self.assertEqual(payload["websites"][1]["impressions"], 40)


if __name__ == "__main__":
    unittest.main()
