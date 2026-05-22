import argparse
import sys

from ga_reporter.client import GADataClient
from ga_reporter.config import load_property_config
from ga_reporter.date_utils import resolve_date_range
from ga_reporter.output import export_csv, export_json, export_text, format_text_summary
from ga_reporter.reporter import build_summary


def prompt_filter_selection() -> tuple[str, str | None, str | None]:
    print("Select date filter:")
    print("1. Daily")
    print("2. Weekly")
    print("3. Yearly")
    print("4. Range")
    choice = input("Enter option number (1-4): ").strip()

    option_map = {
        "1": "daily",
        "2": "weekly",
        "3": "yearly",
        "4": "range",
    }
    selected = option_map.get(choice)
    if not selected:
        raise ValueError("Invalid filter option. Choose 1, 2, 3, or 4.")

    if selected != "range":
        return (selected, None, None)

    start = input("Enter start date (YYYY-MM-DD): ").strip()
    end = input("Enter end date (YYYY-MM-DD): ").strip()
    return (selected, start, end)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="GA4 website metrics summary CLI")
    parser.add_argument(
        "--filter",
        choices=["daily", "weekly", "yearly", "range"],
        default="range",
        help="Date filter mode. Use 'range' with --start and --end, or choose a preset.",
    )
    parser.add_argument("--start", help="Start date (YYYY-MM-DD), required for --filter range")
    parser.add_argument("--end", help="End date (YYYY-MM-DD), required for --filter range")
    parser.add_argument(
        "--menu",
        action="store_true",
        help="Interactive menu to choose date filter by number.",
    )
    parser.add_argument(
        "--config",
        default="config/properties.json",
        help="Path to JSON config containing GA properties",
    )
    parser.add_argument(
        "--service-account",
        help="Path to a Google service account JSON key file",
    )
    parser.add_argument(
        "--impressions-metric",
        choices=["organicGoogleSearchImpressions"],
        default="organicGoogleSearchImpressions",
        help="Metric used for the 'Impressions' field in output.",
    )
    parser.add_argument("--export-txt", help="Optional path to export text report")
    parser.add_argument("--export-csv", help="Optional path to export CSV report")
    parser.add_argument("--export-json", help="Optional path to export JSON report")
    parser.add_argument(
        "--retries", type=int, default=2, help="Retries per property request after failure"
    )
    parser.add_argument(
        "--retry-delay",
        type=float,
        default=1.0,
        help="Delay between retries in seconds",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continue and output zeros when a property fails after retries",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    raw_argv = sys.argv[1:] if argv is None else argv
    args = parse_args(raw_argv)

    try:
        selected_filter = args.filter
        selected_start = args.start
        selected_end = args.end
        if not raw_argv:
            args.menu = True
        if args.menu:
            selected_filter, selected_start, selected_end = prompt_filter_selection()

        date_range = resolve_date_range(selected_filter, selected_start, selected_end)
        properties = load_property_config(args.config)
        client = GADataClient(
            service_account_path=args.service_account,
            impressions_metric=args.impressions_metric,
        )
        summary = build_summary(
            client=client,
            properties=properties,
            start_date=date_range.start_date,
            end_date=date_range.end_date,
            retries=args.retries,
            retry_delay_seconds=args.retry_delay,
            continue_on_error=args.continue_on_error,
        )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    text_summary = format_text_summary(summary, date_range)
    print(text_summary)
    if hasattr(client, "get_warnings"):
        warnings = client.get_warnings()
        if warnings:
            print("\nWarnings:")
            for warning in warnings:
                print(f"- {warning}")

    if args.export_txt:
        export_text(args.export_txt, text_summary)
    if args.export_csv:
        export_csv(args.export_csv, summary, date_range)
    if args.export_json:
        export_json(args.export_json, summary, date_range)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
