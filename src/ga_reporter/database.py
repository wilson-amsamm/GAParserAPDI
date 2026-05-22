from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ga_reporter.meta_capture import MetaCapturedRecord


@dataclass(frozen=True)
class PostgresConfig:
    host: str
    port: int
    database: str
    user: str
    password: str

    def dsn(self) -> str:
        return (
            f"host={self.host} port={self.port} dbname={self.database} "
            f"user={self.user} password={self.password}"
        )


def resolve_postgres_config(streamlit_secrets: Any | None = None) -> tuple[PostgresConfig | None, str]:
    import os

    secrets = streamlit_secrets or {}
    postgres_section = secrets.get("postgres")
    if hasattr(postgres_section, "to_dict"):
        postgres_section = postgres_section.to_dict()

    if isinstance(postgres_section, dict):
        config = _config_from_mapping(postgres_section)
        if config:
            return config, "streamlit secret [postgres]"

    env_mapping = {
        "host": os.getenv("PGHOST") or os.getenv("POSTGRES_HOST"),
        "port": os.getenv("PGPORT") or os.getenv("POSTGRES_PORT"),
        "database": os.getenv("PGDATABASE") or os.getenv("POSTGRES_DB"),
        "user": os.getenv("PGUSER") or os.getenv("POSTGRES_USER"),
        "password": os.getenv("PGPASSWORD") or os.getenv("POSTGRES_PASSWORD"),
    }
    config = _config_from_mapping(env_mapping)
    if config:
        return config, "environment"

    return None, "not configured"


