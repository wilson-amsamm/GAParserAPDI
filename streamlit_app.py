from __future__ import annotations

import html
import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components


ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ga_reporter.dashboard_data import (
    SocialProfileSnapshot,
    load_ga4_summary,
    load_meta_captured_summary,
    load_meta_summary,
    merge_social_profiles,
    load_social_config,
    metric_summaries_to_rows,
    total_social_metric,
)
from ga_reporter.credentials import resolve_meta_access_token, resolve_service_account_path
from ga_reporter.date_utils import last_completed_business_week_range, resolve_meta_date_range
from ga_reporter.dashboard_ui import (
    _apply_platform_column_rules,
    _build_overview_status_dataframe,
    _build_overview_website_snapshot_dataframe,
    _build_website_history_dataframe_from_postgres,
    _build_website_monthly_comparison_dataframe,
    _build_website_monthly_progress_dataframe,
    _build_monthly_progress_dataframe,
    _build_monthly_rate_comparison_dataframe,
    _build_page_summary_dataframe,
    _build_social_detail_dataframe,
    _build_social_detail_dataframe_from_postgres,
    _build_social_summary_dataframe,
    _build_tiktok_detail_dataframe,
    _build_tiktok_detail_dataframe_from_postgres,
    _build_tiktok_monthly_comparison_dataframe,
    _build_tiktok_monthly_progress_dataframe,
    _build_tiktok_summary_dataframe,
    _build_tiktok_weekly_comparison_dataframe,
    _build_tiktok_weekly_progress_dataframe,
    _build_website_detail_dataframe,
    _build_website_detail_dataframe_from_postgres,
    _build_website_summary_dataframe,
    _build_website_summary_dataframe_from_postgres,
    _build_website_weekly_comparison_dataframe,
    _build_website_weekly_progress_dataframe,
    _build_weekly_progress_dataframe,
    _build_weekly_rate_comparison_dataframe,
    _filter_social_detail_dataframe,
    _filter_tiktok_detail_dataframe,
    _render_rate_metric_guide,
    _render_tab_controls,
    _render_tiktok_rate_metric_guide,
    _render_website_rate_metric_guide,
    _single_platform_or_none,
    _social_period_label,
    build_viber_summary_preview,
)
from ga_reporter.database import (
    ensure_schema,
    load_social_daily_metrics,
    load_social_profile_aggregates,
    load_tiktok_daily_metrics,
    load_website_daily_metrics,
    resolve_postgres_config,
)
from ga_reporter.meta_capture import MetaCapturedRecord, load_captured_records
from ga_reporter.tiktok_capture import TikTokCapturedRecord, load_captured_records as load_tiktok_captured_records


DEFAULT_GA_CONFIG = ROOT / "config" / "properties.json"
DEFAULT_GA_EXAMPLE = ROOT / "config" / "properties.example.json"
DEFAULT_SOCIAL_CONFIG = ROOT / "config" / "social_profiles.json"
DEFAULT_SOCIAL_EXAMPLE = ROOT / "config" / "social_profiles.example.json"
DEFAULT_META_CONFIG = ROOT / "config" / "meta_accounts.json"
DEFAULT_META_EXAMPLE = ROOT / "config" / "meta_accounts.example.json"
DEFAULT_META_CAPTURED_DATA = ROOT / "data" / "meta_business_suite_records.json"
DEFAULT_TIKTOK_CONFIG = ROOT / "config" / "tiktok_targets.json"
DEFAULT_TIKTOK_EXAMPLE = ROOT / "config" / "tiktok_targets.example.json"
DEFAULT_TIKTOK_CAPTURED_DATA = ROOT / "data" / "tiktok_shop_records.json"
DOC_RECORD = ROOT / "docs" / "streamlit-dashboard-record.md"


