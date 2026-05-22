import unittest
from datetime import date

import tests._path  # noqa: F401
from ga_reporter.date_utils import (
    business_week_end,
    business_week_start,
    last_completed_business_week_range,
    resolve_date_range,
    validate_date_range,
)


class TestDateUtils(unittest.TestCase):
    def test_valid_range(self) -> None:
        result = validate_date_range("2026-02-01", "2026-02-15")
        self.assertEqual(result.start_date, "2026-02-01")
        self.assertEqual(result.end_date, "2026-02-15")

    def test_invalid_format_raises(self) -> None:
        with self.assertRaises(ValueError):
            validate_date_range("02-01-2026", "2026-02-15")

    def test_end_before_start_raises(self) -> None:
        with self.assertRaises(ValueError):
            validate_date_range("2026-02-15", "2026-02-01")

    def test_resolve_range_requires_start_end(self) -> None:
        with self.assertRaises(ValueError):
            resolve_date_range("range", None, None)

    def test_resolve_daily(self) -> None:
        result = resolve_date_range("daily", None, None, today=date(2026, 2, 18))
        self.assertEqual(result.start_date, "2026-02-18")
        self.assertEqual(result.end_date, "2026-02-18")

    def test_resolve_weekly(self) -> None:
        result = resolve_date_range("weekly", None, None, today=date(2026, 2, 18))
        self.assertEqual(result.start_date, "2026-02-14")
        self.assertEqual(result.end_date, "2026-02-18")

    def test_business_week_helpers(self) -> None:
        start = business_week_start(date(2026, 2, 18))
        end = business_week_end(date(2026, 2, 18))
        self.assertEqual(start.isoformat(), "2026-02-14")
        self.assertEqual(end.isoformat(), "2026-02-20")

    def test_last_completed_business_week_range(self) -> None:
        result = last_completed_business_week_range(date(2026, 4, 6))
        self.assertEqual(result.start_date, "2026-03-28")
        self.assertEqual(result.end_date, "2026-04-03")

    def test_resolve_yearly(self) -> None:
        result = resolve_date_range("yearly", None, None, today=date(2026, 2, 18))
        self.assertEqual(result.start_date, "2025-02-19")
        self.assertEqual(result.end_date, "2026-02-18")

    def test_resolve_explicit_range(self) -> None:
        result = resolve_date_range("range", "2026-02-01", "2026-02-15")
        self.assertEqual(result.start_date, "2026-02-01")
        self.assertEqual(result.end_date, "2026-02-15")


if __name__ == "__main__":
    unittest.main()