def ensure_schema(config: PostgresConfig) -> None:
    with _connect(config) as conn, conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS platform_sources (
                id BIGSERIAL PRIMARY KEY,
                platform TEXT NOT NULL,
                profile_name TEXT NOT NULL,
                external_id TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE(platform, profile_name)
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_social_metrics (
                id BIGSERIAL PRIMARY KEY,
                source_id BIGINT NOT NULL REFERENCES platform_sources(id) ON DELETE CASCADE,
                metric_date DATE NOT NULL,
                views DOUBLE PRECISION NOT NULL DEFAULT 0,
                viewers DOUBLE PRECISION NOT NULL DEFAULT 0,
                reach DOUBLE PRECISION NOT NULL DEFAULT 0,
                impressions DOUBLE PRECISION NOT NULL DEFAULT 0,
                content_interactions DOUBLE PRECISION NOT NULL DEFAULT 0,
                link_clicks DOUBLE PRECISION NOT NULL DEFAULT 0,
                visits DOUBLE PRECISION NOT NULL DEFAULT 0,
                follows DOUBLE PRECISION NOT NULL DEFAULT 0,
                unfollows DOUBLE PRECISION NOT NULL DEFAULT 0,
                net_follows DOUBLE PRECISION NOT NULL DEFAULT 0,
                captured_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                capture_source TEXT NOT NULL DEFAULT 'meta_business_suite_automation',
                visible_date_range TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE(source_id, metric_date)
            );
            """
        )
        cur.execute(
            """
            ALTER TABLE daily_social_metrics
            ADD COLUMN IF NOT EXISTS viewers DOUBLE PRECISION NOT NULL DEFAULT 0;
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_daily_social_metrics_metric_date
            ON daily_social_metrics(metric_date);
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_website_metrics (
                id BIGSERIAL PRIMARY KEY,
                source_id BIGINT NOT NULL REFERENCES platform_sources(id) ON DELETE CASCADE,
                metric_date DATE NOT NULL,
                visitors DOUBLE PRECISION NOT NULL DEFAULT 0,
                impressions DOUBLE PRECISION NOT NULL DEFAULT 0,
                captured_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                capture_source TEXT NOT NULL DEFAULT 'ga4_api',
                notes TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE(source_id, metric_date)
            );
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_daily_website_metrics_metric_date
            ON daily_website_metrics(metric_date);
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_tiktok_metrics (
                id BIGSERIAL PRIMARY KEY,
                source_id BIGINT NOT NULL REFERENCES platform_sources(id) ON DELETE CASCADE,
                metric_date DATE NOT NULL,
                gross_revenue DOUBLE PRECISION NOT NULL DEFAULT 0,
                items_sold DOUBLE PRECISION NOT NULL DEFAULT 0,
                page_views DOUBLE PRECISION NOT NULL DEFAULT 0,
                visitors DOUBLE PRECISION NOT NULL DEFAULT 0,
                conversion_rate DOUBLE PRECISION NOT NULL DEFAULT 0,
                captured_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                capture_source TEXT NOT NULL DEFAULT 'tiktok_seller_manual_capture',
                visible_date_range TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE(source_id, metric_date)
            );
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_daily_tiktok_metrics_metric_date
            ON daily_tiktok_metrics(metric_date);
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS viber_subscribers (
                id BIGSERIAL PRIMARY KEY,
                subscriber_id TEXT NOT NULL UNIQUE,
                subscriber_name TEXT NOT NULL DEFAULT '',
                avatar_url TEXT NOT NULL DEFAULT '',
                language TEXT NOT NULL DEFAULT '',
                country TEXT NOT NULL DEFAULT '',
                subscribed BOOLEAN NOT NULL DEFAULT TRUE,
                first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )
        conn.commit()


def upsert_meta_captured_records(config: PostgresConfig, records: list[MetaCapturedRecord]) -> int:
    inserted = 0
    with _connect(config) as conn, conn.cursor() as cur:
        for record in records:
            if not record.metrics:
                continue
            cur.execute(
                """
                INSERT INTO platform_sources(platform, profile_name)
                VALUES (%s, %s)
                ON CONFLICT (platform, profile_name)
                DO UPDATE SET updated_at = NOW()
                RETURNING id;
                """,
                (record.platform, record.profile_name),
            )
            source_id = cur.fetchone()[0]
            metric_date = record.captured_at[:10]
            metrics = record.metrics
            cur.execute(
                """
                INSERT INTO daily_social_metrics (
                    source_id,
                    metric_date,
                    views,
                    viewers,
                    reach,
                    impressions,
                    content_interactions,
                    link_clicks,
                    visits,
                    follows,
                    unfollows,
                    net_follows,
                    captured_at,
                    capture_source,
                    visible_date_range,
                    notes,
                    updated_at
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW()
                )
                ON CONFLICT (source_id, metric_date)
                DO UPDATE SET
                    views = EXCLUDED.views,
                    viewers = EXCLUDED.viewers,
                    reach = EXCLUDED.reach,
                    impressions = EXCLUDED.impressions,
                    content_interactions = EXCLUDED.content_interactions,
                    link_clicks = EXCLUDED.link_clicks,
                    visits = EXCLUDED.visits,
                    follows = EXCLUDED.follows,
                    unfollows = EXCLUDED.unfollows,
                    net_follows = EXCLUDED.net_follows,
                    captured_at = EXCLUDED.captured_at,
                    capture_source = EXCLUDED.capture_source,
                    visible_date_range = EXCLUDED.visible_date_range,
                    notes = EXCLUDED.notes,
                    updated_at = NOW();
                """,
                (
                    source_id,
                    metric_date,
                    _metric(metrics, "views"),
                    _metric(metrics, "viewers"),
                    _metric(metrics, "reach"),
                    _metric(metrics, "impressions", "page_impressions", "post_impressions"),
                    _metric(metrics, "content_interactions", "interaction", "engaged_users"),
                    _metric(metrics, "link_clicks", "clicks"),
                    _metric(metrics, "visits", "facebook_visits", "profile_visits"),
                    _metric(metrics, "follows"),
                    _metric(metrics, "unfollows"),
                    _metric(metrics, "net_follows"),
                    record.captured_at,
                    record.source,
                    record.visible_date_range,
                    record.notes,
                ),
            )
            inserted += 1
        conn.commit()
    return inserted


def load_social_daily_metrics(
    config: PostgresConfig,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict[str, Any]]:
    query = """
        SELECT
            ps.platform,
            ps.profile_name,
            dsm.metric_date,
            dsm.views,
            dsm.viewers,
            dsm.reach,
            dsm.impressions,
            dsm.content_interactions,
            dsm.link_clicks,
            dsm.visits,
            dsm.follows,
            dsm.unfollows,
            dsm.net_follows,
            dsm.captured_at,
            dsm.capture_source,
            dsm.visible_date_range,
            dsm.notes
        FROM daily_social_metrics dsm
        JOIN platform_sources ps ON ps.id = dsm.source_id
    """
    params: list[Any] = []
    clauses: list[str] = []
    if start_date:
        clauses.append("dsm.metric_date >= %s")
        params.append(start_date)
    if end_date:
        clauses.append("dsm.metric_date <= %s")
        params.append(end_date)
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY dsm.metric_date DESC, ps.profile_name ASC"

    with _connect(config) as conn, conn.cursor() as cur:
        cur.execute(query, params)
        rows = cur.fetchall()

    result: list[dict[str, Any]] = []
    for row in rows:
        result.append(
            {
                "platform": row[0],
                "profile_name": row[1],
                "metric_date": row[2],
                "views": row[3],
                "viewers": row[4],
                "reach": row[5],
                "impressions": row[6],
                "content_interactions": row[7],
                "link_clicks": row[8],
                "visits": row[9],
                "follows": row[10],
                "unfollows": row[11],
                "net_follows": row[12],
                "captured_at": row[13],
                "capture_source": row[14],
                "visible_date_range": row[15],
                "notes": row[16],
            }
        )
    return result


def load_social_profile_aggregates(
    config: PostgresConfig,
    start_date: str,
    end_date: str,
) -> list[dict[str, Any]]:
    with _connect(config) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                ps.platform,
                ps.profile_name,
                SUM(dsm.views) AS views,
                SUM(dsm.viewers) AS viewers,
                SUM(dsm.reach) AS reach,
                SUM(dsm.impressions) AS impressions,
                SUM(dsm.content_interactions) AS content_interactions,
                SUM(dsm.link_clicks) AS link_clicks,
                SUM(dsm.visits) AS visits,
                SUM(dsm.follows) AS follows,
                SUM(dsm.unfollows) AS unfollows,
                SUM(dsm.net_follows) AS net_follows
            FROM daily_social_metrics dsm
            JOIN platform_sources ps ON ps.id = dsm.source_id
            WHERE dsm.metric_date >= %s AND dsm.metric_date <= %s
            GROUP BY ps.platform, ps.profile_name
            ORDER BY ps.profile_name ASC
            """,
            (start_date, end_date),
        )
        rows = cur.fetchall()

    aggregates: list[dict[str, Any]] = []
    for row in rows:
        aggregates.append(
            {
                "platform": row[0],
                "profile_name": row[1],
                "metrics": {
                    "views": row[2],
                    "viewers": row[3],
                    "reach": row[4],
                    "impressions": row[5],
                    "content_interactions": row[6],
                    "link_clicks": row[7],
                    "visits": row[8],
                    "follows": row[9],
                    "unfollows": row[10],
                    "net_follows": row[11],
                },
            }
        )
    return aggregates


def upsert_website_daily_metrics(
    config: PostgresConfig,
    *,
    site_name: str,
    property_id: str,
    daily_rows: list[dict[str, Any]],
    capture_source: str = "ga4_api",
    notes: str = "",
) -> int:
    if not daily_rows:
        return 0

    inserted = 0
    with _connect(config) as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO platform_sources(platform, profile_name, external_id)
            VALUES (%s, %s, %s)
            ON CONFLICT (platform, profile_name)
            DO UPDATE SET
                external_id = EXCLUDED.external_id,
                updated_at = NOW()
            RETURNING id;
            """,
            ("website_ga4", site_name, property_id),
        )
        source_id = cur.fetchone()[0]

        for row in daily_rows:
            cur.execute(
                """
                INSERT INTO daily_website_metrics (
                    source_id,
                    metric_date,
                    visitors,
                    impressions,
                    capture_source,
                    notes,
                    updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (source_id, metric_date)
                DO UPDATE SET
                    visitors = EXCLUDED.visitors,
                    impressions = EXCLUDED.impressions,
                    capture_source = EXCLUDED.capture_source,
                    notes = EXCLUDED.notes,
                    updated_at = NOW();
                """,
                (
                    source_id,
                    row["metric_date"],
                    float(row.get("visitors", 0) or 0),
                    float(row.get("impressions", 0) or 0),
                    capture_source,
                    notes,
                ),
            )
            inserted += 1
        conn.commit()
    return inserted


