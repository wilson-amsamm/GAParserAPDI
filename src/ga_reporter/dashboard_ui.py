from __future__ import annotations

from calendar import monthrange
from datetime import date

import pandas as pd
import streamlit as st

from ga_reporter.dashboard_data import SocialProfileSnapshot
from ga_reporter.date_utils import BUSINESS_WEEK_START_WEEKDAY, resolve_date_range, resolve_meta_date_range
from ga_reporter.meta_capture import MetaCapturedRecord
from ga_reporter.tiktok_capture import TikTokCapturedRecord, visible_date_range_is_single_day
from ga_reporter.viber_summary import format_viber_summary


def _business_week_start_series(series: pd.Series) -> pd.Series:
    return series - pd.to_timedelta((series.dt.weekday - BUSINESS_WEEK_START_WEEKDAY) % 7, unit="D")


def _business_week_end_series(week_start_series: pd.Series) -> pd.Series:
    return week_start_series + pd.to_timedelta(6, unit="D")


def _business_week_label(value: pd.Timestamp) -> str:
    return f"Week of {value:%b %d}"


def _build_social_detail_dataframe(records: list[MetaCapturedRecord]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for record in records:
        captured_timestamp = pd.to_datetime(record.captured_at, errors="coerce")
        if pd.isna(captured_timestamp):
            continue
        metrics = record.metrics or {}
        if not metrics:
            continue
        row_date = captured_timestamp.normalize()
        week_start = row_date - pd.to_timedelta((row_date.weekday() - BUSINESS_WEEK_START_WEEKDAY) % 7, unit="D")
        week_end = week_start + pd.Timedelta(days=6)
        rows.append(
            {
                "Page": record.profile_name,
                "Platform": record.platform,
                "Snapshot Date": row_date,
                "Week": f"{week_start:%b %d} - {week_end:%b %d, %Y}",
                "Month": row_date.strftime("%B %Y"),
                "Date": row_date.strftime("%b %d, %Y"),
                "Page Views": _pick_social_metric(metrics, "views", "page_views", "impressions", "post_impressions"),
                "Viewers": _pick_social_metric(metrics, "viewers"),
                "Reach": _pick_social_metric(metrics, "reach", "accounts_reached"),
                "Interaction": _pick_social_metric(metrics, "content_interactions", "interaction", "engaged_users"),
                "Link Clicks": _pick_social_metric(metrics, "link_clicks", "clicks"),
                "Visit": _pick_social_metric(metrics, "facebook_visits", "visits", "profile_visits"),
                "Follow": _pick_social_metric(metrics, "follows", "net_follows"),
            }
        )

    if not rows:
        return pd.DataFrame()

    detail_df = pd.DataFrame(rows).sort_values(["Snapshot Date", "Page"], ascending=[False, True])
    return detail_df.reset_index(drop=True)


def _build_social_detail_dataframe_from_postgres(rows: list[dict[str, object]]) -> pd.DataFrame:
    normalized_rows: list[dict[str, object]] = []
    for row in rows:
        snapshot_date = pd.to_datetime(row["metric_date"], errors="coerce")
        if pd.isna(snapshot_date):
            continue
        week_start = snapshot_date.normalize() - pd.to_timedelta(
            (snapshot_date.weekday() - BUSINESS_WEEK_START_WEEKDAY) % 7, unit="D"
        )
        week_end = week_start + pd.Timedelta(days=6)
        normalized_rows.append(
            {
                "Page": row["profile_name"],
                "Platform": row["platform"],
                "Snapshot Date": snapshot_date.normalize(),
                "Week": f"{week_start:%b %d} - {week_end:%b %d, %Y}",
                "Month": snapshot_date.strftime("%B %Y"),
                "Date": snapshot_date.strftime("%b %d, %Y"),
                "Page Views": int(round(float(row.get("views", 0) or 0))),
                "Viewers": int(round(float(row.get("viewers", 0) or 0))),
                "Reach": int(round(float(row.get("reach", 0) or 0))),
                "Interaction": int(round(float(row.get("content_interactions", 0) or 0))),
                "Link Clicks": int(round(float(row.get("link_clicks", 0) or 0))),
                "Visit": int(round(float(row.get("visits", 0) or 0))),
                "Follow": int(round(float(row.get("follows", 0) or 0))),
            }
        )
    if not normalized_rows:
        return pd.DataFrame()
    return (
        pd.DataFrame(normalized_rows)
        .sort_values(["Snapshot Date", "Page"], ascending=[False, True])
        .reset_index(drop=True)
    )


def _filter_social_detail_dataframe(
    detail_df: pd.DataFrame, start_date: str, end_date: str
) -> pd.DataFrame:
    start_ts = pd.Timestamp(start_date)
    end_ts = pd.Timestamp(end_date)
    mask = (detail_df["Snapshot Date"] >= start_ts) & (detail_df["Snapshot Date"] <= end_ts)
    return detail_df.loc[mask].copy()


def _build_social_summary_dataframe(detail_df: pd.DataFrame, filter_name: str) -> pd.DataFrame:
    summary_source = detail_df.copy()

    grouped = (
        summary_source.groupby(["Page"], dropna=False)
        .agg(
            StartDate=("Snapshot Date", "min"),
            EndDate=("Snapshot Date", "max"),
            TotalViews=("Page Views", "sum"),
            Reach=("Reach", "sum"),
            Interaction=("Interaction", "sum"),
            LinkClicks=("Link Clicks", "sum"),
            Visits=("Visit", "sum"),
            Follow=("Follow", "sum"),
        )
        .reset_index()
    )

    grouped["Period"] = _social_period_label(filter_name)
    grouped["Date Range"] = grouped.apply(
        lambda row: f"{row['StartDate']:%b %d, %Y} - {row['EndDate']:%b %d, %Y}",
        axis=1,
    )
    grouped = grouped[
        ["Page", "Period", "Date Range", "TotalViews", "Reach", "Interaction", "LinkClicks", "Visits", "Follow"]
    ].rename(
        columns={
            "TotalViews": "Total Views",
            "LinkClicks": "Link Clicks",
        }
    )

    numeric_columns = ["Total Views", "Reach", "Interaction", "Link Clicks", "Visits", "Follow"]
    for column in numeric_columns:
        grouped[column] = grouped[column].astype(int)

    return grouped.sort_values(["Page", "Date Range"], ascending=[True, False]).reset_index(drop=True)


def _build_page_summary_dataframe(detail_df: pd.DataFrame, filter_name: str, platform: str | None) -> pd.DataFrame:
    grouped = (
        detail_df.groupby(["Page"], dropna=False)
        .agg(
            StartDate=("Snapshot Date", "min"),
            EndDate=("Snapshot Date", "max"),
            TotalViews=("Page Views", "sum"),
            Viewers=("Viewers", "sum"),
            Reach=("Reach", "sum"),
            Interaction=("Interaction", "sum"),
            LinkClicks=("Link Clicks", "sum"),
            Visits=("Visit", "sum"),
            Follow=("Follow", "sum"),
        )
        .reset_index()
    )
    grouped["Period"] = _social_period_label(filter_name)
    grouped["Date Range"] = grouped.apply(
        lambda row: f"{row['StartDate']:%b %d, %Y} - {row['EndDate']:%b %d, %Y}",
        axis=1,
    )

    if platform == "facebook_page":
        result = grouped[
            ["Page", "Period", "Date Range", "TotalViews", "Viewers", "Interaction", "LinkClicks", "Visits", "Follow"]
        ].rename(
            columns={
                "TotalViews": "Total Views",
                "LinkClicks": "Link Clicks",
            }
        )
    else:
        result = grouped[
            ["Page", "Period", "Date Range", "TotalViews", "Reach", "Interaction", "LinkClicks", "Visits", "Follow"]
        ].rename(
            columns={
                "TotalViews": "Total Views",
                "LinkClicks": "Link Clicks",
            }
        )

    numeric_columns = [column for column in result.columns if column not in {"Page", "Period", "Date Range"}]
    for column in numeric_columns:
        result[column] = result[column].astype(int)
    return result


def _build_website_summary_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    result = df[
        [
            "Site",
            "Period",
            "Date Range",
            "Visitors",
            "Impressions",
        ]
    ].copy()
    return result


def _build_website_summary_dataframe_from_postgres(
    rows: list[dict[str, object]],
    filter_name: str,
    date_range,
) -> pd.DataFrame:
    history_df = _build_website_history_dataframe_from_postgres(rows)
    if history_df.empty:
        return pd.DataFrame(columns=["Site", "Period", "Date Range", "Visitors", "Impressions"])

    grouped = (
        history_df.groupby("Site", dropna=False)
        .agg(
            StartDate=("Metric Date", "min"),
            EndDate=("Metric Date", "max"),
            Visitors=("Visitors", "sum"),
            Impressions=("Impressions", "sum"),
        )
        .reset_index()
        .sort_values("Site", ascending=True)
        .reset_index(drop=True)
    )
    grouped["Period"] = _social_period_label(filter_name)
    grouped["Date Range"] = grouped.apply(
        lambda row: f"{row['StartDate']:%b %d, %Y} - {row['EndDate']:%b %d, %Y}",
        axis=1,
    )
    result = grouped[["Site", "Period", "Date Range", "Visitors", "Impressions"]].copy()
    result["Visitors"] = result["Visitors"].astype(int)
    result["Impressions"] = result["Impressions"].astype(int)
    return result


def _build_website_detail_dataframe_from_postgres(
    rows: list[dict[str, object]],
    filter_name: str,
    date_range,
) -> pd.DataFrame:
    result = _build_website_summary_dataframe_from_postgres(rows, filter_name, date_range)
    if result.empty:
        return result
    result["Data Source"] = "PostgreSQL Fallback"
    return result[["Site", "Period", "Date Range", "Visitors", "Impressions", "Data Source"]]


def _build_website_todate_dataframe(
    df: pd.DataFrame,
    date_range,
    summary_mode: str,
    postgres_rows: list[dict[str, object]] | None = None,
) -> pd.DataFrame:
    site_row = df.iloc[[0]].copy()
    start_ts = pd.Timestamp(date_range.start_date)
    end_ts = pd.Timestamp(date_range.end_date)
    if summary_mode == "Weekly":
        period_label = _business_week_label(pd.Timestamp(start_ts))
    else:
        period_label = start_ts.strftime("%B %Y")
    actual_visitors = int(site_row.iloc[0]["Visitors"])
    actual_impressions = int(site_row.iloc[0]["Impressions"])
    if postgres_rows:
        actual_visitors = int(sum(float(row.get("visitors", 0) or 0) for row in postgres_rows))
        actual_impressions = int(sum(float(row.get("impressions", 0) or 0) for row in postgres_rows))
    expected_visitors = float(site_row.iloc[0]["Expected Visitors For Period"])
    expected_impressions = float(site_row.iloc[0]["Expected Impressions For Period"])
    visitors_change = None if expected_visitors == 0 else ((actual_visitors - expected_visitors) / expected_visitors) * 100
    impressions_change = None if expected_impressions == 0 else ((actual_impressions - expected_impressions) / expected_impressions) * 100
    result = pd.DataFrame(
        {
            "Mode": [summary_mode],
            "Period": [period_label],
            "Date Range": [f"{start_ts:%b %d, %Y} - {end_ts:%b %d, %Y}"],
            "Visitors": [actual_visitors],
            "Impressions": [actual_impressions],
            "Visitor Pace": [
                _format_rate_ratio(
                    float(actual_visitors),
                    expected_visitors,
                )
            ],
            "Impression Pace": [
                _format_rate_ratio(
                    float(actual_impressions),
                    expected_impressions,
                )
            ],
            "Visitors Change Rate": [_format_percent_or_na(visitors_change)],
            "Impressions Change Rate": [_format_percent_or_na(impressions_change)],
        }
    )
    return result


def _build_website_history_dataframe_from_postgres(rows: list[dict[str, object]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    normalized_rows: list[dict[str, object]] = []
    for row in rows:
        metric_date = pd.to_datetime(row["metric_date"], errors="coerce")
        if pd.isna(metric_date):
            continue
        week_start = metric_date.normalize() - pd.to_timedelta(
            (metric_date.weekday() - BUSINESS_WEEK_START_WEEKDAY) % 7, unit="D"
        )
        week_end = week_start + pd.Timedelta(days=6)
        normalized_rows.append(
            {
                "Site": row["site_name"],
                "Metric Date": metric_date.normalize(),
                "Week": f"{week_start:%b %d} - {week_end:%b %d, %Y}",
                "Month": metric_date.strftime("%B %Y"),
                "Date Range Label": metric_date.strftime("%b %d, %Y"),
                "Visitors": int(round(float(row.get("visitors", 0) or 0))),
                "Impressions": int(round(float(row.get("impressions", 0) or 0))),
            }
        )
    if not normalized_rows:
        return pd.DataFrame()
    return pd.DataFrame(normalized_rows).sort_values(["Metric Date", "Site"], ascending=[False, True]).reset_index(drop=True)


def _build_website_weekly_progress_dataframe(detail_df: pd.DataFrame) -> pd.DataFrame:
    summary = (
        detail_df.assign(
            WeekStart=_business_week_start_series(detail_df["Metric Date"])
        )
        .groupby("WeekStart", dropna=False)
        .agg(
            StartDate=("Metric Date", "min"),
            EndDate=("Metric Date", "max"),
            Visitors=("Visitors", "sum"),
            Impressions=("Impressions", "sum"),
        )
        .reset_index()
        .sort_values("WeekStart", ascending=False)
        .reset_index(drop=True)
    )
    if summary.empty:
        return pd.DataFrame(columns=["Week", "Period", "Visitors", "Impressions"])
    summary["Week"] = summary["WeekStart"].apply(_business_week_label)
    summary["Period"] = summary.apply(
        lambda row: f"{row['StartDate']:%b %d} - {row['EndDate']:%b %d, %Y}",
        axis=1,
    )
    result = summary[["Week", "Period", "Visitors", "Impressions"]].copy()
    result["Visitors"] = result["Visitors"].astype(int)
    result["Impressions"] = result["Impressions"].astype(int)
    return result


def _build_website_monthly_progress_dataframe(detail_df: pd.DataFrame) -> pd.DataFrame:
    summary = (
        detail_df.assign(MonthStart=detail_df["Metric Date"].values.astype("datetime64[M]"))
        .groupby("MonthStart", dropna=False)
        .agg(
            StartDate=("Metric Date", "min"),
            EndDate=("Metric Date", "max"),
            Visitors=("Visitors", "sum"),
            Impressions=("Impressions", "sum"),
        )
        .reset_index()
        .sort_values("MonthStart", ascending=False)
        .reset_index(drop=True)
    )
    if summary.empty:
        return pd.DataFrame(columns=["Month", "Date Range", "Visitors", "Impressions"])
    summary["Month"] = summary["MonthStart"].dt.strftime("%B %Y")
    summary["Date Range"] = summary.apply(
        lambda row: f"{row['StartDate']:%b %d} - {row['EndDate']:%b %d, %Y}",
        axis=1,
    )
    result = summary[["Month", "Date Range", "Visitors", "Impressions"]].copy()
    result["Visitors"] = result["Visitors"].astype(int)
    result["Impressions"] = result["Impressions"].astype(int)
    return result


def _build_website_rate_report_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    site_row = df.iloc[[0]].copy()
    visitors = float(site_row.iloc[0]["Visitors"])
    impressions = float(site_row.iloc[0]["Impressions"])
    result = pd.DataFrame(
        {
            "Site": [site_row.iloc[0]["Site"]],
            "Visitors": [int(visitors)],
            "Impressions": [int(impressions)],
            "Visitors Change Rate": [_format_percent_or_na(site_row.iloc[0]["Visitors Change % vs 2025 Avg"])],
            "Impressions Change Rate": [_format_percent_or_na(site_row.iloc[0]["Impressions Change % vs 2025 Avg"])],
            "Visitor Pace": [
                _format_rate_ratio(
                    visitors,
                    float(site_row.iloc[0]["Expected Visitors For Period"]),
                )
            ],
            "Impression Pace": [
                _format_rate_ratio(
                    impressions,
                    float(site_row.iloc[0]["Expected Impressions For Period"]),
                )
            ],
            "Impressions Per Visitor": [_format_rate_ratio(impressions, visitors)],
        }
    )
    return result


def _build_website_weekly_comparison_dataframe(detail_df: pd.DataFrame) -> pd.DataFrame:
    summary = (
        detail_df.assign(
            WeekStart=_business_week_start_series(detail_df["Metric Date"])
        )
        .groupby("WeekStart", dropna=False)
        .agg(
            StartDate=("Metric Date", "min"),
            EndDate=("Metric Date", "max"),
            Visitors=("Visitors", "sum"),
            Impressions=("Impressions", "sum"),
        )
        .reset_index()
        .sort_values("WeekStart", ascending=False)
        .reset_index(drop=True)
    )
    if summary.empty:
        return pd.DataFrame(
            columns=[
                "Week",
                "Period",
                "Visitor Growth Rate",
                "Visitor Trend",
                "Impression Growth Rate",
                "Impression Trend",
                "Visitor Conversion Rate",
            ]
        )
    summary["Week"] = summary["WeekStart"].apply(_business_week_label)
    summary["Period"] = summary.apply(lambda row: f"{row['StartDate']:%b %d} - {row['EndDate']:%b %d, %Y}", axis=1)
    summary["Visitor Growth Rate"] = _build_change_rate_series(summary["Visitors"])
    summary["Impression Growth Rate"] = _build_change_rate_series(summary["Impressions"])
    summary["Visitor Trend"] = summary["Visitor Growth Rate"].apply(_format_growth_status)
    summary["Impression Trend"] = summary["Impression Growth Rate"].apply(_format_growth_status)
    summary["Visitor Conversion Rate"] = [
        _format_rate_percent(float(visitors), float(impressions))
        for visitors, impressions in zip(summary["Visitors"], summary["Impressions"])
    ]
    return summary[
        [
            "Week",
            "Period",
            "Visitor Growth Rate",
            "Visitor Trend",
            "Impression Growth Rate",
            "Impression Trend",
            "Visitor Conversion Rate",
        ]
    ].copy()


def _build_website_monthly_comparison_dataframe(detail_df: pd.DataFrame) -> pd.DataFrame:
    summary = (
        detail_df.assign(MonthStart=detail_df["Metric Date"].values.astype("datetime64[M]"))
        .groupby("MonthStart", dropna=False)
        .agg(
            StartDate=("Metric Date", "min"),
            EndDate=("Metric Date", "max"),
            Visitors=("Visitors", "sum"),
            Impressions=("Impressions", "sum"),
        )
        .reset_index()
        .sort_values("MonthStart", ascending=False)
        .reset_index(drop=True)
    )
    if summary.empty:
        return pd.DataFrame(
            columns=[
                "Month",
                "Period",
                "Visitor Growth Rate",
                "Visitor Trend",
                "Impression Growth Rate",
                "Impression Trend",
                "Visitor Conversion Rate",
            ]
        )
    summary["Month"] = summary["MonthStart"].dt.strftime("%B %Y")
    summary["Period"] = summary.apply(lambda row: f"{row['StartDate']:%b %d} - {row['EndDate']:%b %d, %Y}", axis=1)
    summary["Visitor Growth Rate"] = _build_change_rate_series(summary["Visitors"])
    summary["Impression Growth Rate"] = _build_change_rate_series(summary["Impressions"])
    summary["Visitor Trend"] = summary["Visitor Growth Rate"].apply(_format_growth_status)
    summary["Impression Trend"] = summary["Impression Growth Rate"].apply(_format_growth_status)
    summary["Visitor Conversion Rate"] = [
        _format_rate_percent(float(visitors), float(impressions))
        for visitors, impressions in zip(summary["Visitors"], summary["Impressions"])
    ]
    return summary[
        [
            "Month",
            "Period",
            "Visitor Growth Rate",
            "Visitor Trend",
            "Impression Growth Rate",
            "Impression Trend",
            "Visitor Conversion Rate",
        ]
    ].copy()


def _build_website_detail_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    result = df[
        [
            "Site",
            "Period",
            "Date Range",
            "Visitors",
            "Impressions",
            "2025 Avg Daily Visitors",
            "2025 Avg Daily Impressions",
            "Expected Visitors For Period",
            "Expected Impressions For Period",
            "Visitors Change % vs 2025 Avg",
            "Impressions Change % vs 2025 Avg",
        ]
    ].copy()
    for column in [
        "2025 Avg Daily Visitors",
        "2025 Avg Daily Impressions",
        "Expected Visitors For Period",
        "Expected Impressions For Period",
    ]:
        result[column] = result[column].round(2)
    result["Visitors Change % vs 2025 Avg"] = result["Visitors Change % vs 2025 Avg"].apply(_format_percent_or_na)
    result["Impressions Change % vs 2025 Avg"] = result["Impressions Change % vs 2025 Avg"].apply(
        _format_percent_or_na
    )
    result = result.rename(
        columns={
            "Visitors Change % vs 2025 Avg": "Visitors Change Rate",
            "Impressions Change % vs 2025 Avg": "Impressions Change Rate",
        }
    )
    return result


def _build_tiktok_detail_dataframe(records: list[TikTokCapturedRecord]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for record in records:
        captured_timestamp = pd.to_datetime(record.captured_at, errors="coerce")
        if pd.isna(captured_timestamp):
            continue
        metrics = record.metrics or {}
        if not metrics:
            continue
        row_date = captured_timestamp.normalize()
        week_start = row_date - pd.to_timedelta((row_date.weekday() - BUSINESS_WEEK_START_WEEKDAY) % 7, unit="D")
        week_end = week_start + pd.Timedelta(days=6)
        rows.append(
            {
                "Shop": record.profile_name,
                "Snapshot Date": row_date,
                "Week": f"{week_start:%b %d} - {week_end:%b %d, %Y}",
                "Month": row_date.strftime("%B %Y"),
                "Date": row_date.strftime("%b %d, %Y"),
                "Gross Revenue": float(metrics.get("gross_revenue", 0) or 0),
                "Items Sold": int(round(float(metrics.get("items_sold", 0) or 0))),
                "Page Views": int(round(float(metrics.get("page_views", 0) or 0))),
                "Visitors": int(round(float(metrics.get("visitors", 0) or 0))),
                "Conversion Rate": float(metrics.get("conversion_rate", 0) or 0),
            }
        )
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(["Snapshot Date", "Shop"], ascending=[False, True]).reset_index(drop=True)


def _build_tiktok_detail_dataframe_from_postgres(rows: list[dict[str, object]]) -> pd.DataFrame:
    normalized_rows: list[dict[str, object]] = []
    for row in rows:
        visible_date_range = str(row.get("visible_date_range", "") or "").strip()
        capture_source = str(row.get("capture_source", "") or "").strip().lower()
        if visible_date_range and not visible_date_range_is_single_day(visible_date_range):
            continue
        if not visible_date_range and "weekly_backfill" in capture_source:
            continue
        snapshot_date = pd.to_datetime(row["metric_date"], errors="coerce")
        if pd.isna(snapshot_date):
            continue
        week_start = snapshot_date.normalize() - pd.to_timedelta(
            (snapshot_date.weekday() - BUSINESS_WEEK_START_WEEKDAY) % 7, unit="D"
        )
        week_end = week_start + pd.Timedelta(days=6)
        normalized_rows.append(
            {
                "Shop": row["profile_name"],
                "Snapshot Date": snapshot_date.normalize(),
                "Week": f"{week_start:%b %d} - {week_end:%b %d, %Y}",
                "Month": snapshot_date.strftime("%B %Y"),
                "Date": snapshot_date.strftime("%b %d, %Y"),
                "Gross Revenue": float(row.get("gross_revenue", 0) or 0),
                "Items Sold": int(round(float(row.get("items_sold", 0) or 0))),
                "Page Views": int(round(float(row.get("page_views", 0) or 0))),
                "Visitors": int(round(float(row.get("visitors", 0) or 0))),
                "Conversion Rate": float(row.get("conversion_rate", 0) or 0),
            }
        )
    if not normalized_rows:
        return pd.DataFrame()
    return pd.DataFrame(normalized_rows).sort_values(["Snapshot Date", "Shop"], ascending=[False, True]).reset_index(drop=True)


def _filter_tiktok_detail_dataframe(detail_df: pd.DataFrame, start_date: str, end_date: str) -> pd.DataFrame:
    start_ts = pd.Timestamp(start_date)
    end_ts = pd.Timestamp(end_date)
    mask = (detail_df["Snapshot Date"] >= start_ts) & (detail_df["Snapshot Date"] <= end_ts)
    return detail_df.loc[mask].copy()


def _build_tiktok_summary_dataframe(detail_df: pd.DataFrame, filter_name: str) -> pd.DataFrame:
    grouped = (
        detail_df.groupby(["Shop"], dropna=False)
        .agg(
            StartDate=("Snapshot Date", "min"),
            EndDate=("Snapshot Date", "max"),
            GrossRevenue=("Gross Revenue", "sum"),
            ItemsSold=("Items Sold", "sum"),
            PageViews=("Page Views", "sum"),
            Visitors=("Visitors", "sum"),
        )
        .reset_index()
    )
    grouped["Period"] = _social_period_label(filter_name)
    grouped["Date Range"] = grouped.apply(
        lambda row: f"{row['StartDate']:%b %d, %Y} - {row['EndDate']:%b %d, %Y}",
        axis=1,
    )
    grouped["Conversion Rate"] = [
        _format_rate_percent(float(items_sold), float(visitors))
        for items_sold, visitors in zip(grouped["ItemsSold"], grouped["Visitors"])
    ]
    result = grouped[
        ["Shop", "Period", "Date Range", "GrossRevenue", "ItemsSold", "PageViews", "Visitors", "Conversion Rate"]
    ].rename(
        columns={
            "GrossRevenue": "Gross Revenue",
            "ItemsSold": "Items Sold",
            "PageViews": "Page Views",
        }
    )
    result["Gross Revenue"] = result["Gross Revenue"].apply(_format_currency)
    for column in ["Items Sold", "Page Views", "Visitors"]:
        result[column] = result[column].astype(int)
    return result.sort_values(["Shop"], ascending=[True]).reset_index(drop=True)


def _build_tiktok_weekly_progress_dataframe(detail_df: pd.DataFrame) -> pd.DataFrame:
    summary = (
        detail_df.assign(
            WeekStart=_business_week_start_series(detail_df["Snapshot Date"])
        )
        .groupby("WeekStart", dropna=False)
        .agg(
            StartDate=("Snapshot Date", "min"),
            EndDate=("Snapshot Date", "max"),
            GrossRevenue=("Gross Revenue", "sum"),
            ItemsSold=("Items Sold", "sum"),
            PageViews=("Page Views", "sum"),
            Visitors=("Visitors", "sum"),
        )
        .reset_index()
        .sort_values("WeekStart", ascending=False)
        .reset_index(drop=True)
    )
    if summary.empty:
        return pd.DataFrame(columns=["Week", "Period", "Gross Revenue", "Items Sold", "Page Views", "Visitors", "Conversion Rate"])
    summary["Week"] = summary["WeekStart"].apply(_business_week_label)
    summary["Period"] = summary.apply(lambda row: f"{row['StartDate']:%b %d} - {row['EndDate']:%b %d, %Y}", axis=1)
    summary["Conversion Rate"] = [
        _format_rate_percent(float(items_sold), float(visitors))
        for items_sold, visitors in zip(summary["ItemsSold"], summary["Visitors"])
    ]
    result = summary[["Week", "Period", "GrossRevenue", "ItemsSold", "PageViews", "Visitors", "Conversion Rate"]].rename(
        columns={"GrossRevenue": "Gross Revenue", "ItemsSold": "Items Sold", "PageViews": "Page Views"}
    )
    result["Gross Revenue"] = result["Gross Revenue"].apply(_format_currency)
    for column in ["Items Sold", "Page Views", "Visitors"]:
        result[column] = result[column].astype(int)
    return result


def _build_tiktok_monthly_progress_dataframe(detail_df: pd.DataFrame) -> pd.DataFrame:
    summary = (
        detail_df.assign(MonthStart=detail_df["Snapshot Date"].values.astype("datetime64[M]"))
        .groupby("MonthStart", dropna=False)
        .agg(
            StartDate=("Snapshot Date", "min"),
            EndDate=("Snapshot Date", "max"),
            GrossRevenue=("Gross Revenue", "sum"),
            ItemsSold=("Items Sold", "sum"),
            PageViews=("Page Views", "sum"),
            Visitors=("Visitors", "sum"),
        )
        .reset_index()
        .sort_values("MonthStart", ascending=False)
        .reset_index(drop=True)
    )
    if summary.empty:
        return pd.DataFrame(columns=["Month", "Date Range", "Gross Revenue", "Items Sold", "Page Views", "Visitors", "Conversion Rate"])
    summary["Month"] = summary["MonthStart"].dt.strftime("%B %Y")
    summary["Date Range"] = summary.apply(lambda row: f"{row['StartDate']:%b %d} - {row['EndDate']:%b %d, %Y}", axis=1)
    summary["Conversion Rate"] = [
        _format_rate_percent(float(items_sold), float(visitors))
        for items_sold, visitors in zip(summary["ItemsSold"], summary["Visitors"])
    ]
    result = summary[["Month", "Date Range", "GrossRevenue", "ItemsSold", "PageViews", "Visitors", "Conversion Rate"]].rename(
        columns={"GrossRevenue": "Gross Revenue", "ItemsSold": "Items Sold", "PageViews": "Page Views"}
    )
    result["Gross Revenue"] = result["Gross Revenue"].apply(_format_currency)
    for column in ["Items Sold", "Page Views", "Visitors"]:
        result[column] = result[column].astype(int)
    return result


def _build_tiktok_weekly_comparison_dataframe(detail_df: pd.DataFrame) -> pd.DataFrame:
    summary = (
        detail_df.assign(
            WeekStart=_business_week_start_series(detail_df["Snapshot Date"])
        )
        .groupby("WeekStart", dropna=False)
        .agg(
            StartDate=("Snapshot Date", "min"),
            EndDate=("Snapshot Date", "max"),
            GrossRevenue=("Gross Revenue", "sum"),
            PageViews=("Page Views", "sum"),
            Visitors=("Visitors", "sum"),
        )
        .reset_index()
        .sort_values("WeekStart", ascending=False)
        .reset_index(drop=True)
    )
    if summary.empty:
        return pd.DataFrame(columns=["Week", "Period", "Revenue Growth Rate", "Revenue Trend", "Traffic Growth Rate", "Traffic Trend", "Visitor Conversion Rate"])
    summary["Week"] = summary["WeekStart"].apply(_business_week_label)
    summary["Period"] = summary.apply(lambda row: f"{row['StartDate']:%b %d} - {row['EndDate']:%b %d, %Y}", axis=1)
    summary["Revenue Growth Rate"] = _build_change_rate_series(summary["GrossRevenue"])
    summary["Traffic Growth Rate"] = _build_change_rate_series(summary["Visitors"])
    summary["Revenue Trend"] = summary["Revenue Growth Rate"].apply(_format_growth_status)
    summary["Traffic Trend"] = summary["Traffic Growth Rate"].apply(_format_growth_status)
    summary["Visitor Conversion Rate"] = [
        _format_rate_percent(float(visitors), float(page_views))
        for visitors, page_views in zip(summary["Visitors"], summary["PageViews"])
    ]
    return summary[["Week", "Period", "Revenue Growth Rate", "Revenue Trend", "Traffic Growth Rate", "Traffic Trend", "Visitor Conversion Rate"]].copy()


def _build_tiktok_monthly_comparison_dataframe(detail_df: pd.DataFrame) -> pd.DataFrame:
    summary = (
        detail_df.assign(MonthStart=detail_df["Snapshot Date"].values.astype("datetime64[M]"))
        .groupby("MonthStart", dropna=False)
        .agg(
            StartDate=("Snapshot Date", "min"),
            EndDate=("Snapshot Date", "max"),
            GrossRevenue=("Gross Revenue", "sum"),
            PageViews=("Page Views", "sum"),
            Visitors=("Visitors", "sum"),
        )
        .reset_index()
        .sort_values("MonthStart", ascending=False)
        .reset_index(drop=True)
    )
    if summary.empty:
        return pd.DataFrame(columns=["Month", "Period", "Revenue Growth Rate", "Revenue Trend", "Traffic Growth Rate", "Traffic Trend", "Visitor Conversion Rate"])
    summary["Month"] = summary["MonthStart"].dt.strftime("%B %Y")
    summary["Period"] = summary.apply(lambda row: f"{row['StartDate']:%b %d} - {row['EndDate']:%b %d, %Y}", axis=1)
    summary["Revenue Growth Rate"] = _build_change_rate_series(summary["GrossRevenue"])
    summary["Traffic Growth Rate"] = _build_change_rate_series(summary["Visitors"])
    summary["Revenue Trend"] = summary["Revenue Growth Rate"].apply(_format_growth_status)
    summary["Traffic Trend"] = summary["Traffic Growth Rate"].apply(_format_growth_status)
    summary["Visitor Conversion Rate"] = [
        _format_rate_percent(float(visitors), float(page_views))
        for visitors, page_views in zip(summary["Visitors"], summary["PageViews"])
    ]
    return summary[["Month", "Period", "Revenue Growth Rate", "Revenue Trend", "Traffic Growth Rate", "Traffic Trend", "Visitor Conversion Rate"]].copy()


def _pick_social_metric(metrics: dict[str, float], *names: str) -> int:
    for name in names:
        if name in metrics:
            return int(round(float(metrics[name])))
    return 0


def _render_tab_controls(key_prefix: str, control_mode: str = "standard") -> tuple[str, object]:
    st.markdown("##### Filters")
    left, right = st.columns([0.34, 0.18])
    with left:
        if control_mode == "meta":
            social_options = [
                ("Yesterday", "yesterday"),
                ("Last 7 days", "last_7_days"),
                ("Last 28 days", "last_28_days"),
                ("Last 90 days", "last_90_days"),
                ("This week", "this_week"),
                ("This month", "this_month"),
                ("This year", "this_year"),
                ("Last week", "last_week"),
                ("Last month", "last_month"),
                ("Custom", "custom"),
            ]
            option_labels = [label for label, _ in social_options]
            selected_label = st.selectbox(
                "Date period",
                options=option_labels,
                index=0,
                key=f"{key_prefix}_filter_label",
            )
            filter_name = next(value for label, value in social_options if label == selected_label)
        else:
            filter_name = st.selectbox(
                "Date period",
                options=["daily", "weekly", "yearly", "range"],
                index=1,
                key=f"{key_prefix}_filter_name",
            )

    start_date = None
    end_date = None
    with right:
        st.write("")
        if st.button("Refresh Tab", key=f"{key_prefix}_refresh", use_container_width=True):
            st.rerun()

    if filter_name in {"range", "custom"}:
        start_col, end_col = st.columns(2)
        with start_col:
            start_input = st.date_input(
                "Start date",
                value=date.today().replace(day=1),
                key=f"{key_prefix}_start_date",
            )
        with end_col:
            end_input = st.date_input(
                "End date",
                value=date.today(),
                key=f"{key_prefix}_end_date",
            )
        start_date = start_input.strftime("%Y-%m-%d")
        end_date = end_input.strftime("%Y-%m-%d")
    else:
        if control_mode == "meta":
            st.caption("Meta-style period presets.")
        else:
            st.caption("Preset reporting window.")

    try:
        if control_mode == "meta":
            date_range = resolve_meta_date_range(filter_name, start_date, end_date)
        else:
            date_range = resolve_date_range(filter_name, start_date, end_date)
    except Exception as exc:
        st.error(f"Date range error: {exc}")
        st.stop()

    st.caption(f"Selected window: {date_range.start_date} to {date_range.end_date}")
    return filter_name, date_range


def _social_period_label(filter_name: str) -> str:
    labels = {
        "yesterday": "Yesterday",
        "last_7_days": "Last 7 days",
        "last_28_days": "Last 28 days",
        "last_90_days": "Last 90 days",
        "this_week": "This week",
        "this_month": "This month",
        "this_year": "This year",
        "last_week": "Last week",
        "last_month": "Last month",
        "custom": "Custom",
        "daily": "Daily",
        "weekly": "Weekly",
        "yearly": "Yearly",
        "range": "Custom",
    }
    return labels.get(filter_name, filter_name.replace("_", " ").title())


def _build_weekly_period_ranges_dataframe(detail_df: pd.DataFrame) -> pd.DataFrame:
    week_rows: list[dict[str, str]] = []
    summary = (
        detail_df.assign(
            WeekStart=_business_week_start_series(detail_df["Snapshot Date"])
        )
        .groupby("WeekStart", dropna=False)
        .agg(StartDate=("Snapshot Date", "min"), EndDate=("Snapshot Date", "max"))
        .reset_index()
        .sort_values("WeekStart", ascending=False)
        .reset_index(drop=True)
    )
    for _, row in summary.iterrows():
        week_rows.append(
            {
                "Week": _business_week_label(row["WeekStart"]),
                "Date Range": f"{row['StartDate']:%b %d} - {row['EndDate']:%b %d, %Y}",
            }
        )
    return pd.DataFrame(week_rows)


def _build_monthly_period_ranges_dataframe(detail_df: pd.DataFrame) -> pd.DataFrame:
    month_rows: list[dict[str, str]] = []
    max_date = detail_df["Snapshot Date"].max()
    summary = (
        detail_df.assign(MonthStart=detail_df["Snapshot Date"].values.astype("datetime64[M]"))
        .groupby("MonthStart", dropna=False)
        .agg(StartDate=("Snapshot Date", "min"), EndDate=("Snapshot Date", "max"))
        .reset_index()
        .sort_values("MonthStart", ascending=False)
        .reset_index(drop=True)
    )
    for _, row in summary.iterrows():
        end_date = row["EndDate"]
        last_day = monthrange(int(end_date.year), int(end_date.month))[1]
        is_partial_month = (
            end_date.year == max_date.year
            and end_date.month == max_date.month
            and end_date.day < last_day
        )
        range_label = f"{row['StartDate']:%b %d} - {row['EndDate']:%b %d, %Y}"
        if is_partial_month:
            range_label = f"{range_label} (MTD)"
        month_rows.append(
            {
                "Month": row["MonthStart"].strftime("%B %Y"),
                "Date Range": range_label,
            }
        )
    return pd.DataFrame(month_rows)


def _build_weekly_progress_dataframe(detail_df: pd.DataFrame) -> pd.DataFrame:
    summary = (
        detail_df.assign(
            WeekStart=_business_week_start_series(detail_df["Snapshot Date"])
        )
        .groupby("WeekStart", dropna=False)
        .agg(
            StartDate=("Snapshot Date", "min"),
            EndDate=("Snapshot Date", "max"),
            TotalViews=("Page Views", "sum"),
            Reach=("Reach", "sum"),
            Interaction=("Interaction", "sum"),
            LinkClicks=("Link Clicks", "sum"),
            Visits=("Visit", "sum"),
            Follow=("Follow", "sum"),
        )
        .reset_index()
        .sort_values("WeekStart", ascending=False)
        .reset_index(drop=True)
    )

    if summary.empty:
        return pd.DataFrame(
            columns=[
                "Week",
                "Period",
                "Total Views",
                "Reach",
                "Interaction",
                "Link Clicks",
                "Visits",
                "Follow",
                "Reach Rate vs Last Week",
            ]
        )

    summary["Week"] = summary["WeekStart"].apply(_business_week_label)
    summary["Period"] = summary.apply(
        lambda row: f"{row['StartDate']:%b %d} - {row['EndDate']:%b %d, %Y}",
        axis=1,
    )
    summary["Reach Rate vs Last Week"] = _build_change_rate_series(summary["Reach"])

    result = summary[
        [
            "Week",
            "Period",
            "TotalViews",
            "Reach",
            "Interaction",
            "LinkClicks",
            "Visits",
            "Follow",
            "Reach Rate vs Last Week",
        ]
    ].rename(
        columns={
            "TotalViews": "Total Views",
            "LinkClicks": "Link Clicks",
        }
    )
    for column in ["Total Views", "Reach", "Interaction", "Link Clicks", "Visits", "Follow"]:
        result[column] = result[column].astype(int)
    return result


def _build_monthly_progress_dataframe(detail_df: pd.DataFrame) -> pd.DataFrame:
    summary = (
        detail_df.assign(MonthStart=detail_df["Snapshot Date"].values.astype("datetime64[M]"))
        .groupby("MonthStart", dropna=False)
        .agg(
            StartDate=("Snapshot Date", "min"),
            EndDate=("Snapshot Date", "max"),
            TotalViews=("Page Views", "sum"),
            Reach=("Reach", "sum"),
            Interaction=("Interaction", "sum"),
            LinkClicks=("Link Clicks", "sum"),
            Visits=("Visit", "sum"),
            Follow=("Follow", "sum"),
        )
        .reset_index()
        .sort_values("MonthStart", ascending=False)
        .reset_index(drop=True)
    )

    if summary.empty:
        return pd.DataFrame(
            columns=[
                "Month",
                "Date Range",
                "Total Views",
                "Reach",
                "Interaction",
                "Link Clicks",
                "Visits",
                "Follow",
            ]
        )

    summary["Month"] = summary["MonthStart"].dt.strftime("%B %Y")
    summary["Date Range"] = summary.apply(
        lambda row: f"{row['StartDate']:%b %d} - {row['EndDate']:%b %d, %Y}",
        axis=1,
    )

    result = summary[
        [
            "Month",
            "Date Range",
            "TotalViews",
            "Reach",
            "Interaction",
            "LinkClicks",
            "Visits",
            "Follow",
        ]
    ].rename(
        columns={
            "TotalViews": "Total Views",
            "LinkClicks": "Link Clicks",
        }
    )
    for column in ["Total Views", "Reach", "Interaction", "Link Clicks", "Visits", "Follow"]:
        result[column] = result[column].astype(int)
    return result


def _build_weekly_rate_comparison_dataframe(detail_df: pd.DataFrame) -> pd.DataFrame:
    summary = _build_weekly_summary_base(detail_df)
    if summary.empty:
        return pd.DataFrame(
            columns=[
                "Week",
                "Period",
                "Views % vs Last Week",
                "Reach % vs Last Week",
                "Engagement Rate",
                "CTR",
                "Follow Rate",
            ]
        )

    summary["Week"] = summary["WeekStart"].apply(_business_week_label)
    summary["Period"] = summary.apply(
        lambda row: f"{row['StartDate']:%b %d} - {row['EndDate']:%b %d, %Y}",
        axis=1,
    )
    result = pd.DataFrame(
        {
            "Week": summary["Week"],
            "Period": summary["Period"],
            "Views % vs Last Week": _build_percent_change_series(summary["TotalViews"]),
            "Reach % vs Last Week": _build_percent_change_series(summary["Reach"]),
            "Engagement Rate": _build_rate_series(summary["Interaction"], summary["TotalViews"]),
            "CTR": _build_rate_series(summary["LinkClicks"], summary["TotalViews"]),
            "Follow Rate": _build_rate_series(summary["Follow"], summary["TotalViews"]),
        }
    )
    return result


def _build_monthly_rate_comparison_dataframe(detail_df: pd.DataFrame) -> pd.DataFrame:
    summary = _build_monthly_summary_base(detail_df)
    if summary.empty:
        return pd.DataFrame(
            columns=[
                "Month",
                "Date Range",
                "Views % vs Last Month",
                "Reach % vs Last Month",
                "Engagement Rate",
                "CTR",
                "Follow Rate",
            ]
        )

    summary["Month"] = summary["MonthStart"].dt.strftime("%B %Y")
    summary["Date Range"] = summary.apply(
        lambda row: f"{row['StartDate']:%b %d} - {row['EndDate']:%b %d, %Y}",
        axis=1,
    )
    result = pd.DataFrame(
        {
            "Month": summary["Month"],
            "Date Range": summary["Date Range"],
            "Views % vs Last Month": _build_percent_change_series(summary["TotalViews"]),
            "Reach % vs Last Month": _build_percent_change_series(summary["Reach"]),
            "Engagement Rate": _build_rate_series(summary["Interaction"], summary["TotalViews"]),
            "CTR": _build_rate_series(summary["LinkClicks"], summary["TotalViews"]),
            "Follow Rate": _build_rate_series(summary["Follow"], summary["TotalViews"]),
        }
    )
    return result


def _build_weekly_summary_base(detail_df: pd.DataFrame) -> pd.DataFrame:
    return (
        detail_df.assign(
            WeekStart=_business_week_start_series(detail_df["Snapshot Date"])
        )
        .groupby("WeekStart", dropna=False)
        .agg(
            StartDate=("Snapshot Date", "min"),
            EndDate=("Snapshot Date", "max"),
            TotalViews=("Page Views", "sum"),
            Reach=("Reach", "sum"),
            Interaction=("Interaction", "sum"),
            LinkClicks=("Link Clicks", "sum"),
            Visits=("Visit", "sum"),
            Follow=("Follow", "sum"),
        )
        .reset_index()
        .sort_values("WeekStart", ascending=False)
        .reset_index(drop=True)
    )


def _build_monthly_summary_base(detail_df: pd.DataFrame) -> pd.DataFrame:
    return (
        detail_df.assign(MonthStart=detail_df["Snapshot Date"].values.astype("datetime64[M]"))
        .groupby("MonthStart", dropna=False)
        .agg(
            StartDate=("Snapshot Date", "min"),
            EndDate=("Snapshot Date", "max"),
            TotalViews=("Page Views", "sum"),
            Reach=("Reach", "sum"),
            Interaction=("Interaction", "sum"),
            LinkClicks=("Link Clicks", "sum"),
            Visits=("Visit", "sum"),
            Follow=("Follow", "sum"),
        )
        .reset_index()
        .sort_values("MonthStart", ascending=False)
        .reset_index(drop=True)
    )


def _build_change_rate_series(series: pd.Series) -> list[str]:
    result: list[str] = []
    previous_value: float | None = None
    for value in series.tolist():
        current_value = float(value)
        if previous_value is None:
            result.append("N/A")
        elif previous_value == 0:
            result.append("0.00%" if current_value == 0 else "New")
        else:
            change = ((current_value - previous_value) / previous_value) * 100
            result.append(f"{change:.2f}%")
        previous_value = current_value
    return result


def _build_percent_change_series(series: pd.Series) -> list[str]:
    return _build_change_rate_series(series)


def _build_rate_series(numerator: pd.Series, denominator: pd.Series) -> list[str]:
    result: list[str] = []
    for num, den in zip(numerator.tolist(), denominator.tolist()):
        num_value = float(num)
        den_value = float(den)
        if den_value == 0:
            result.append("N/A")
        else:
            result.append(f"{(num_value / den_value) * 100:.2f}%")
    return result


def _format_percent_or_na(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    return f"{float(value):.2f}%"


def _format_currency(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "₱0.00"
    return f"₱{float(value):,.2f}"


def _format_rate_ratio(current_value: float, expected_value: float) -> str:
    if expected_value == 0 or pd.isna(expected_value) or pd.isna(current_value):
        return "N/A"
    return f"{(current_value / expected_value) * 100:.2f}%"


def _format_decimal_ratio(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    return f"{float(value):.2f}"


def _format_delta_percent(current_value: float | None, previous_value: float | None) -> str:
    if current_value is None or previous_value is None or pd.isna(current_value) or pd.isna(previous_value):
        return "N/A"
    previous_float = float(previous_value)
    current_float = float(current_value)
    if previous_float == 0:
        return "0.00%" if current_float == 0 else "New"
    return f"{((current_float - previous_float) / previous_float) * 100:.2f}%"


def _format_rate_percent(numerator: float | None, denominator: float | None) -> str:
    if numerator is None or denominator is None or pd.isna(numerator) or pd.isna(denominator):
        return "N/A"
    denominator_float = float(denominator)
    numerator_float = float(numerator)
    if denominator_float == 0:
        return "N/A"
    return f"{(numerator_float / denominator_float) * 100:.2f}%"


def _format_growth_status(change_text: str) -> str:
    if change_text in {"N/A", "New"}:
        return change_text
    try:
        value = float(str(change_text).replace("%", ""))
    except ValueError:
        return "N/A"
    if value > 0:
        return "Growth"
    if value < 0:
        return "Disgrowth"
    return "No Change"


def _single_platform_or_none(detail_df: pd.DataFrame) -> str | None:
    if "Platform" not in detail_df.columns or detail_df.empty:
        return None
    platforms = detail_df["Platform"].dropna().astype(str).unique().tolist()
    if len(platforms) == 1:
        return platforms[0]
    return None


def _apply_platform_column_rules(df: pd.DataFrame, platform: str | None, context: str) -> pd.DataFrame:
    if df.empty or not platform:
        return df

    result = df.copy()
    if platform == "facebook_page":
        drop_columns = {"Reach"}
        if context == "rate":
            drop_columns.update({"Reach % vs Last Week", "Reach % vs Last Month"})
        existing = [column for column in drop_columns if column in result.columns]
        if existing:
            result = result.drop(columns=existing)
    return result


def _render_rate_metric_guide() -> None:
    st.markdown(
        """
        <div class="metric-guide">
            <span class="metric-guide-item" title="Percent change in total views versus the previous comparable period.">Views %</span>
            <span class="metric-guide-item" title="Percent change in total reach versus the previous comparable period. If the prior period had zero reach and the current period has reach, the value is shown as New.">Reach %</span>
            <span class="metric-guide-item" title="Interactions divided by total views for the selected period.">Engagement Rate</span>
            <span class="metric-guide-item" title="Link clicks divided by total views for the selected period.">CTR</span>
            <span class="metric-guide-item" title="Follows divided by total views for the selected period.">Follow Rate</span>
        </div>
        <div class="metric-guide-note">Legend: <strong>N/A</strong> means the rate cannot be calculated from zero baseline data. <strong>New</strong> means the previous period was zero and the current period is above zero.</div>
        """,
        unsafe_allow_html=True,
    )


def _render_website_rate_metric_guide() -> None:
    st.markdown(
        """
        <div class="metric-guide">
            <span class="metric-guide-item" title="Percent change in visitors versus the previous week or previous month, depending on the selected comparison mode.">Visitor Growth Rate</span>
            <span class="metric-guide-item" title="Simple interpretation of the visitor growth rate: Growth, Disgrowth, No Change, New, or N/A.">Visitor Trend</span>
            <span class="metric-guide-item" title="Percent change in impressions versus the previous week or previous month, depending on the selected comparison mode.">Impression Growth Rate</span>
            <span class="metric-guide-item" title="Simple interpretation of the impression growth rate: Growth, Disgrowth, No Change, New, or N/A.">Impression Trend</span>
            <span class="metric-guide-item" title="Visitors divided by impressions for the same row period, shown as a percentage. This shows what share of impressions turned into visitors.">Visitor Conversion Rate</span>
        </div>
        <div class="metric-guide-note">Legend: <strong>Growth</strong> means increase, <strong>Disgrowth</strong> means decrease, <strong>No Change</strong> means equal, and <strong>New</strong> means the previous period was zero while the current period has data.</div>
        """,
        unsafe_allow_html=True,
    )


def _render_tiktok_rate_metric_guide() -> None:
    st.markdown(
        """
        <div class="metric-guide">
            <span class="metric-guide-item" title="Percent change in gross revenue versus the previous week or previous month, depending on the selected comparison mode.">Revenue Growth Rate</span>
            <span class="metric-guide-item" title="Simple interpretation of the revenue growth rate: Growth, Disgrowth, No Change, New, or N/A.">Revenue Trend</span>
            <span class="metric-guide-item" title="Percent change in visitors versus the previous week or previous month, depending on the selected comparison mode.">Traffic Growth Rate</span>
            <span class="metric-guide-item" title="Simple interpretation of the traffic growth rate: Growth, Disgrowth, No Change, New, or N/A.">Traffic Trend</span>
            <span class="metric-guide-item" title="Visitors divided by page views for the same row period, shown as a percentage.">Visitor Conversion Rate</span>
        </div>
        <div class="metric-guide-note">Legend: <strong>Growth</strong> means increase, <strong>Disgrowth</strong> means decrease, <strong>No Change</strong> means equal, and <strong>New</strong> means the previous period was zero while the current period has data.</div>
        """,
        unsafe_allow_html=True,
    )


def _build_overview_website_snapshot_dataframe(
    ga_rows: list[dict[str, float | int | str | None]],
) -> pd.DataFrame:
    if not ga_rows:
        return pd.DataFrame(columns=["Site", "Visitors", "Impressions"])
    result = pd.DataFrame(ga_rows)[["Site", "Visitors", "Impressions"]].copy()
    for column in ["Visitors", "Impressions"]:
        result[column] = pd.to_numeric(result[column], errors="coerce").fillna(0).astype(int)
    return result.sort_values(["Visitors", "Impressions"], ascending=[False, False]).reset_index(drop=True)


def _build_overview_social_snapshot_dataframe(
    social_profiles: list[SocialProfileSnapshot],
) -> pd.DataFrame:
    if not social_profiles:
        return pd.DataFrame(
            columns=[
                "Platform",
                "Profile",
                "Views",
                "Viewers",
                "Reach",
                "Interaction",
                "Link Clicks",
                "Visits",
                "Follow",
            ]
        )

    rows: list[dict[str, object]] = []
    for profile in social_profiles:
        metrics = profile.metrics or {}
        rows.append(
            {
                "Platform": profile.platform,
                "Profile": profile.profile_name,
                "Views": int(round(float(metrics.get("views", 0) or 0))),
                "Viewers": int(round(float(metrics.get("viewers", 0) or 0))),
                "Reach": int(round(float(metrics.get("reach", 0) or 0))),
                "Interaction": int(
                    round(
                        float(
                            metrics.get(
                                "content_interactions",
                                metrics.get("interaction", metrics.get("engaged_users", 0)),
                            )
                            or 0
                        )
                    )
                ),
                "Link Clicks": int(round(float(metrics.get("link_clicks", metrics.get("clicks", 0)) or 0))),
                "Visits": int(
                    round(
                        float(
                            metrics.get(
                                "visits",
                                metrics.get("facebook_visits", metrics.get("profile_visits", 0)),
                            )
                            or 0
                        )
                    )
                ),
                "Follow": int(
                    round(
                        float(
                            metrics.get(
                                "follows",
                                metrics.get(
                                    "followers",
                                    metrics.get(
                                        "page_followers",
                                        metrics.get("instagram_followers", metrics.get("subscribers", 0)),
                                    ),
                                ),
                            )
                            or 0
                        )
                    )
                ),
            }
        )
    return pd.DataFrame(rows).sort_values(["Platform", "Profile"]).reset_index(drop=True)


def _build_overview_status_dataframe(
    *,
    total_websites: int,
    ga_error: str | None,
    social_error: str | None,
    meta_error: str | None,
    captured_meta_error: str | None,
    postgres_error: str | None,
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Source": "GA4 Websites",
                "Status": "Ready" if not ga_error else "Issue",
                "Detail": ga_error or f"{total_websites} sites loaded",
            },
            {
                "Source": "Manual Social Snapshots",
                "Status": "Ready" if not social_error else "Issue",
                "Detail": social_error or "Loaded",
            },
            {
                "Source": "Meta Graph API",
                "Status": "Ready" if not meta_error else "Issue",
                "Detail": meta_error or "Live insights loaded",
            },
            {
                "Source": "PostgreSQL Social Warehouse",
                "Status": "Ready" if not postgres_error else "Issue",
                "Detail": postgres_error or "Daily warehouse connected",
            },
            {
                "Source": "Meta Business Suite Capture",
                "Status": "Ready" if not captured_meta_error else "Issue",
                "Detail": captured_meta_error or "Captured data loaded",
            },
        ]
    )


def build_viber_summary_preview(
    *,
    date_range,
    ga_rows: list[dict[str, float | int | str | None]],
    social_profiles: list[SocialProfileSnapshot],
    tiktok_rows: list[dict[str, object]] | None = None,
) -> str:
    website_df = _build_overview_website_snapshot_dataframe(ga_rows)
    social_df = _build_overview_social_snapshot_dataframe(social_profiles)
    tiktok_entries: list[dict[str, object]] = []
    if tiktok_rows:
        tiktok_df = _build_tiktok_detail_dataframe_from_postgres(tiktok_rows)
        if not tiktok_df.empty:
            grouped = (
                tiktok_df.groupby("Shop", dropna=False)
                .agg(
                    GrossRevenue=("Gross Revenue", "sum"),
                    ItemsSold=("Items Sold", "sum"),
                    PageViews=("Page Views", "sum"),
                    Visitors=("Visitors", "sum"),
                )
                .reset_index()
            )
            tiktok_entries = [
                {
                    "Shop": row["Shop"],
                    "Gross Revenue": row["GrossRevenue"],
                    "Items Sold": row["ItemsSold"],
                    "Page Views": row["PageViews"],
                    "Visitors": row["Visitors"],
                }
                for row in grouped.to_dict(orient="records")
            ]

    return format_viber_summary(
        start_date=date_range.start_date,
        end_date=date_range.end_date,
        website_rows=[
            {
                "site_name": row["Site"],
                "visitors": row["Visitors"],
                "impressions": row["Impressions"],
            }
            for row in website_df.to_dict(orient="records")
        ],
        social_rows=[
            {
                "platform": row["Platform"],
                "profile_name": row["Profile"],
                "views": row["Views"],
                "viewers": row["Viewers"],
                "reach": row["Reach"],
                "content_interactions": row["Interaction"],
                "visits": row["Visits"],
            }
            for row in social_df.to_dict(orient="records")
        ],
        tiktok_rows=tiktok_entries,
    )
