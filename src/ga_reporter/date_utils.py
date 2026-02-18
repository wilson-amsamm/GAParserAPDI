from datetime import date, datetime, timedelta

from ga_reporter.models import DateRange


DATE_FMT = "%Y-%m-%d"


def validate_date_range(start_date: str, end_date: str) -> DateRange:
    start = datetime.strptime(start_date, DATE_FMT)
    end = datetime.strptime(end_date, DATE_FMT)
    if end < start:
        raise ValueError("End date must be on or after start date.")
    return DateRange(start_date=start_date, end_date=end_date)


def resolve_date_range(
    filter_name: str,
    start_date: str | None,
    end_date: str | None,
    today: date | None = None,
) -> DateRange:
    current_day = today or date.today()

    if filter_name == "range":
        if not start_date or not end_date:
            raise ValueError("--start and --end are required when --filter range is used.")
        return validate_date_range(start_date, end_date)

    if filter_name == "daily":
        day = current_day.strftime(DATE_FMT)
        return DateRange(start_date=day, end_date=day)

    if filter_name == "weekly":
        start = (current_day - timedelta(days=6)).strftime(DATE_FMT)
        end = current_day.strftime(DATE_FMT)
        return DateRange(start_date=start, end_date=end)

    if filter_name == "monthly":
        start = (current_day - timedelta(days=29)).strftime(DATE_FMT)
        end = current_day.strftime(DATE_FMT)
        return DateRange(start_date=start, end_date=end)

    raise ValueError("Unsupported filter. Use one of: daily, weekly, monthly, range.")
