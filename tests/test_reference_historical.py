import tempfile
import unittest
from pathlib import Path

import tests._path  # noqa: F401
from ga_reporter.reference_historical import (
    build_historical_records,
    discover_historical_series,
    load_historical_metric_series,
)


class TestReferenceHistorical(unittest.TestCase):
    def test_discover_and_load_series(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            file_path = folder / "QuadroDecorPhilippinesFB_Views2025.csv"
            file_path.write_text(
                'sep=,\n"Views"\n"Date","Primary"\n"2025-01-01T00:00:00","7"\n"2025-01-02T00:00:00","1"\n',
                encoding="utf-8",
            )
            series_files = discover_historical_series(folder)
            self.assertEqual(len(series_files), 1)
            self.assertEqual(series_files[0].profile_name, "Quadro Decor Philippines Facebook")
            self.assertEqual(series_files[0].metric_name, "views")
            values = load_historical_metric_series(series_files[0])
            self.assertEqual(values["2025-01-01"], 7.0)
            self.assertEqual(values["2025-01-02"], 1.0)

    def test_build_records_merges_metrics_by_day(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "Harmony&HomesFB_Views2026.csv").write_text(
                'sep=,\n"Views"\n"Date","Primary"\n"2026-03-19T00:00:00","12"\n',
                encoding="utf-8",
            )
            (folder / "Harmony&HomesFB_Viewers2026.csv").write_text(
                'sep=,\n"Viewers"\n"Date","Primary"\n"2026-03-19T00:00:00","5"\n',
                encoding="utf-8",
            )
            records = build_historical_records(folder)
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0].profile_name, "Harmony & Homes Facebook")
            self.assertEqual(records[0].metrics["views"], 12.0)
            self.assertEqual(records[0].metrics["viewers"], 5.0)
            self.assertEqual(records[0].source, "meta_historical_reference_csv")


if __name__ == "__main__":
    unittest.main()
