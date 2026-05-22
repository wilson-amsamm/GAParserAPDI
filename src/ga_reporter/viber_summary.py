from __future__ import annotations

from datetime import date
from typing import Iterable


WEBSITE_ORDER = ["Q", "HNH", "RHC", "SH", "MSI"]
SOCIAL_ORDER = ["HNH FB", "Q FB", "Q IG", "RHC FB", "RHC IG", "SH FB", "SH IG", "MSI FB", "MSI IG"]
TIKTOK_ORDER = ["HNH", "Q", "RHC", "SH", "MSI"]


def format_viber_summary(
    *,
    start_date: str | date,
    end_date: str | date,
    website_rows: Iterable[dict[str, object]],
    social_rows: Iterable[dict[str, object]],
    tiktok_rows: Iterable[dict[str, object]],
) -> str:
    website_map = _build_website_map(website_rows)
    social_map = _build_social_map(social_rows)
    tiktok_map = _build_tiktok_map(tiktok_rows)

    lines = [
        "Online Platform Analytics Summary",
        f"{_format_date(start_date)} - {_format_date(end_date)}",
        "",
        "Websites (Visitors/Impressions)",
    ]
    for alias in WEBSITE_ORDER:
        visitors, impressions = website_map.get(alias, (0, 0))
        lines.append(f"- {alias}: {visitors}/{impressions}")

    lines.extend(["", "Social (Views/Viewers/Interactions/Visits)"])
    social_aliases = [alias for alias in SOCIAL_ORDER if alias in social_map]
    if not social_aliases:
        lines.append("- None")
    else:
        for alias in social_aliases:
            views, secondary, interactions, visits = social_map[alias]
            lines.append(f"- {alias}: {views}/{secondary}/{interactions}/{visits}")

    lines.extend(["", "TikTok Shop (Revenue/Sold/Views/Visitors)"])
    tiktok_aliases = [alias for alias in TIKTOK_ORDER if alias in tiktok_map]
    if not tiktok_aliases:
        lines.append("- None")
    else:
        for alias in tiktok_aliases:
            revenue, sold, views, visitors = tiktok_map[alias]
            lines.append(f"- {alias}: {_format_currency(revenue)}/{sold}/{views}/{visitors}")

    return "\n".join(lines)


def _build_website_map(rows: Iterable[dict[str, object]]) -> dict[str, tuple[int, int]]:
    result: dict[str, tuple[int, int]] = {}
    for row in rows:
        alias = _brand_alias(str(row.get("site_name", row.get("Site", ""))))
        if not alias:
            continue
        result[alias] = (
            int(round(float(row.get("visitors", row.get("Visitors", 0)) or 0))),
            int(round(float(row.get("impressions", row.get("Impressions", 0)) or 0))),
        )
    return result


def _build_social_map(rows: Iterable[dict[str, object]]) -> dict[str, tuple[int, int, int, int]]:
    result: dict[str, tuple[int, int, int, int]] = {}
    for row in rows:
        platform = str(row.get("platform", row.get("Platform", ""))).strip()
        profile_name = str(row.get("profile_name", row.get("Profile", ""))).strip()
        brand_alias = _brand_alias(profile_name)
        platform_alias = _platform_alias(platform, profile_name)
        if not brand_alias or not platform_alias:
            continue
        result[f"{brand_alias} {platform_alias}"] = (
            int(round(float(row.get("views", row.get("Views", 0)) or 0))),
            int(
                round(
                    float(
                        row.get(
                            "viewers",
                            row.get("Viewers", row.get("reach", row.get("Reach", 0))),
                        )
                        or 0
                    )
                )
            ),
            int(round(float(row.get("content_interactions", row.get("Interaction", 0)) or 0))),
            int(round(float(row.get("visits", row.get("Visits", 0)) or 0))),
        )
    return result


def _build_tiktok_map(rows: Iterable[dict[str, object]]) -> dict[str, tuple[float, int, int, int]]:
    result: dict[str, tuple[float, int, int, int]] = {}
    for row in rows:
        alias = _brand_alias(str(row.get("shop_name", row.get("Shop", row.get("profile_name", "")))))
        if not alias:
            continue
        result[alias] = (
            float(row.get("gross_revenue", row.get("Gross Revenue", 0)) or 0),
            int(round(float(row.get("items_sold", row.get("Items Sold", 0)) or 0))),
            int(round(float(row.get("page_views", row.get("Page Views", 0)) or 0))),
            int(round(float(row.get("visitors", row.get("Visitors", 0)) or 0))),
        )
    return result


def _brand_alias(raw_name: str) -> str | None:
    normalized = " ".join(raw_name.lower().replace("&", " and ").split())
    if any(token in normalized for token in ["quadro", "quadro website"]):
        return "Q"
    if any(token in normalized for token in ["harmony and homes", "harmony homes"]):
        return "HNH"
    if any(token in normalized for token in ["royal hang tock", "royal hangtock"]):
        return "RHC"
    if any(token in normalized for token in ["metro shirt", "metroshirt", "msi"]):
        return "MSI"
    if "solace hotel" in normalized:
        return "SH"
    if "tiktok shop ph" in normalized:
        return "HNH"
    return None


def _platform_alias(platform: str, profile_name: str) -> str | None:
    normalized_platform = platform.lower()
    normalized_name = profile_name.lower()
    if "instagram" in normalized_platform or "instagram" in normalized_name:
        return "IG"
    if "facebook" in normalized_platform or "facebook" in normalized_name:
        return "FB"
    return None


def _format_currency(value: float) -> str:
    return f"\u20b1{float(value):,.2f}"


def _format_date(value: str | date) -> str:
    if isinstance(value, date):
        return value.strftime("%b %d, %Y")
    return date.fromisoformat(str(value)).strftime("%b %d, %Y")