def load_website_daily_metrics(
    config: PostgresConfig,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict[str, Any]]:
    query = """
        SELECT
            ps.profile_name,
            ps.external_id,
            dwm.metric_date,
            dwm.visitors,
            dwm.impressions,
            dwm.captured_at,
            dwm.capture_source,
            dwm.notes
        FROM daily_website_metrics dwm
        JOIN platform_sources ps ON ps.id = dwm.source_id
        WHERE ps.platform = 'website_ga4'
    """
    params: list[Any] = []
    if start_date:
        query += " AND dwm.metric_date >= %s"
        params.append(start_date)
    if end_date:
        query += " AND dwm.metric_date <= %s"
        params.append(end_date)
    query += " ORDER BY dwm.metric_date DESC, ps.profile_name ASC"

    with _connect(config) as conn, conn.cursor() as cur:
        cur.execute(query, params)
        rows = cur.fetchall()

    result: list[dict[str, Any]] = []
    for row in rows:
        result.append(
            {
                "site_name": row[0],
                "property_id": row[1],
                "metric_date": row[2],
                "visitors": row[3],
                "impressions": row[4],
                "captured_at": row[5],
                "capture_source": row[6],
                "notes": row[7],
            }
        )
    return result


def upsert_tiktok_daily_metrics(
    config: PostgresConfig,
    *,
    profile_name: str,
    external_id: str,
    daily_rows: list[dict[str, Any]],
    capture_source: str = "tiktok_seller_manual_capture",
    notes: str = "",
) -> int:
    if not daily_rows:
        return 0

    inserted = 0
    with _connect(config) as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO platform_sources(platform, profile_name, external_id)
            VALUES (%s, %s, %s)
            ON CONFLICT (platform, profile_name)
            DO UPDATE SET
                external_id = EXCLUDED.external_id,
                updated_at = NOW()
            RETURNING id;
            """,
            ("tiktok_shop", profile_name, external_id),
        )
        source_id = cur.fetchone()[0]

        for row in daily_rows:
            cur.execute(
                """
                INSERT INTO daily_tiktok_metrics (
                    source_id,
                    metric_date,
                    gross_revenue,
                    items_sold,
                    page_views,
                    visitors,
                    conversion_rate,
                    capture_source,
                    visible_date_range,
                    notes,
                    updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (source_id, metric_date)
                DO UPDATE SET
                    gross_revenue = EXCLUDED.gross_revenue,
                    items_sold = EXCLUDED.items_sold,
                    page_views = EXCLUDED.page_views,
                    visitors = EXCLUDED.visitors,
                    conversion_rate = EXCLUDED.conversion_rate,
                    capture_source = EXCLUDED.capture_source,
                    visible_date_range = EXCLUDED.visible_date_range,
                    notes = EXCLUDED.notes,
                    updated_at = NOW();
                """,
                (
                    source_id,
                    row["metric_date"],
                    float(row.get("gross_revenue", 0) or 0),
                    float(row.get("items_sold", 0) or 0),
                    float(row.get("page_views", 0) or 0),
                    float(row.get("visitors", 0) or 0),
                    float(row.get("conversion_rate", 0) or 0),
                    capture_source,
                    str(row.get("visible_date_range", "") or ""),
                    notes or str(row.get("notes", "") or ""),
                ),
            )
            inserted += 1
        conn.commit()
    return inserted


def load_tiktok_daily_metrics(
    config: PostgresConfig,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict[str, Any]]:
    query = """
        SELECT
            ps.profile_name,
            ps.external_id,
            dtm.metric_date,
            dtm.gross_revenue,
            dtm.items_sold,
            dtm.page_views,
            dtm.visitors,
            dtm.conversion_rate,
            dtm.captured_at,
            dtm.capture_source,
            dtm.visible_date_range,
            dtm.notes
        FROM daily_tiktok_metrics dtm
        JOIN platform_sources ps ON ps.id = dtm.source_id
        WHERE ps.platform = 'tiktok_shop'
    """
    params: list[Any] = []
    if start_date:
        query += " AND dtm.metric_date >= %s"
        params.append(start_date)
    if end_date:
        query += " AND dtm.metric_date <= %s"
        params.append(end_date)
    query += " ORDER BY dtm.metric_date DESC, ps.profile_name ASC"

    with _connect(config) as conn, conn.cursor() as cur:
        cur.execute(query, params)
        rows = cur.fetchall()

    return [
        {
            "profile_name": row[0],
            "external_id": row[1],
            "metric_date": row[2],
            "gross_revenue": row[3],
            "items_sold": row[4],
            "page_views": row[5],
            "visitors": row[6],
            "conversion_rate": row[7],
            "captured_at": row[8],
            "capture_source": row[9],
            "visible_date_range": row[10],
            "notes": row[11],
        }
        for row in rows
    ]


def upsert_viber_subscriber(
    config: PostgresConfig,
    *,
    subscriber_id: str,
    subscriber_name: str = "",
    avatar_url: str = "",
    language: str = "",
    country: str = "",
    subscribed: bool = True,
) -> None:
    with _connect(config) as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO viber_subscribers (
                subscriber_id,
                subscriber_name,
                avatar_url,
                language,
                country,
                subscribed,
                last_seen_at,
                updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW())
            ON CONFLICT (subscriber_id)
            DO UPDATE SET
                subscriber_name = EXCLUDED.subscriber_name,
                avatar_url = EXCLUDED.avatar_url,
                language = EXCLUDED.language,
                country = EXCLUDED.country,
                subscribed = EXCLUDED.subscribed,
                last_seen_at = NOW(),
                updated_at = NOW();
            """,
            (
                subscriber_id,
                subscriber_name,
                avatar_url,
                language,
                country,
                subscribed,
            ),
        )
        conn.commit()


