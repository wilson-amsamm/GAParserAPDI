from datetime import date, datetime, timedelta

from ga_reporter.models import DateRange


DATE_FMT = "%Y-%m-%d"
BUSINESS_WEEK_START_WEEKDAY = 5  # Saturday


def validate_date_range(start_date: str, end_date: str) -> DateRange:
    start = datetime.strptime(start_date, DATE_FMT)
    end = datetime.strptime(end_date, DATE_FMT)
    if end < start:
        raise ValueError("End date must be on or after start date.")
    return DateRange(start_date=start_date, end_date=end_date)


def business_week_start(current_day: date) -> date:
    return current_day - timedelta(days=(current_day.weekday() - BUSINESS_WEEK_START_WEEKDAY) % 7)


def business_week_end(current_day: date) -> date:
    return business_week_start(current_day) + timedelta(days=6)


def last_completed_business_week_range(today: date | None = None) -> DateRange:
    current_day = today or date.today()
    current_week_start = business_week_start(current_day)
    start = current_week_start - timedelta(days=7)
    end = current_week_start - timedelta(days=1)
    return DateRange(start_date=start.strftime(DATE_FMT), end_date=end.strftime(DATE_FMT))


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
        start = business_week_start(current_day).strftime(DATE_FMT)
        end = current_day.strftime(DATE_FMT)
        return DateRange(start_date=start, end_date=end)

    if filter_name == "yearly":
        start = (current_day - timedelta(days=364)).strftime(DATE_FMT)
        end = current_day.strftime(DATE_FMT)
        return DateRange(start_date=start, end_date=end)

    raise ValueError("Unsupported filter. Use one of: daily, weekly, yearly, range.")


def resolve_meta_date_range(
    filter_name: str,
    start_date: str | None,
    end_date: str | None,
    today: date | None = None,
) -> DateRange:
    current_day = today or date.today()
    yesterday = current_day - timedelta(days=1)

    if filter_name == "custom":
        if not start_date or not end_date:
            raise ValueError("Start and end dates are required when the custom Meta filter is used.")
        return validate_date_range(start_date, end_date)

    if filter_name == "yesterday":
        day = yesterday.strftime(DATE_FMT)
        return DateRange(start_date=day, end_date=day)

    if filter_name == "last_7_days":
        return DateRange(
            start_date=(current_day - timedelta(days=7)).strftime(DATE_FMT),
            end_date=yesterday.strftime(DATE_FMT),
        )

    if filter_name == "last_28_days":
        return DateRange(
            start_date=(current_day - timedelta(days=28)).strftime(DATE_FMT),
            end_date=yesterday.strftime(DATE_FMT),
        )

    if filter_name == "last_90_days":
        return DateRange(
            start_date=(current_day - timedelta(days=90)).strftime(DATE_FMT),
            end_date=yesterday.strftime(DATE_FMT),
        )

    if filter_name == "this_week":
        start = business_week_start(current_day)
        return DateRange(start_date=start.strftime(DATE_FMT), end_date=current_day.strftime(DATE_FMT))

    if filter_name == "this_month":
        start = current_day.replace(day=1)
        return DateRange(start_date=start.strftime(DATE_FMT), end_date=current_day.strftime(DATE_FMT))

    if filter_name == "this_year":
        start = current_day.replace(month=1, day=1)
        return DateRange(start_date=start.strftime(DATE_FMT), end_date=current_day.strftime(DATE_FMT))

    if filter_name == "last_week":
        this_week_start = business_week_start(current_day)
        start = this_week_start - timedelta(days=7)
        end = this_week_start - timedelta(days=1)
        return DateRange(start_date=start.strftime(DATE_FMT), end_date=end.strftime(DATE_FMT))

    if filter_name == "last_month":
        this_month_start = current_day.replace(day=1)
        last_month_end = this_month_start - timedelta(days=1)
        last_month_start = last_month_end.replace(day=1)
        return DateRange(
            start_date=last_month_start.strftime(DATE_FMT),
            end_date=last_month_end.strftime(DATE_FMT),
        )

    raise ValueError(
        "Unsupported Meta filter. Use one of: yesterday, last_7_days, last_28_days, "
        "last_90_days, this_week, this_month, this_year, last_week, last_month, custom."
    )