def main() -> None:
    st.set_page_config(
        page_title="Online Platform Analytics",
        page_icon="chart_with_upwards_trend",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    _inject_styles()

    st.markdown(
        """
        <div class="sticky-hero">
            <h1>Online Platform Analytics Dashboard</h1>
            <p>Unified website and social reporting for GA4, Meta-style page insights, and future platform connectors.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    ga_config_path = str(_first_existing_path(DEFAULT_GA_CONFIG, DEFAULT_GA_EXAMPLE))
    social_config_path = str(_first_existing_path(DEFAULT_SOCIAL_CONFIG, DEFAULT_SOCIAL_EXAMPLE))
    meta_config_path = str(_first_existing_path(DEFAULT_META_CONFIG, DEFAULT_META_EXAMPLE))
    meta_captured_path = str(DEFAULT_META_CAPTURED_DATA)
    tiktok_config_path = str(_first_existing_path(DEFAULT_TIKTOK_CONFIG, DEFAULT_TIKTOK_EXAMPLE))
    tiktok_captured_path = str(DEFAULT_TIKTOK_CAPTURED_DATA)

    service_account_path, credential_source = resolve_service_account_path(
        repo_root=ROOT,
        streamlit_secrets=st.secrets,
    )
    meta_access_token, meta_credential_source = resolve_meta_access_token(st.secrets)
    postgres_config, postgres_source = resolve_postgres_config(st.secrets)

    main_tab = _render_button_nav(
        [
            ("Overview", "Overview"),
            ("🟡 Harmony & Homes", "Harmony & Homes"),
            ("🔴 Quadro Philippines", "Quadro Philippines"),
            ("Website Analytics", "Website Analytics"),
        ],
        key="main_nav",
        default="Overview",
    )

    if main_tab == "Overview":
        overview_date_range = _render_overview_controls()
        overview_data = _load_dashboard_state(
            date_range=overview_date_range,
            ga_config_path=ga_config_path,
            service_account_path=service_account_path,
            social_config_path=social_config_path,
            meta_config_path=meta_config_path,
            meta_captured_path=meta_captured_path,
            tiktok_captured_path=tiktok_captured_path,
            meta_access_token=meta_access_token,
            postgres_config=postgres_config,
            postgres_source=postgres_source,
        )
        _render_overview(
            overview_date_range,
            overview_data["ga_rows"],
            overview_data["social_profiles"],
            overview_data["tiktok_rows"],
            overview_data["ga_error"],
            overview_data["manual_social_error"],
            overview_data["meta_error"],
            overview_data["captured_meta_error"],
            overview_data["postgres_error"],
        )
    elif main_tab == "Harmony & Homes":
        brand_date_range = resolve_meta_date_range("yesterday", None, None)
        social_data = _load_social_state(
            date_range=brand_date_range,
            meta_captured_path=meta_captured_path,
            postgres_config=postgres_config,
            postgres_source=postgres_source,
        )
        tiktok_data = _load_tiktok_state(
            date_range=brand_date_range,
            tiktok_captured_path=tiktok_captured_path,
            postgres_config=postgres_config,
        )
        _render_brand_page(
            brand_name="Harmony & Homes",
            facebook_pages=["Harmony & Homes Facebook"],
            instagram_pages=["Harmony & Homes Instagram"],
            social_data=social_data,
            tiktok_data=tiktok_data,
            include_tiktok=True,
            instagram_ready=False,
        )

    elif main_tab == "Quadro Philippines":
        brand_date_range = resolve_meta_date_range("yesterday", None, None)
        social_data = _load_social_state(
            date_range=brand_date_range,
            meta_captured_path=meta_captured_path,
            postgres_config=postgres_config,
            postgres_source=postgres_source,
        )
        _render_brand_page(
            brand_name="Quadro Philippines",
            facebook_pages=["Quadro Decor Philippines Facebook"],
            instagram_pages=["Quadro Decor Philippines Instagram"],
            social_data=social_data,
            tiktok_data=None,
            include_tiktok=False,
            instagram_ready=True,
        )

    elif main_tab == "Website Analytics":
        website_filter_name, website_date_range = _render_tab_controls("websites", control_mode="meta")
        website_data = _load_website_state(
            date_range=website_date_range,
            ga_config_path=ga_config_path,
            service_account_path=service_account_path,
            postgres_config=postgres_config,
        )
        _render_websites(
            website_filter_name,
            website_date_range,
            website_data["ga_rows"],
            website_data["ga_summaries"],
            website_data["ga_warnings"],
            website_data["ga_error"],
            website_data["postgres_website_rows"],
            website_data["all_postgres_website_rows"],
            website_data["postgres_error"],
            ga_config_path,
            service_account_path,
        )


def _render_button_nav(
    options: list[tuple[str, str]],
    *,
    key: str,
    default: str,
) -> str:
    if key not in st.session_state:
        st.session_state[key] = default

    columns = st.columns(len(options))
    for column, (label, value) in zip(columns, options, strict=False):
        with column:
            if st.button(
                label,
                key=f"{key}_{value}",
                use_container_width=True,
                type="primary" if st.session_state[key] == value else "secondary",
            ):
                if st.session_state[key] != value:
                    st.session_state[key] = value
                    st.rerun()

    return st.session_state[key]


def _load_dashboard_state(
    *,
    date_range,
    ga_config_path: str,
    service_account_path: str | None,
    social_config_path: str,
    meta_config_path: str,
    meta_captured_path: str,
    tiktok_captured_path: str,
    meta_access_token: str | None,
    postgres_config,
    postgres_source: str,
) -> dict[str, object]:
    ga_rows: list[dict[str, object]] = []
    ga_error: str | None = None
    manual_social_profiles: list[SocialProfileSnapshot] = []
    manual_social_error: str | None = None
    meta_social_profiles: list[SocialProfileSnapshot] = []
    meta_error: str | None = None
    captured_meta_profiles: list[SocialProfileSnapshot] = []
    captured_meta_error: str | None = None
    postgres_social_profiles: list[SocialProfileSnapshot] = []
    postgres_tiktok_rows: list[dict[str, object]] = []
    captured_tiktok_error: str | None = None
    postgres_error: str | None = None
    postgres_website_error: str | None = None

    with st.spinner("Loading overview data..."):
        if postgres_config:
            try:
                ensure_schema(postgres_config)
                postgres_website_rows = load_website_daily_metrics(
                    postgres_config,
                    start_date=date_range.start_date,
                    end_date=date_range.end_date,
                )
                ga_rows = _build_website_summary_dataframe_from_postgres(
                    postgres_website_rows,
                    "yesterday",
                    date_range,
                ).to_dict("records")
                if not ga_rows:
                    ga_error = "No PostgreSQL website rows are available for the selected date window."
            except Exception as exc:
                postgres_website_error = str(exc)
                ga_error = f"Website warehouse load failed: {exc}"
        else:
            ga_error = "Website warehouse is not configured."

        try:
            manual_social_profiles = load_social_config(social_config_path)
        except Exception as exc:
            manual_social_error = str(exc)

        if meta_access_token:
            try:
                meta_social_profiles, _ = load_meta_summary(
                    config_path=meta_config_path,
                    access_token=meta_access_token,
                    date_range=date_range,
                )
            except Exception as exc:
                meta_error = str(exc)
        elif Path(meta_config_path).exists():
            meta_error = "Meta access token is not configured."

        try:
            captured_meta_profiles = load_meta_captured_summary(meta_captured_path)
        except Exception as exc:
            captured_meta_error = str(exc)

        try:
            load_tiktok_captured_records(tiktok_captured_path)
        except Exception as exc:
            captured_tiktok_error = str(exc)

        if postgres_config:
            try:
                ensure_schema(postgres_config)
                aggregate_rows = load_social_profile_aggregates(
                    postgres_config,
                    start_date=date_range.start_date,
                    end_date=date_range.end_date,
                )
                postgres_social_profiles = [
                    SocialProfileSnapshot(
                        platform=row["platform"],
                        profile_name=row["profile_name"],
                        metrics={
                            metric_name: float(metric_value)
                            for metric_name, metric_value in row["metrics"].items()
                            if float(metric_value) != 0
                        },
                        source="postgresql",
                        notes=f"Loaded from PostgreSQL ({postgres_source}).",
                    )
                    for row in aggregate_rows
                ]
                postgres_tiktok_rows = load_tiktok_daily_metrics(
                    postgres_config,
                    start_date=date_range.start_date,
                    end_date=date_range.end_date,
                )
            except Exception as exc:
                postgres_error = str(exc)

    social_profiles = (
        merge_social_profiles(meta_social_profiles, postgres_social_profiles)
        if postgres_social_profiles
        else merge_social_profiles(meta_social_profiles, captured_meta_profiles, manual_social_profiles)
    )
    return {
        "ga_rows": ga_rows,
        "social_profiles": social_profiles,
        "ga_error": ga_error,
        "manual_social_error": manual_social_error,
        "meta_error": meta_error,
        "captured_meta_error": captured_meta_error,
        "captured_tiktok_error": captured_tiktok_error,
        "tiktok_rows": postgres_tiktok_rows,
        "postgres_error": postgres_error or postgres_website_error,
    }


def _load_website_state(
    *,
    date_range,
    ga_config_path: str,
    service_account_path: str | None,
    postgres_config=None,
) -> dict[str, object]:
    ga_rows: list[dict[str, object]] = []
    ga_error: str | None = None
    postgres_website_rows: list[dict[str, object]] = []
    all_postgres_website_rows: list[dict[str, object]] = []
    postgres_error: str | None = None
    with st.spinner("Loading website analytics..."):
        if postgres_config:
            try:
                ensure_schema(postgres_config)
                postgres_website_rows = load_website_daily_metrics(
                    postgres_config,
                    start_date=date_range.start_date,
                    end_date=date_range.end_date,
                )
                all_postgres_website_rows = load_website_daily_metrics(postgres_config)
                ga_rows = _build_website_summary_dataframe_from_postgres(
                    postgres_website_rows,
                    "meta",
                    date_range,
                ).to_dict("records")
                if not ga_rows and not all_postgres_website_rows:
                    ga_error = "No website warehouse rows are available yet."
            except Exception as exc:
                postgres_error = str(exc)
                ga_error = f"Website warehouse load failed: {exc}"
        else:
            ga_error = "Website warehouse is not configured."
    return {
        "ga_rows": ga_rows,
        "ga_summaries": [],
        "ga_warnings": [],
        "ga_error": ga_error,
        "postgres_website_rows": postgres_website_rows,
        "all_postgres_website_rows": all_postgres_website_rows,
        "postgres_error": postgres_error,
    }


def _load_social_state(*, date_range, meta_captured_path: str, postgres_config, postgres_source: str) -> dict[str, object]:
    captured_meta_records: list[MetaCapturedRecord] = []
    captured_meta_error: str | None = None
    postgres_social_rows: list[dict[str, object]] = []
    all_postgres_social_rows: list[dict[str, object]] = []
    postgres_error: str | None = None

    with st.spinner("Loading social history..."):
        try:
            captured_meta_records = load_captured_records(meta_captured_path)
        except Exception as exc:
            captured_meta_error = str(exc)

        if postgres_config:
            try:
                ensure_schema(postgres_config)
                postgres_social_rows = load_social_daily_metrics(
                    postgres_config,
                    start_date=date_range.start_date,
                    end_date=date_range.end_date,
                )
                all_postgres_social_rows = load_social_daily_metrics(postgres_config)
            except Exception as exc:
                postgres_error = str(exc)

    return {
        "captured_meta_records": captured_meta_records,
        "captured_meta_error": captured_meta_error,
        "postgres_social_rows": postgres_social_rows,
        "all_postgres_social_rows": all_postgres_social_rows,
        "postgres_enabled": bool(postgres_config),
        "postgres_error": postgres_error,
        "postgres_source": postgres_source,
    }


def _load_tiktok_state(*, date_range, tiktok_captured_path: str, postgres_config) -> dict[str, object]:
    captured_tiktok_records: list[TikTokCapturedRecord] = []
    captured_tiktok_error: str | None = None
    postgres_tiktok_rows: list[dict[str, object]] = []
    all_postgres_tiktok_rows: list[dict[str, object]] = []
    postgres_error: str | None = None

    with st.spinner("Loading TikTok shop history..."):
        try:
            captured_tiktok_records = load_tiktok_captured_records(tiktok_captured_path)
        except Exception as exc:
            captured_tiktok_error = str(exc)

        if postgres_config:
            try:
                ensure_schema(postgres_config)
                postgres_tiktok_rows = load_tiktok_daily_metrics(
                    postgres_config,
                    start_date=date_range.start_date,
                    end_date=date_range.end_date,
                )
                all_postgres_tiktok_rows = load_tiktok_daily_metrics(postgres_config)
            except Exception as exc:
                postgres_error = str(exc)

    return {
        "captured_tiktok_records": captured_tiktok_records,
        "captured_tiktok_error": captured_tiktok_error,
        "postgres_tiktok_rows": postgres_tiktok_rows,
        "all_postgres_tiktok_rows": all_postgres_tiktok_rows,
        "postgres_enabled": bool(postgres_config),
        "postgres_error": postgres_error,
    }


def _render_overview_controls():
    controls_col, _spacer = st.columns([0.12, 0.88])
    with controls_col:
        if st.button("Refresh", key="overview_refresh_small", use_container_width=True):
            st.rerun()
    return last_completed_business_week_range()


def _render_copy_button(text: str, button_label: str = "Copy") -> None:
    safe_label = html.escape(button_label)
    text_literal = json.dumps(text).replace("</", "<\\/")
    button_id = f"copy-btn-{abs(hash(text)) % 1000000}"
    source_id = f"copy-source-{abs(hash(text)) % 1000000}"
    components.html(
        f"""
        <div style="display:flex; justify-content:flex-end; align-items:center; padding-top:0.1rem; margin:0; overflow:hidden;">
            <textarea id="{source_id}" style="position:absolute; left:-9999px; top:-9999px; opacity:0;"></textarea>
            <button
                id="{button_id}"
                style="
                    background:#ffffff;
                    border:1px solid rgba(19,39,70,0.18);
                    border-radius:10px;
                    color:#132746;
                    cursor:pointer;
                    font-family:inherit;
                    font-size:0.95rem;
                    font-weight:700;
                    padding:0.55rem 1rem;
                    width:100%;
                "
                type="button"
            >
                {safe_label}
            </button>
        </div>
        <script>
            (() => {{
                const payload = {text_literal};
                const button = document.getElementById('{button_id}');
                const source = document.getElementById('{source_id}');
                const reset = () => {{
                    button.innerText = {json.dumps(button_label)};
                }};
                const markCopied = () => {{
                    button.innerText = 'Copied';
                    setTimeout(reset, 1500);
                }};
                const markFailed = () => {{
                    button.innerText = 'Copy failed';
                    setTimeout(reset, 2200);
                }};
                const fallbackCopy = () => {{
                    source.value = payload;
                    source.focus();
                    source.select();
                    source.setSelectionRange(0, source.value.length);
                    try {{
                        const ok = document.execCommand('copy');
                        if (ok) {{
                            markCopied();
                        }} else {{
                            markFailed();
                        }}
                    }} catch (e) {{
                        markFailed();
                    }}
                }};
                button.addEventListener('click', () => {{
                    if (navigator.clipboard && window.isSecureContext) {{
                        navigator.clipboard.writeText(payload).then(markCopied).catch(fallbackCopy);
                    }} else {{
                        fallbackCopy();
                    }}
                }});
            }})();
        </script>
        """,
        height=58,
        width=220,
    )


def _render_overview(
    date_range,
    ga_rows: list[dict[str, float | int | str | None]],
    social_profiles: list[SocialProfileSnapshot],
    tiktok_rows: list[dict[str, object]],
    ga_error: str | None,
    social_error: str | None,
    meta_error: str | None,
    captured_meta_error: str | None,
    postgres_error: str | None,
) -> None:
    total_websites = len(ga_rows)
    total_social_views = int(total_social_metric(social_profiles, ["views", "page_views", "impressions"]))
    total_social_visits = int(total_social_metric(social_profiles, ["visits", "facebook_visits", "profile_visits"]))

    summary_pane, technical_pane = st.tabs(["Summary", "Technical Summary"])

    website_snapshot_df = _build_overview_website_snapshot_dataframe(ga_rows)
    status_df = _build_overview_status_dataframe(
        total_websites=total_websites,
        ga_error=ga_error,
        social_error=social_error,
        meta_error=meta_error,
        captured_meta_error=captured_meta_error,
        postgres_error=postgres_error,
    )
    viber_preview = build_viber_summary_preview(
        date_range=date_range,
        ga_rows=ga_rows,
        social_profiles=social_profiles,
        tiktok_rows=tiktok_rows,
    )

    with summary_pane:
        summary_header_col, summary_copy_col = st.columns([0.82, 0.18])
        with summary_header_col:
            st.markdown("##### Summary")
            st.caption("Copy this message to Viber for sending.")
        with summary_copy_col:
            st.write("")
            _render_copy_button(viber_preview, button_label="Copy Message")
        st.code(viber_preview, language=None)

    with technical_pane:
        st.markdown("##### Platform Status")
        _render_report_table(status_df, table_key="overview_status")


def _build_social_history_source(
    all_postgres_social_rows: list[dict[str, object]],
    captured_records: list[MetaCapturedRecord],
    postgres_enabled: bool,
    postgres_error: str | None,
) -> pd.DataFrame:
    if all_postgres_social_rows:
        return _build_social_detail_dataframe_from_postgres(all_postgres_social_rows)
    if not postgres_enabled and captured_records:
        return _build_social_detail_dataframe(captured_records)
    return pd.DataFrame()


def _build_tiktok_history_source(
    all_postgres_tiktok_rows: list[dict[str, object]],
    captured_records: list[TikTokCapturedRecord],
    postgres_enabled: bool,
    postgres_error: str | None,
) -> pd.DataFrame:
    if all_postgres_tiktok_rows:
        return _build_tiktok_detail_dataframe_from_postgres(all_postgres_tiktok_rows)
    if not postgres_enabled and captured_records:
        return _build_tiktok_detail_dataframe(captured_records)
    return pd.DataFrame()


def _render_brand_social_channel(
    channel_label: str,
    history_df: pd.DataFrame,
    page_names: list[str],
    platform: str,
    key_prefix: str,
    empty_message: str,
) -> None:
    channel_df = history_df[history_df["Page"].isin(page_names)].copy()
    if channel_df.empty:
        st.info(empty_message)
        return

    mode = st.radio(
        "To-date mode",
        options=["Weekly", "Monthly"],
        horizontal=True,
        key=f"{key_prefix}_todate_mode",
    )
    st.markdown(f"##### {channel_label}")
    for page_name in page_names:
        page_df = channel_df[channel_df["Page"] == page_name].copy()
        if page_df.empty:
            continue
        progress_df = (
            _build_weekly_progress_dataframe(page_df)
            if mode == "Weekly"
            else _build_monthly_progress_dataframe(page_df)
        )
        _render_report_table(
            _apply_platform_column_rules(progress_df, platform, context="progress"),
            table_key=f"{key_prefix}_{mode.lower()}_{page_name}",
        )


def _render_brand_rate_metrics(
    brand_name: str,
    social_history_df: pd.DataFrame,
    page_names: list[str],
    key_prefix: str,
    tiktok_history_df: pd.DataFrame | None = None,
) -> None:
    comparison_view = st.radio(
        "Comparison mode",
        options=["Weekly", "Monthly"],
        horizontal=True,
        key=f"{key_prefix}_rate_mode",
    )
    _render_rate_metric_guide()
    st.markdown(f"##### {brand_name} Rate Metrics")
    for page_name in page_names:
        page_df = social_history_df[social_history_df["Page"] == page_name].copy()
        if page_df.empty:
            continue
        st.markdown(f"###### {page_name}")
        page_platform = _single_platform_or_none(page_df)
        comparison_df = (
            _build_weekly_rate_comparison_dataframe(page_df)
            if comparison_view == "Weekly"
            else _build_monthly_rate_comparison_dataframe(page_df)
        )
        _render_report_table(
            _apply_platform_column_rules(comparison_df, page_platform, context="rate"),
            table_key=f"{key_prefix}_rate_{comparison_view.lower()}_{page_name}",
            header_tooltips={
                "Views % vs Last Week": "Percent change in total views compared with the previous week.",
                "Views % vs Last Month": "Percent change in total views compared with the previous month.",
                "Reach % vs Last Week": "Percent change in total reach compared with the previous week.",
                "Reach % vs Last Month": "Percent change in total reach compared with the previous month.",
                "Engagement Rate": "Interactions divided by total views for the period.",
                "CTR": "Link clicks divided by total views for the period.",
                "Follow Rate": "Follows divided by total views for the period.",
            },
        )

    if tiktok_history_df is not None and not tiktok_history_df.empty:
        _render_tiktok_rate_metric_guide()
        st.markdown("##### TikTok Rate Metrics")
        comparison_df = (
            _build_tiktok_weekly_comparison_dataframe(tiktok_history_df)
            if comparison_view == "Weekly"
            else _build_tiktok_monthly_comparison_dataframe(tiktok_history_df)
        )
        _render_report_table(
            comparison_df,
            table_key=f"{key_prefix}_tiktok_rate_{comparison_view.lower()}",
            header_tooltips={
                "Revenue Growth Rate": "Percent change in gross revenue versus the previous comparable period.",
                "Revenue Trend": "Simple interpretation of the revenue growth rate.",
                "Traffic Growth Rate": "Percent change in visitors versus the previous comparable period.",
                "Traffic Trend": "Simple interpretation of the visitor growth rate.",
                "Visitor Conversion Rate": "Visitors divided by page views for the same row period, shown as a percentage.",
            },
        )


def _render_brand_tiktok_analytics(
    brand_name: str,
    tiktok_history_df: pd.DataFrame,
    key_prefix: str,
) -> None:
    st.markdown("##### TikTok Analytics")
    if tiktok_history_df.empty:
        st.info(f"No TikTok warehouse rows are available yet for {brand_name}.")
        return
    mode = st.radio(
        "To-date mode",
        options=["Weekly", "Monthly"],
        horizontal=True,
        key=f"{key_prefix}_tiktok_todate_mode",
    )
    shops = tiktok_history_df["Shop"].drop_duplicates().tolist()
    for shop_name in shops:
        shop_df = tiktok_history_df[tiktok_history_df["Shop"] == shop_name].copy()
        if shop_df.empty:
            continue
        st.markdown(f"###### {shop_name}")
        progress_df = (
            _build_tiktok_weekly_progress_dataframe(shop_df)
            if mode == "Weekly"
            else _build_tiktok_monthly_progress_dataframe(shop_df)
        )
        _render_report_table(
            progress_df,
            table_key=f"{key_prefix}_tiktok_{mode.lower()}_{shop_name}",
        )


def _render_brand_page(
    *,
    brand_name: str,
    facebook_pages: list[str],
    instagram_pages: list[str],
    social_data: dict[str, object],
    tiktok_data: dict[str, object] | None,
    include_tiktok: bool,
    instagram_ready: bool,
) -> None:
    st.subheader(brand_name)

    if social_data.get("postgres_error"):
        st.warning(f"Social warehouse issue: {social_data['postgres_error']}")
    elif social_data.get("captured_meta_error") and not social_data.get("all_postgres_social_rows"):
        st.warning(f"Meta capture issue: {social_data['captured_meta_error']}")

    social_history_df = _build_social_history_source(
        social_data.get("all_postgres_social_rows", []),
        social_data.get("captured_meta_records", []),
        bool(social_data.get("postgres_enabled")),
        social_data.get("postgres_error"),
    )

    brand_social_pages = facebook_pages + instagram_pages
    brand_social_history_df = social_history_df[social_history_df["Page"].isin(brand_social_pages)].copy()

    tiktok_history_df = pd.DataFrame()
    if include_tiktok and tiktok_data is not None:
        if tiktok_data.get("postgres_error"):
            st.warning(f"TikTok warehouse issue: {tiktok_data['postgres_error']}")
        elif tiktok_data.get("captured_tiktok_error") and not tiktok_data.get("all_postgres_tiktok_rows"):
            st.warning(f"TikTok capture issue: {tiktok_data['captured_tiktok_error']}")
        tiktok_history_df = _build_tiktok_history_source(
            tiktok_data.get("all_postgres_tiktok_rows", []),
            tiktok_data.get("captured_tiktok_records", []),
            bool(tiktok_data.get("postgres_enabled")),
            tiktok_data.get("postgres_error"),
        )

    if include_tiktok:
        selected_brand_tab = _render_button_nav(
            [
                ("⚫ TikTok Analytics", "tiktok"),
                ("🔵 Facebook Analytics", "facebook"),
                ("🩷 Instagram Analytics", "instagram"),
                ("Rate Metrics Report", "rate"),
            ],
            key=f"{brand_name}_nav",
            default="tiktok",
        )
    else:
        selected_brand_tab = _render_button_nav(
            [
                ("🔵 Facebook Analytics", "facebook"),
                ("🩷 Instagram Analytics", "instagram"),
                ("Rate Metrics Report", "rate"),
            ],
            key=f"{brand_name}_nav",
            default="facebook",
        )

    if include_tiktok and selected_brand_tab == "tiktok":
        _render_brand_tiktok_analytics(brand_name, tiktok_history_df, key_prefix=f"{brand_name}_tiktok")

    if selected_brand_tab == "facebook":
        _render_brand_social_channel(
            "Facebook Analytics",
            brand_social_history_df,
            facebook_pages,
            "facebook_page",
            key_prefix=f"{brand_name}_facebook",
            empty_message=f"No Facebook warehouse rows are available yet for {brand_name}.",
        )

    if selected_brand_tab == "instagram":
        if not instagram_ready:
            st.info(f"Instagram Analytics is not wired yet for {brand_name}.")
        else:
            _render_brand_social_channel(
                "Instagram Analytics",
                brand_social_history_df,
                instagram_pages,
                "instagram_business",
                key_prefix=f"{brand_name}_instagram",
                empty_message=f"No Instagram warehouse rows are available yet for {brand_name}.",
            )

    if selected_brand_tab == "rate":
        _render_brand_rate_metrics(
            brand_name=brand_name,
            social_history_df=brand_social_history_df,
            page_names=brand_social_pages,
            key_prefix=brand_name,
            tiktok_history_df=tiktok_history_df if include_tiktok else None,
        )


def _render_websites(
    filter_name,
    date_range,
    ga_rows,
    ga_summaries,
    ga_warnings,
    ga_error,
    postgres_website_rows,
    all_postgres_website_rows,
    postgres_error,
    ga_config_path: str,
    service_account_path: str | None,
) -> None:
    st.subheader("Website Analytics")
    if postgres_error:
        st.warning(f"Website warehouse issue: {postgres_error}")
    if ga_error and not postgres_website_rows:
        st.error(ga_error)
        return
    if not postgres_website_rows:
        st.warning("No website analytics rows are available for the selected configuration.")
        return
    ga_df = _build_website_summary_dataframe_from_postgres(
        postgres_website_rows,
        filter_name,
        date_range,
    )
    site_options = ga_df["Site"].drop_duplicates().tolist()
    selected_sites = st.multiselect(
        "Websites",
        options=site_options,
        default=site_options,
        help="Choose which websites should be included in the website reporting panes.",
        key="website_selected_sites",
    )
    visible_df = ga_df[ga_df["Site"].isin(selected_sites or site_options)].copy()
    if visible_df.empty:
        st.info("No website rows remain after applying the site filter.")
        return
    website_start = pd.Timestamp(date_range.start_date)
    website_end = pd.Timestamp(date_range.end_date)
    visible_df["Period"] = _social_period_label(filter_name)
    visible_df["Date Range"] = f"{website_start:%b %d, %Y} - {website_end:%b %d, %Y}"
    history_df = _build_website_history_dataframe_from_postgres(all_postgres_website_rows)

    summary_pane, todate_pane, rate_pane, detail_pane = st.tabs(
        ["Summary", "To Date Summary", "Rate Metrics Report", "Detailed Rows"]
    )

    with summary_pane:
        st.markdown("##### Summary Table")
        summary_table_df = _build_website_summary_dataframe_from_postgres(
            postgres_website_rows,
            filter_name,
            date_range,
        )
        if selected_sites:
            summary_table_df = summary_table_df[summary_table_df["Site"].isin(selected_sites)].copy()
        _render_report_table(summary_table_df, table_key="website_summary")

    with todate_pane:
        st.markdown("##### To Date Summary")
        summary_mode = st.radio(
            "To-date mode",
            options=["Weekly", "Monthly"],
            horizontal=True,
            key="website_todate_mode",
        )
        history_df = _build_website_history_dataframe_from_postgres(all_postgres_website_rows)
        for site_name in selected_sites or site_options:
            site_history_df = history_df[history_df["Site"] == site_name].copy()
            if site_history_df.empty:
                continue
            st.markdown(f"###### {site_name}")
            if summary_mode == "Weekly":
                site_progress_df = _build_website_weekly_progress_dataframe(site_history_df)
            else:
                site_progress_df = _build_website_monthly_progress_dataframe(site_history_df)
            _render_report_table(
                site_progress_df,
                table_key=f"website_todate_{site_name}",
            )

    with rate_pane:
        st.markdown("##### Rate Metrics Report")
        _render_website_rate_metric_guide()
        comparison_mode = st.radio(
            "Comparison mode",
            options=["Weekly", "Monthly"],
            horizontal=True,
            key="website_rate_mode",
        )
        for site_name in selected_sites or site_options:
            site_history_df = history_df[history_df["Site"] == site_name].copy()
            if site_history_df.empty:
                continue
            st.markdown(f"###### {site_name}")
            if comparison_mode == "Weekly":
                site_rate_df = _build_website_weekly_comparison_dataframe(site_history_df)
            else:
                site_rate_df = _build_website_monthly_comparison_dataframe(site_history_df)
            _render_report_table(
                site_rate_df,
                table_key=f"website_rate_{site_name}",
                header_tooltips={
                    "Visitor Growth Rate": "Percent change in visitors versus the previous comparable period.",
                    "Visitor Trend": "Simple interpretation of the visitor growth rate.",
                    "Impression Growth Rate": "Percent change in impressions versus the previous comparable period.",
                    "Impression Trend": "Simple interpretation of the impression growth rate.",
                    "Visitor Conversion Rate": "Visitors divided by impressions for the same row period, shown as a percentage.",
                },
            )

    with detail_pane:
        st.markdown("##### Detailed Table")
        detail_table_df = _build_website_detail_dataframe_from_postgres(
            postgres_website_rows,
            filter_name,
            date_range,
        )
        if selected_sites:
            detail_table_df = detail_table_df[detail_table_df["Site"].isin(selected_sites)].copy()
        _render_report_table(detail_table_df, table_key="website_detail")


def _render_social(
    date_range,
    filter_name: str,
    postgres_social_rows: list[dict[str, object]],
    all_postgres_social_rows: list[dict[str, object]],
    captured_records: list[MetaCapturedRecord],
    postgres_enabled: bool,
    postgres_error: str | None,
    captured_meta_error: str | None,
) -> None:
    st.subheader("Social Media")
    st.caption(
        "Clean Meta page reporting from captured Business Suite history. The first table summarizes each page for the selected period, and the second table lists the underlying dated rows."
    )

    if postgres_error:
        st.warning(f"PostgreSQL issue: {postgres_error}")
    if captured_meta_error and not postgres_social_rows:
        st.warning(f"Meta capture issue: {captured_meta_error}")

    using_postgres_history = postgres_enabled and postgres_error is None

    if postgres_social_rows:
        detail_df = _build_social_detail_dataframe_from_postgres(postgres_social_rows)
    elif not using_postgres_history:
        detail_df = _build_social_detail_dataframe(captured_records)
    else:
        detail_df = pd.DataFrame()

    if all_postgres_social_rows:
        progress_history_df = _build_social_detail_dataframe_from_postgres(all_postgres_social_rows)
    else:
        progress_history_df = _build_social_detail_dataframe(captured_records)

    effective_filter_name = filter_name

    if detail_df.empty:
        if using_postgres_history and not progress_history_df.empty:
            latest_available = pd.to_datetime(progress_history_df["Date"]).max()
            latest_label = latest_available.strftime("%b %d, %Y")
            fallback_detail_df = progress_history_df[
                pd.to_datetime(progress_history_df["Date"]) == latest_available
            ].copy()
            if not fallback_detail_df.empty:
                st.info(
                    "No PostgreSQL social rows are available for the selected date window. "
                    f"Showing the latest available imported social day instead: {latest_label}."
                )
                detail_df = fallback_detail_df
                effective_filter_name = f"{filter_name} (Latest Available)"
            else:
                st.info(
                    "No PostgreSQL social rows are available for the selected date window. "
                    "This usually means the selected day has no imported daily record yet."
                )
                return
        else:
            if using_postgres_history:
                st.info(
                    "No PostgreSQL social rows are available for the selected date window. "
                    "This usually means the selected day has no imported daily record yet."
                )
            else:
                st.info("No captured Meta history is available yet.")
            return

    filtered_detail_df = _filter_social_detail_dataframe(detail_df, date_range.start_date, date_range.end_date)
    if filtered_detail_df.empty and not detail_df.empty:
        filtered_detail_df = detail_df.copy()
    if filtered_detail_df.empty:
        st.info("No captured Meta rows fall inside the selected reporting period.")
        return

    page_options = filtered_detail_df["Page"].drop_duplicates().tolist()
    selected_pages = st.multiselect(
        "Pages",
        options=page_options,
        default=page_options,
        help="Choose which Meta pages/profiles should be included in the summary and detailed tables.",
    )
    visible_detail_df = filtered_detail_df[
        filtered_detail_df["Page"].isin(selected_pages or page_options)
    ].copy()

    if visible_detail_df.empty:
        st.info("No rows remain after applying the page filter.")
        return

    summary_df = _build_social_summary_dataframe(visible_detail_df, effective_filter_name)

    summary_pane, progress_pane, rate_pane, detail_pane = st.tabs(
        ["Summary", "To Date Summary", "Rate Metrics Report", "Detailed Rows"]
    )

    with summary_pane:
        st.markdown("##### Summary Table")
        for page_name in selected_pages or page_options:
            page_detail_df = visible_detail_df[visible_detail_df["Page"] == page_name].copy()
            if page_detail_df.empty:
                continue
            st.markdown(f"###### {page_name}")
            page_platform = _single_platform_or_none(page_detail_df)
            page_summary_df = _build_page_summary_dataframe(page_detail_df, filter_name, page_platform)
            if effective_filter_name != filter_name:
                page_summary_df["Period"] = effective_filter_name
            _render_report_table(page_summary_df, table_key=f"summary_{page_name}")

    with progress_pane:
        progress_view = st.radio(
            "Progress view",
            options=["Weekly", "Monthly"],
            horizontal=True,
            key="social_progress_view",
        )
        st.markdown(f"##### {progress_view} Progress By Page")
        for page_name in selected_pages or page_options:
            page_detail_df = progress_history_df[progress_history_df["Page"] == page_name].copy()
            if page_detail_df.empty:
                continue
            st.markdown(f"###### {page_name}")
            page_platform = _single_platform_or_none(page_detail_df)
            if progress_view == "Weekly":
                progress_df = _build_weekly_progress_dataframe(page_detail_df)
            else:
                progress_df = _build_monthly_progress_dataframe(page_detail_df)
            _render_report_table(
                _apply_platform_column_rules(progress_df, page_platform, context="progress"),
                table_key=f"progress_{progress_view.lower()}_{page_name}",
            )

    with rate_pane:
        comparison_view = st.radio(
            "Comparison mode",
            options=["Weekly", "Monthly"],
            horizontal=True,
            key="social_rate_view",
        )
        _render_rate_metric_guide()
        st.markdown(f"##### {comparison_view} Rate Comparison By Page")
        for page_name in selected_pages or page_options:
            page_detail_df = progress_history_df[progress_history_df["Page"] == page_name].copy()
            if page_detail_df.empty:
                continue
            st.markdown(f"###### {page_name}")
            page_platform = _single_platform_or_none(page_detail_df)
            if comparison_view == "Weekly":
                comparison_df = _build_weekly_rate_comparison_dataframe(page_detail_df)
            else:
                comparison_df = _build_monthly_rate_comparison_dataframe(page_detail_df)
            _render_report_table(
                _apply_platform_column_rules(comparison_df, page_platform, context="rate"),
                table_key=f"rate_{comparison_view.lower()}_{page_name}",
                header_tooltips={
                    "Views % vs Last Week": "Percent change in total views compared with the previous week.",
                    "Views % vs Last Month": "Percent change in total views compared with the previous month.",
                    "Reach % vs Last Week": "Percent change in total reach compared with the previous week. Shows 'New' when the previous period had zero reach and the current period has reach.",
                    "Reach % vs Last Month": "Percent change in total reach compared with the previous month. Shows 'New' when the previous period had zero reach and the current period has reach.",
                    "Engagement Rate": "Interactions divided by total views for the period.",
                    "CTR": "Link clicks divided by total views for the period.",
                    "Follow Rate": "Follows divided by total views for the period.",
                },
            )

    with detail_pane:
        st.markdown("##### Detailed Table")
        detail_table_df = visible_detail_df[
                [
                    "Page",
                    "Platform",
                    "Week",
                    "Month",
                    "Date",
                    "Page Views",
                    "Viewers",
                    "Reach",
                    "Interaction",
                    "Link Clicks",
                    "Visit",
                    "Follow",
            ]
        ].copy()
        detail_platform = _single_platform_or_none(visible_detail_df)
        detail_table_df = _apply_platform_column_rules(detail_table_df, detail_platform, context="detail")
        if "Platform" in detail_table_df.columns:
            detail_table_df = detail_table_df.drop(columns=["Platform"])
        _render_report_table(detail_table_df, table_key="social_detail")

    st.caption(
        "These rows are built from captured Meta Business Suite records. Re-running the capture job will append more dated rows and make the period summaries richer over time."
    )


def _render_tiktok(
    date_range,
    filter_name: str,
    postgres_tiktok_rows: list[dict[str, object]],
    all_postgres_tiktok_rows: list[dict[str, object]],
    captured_records: list[TikTokCapturedRecord],
    postgres_enabled: bool,
    postgres_error: str | None,
    captured_tiktok_error: str | None,
) -> None:
    st.subheader("TikTok Shop")
    st.caption(
        "TikTok Shop reporting for sales and traffic metrics. This tab tracks gross revenue, items sold, page views, visitors, and conversion rate."
    )

    if postgres_error:
        st.warning(f"PostgreSQL issue: {postgres_error}")
    if captured_tiktok_error and not postgres_tiktok_rows:
        st.warning(f"TikTok capture issue: {captured_tiktok_error}")

    using_postgres_history = postgres_enabled and postgres_error is None

    if postgres_tiktok_rows:
        detail_df = _build_tiktok_detail_dataframe_from_postgres(postgres_tiktok_rows)
    elif not using_postgres_history:
        detail_df = _build_tiktok_detail_dataframe(captured_records)
    else:
        detail_df = pd.DataFrame()

    if all_postgres_tiktok_rows:
        progress_history_df = _build_tiktok_detail_dataframe_from_postgres(all_postgres_tiktok_rows)
    else:
        progress_history_df = _build_tiktok_detail_dataframe(captured_records)

    effective_filter_name = filter_name
    if detail_df.empty:
        if using_postgres_history and not progress_history_df.empty:
            latest_available = pd.to_datetime(progress_history_df["Date"]).max()
            latest_label = latest_available.strftime("%b %d, %Y")
            fallback_detail_df = progress_history_df[pd.to_datetime(progress_history_df["Date"]) == latest_available].copy()
            if not fallback_detail_df.empty:
                st.info(
                    "No PostgreSQL TikTok rows are available for the selected date window. "
                    f"Showing the latest available imported TikTok day instead: {latest_label}."
                )
                detail_df = fallback_detail_df
                effective_filter_name = f"{filter_name} (Latest Available)"
            else:
                st.info("No TikTok rows are available for the selected date window yet.")
                return
        else:
            st.info("No TikTok rows are available yet.")
            return

    filtered_detail_df = _filter_tiktok_detail_dataframe(detail_df, date_range.start_date, date_range.end_date)
    if filtered_detail_df.empty and not detail_df.empty:
        filtered_detail_df = detail_df.copy()
    if filtered_detail_df.empty:
        st.info("No TikTok rows fall inside the selected reporting period.")
        return

    shop_options = filtered_detail_df["Shop"].drop_duplicates().tolist()
    selected_shops = st.multiselect(
        "TikTok Shops",
        options=shop_options,
        default=shop_options,
        help="Choose which TikTok shops should be included in the reporting panes.",
        key="tiktok_selected_shops",
    )
    visible_detail_df = filtered_detail_df[filtered_detail_df["Shop"].isin(selected_shops or shop_options)].copy()
    if visible_detail_df.empty:
        st.info("No TikTok rows remain after applying the shop filter.")
        return

    summary_df = _build_tiktok_summary_dataframe(visible_detail_df, effective_filter_name)

    summary_pane, progress_pane, rate_pane, detail_pane = st.tabs(
        ["Summary", "To Date Summary", "Rate Metrics Report", "Detailed Rows"]
    )

    with summary_pane:
        st.markdown("##### Summary Table")
        _render_report_table(summary_df, table_key="tiktok_summary")

    with progress_pane:
        progress_view = st.radio(
            "To-date mode",
            options=["Weekly", "Monthly"],
            horizontal=True,
            key="tiktok_progress_view",
        )
        st.markdown(f"##### {progress_view} Progress By Shop")
        for shop_name in selected_shops or shop_options:
            shop_detail_df = progress_history_df[progress_history_df["Shop"] == shop_name].copy()
            if shop_detail_df.empty:
                continue
            st.markdown(f"###### {shop_name}")
            progress_df = (
                _build_tiktok_weekly_progress_dataframe(shop_detail_df)
                if progress_view == "Weekly"
                else _build_tiktok_monthly_progress_dataframe(shop_detail_df)
            )
            _render_report_table(progress_df, table_key=f"tiktok_progress_{progress_view.lower()}_{shop_name}")

    with rate_pane:
        comparison_view = st.radio(
            "Comparison mode",
            options=["Weekly", "Monthly"],
            horizontal=True,
            key="tiktok_rate_view",
        )
        _render_tiktok_rate_metric_guide()
        st.markdown(f"##### {comparison_view} Rate Comparison By Shop")
        for shop_name in selected_shops or shop_options:
            shop_detail_df = progress_history_df[progress_history_df["Shop"] == shop_name].copy()
            if shop_detail_df.empty:
                continue
            st.markdown(f"###### {shop_name}")
            comparison_df = (
                _build_tiktok_weekly_comparison_dataframe(shop_detail_df)
                if comparison_view == "Weekly"
                else _build_tiktok_monthly_comparison_dataframe(shop_detail_df)
            )
            _render_report_table(
                comparison_df,
                table_key=f"tiktok_rate_{comparison_view.lower()}_{shop_name}",
                header_tooltips={
                    "Revenue Growth Rate": "Percent change in gross revenue versus the previous comparable period.",
                    "Revenue Trend": "Simple interpretation of the revenue growth rate.",
                    "Traffic Growth Rate": "Percent change in visitors versus the previous comparable period.",
                    "Traffic Trend": "Simple interpretation of the visitor growth rate.",
                    "Visitor Conversion Rate": "Visitors divided by page views for the same row period, shown as a percentage.",
                },
            )

    with detail_pane:
        st.markdown("##### Detailed Table")
        detail_table_df = visible_detail_df[
            ["Shop", "Week", "Month", "Date", "Gross Revenue", "Items Sold", "Page Views", "Visitors", "Conversion Rate"]
        ].copy()
        detail_table_df["Gross Revenue"] = detail_table_df["Gross Revenue"].apply(lambda value: f"₱{float(value):,.2f}")
        detail_table_df["Conversion Rate"] = detail_table_df["Conversion Rate"].apply(lambda value: f"{float(value):.2f}%")
        _render_report_table(detail_table_df, table_key="tiktok_detail")

    st.caption(
        "These rows are built from captured TikTok Shop records. Re-running the capture job will append more dated rows and make the period summaries richer over time."
    )


def _render_record_tab(
    *,
    credential_source: str,
    meta_credential_source: str,
    postgres_source: str,
    service_account_path: str | None,
    meta_access_token: str | None,
    postgres_config,
) -> None:
    st.subheader("Implementation Record")

    status_rows = [
        {
            "Backend Source": "GA4 Credentials",
            "Status": "Ready" if service_account_path else "Missing",
            "Detail": credential_source if service_account_path else "Not configured in backend yet",
        },
        {
            "Backend Source": "Meta Access Token",
            "Status": "Ready" if meta_access_token else "Optional / Missing",
            "Detail": meta_credential_source if meta_access_token else "Live Graph API not configured",
        },
        {
            "Backend Source": "PostgreSQL Warehouse",
            "Status": "Ready" if postgres_config else "Missing",
            "Detail": postgres_source if postgres_config else "Not configured in backend yet",
        },
    ]
    st.dataframe(pd.DataFrame(status_rows), hide_index=True, use_container_width=True)

    if DOC_RECORD.exists():
        st.markdown(DOC_RECORD.read_text(encoding="utf-8"))
    else:
        st.info("Documentation record not found yet.")


def _render_report_table(
    df: pd.DataFrame,
    header_tooltips: dict[str, str] | None = None,
    table_key: str = "report_table",
) -> None:
    if df.empty:
        st.info("No rows available.")
        return

    total_rows = len(df)
    page_size = 12
    total_pages = max(1, (total_rows + page_size - 1) // page_size)
    state_key = f"{table_key}_page"
    if state_key not in st.session_state:
        st.session_state[state_key] = 1
    st.session_state[state_key] = max(1, min(int(st.session_state[state_key]), total_pages))

    if total_rows > page_size:
        nav_col1, nav_col2, nav_col3 = st.columns([0.12, 0.16, 0.72])
        with nav_col1:
            if st.button("Prev", key=f"{table_key}_prev", use_container_width=True, disabled=st.session_state[state_key] <= 1):
                st.session_state[state_key] -= 1
                st.rerun()
        with nav_col2:
            if st.button(
                "Next",
                key=f"{table_key}_next",
                use_container_width=True,
                disabled=st.session_state[state_key] >= total_pages,
            ):
                st.session_state[state_key] += 1
                st.rerun()
        with nav_col3:
            st.caption(
                f"Showing rows {((st.session_state[state_key] - 1) * page_size) + 1}"
                f" - {min(st.session_state[state_key] * page_size, total_rows)} of {total_rows}"
            )

    start_index = (st.session_state[state_key] - 1) * page_size
    end_index = start_index + page_size
    page_df = df.iloc[start_index:end_index].copy()
    display_df = page_df.copy().astype(object)
    for column in display_df.columns:
        display_df[column] = display_df[column].apply(_style_table_cell)

    table_html = display_df.to_html(index=False, classes=["report-table"], border=0, justify="left", escape=False)
    if header_tooltips:
        for header, tooltip in header_tooltips.items():
            table_html = table_html.replace(
                f"<th>{header}</th>",
                f'<th title="{html.escape(tooltip, quote=True)}">{header}</th>',
            )
    st.markdown(f'<div class="report-table-wrap">{table_html}</div>', unsafe_allow_html=True)


def _style_table_cell(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""

    text = html.escape(str(value))
    raw = str(value).strip()
    lower = raw.lower()

    if lower in {"growth", "new"}:
        return f'<span class="metric-positive metric-badge">{text}</span>'
    if lower in {"disgrowth"}:
        return f'<span class="metric-negative metric-badge">{text}</span>'
    if lower in {"no change"}:
        return f'<span class="metric-neutral metric-badge">{text}</span>'
    if lower in {"n/a"}:
        return f'<span class="metric-muted metric-badge">{text}</span>'

    if raw.endswith("%"):
        try:
            numeric_value = float(raw.replace("%", "").replace(",", ""))
        except ValueError:
            return text
        if numeric_value > 0:
            return f'<span class="metric-positive">{text}</span>'
        if numeric_value < 0:
            return f'<span class="metric-negative">{text}</span>'
        return f'<span class="metric-neutral">{text}</span>'

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if float(value) < 0:
            return f'<span class="metric-negative">{text}</span>'

    return text


def _first_existing_path(*paths: Path) -> Path:
    for path in paths:
        if path.exists():
            return path
    return paths[0]


def _inject_styles() -> None:
    st.markdown(
        """
        <style>
        .stApp {
            background:
                radial-gradient(circle at top left, rgba(20, 157, 221, 0.18), transparent 28%),
                radial-gradient(circle at top right, rgba(62, 207, 142, 0.14), transparent 24%),
                linear-gradient(180deg, #f4f8fb 0%, #eef4f2 100%);
        }
        .block-container {
            padding-top: 1.1rem;
            padding-bottom: 1.5rem;
        }
        .sticky-hero {
            position: sticky;
            top: 0.5rem;
            z-index: 1000;
            padding: 0.85rem 1.15rem 0.7rem 1.15rem;
            margin-bottom: 0.45rem;
            border-radius: 1rem;
            background: linear-gradient(90deg, rgba(255,255,255,0.92), rgba(244,250,253,0.88));
            border: 1px solid rgba(11, 66, 96, 0.08);
            backdrop-filter: blur(12px);
            box-shadow: 0 8px 24px rgba(14, 50, 67, 0.06);
        }
        .sticky-hero h1 {
            margin: 0;
            font-size: 2.7rem;
            line-height: 1.02;
            color: #203049;
            font-weight: 800;
        }
        .sticky-hero p {
            margin: 0.3rem 0 0 0;
            color: #6f7f8d;
            font-size: 1rem;
        }
        div[data-testid="stMetric"] {
            background: rgba(255, 255, 255, 0.78);
            border: 1px solid rgba(11, 66, 96, 0.08);
            padding: 0.6rem;
            border-radius: 0.8rem;
            box-shadow: 0 8px 20px rgba(14, 50, 67, 0.05);
        }
        div[data-testid="stMetric"] label {
            font-size: 1rem !important;
            font-weight: 700 !important;
        }
        div[data-testid="stMetric"] [data-testid="stMetricValue"] {
            font-size: 2rem !important;
            font-weight: 800 !important;
            line-height: 1.05 !important;
        }
        div[data-testid="stDataFrame"] {
            background: rgba(255, 255, 255, 0.74);
            border-radius: 0.8rem;
        }
        div[data-testid="stTabs"] {
            margin-top: -0.1rem;
            margin-bottom: 0.55rem;
        }
        div[data-testid="stTabs"] [data-baseweb="tab-list"] {
            gap: 0.45rem;
            padding: 0.2rem;
            background: rgba(255, 255, 255, 0.48);
            border: 1px solid rgba(11, 66, 96, 0.08);
            border-radius: 0.95rem;
        }
        div[data-testid="stTabs"] [data-baseweb="tab"] {
            height: auto !important;
            padding: 0.72rem 1rem !important;
            border-radius: 0.8rem !important;
            background: rgba(255, 255, 255, 0.72);
            border: 1px solid transparent;
            font-size: 1rem !important;
            font-weight: 700 !important;
            color: #27415e !important;
        }
        div[data-testid="stTabs"] [data-baseweb="tab"]:hover {
            background: rgba(232, 243, 250, 0.96);
            border-color: rgba(64, 129, 173, 0.18);
        }
        div[data-testid="stTabs"] [aria-selected="true"] {
            background: linear-gradient(180deg, #ffffff 0%, #edf6ff 100%) !important;
            border: 1px solid rgba(64, 129, 173, 0.22) !important;
            color: #12365c !important;
            box-shadow: 0 8px 18px rgba(27, 88, 132, 0.10);
        }
        .main-tabs-anchor, .harmony-tabs-anchor, .quadro-tabs-anchor {
            height: 0;
            overflow: hidden;
        }
        .stElementContainer:has(.main-tabs-anchor) ~ div[data-testid="stTabs"] > div > div[data-baseweb="tab-list"] > [data-baseweb="tab"]:nth-child(2) {
            background: rgba(255, 214, 10, 0.14) !important;
            border-color: rgba(255, 214, 10, 0.30) !important;
            color: #181818 !important;
        }
        .stElementContainer:has(.main-tabs-anchor) ~ div[data-testid="stTabs"] > div > div[data-baseweb="tab-list"] > [data-baseweb="tab"]:nth-child(2):hover {
            background: rgba(255, 214, 10, 0.22) !important;
            border-color: rgba(255, 214, 10, 0.42) !important;
        }
        .stElementContainer:has(.main-tabs-anchor) ~ div[data-testid="stTabs"] > div > div[data-baseweb="tab-list"] > [data-baseweb="tab"]:nth-child(2)[aria-selected="true"] {
            background: linear-gradient(180deg, #2b2b2b 0%, #111111 100%) !important;
            border-color: rgba(255, 214, 10, 0.70) !important;
            color: #ffd60a !important;
            box-shadow: 0 8px 18px rgba(0, 0, 0, 0.18);
        }
        .stElementContainer:has(.main-tabs-anchor) ~ div[data-testid="stTabs"] > div > div[data-baseweb="tab-list"] > [data-baseweb="tab"]:nth-child(2)[aria-selected="true"] p {
            color: #ffd60a !important;
        }
        .stElementContainer:has(.main-tabs-anchor) ~ div[data-testid="stTabs"] > div > div[data-baseweb="tab-list"] > [data-baseweb="tab"]:nth-child(3) {
            background: rgba(214, 40, 40, 0.10) !important;
            border-color: rgba(214, 40, 40, 0.24) !important;
            color: #8f1010 !important;
        }
        .stElementContainer:has(.main-tabs-anchor) ~ div[data-testid="stTabs"] > div > div[data-baseweb="tab-list"] > [data-baseweb="tab"]:nth-child(3):hover {
            background: rgba(214, 40, 40, 0.17) !important;
            border-color: rgba(214, 40, 40, 0.36) !important;
        }
        .stElementContainer:has(.main-tabs-anchor) ~ div[data-testid="stTabs"] > div > div[data-baseweb="tab-list"] > [data-baseweb="tab"]:nth-child(3)[aria-selected="true"] {
            background: linear-gradient(180deg, #d62828 0%, #b91f1f 100%) !important;
            border-color: rgba(214, 40, 40, 0.70) !important;
            color: #ffffff !important;
            box-shadow: 0 8px 18px rgba(185, 31, 31, 0.20);
        }
        .stElementContainer:has(.main-tabs-anchor) ~ div[data-testid="stTabs"] > div > div[data-baseweb="tab-list"] > [data-baseweb="tab"]:nth-child(3)[aria-selected="true"] p {
            color: #ffffff !important;
        }
        .stElementContainer:has(.harmony-tabs-anchor) ~ div[data-testid="stTabs"] > div > div[data-baseweb="tab-list"] > [data-baseweb="tab"]:nth-child(1) {
            background: rgba(17, 17, 17, 0.08) !important;
            border-color: rgba(17, 17, 17, 0.22) !important;
            color: #111111 !important;
        }
        .stElementContainer:has(.harmony-tabs-anchor) ~ div[data-testid="stTabs"] > div > div[data-baseweb="tab-list"] > [data-baseweb="tab"]:nth-child(1):hover {
            background: rgba(17, 17, 17, 0.14) !important;
            border-color: rgba(17, 17, 17, 0.34) !important;
        }
        .stElementContainer:has(.harmony-tabs-anchor) ~ div[data-testid="stTabs"] > div > div[data-baseweb="tab-list"] > [data-baseweb="tab"]:nth-child(1)[aria-selected="true"] {
            background: linear-gradient(180deg, #111111 0%, #000000 100%) !important;
            border-color: rgba(17, 17, 17, 0.75) !important;
            color: #ffffff !important;
            box-shadow: 0 8px 18px rgba(0, 0, 0, 0.20);
        }
        .stElementContainer:has(.harmony-tabs-anchor) ~ div[data-testid="stTabs"] > div > div[data-baseweb="tab-list"] > [data-baseweb="tab"]:nth-child(1)[aria-selected="true"] p {
            color: #ffffff !important;
        }
        .stElementContainer:has(.harmony-tabs-anchor) ~ div[data-testid="stTabs"] > div > div[data-baseweb="tab-list"] > [data-baseweb="tab"]:nth-child(2),
        .stElementContainer:has(.quadro-tabs-anchor) ~ div[data-testid="stTabs"] > div > div[data-baseweb="tab-list"] > [data-baseweb="tab"]:nth-child(1) {
            background: rgba(24, 119, 242, 0.10) !important;
            border-color: rgba(24, 119, 242, 0.24) !important;
            color: #0f4aa6 !important;
        }
        .stElementContainer:has(.harmony-tabs-anchor) ~ div[data-testid="stTabs"] > div > div[data-baseweb="tab-list"] > [data-baseweb="tab"]:nth-child(2):hover,
        .stElementContainer:has(.quadro-tabs-anchor) ~ div[data-testid="stTabs"] > div > div[data-baseweb="tab-list"] > [data-baseweb="tab"]:nth-child(1):hover {
            background: rgba(24, 119, 242, 0.17) !important;
            border-color: rgba(24, 119, 242, 0.34) !important;
        }
        .stElementContainer:has(.harmony-tabs-anchor) ~ div[data-testid="stTabs"] > div > div[data-baseweb="tab-list"] > [data-baseweb="tab"]:nth-child(2)[aria-selected="true"],
        .stElementContainer:has(.quadro-tabs-anchor) ~ div[data-testid="stTabs"] > div > div[data-baseweb="tab-list"] > [data-baseweb="tab"]:nth-child(1)[aria-selected="true"] {
            background: linear-gradient(180deg, #1877f2 0%, #145dc2 100%) !important;
            border-color: rgba(24, 119, 242, 0.75) !important;
            color: #ffffff !important;
            box-shadow: 0 8px 18px rgba(20, 93, 194, 0.18);
        }
        .stElementContainer:has(.harmony-tabs-anchor) ~ div[data-testid="stTabs"] > div > div[data-baseweb="tab-list"] > [data-baseweb="tab"]:nth-child(2)[aria-selected="true"] p,
        .stElementContainer:has(.quadro-tabs-anchor) ~ div[data-testid="stTabs"] > div > div[data-baseweb="tab-list"] > [data-baseweb="tab"]:nth-child(1)[aria-selected="true"] p {
            color: #ffffff !important;
        }
        .stElementContainer:has(.harmony-tabs-anchor) ~ div[data-testid="stTabs"] > div > div[data-baseweb="tab-list"] > [data-baseweb="tab"]:nth-child(3),
        .stElementContainer:has(.quadro-tabs-anchor) ~ div[data-testid="stTabs"] > div > div[data-baseweb="tab-list"] > [data-baseweb="tab"]:nth-child(2) {
            background: rgba(225, 48, 108, 0.10) !important;
            border-color: rgba(225, 48, 108, 0.22) !important;
            color: #a61c50 !important;
        }
        .stElementContainer:has(.harmony-tabs-anchor) ~ div[data-testid="stTabs"] > div > div[data-baseweb="tab-list"] > [data-baseweb="tab"]:nth-child(3):hover,
        .stElementContainer:has(.quadro-tabs-anchor) ~ div[data-testid="stTabs"] > div > div[data-baseweb="tab-list"] > [data-baseweb="tab"]:nth-child(2):hover {
            background: rgba(225, 48, 108, 0.17) !important;
            border-color: rgba(225, 48, 108, 0.34) !important;
        }
        .stElementContainer:has(.harmony-tabs-anchor) ~ div[data-testid="stTabs"] > div > div[data-baseweb="tab-list"] > [data-baseweb="tab"]:nth-child(3)[aria-selected="true"],
        .stElementContainer:has(.quadro-tabs-anchor) ~ div[data-testid="stTabs"] > div > div[data-baseweb="tab-list"] > [data-baseweb="tab"]:nth-child(2)[aria-selected="true"] {
            background: linear-gradient(180deg, #e1306c 0%, #c52d8b 100%) !important;
            border-color: rgba(225, 48, 108, 0.70) !important;
            color: #ffffff !important;
            box-shadow: 0 8px 18px rgba(197, 45, 139, 0.18);
        }
        .stElementContainer:has(.harmony-tabs-anchor) ~ div[data-testid="stTabs"] > div > div[data-baseweb="tab-list"] > [data-baseweb="tab"]:nth-child(3)[aria-selected="true"] p,
        .stElementContainer:has(.quadro-tabs-anchor) ~ div[data-testid="stTabs"] > div > div[data-baseweb="tab-list"] > [data-baseweb="tab"]:nth-child(2)[aria-selected="true"] p {
            color: #ffffff !important;
        }
        div[data-testid="stTabs"] [aria-selected="true"] p,
        div[data-testid="stTabs"] [data-baseweb="tab"] p {
            font-size: 1rem !important;
            font-weight: 800 !important;
        }
        div[data-testid="stMarkdownContainer"] h2,
        div[data-testid="stMarkdownContainer"] h3,
        div[data-testid="stMarkdownContainer"] h4,
        div[data-testid="stMarkdownContainer"] h5,
        div[data-testid="stMarkdownContainer"] h6 {
            margin-top: 0.35rem;
            margin-bottom: 0.35rem;
            color: #203049;
            font-weight: 800;
        }
        div[data-testid="stMultiSelect"] {
            margin-bottom: 0.15rem;
        }
        .report-table-wrap {
            width: 100%;
            overflow-x: auto;
            overflow-y: auto;
            max-height: 28rem;
            background: rgba(255,255,255,0.78);
            border: 1px solid rgba(11, 66, 96, 0.08);
            border-radius: 0.9rem;
            box-shadow: 0 8px 20px rgba(14, 50, 67, 0.05);
        }
        .report-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 1.08rem;
            line-height: 1.25;
            color: #203049;
        }
        .report-table thead th {
            position: sticky;
            top: 0;
            background: #eef5fb;
            color: #203049;
            font-size: 1.15rem;
            font-weight: 800;
            padding: 0.8rem 0.7rem;
            border-bottom: 1px solid rgba(11, 66, 96, 0.12);
            text-align: left;
            white-space: nowrap;
        }
        .report-table tbody td {
            font-size: 1.08rem;
            font-weight: 650;
            padding: 0.72rem 0.7rem;
            border-bottom: 1px solid rgba(11, 66, 96, 0.08);
            vertical-align: top;
        }
        .report-table tbody tr:last-child td {
            border-bottom: none;
        }
        .metric-positive {
            color: #0f8a4a;
            font-weight: 800;
        }
        .metric-negative {
            color: #c43d2f;
            font-weight: 800;
        }
        .metric-neutral {
            color: #7b5b00;
            font-weight: 800;
        }
        .metric-muted {
            color: #708192;
            font-weight: 700;
        }
        .metric-badge {
            display: inline-block;
            padding: 0.12rem 0.45rem;
            border-radius: 999px;
            background: rgba(255, 255, 255, 0.75);
            border: 1px solid rgba(11, 66, 96, 0.08);
        }
        .metric-guide {
            display: flex;
            flex-wrap: wrap;
            gap: 0.45rem;
            margin: 0.1rem 0 0.7rem 0;
        }
        .metric-guide-item {
            display: inline-flex;
            align-items: center;
            padding: 0.34rem 0.58rem;
            border-radius: 999px;
            background: rgba(238, 245, 251, 0.95);
            border: 1px solid rgba(11, 66, 96, 0.10);
            color: #203049;
            font-size: 0.92rem;
            font-weight: 700;
            cursor: help;
        }
        .metric-guide-note {
            margin: 0.15rem 0 0.6rem 0;
            font-size: 0.95rem;
            color: #526b84;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