def update_viber_subscription_status(
    config: PostgresConfig,
    *,
    subscriber_id: str,
    subscribed: bool,
) -> None:
    with _connect(config) as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE viber_subscribers
            SET subscribed = %s,
                last_seen_at = NOW(),
                updated_at = NOW()
            WHERE subscriber_id = %s;
            """,
            (subscribed, subscriber_id),
        )
        conn.commit()


def load_viber_subscribers(config: PostgresConfig, subscribed_only: bool = True) -> list[dict[str, Any]]:
    query = """
        SELECT subscriber_id, subscriber_name, avatar_url, language, country, subscribed, first_seen_at, last_seen_at
        FROM viber_subscribers
    """
    params: list[Any] = []
    if subscribed_only:
        query += " WHERE subscribed = TRUE"
    query += " ORDER BY subscriber_name ASC, subscriber_id ASC"

    with _connect(config) as conn, conn.cursor() as cur:
        cur.execute(query, params)
        rows = cur.fetchall()

    return [
        {
            "subscriber_id": row[0],
            "subscriber_name": row[1],
            "avatar_url": row[2],
            "language": row[3],
            "country": row[4],
            "subscribed": row[5],
            "first_seen_at": row[6],
            "last_seen_at": row[7],
        }
        for row in rows
    ]


def load_latest_social_profile_metrics(config: PostgresConfig) -> list[dict[str, Any]]:
    with _connect(config) as conn, conn.cursor() as cur:
        cur.execute(
            """
            WITH latest_dates AS (
                SELECT source_id, MAX(metric_date) AS metric_date
                FROM daily_social_metrics
                GROUP BY source_id
            )
            SELECT
                ps.platform,
                ps.profile_name,
                dsm.metric_date,
                dsm.views,
                dsm.viewers,
                dsm.reach,
                dsm.impressions,
                dsm.content_interactions,
                dsm.link_clicks,
                dsm.visits,
                dsm.follows,
                dsm.unfollows,
                dsm.net_follows
            FROM latest_dates ld
            JOIN daily_social_metrics dsm
                ON dsm.source_id = ld.source_id
               AND dsm.metric_date = ld.metric_date
            JOIN platform_sources ps ON ps.id = dsm.source_id
            ORDER BY ps.profile_name ASC
            """
        )
        rows = cur.fetchall()
    return [
        {
            "platform": row[0],
            "profile_name": row[1],
            "metric_date": row[2],
            "views": row[3],
            "viewers": row[4],
            "reach": row[5],
            "impressions": row[6],
            "content_interactions": row[7],
            "link_clicks": row[8],
            "visits": row[9],
            "follows": row[10],
            "unfollows": row[11],
            "net_follows": row[12],
        }
        for row in rows
    ]


def load_latest_website_profile_metrics(config: PostgresConfig) -> list[dict[str, Any]]:
    with _connect(config) as conn, conn.cursor() as cur:
        cur.execute(
            """
            WITH latest_dates AS (
                SELECT source_id, MAX(metric_date) AS metric_date
                FROM daily_website_metrics
                GROUP BY source_id
            )
            SELECT
                ps.profile_name,
                ps.external_id,
                dwm.metric_date,
                dwm.visitors,
                dwm.impressions
            FROM latest_dates ld
            JOIN daily_website_metrics dwm
                ON dwm.source_id = ld.source_id
               AND dwm.metric_date = ld.metric_date
            JOIN platform_sources ps ON ps.id = dwm.source_id
            WHERE ps.platform = 'website_ga4'
            ORDER BY ps.profile_name ASC
            """
        )
        rows = cur.fetchall()
    return [
        {
            "site_name": row[0],
            "property_id": row[1],
            "metric_date": row[2],
            "visitors": row[3],
            "impressions": row[4],
        }
        for row in rows
    ]


def load_latest_tiktok_profile_metrics(config: PostgresConfig) -> list[dict[str, Any]]:
    with _connect(config) as conn, conn.cursor() as cur:
        cur.execute(
            """
            WITH latest_dates AS (
                SELECT source_id, MAX(metric_date) AS metric_date
                FROM daily_tiktok_metrics
                GROUP BY source_id
            )
            SELECT
                ps.profile_name,
                ps.external_id,
                dtm.metric_date,
                dtm.gross_revenue,
                dtm.items_sold,
                dtm.page_views,
                dtm.visitors,
                dtm.conversion_rate
            FROM latest_dates ld
            JOIN daily_tiktok_metrics dtm
                ON dtm.source_id = ld.source_id
               AND dtm.metric_date = ld.metric_date
            JOIN platform_sources ps ON ps.id = dtm.source_id
            WHERE ps.platform = 'tiktok_shop'
            ORDER BY ps.profile_name ASC
            """
        )
        rows = cur.fetchall()
    return [
        {
            "shop_name": row[0],
            "external_id": row[1],
            "metric_date": row[2],
            "gross_revenue": row[3],
            "items_sold": row[4],
            "page_views": row[5],
            "visitors": row[6],
            "conversion_rate": row[7],
        }
        for row in rows
    ]


def _connect(config: PostgresConfig):
    import psycopg

    return psycopg.connect(config.dsn())


def _config_from_mapping(mapping: dict[str, Any]) -> PostgresConfig | None:
    host = str(mapping.get("host", "")).strip()
    port_raw = mapping.get("port", 5432)
    if port_raw in (None, ""):
        port_raw = 5432
    database = str(mapping.get("database", "")).strip()
    user = str(mapping.get("user", "")).strip()
    password = str(mapping.get("password", "")).strip()
    if not all([host, database, user, password]):
        return None
    return PostgresConfig(
        host=host,
        port=int(port_raw),
        database=database,
        user=user,
        password=password,
    )


def _metric(metrics: dict[str, float], *names: str) -> float:
    for name in names:
        if name in metrics:
            return float(metrics[name])
    return 0.0
