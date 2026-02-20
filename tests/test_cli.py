import unittest
from unittest.mock import patch
from unittest.mock import Mock

import tests._path  # noqa: F401
from ga_reporter.models import DateRange, MetricSummary, PropertyConfig


def make_summary(site: str = "Site A") -> MetricSummary:
    return MetricSummary(
        site_name=site,
        visitors=1,
        impressions=2,
        avg_daily_visitors_2025=3.0,
        avg_daily_impressions_2025=4.0,
        expected_visitors_for_period_2025=5.0,
        expected_impressions_for_period_2025=6.0,
        visitors_change_pct_vs_2025_avg=-80.0,
        impressions_change_pct_vs_2025_avg=-66.67,
    )


class TestCLI(unittest.TestCase):
    @patch("ga_reporter.cli.export_json")
    @patch("ga_reporter.cli.export_csv")
    @patch("ga_reporter.cli.export_text")
    @patch("builtins.print")
    @patch("ga_reporter.cli.format_text_summary")
    @patch("ga_reporter.cli.build_summary")
    @patch("ga_reporter.cli.GADataClient")
    @patch("ga_reporter.cli.load_property_config")
    @patch("ga_reporter.cli.resolve_date_range")
    def test_main_success(
        self,
        mock_resolve_date_range,
        mock_load,
        mock_client_cls,
        mock_build,
        mock_format,
        _mock_print,
        mock_export_text,
        mock_export_csv,
        mock_export_json,
    ) -> None:
        mock_resolve_date_range.return_value = DateRange(
            start_date="2026-02-01", end_date="2026-02-15"
        )
        mock_load.return_value = [PropertyConfig(site_name="Site A", property_id="1")]
        mock_client_cls.return_value = object()
        mock_build.return_value = [make_summary()]
        mock_format.return_value = "Website Metrics Summary:\n- Site A"

        from ga_reporter.cli import main

        code = main(
            [
                "--start",
                "2026-02-01",
                "--end",
                "2026-02-15",
                "--export-txt",
                "reports/report.txt",
                "--export-csv",
                "reports/report.csv",
                "--export-json",
                "reports/report.json",
            ]
        )

        self.assertEqual(code, 0)
        mock_export_text.assert_called_once()
        mock_export_csv.assert_called_once()
        mock_export_json.assert_called_once()

    @patch("builtins.print")
    @patch("ga_reporter.cli.format_text_summary")
    @patch("ga_reporter.cli.build_summary")
    @patch("ga_reporter.cli.GADataClient")
    @patch("ga_reporter.cli.load_property_config")
    @patch("ga_reporter.cli.resolve_date_range")
    def test_main_daily_filter_success(
        self,
        mock_resolve_date_range,
        mock_load,
        mock_client_cls,
        mock_build,
        mock_format,
        _mock_print,
    ) -> None:
        mock_resolve_date_range.return_value = DateRange(
            start_date="2026-02-18", end_date="2026-02-18"
        )
        mock_load.return_value = [PropertyConfig(site_name="Site A", property_id="1")]
        mock_client_cls.return_value = object()
        mock_build.return_value = [make_summary()]
        mock_format.return_value = "Website Metrics Summary:\n- Site A"

        from ga_reporter.cli import main

        code = main(["--filter", "daily"])

        self.assertEqual(code, 0)
        mock_resolve_date_range.assert_called_once_with("daily", None, None)
        mock_client_cls.assert_called_once_with(
            service_account_path=None,
            impressions_metric="organicGoogleSearchImpressions",
        )

    @patch("builtins.input", side_effect=["4", "2026-02-01", "2026-02-15"])
    @patch("builtins.print")
    @patch("ga_reporter.cli.format_text_summary")
    @patch("ga_reporter.cli.build_summary")
    @patch("ga_reporter.cli.GADataClient")
    @patch("ga_reporter.cli.load_property_config")
    @patch("ga_reporter.cli.resolve_date_range")
    def test_main_menu_range_success(
        self,
        mock_resolve_date_range,
        mock_load,
        mock_client_cls,
        mock_build,
        mock_format,
        _mock_print,
        _mock_input,
    ) -> None:
        mock_resolve_date_range.return_value = DateRange(
            start_date="2026-02-01", end_date="2026-02-15"
        )
        mock_load.return_value = [PropertyConfig(site_name="Site A", property_id="1")]
        mock_client_cls.return_value = object()
        mock_build.return_value = [make_summary()]
        mock_format.return_value = "Website Metrics Summary:\n- Site A"

        from ga_reporter.cli import main

        code = main(["--menu"])

        self.assertEqual(code, 0)
        mock_resolve_date_range.assert_called_once_with("range", "2026-02-01", "2026-02-15")

    @patch("builtins.input", side_effect=["1"])
    @patch("builtins.print")
    @patch("ga_reporter.cli.format_text_summary")
    @patch("ga_reporter.cli.build_summary")
    @patch("ga_reporter.cli.GADataClient")
    @patch("ga_reporter.cli.load_property_config")
    @patch("ga_reporter.cli.resolve_date_range")
    def test_main_no_args_defaults_to_menu(
        self,
        mock_resolve_date_range,
        mock_load,
        mock_client_cls,
        mock_build,
        mock_format,
        _mock_print,
        _mock_input,
    ) -> None:
        mock_resolve_date_range.return_value = DateRange(
            start_date="2026-02-18", end_date="2026-02-18"
        )
        mock_load.return_value = [PropertyConfig(site_name="Site A", property_id="1")]
        mock_client_cls.return_value = object()
        mock_build.return_value = [make_summary()]
        mock_format.return_value = "Website Metrics Summary:\n- Site A"

        from ga_reporter.cli import main

        code = main([])

        self.assertEqual(code, 0)
        mock_resolve_date_range.assert_called_once_with("daily", None, None)

    @patch("builtins.print")
    @patch("ga_reporter.cli.format_text_summary")
    @patch("ga_reporter.cli.build_summary")
    @patch("ga_reporter.cli.GADataClient")
    @patch("ga_reporter.cli.load_property_config")
    @patch("ga_reporter.cli.resolve_date_range")
    def test_main_custom_impressions_metric(
        self,
        mock_resolve_date_range,
        mock_load,
        mock_client_cls,
        mock_build,
        mock_format,
        _mock_print,
    ) -> None:
        mock_resolve_date_range.return_value = DateRange(
            start_date="2026-02-01", end_date="2026-02-15"
        )
        mock_load.return_value = [PropertyConfig(site_name="Site A", property_id="1")]
        mock_client_cls.return_value = object()
        mock_build.return_value = [make_summary()]
        mock_format.return_value = "Website Metrics Summary:\n- Site A"

        from ga_reporter.cli import main

        code = main(
            [
                "--filter",
                "range",
                "--start",
                "2026-02-01",
                "--end",
                "2026-02-15",
                "--impressions-metric",
                "organicGoogleSearchImpressions",
            ]
        )

        self.assertEqual(code, 0)
        mock_client_cls.assert_called_once_with(
            service_account_path=None,
            impressions_metric="organicGoogleSearchImpressions",
        )

    @patch("builtins.print")
    @patch("ga_reporter.cli.format_text_summary")
    @patch("ga_reporter.cli.build_summary")
    @patch("ga_reporter.cli.GADataClient")
    @patch("ga_reporter.cli.load_property_config")
    @patch("ga_reporter.cli.resolve_date_range")
    def test_main_prints_client_warnings(
        self,
        mock_resolve_date_range,
        mock_load,
        mock_client_cls,
        mock_build,
        mock_format,
        mock_print,
    ) -> None:
        mock_resolve_date_range.return_value = DateRange(
            start_date="2026-02-01", end_date="2026-02-15"
        )
        mock_load.return_value = [PropertyConfig(site_name="Site A", property_id="1")]
        client_mock = Mock()
        client_mock.get_warnings.return_value = ["Fallback used."]
        mock_client_cls.return_value = client_mock
        mock_build.return_value = [make_summary()]
        mock_format.return_value = "Website Metrics Summary:\n- Site A"

        from ga_reporter.cli import main

        code = main(
            [
                "--filter",
                "range",
                "--start",
                "2026-02-01",
                "--end",
                "2026-02-15",
            ]
        )

        self.assertEqual(code, 0)
        mock_print.assert_any_call("\nWarnings:")
        mock_print.assert_any_call("- Fallback used.")


if __name__ == "__main__":
    unittest.main()
