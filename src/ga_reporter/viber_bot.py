from __future__ import annotations

import json
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import requests

from ga_reporter.database import (
    PostgresConfig,
    ensure_schema,
    load_latest_social_profile_metrics,
    load_latest_tiktok_profile_metrics,
    load_latest_website_profile_metrics,
    load_viber_subscribers,
    update_viber_subscription_status,
    upsert_viber_subscriber,
)
from ga_reporter.viber_summary import format_viber_summary


VIBER_API_BASE = "https://chatapi.viber.com/pa"


@dataclass(frozen=True)
class ViberBotConfig:
    auth_token: str
    webhook_url: str = ""
    bot_name: str = "OPA Bot"
    avatar_url: str = ""
    welcome_message: str = (
        "Online Platform Analytics bot is connected. "
        "You can now receive dashboard summary updates here."
    )
    host: str = "0.0.0.0"
    port: int = 8787


def resolve_viber_config(streamlit_secrets: Any | None = None) -> tuple[ViberBotConfig | None, str]:
    import os

    secrets = streamlit_secrets or {}
    viber_section = secrets.get("viber")
    if hasattr(viber_section, "to_dict"):
        viber_section = viber_section.to_dict()

    if isinstance(viber_section, dict):
        auth_token = str(viber_section.get("auth_token", "")).strip()
        if auth_token:
            return (
                ViberBotConfig(
                    auth_token=auth_token,
                    webhook_url=str(viber_section.get("webhook_url", "")).strip(),
                    bot_name=str(viber_section.get("bot_name", "OPA Bot")).strip() or "OPA Bot",
                    avatar_url=str(viber_section.get("avatar_url", "")).strip(),
                    welcome_message=str(viber_section.get("welcome_message", "")).strip()
                    or ViberBotConfig(auth_token=auth_token).welcome_message,
                    host=str(viber_section.get("host", "0.0.0.0")).strip() or "0.0.0.0",
                    port=int(viber_section.get("port", 8787) or 8787),
                ),
                "streamlit secret [viber]",
            )

    auth_token = os.getenv("VIBER_AUTH_TOKEN", "").strip()
    if auth_token:
        return (
            ViberBotConfig(
                auth_token=auth_token,
                webhook_url=os.getenv("VIBER_WEBHOOK_URL", "").strip(),
                bot_name=os.getenv("VIBER_BOT_NAME", "OPA Bot").strip() or "OPA Bot",
                avatar_url=os.getenv("VIBER_AVATAR_URL", "").strip(),
                welcome_message=os.getenv("VIBER_WELCOME_MESSAGE", "").strip()
                or ViberBotConfig(auth_token=auth_token).welcome_message,
                host=os.getenv("VIBER_HOST", "0.0.0.0").strip() or "0.0.0.0",
                port=int(os.getenv("VIBER_PORT", "8787") or "8787"),
            ),
            "environment",
        )

    return None, "not configured"


def set_viber_webhook(config: ViberBotConfig) -> dict[str, Any]:
    if not config.webhook_url:
        raise ValueError("Viber webhook_url is required to register the bot webhook.")

    payload = {
        "url": config.webhook_url,
        "event_types": [
            "conversation_started",
            "subscribed",
            "unsubscribed",
            "message",
            "seen",
            "delivered",
            "failed",
        ],
        "send_name": True,
        "send_photo": True,
    }
    response = requests.post(
        f"{VIBER_API_BASE}/set_webhook",
        headers=_viber_headers(config.auth_token),
        json=payload,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def send_text_message(
    *,
    auth_token: str,
    receiver_id: str,
    text: str,
    sender_name: str = "OPA Bot",
) -> dict[str, Any]:
    payload = {
        "receiver": receiver_id,
        "min_api_version": 1,
        "sender": {"name": sender_name},
        "type": "text",
        "text": text,
    }
    response = requests.post(
        f"{VIBER_API_BASE}/send_message",
        headers=_viber_headers(auth_token),
        json=payload,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def broadcast_latest_summary(
    *,
    bot_config: ViberBotConfig,
    postgres_config: PostgresConfig,
) -> list[dict[str, Any]]:
    message = build_latest_viber_summary(postgres_config)
    subscribers = load_viber_subscribers(postgres_config, subscribed_only=True)
    responses: list[dict[str, Any]] = []
    for subscriber in subscribers:
        result = send_text_message(
            auth_token=bot_config.auth_token,
            receiver_id=subscriber["subscriber_id"],
            text=message,
            sender_name=bot_config.bot_name,
        )
        responses.append({"subscriber_id": subscriber["subscriber_id"], "response": result})
    return responses


def build_latest_viber_summary(postgres_config: PostgresConfig) -> str:
    website_rows = load_latest_website_profile_metrics(postgres_config)
    social_rows = load_latest_social_profile_metrics(postgres_config)
    tiktok_rows = load_latest_tiktok_profile_metrics(postgres_config)

    all_dates = [
        row["metric_date"]
        for row in [*website_rows, *social_rows, *tiktok_rows]
        if row.get("metric_date") is not None
    ]
    if all_dates:
        start_date = min(all_dates)
        end_date = max(all_dates)
    else:
        from datetime import date

        start_date = date.today()
        end_date = date.today()

    return format_viber_summary(
        start_date=start_date,
        end_date=end_date,
        website_rows=website_rows,
        social_rows=social_rows,
        tiktok_rows=tiktok_rows,
    )


def run_viber_webhook_server(
    *,
    bot_config: ViberBotConfig,
    postgres_config: PostgresConfig,
) -> None:
    ensure_schema(postgres_config)
    handler_class = _make_handler(bot_config, postgres_config)
    server = ThreadingHTTPServer((bot_config.host, bot_config.port), handler_class)
    print(f"Viber bot webhook listening on http://{bot_config.host}:{bot_config.port}")
    server.serve_forever()


def _make_handler(bot_config: ViberBotConfig, postgres_config: PostgresConfig):
    class ViberWebhookHandler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            if self.path.rstrip("/") == "/health":
                self._send_json(200, {"status": "ok"})
                return
            self._send_json(404, {"status": "not_found"})

        def do_POST(self):  # noqa: N802
            if self.path.rstrip("/") != "/webhook":
                self._send_json(404, {"status": "not_found"})
                return

            content_length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(content_length) if content_length else b"{}"
            try:
                payload = json.loads(body.decode("utf-8"))
            except json.JSONDecodeError:
                self._send_json(400, {"status": "invalid_json"})
                return

            event = str(payload.get("event", "")).strip()
            try:
                if event == "subscribed":
                    _store_viber_user(postgres_config, payload.get("user"), subscribed=True)
                    self._send_json(200, {"status": 0})
                    return
                if event == "unsubscribed":
                    user_id = str(payload.get("user_id", "")).strip()
                    if user_id:
                        update_viber_subscription_status(
                            postgres_config,
                            subscriber_id=user_id,
                            subscribed=False,
                        )
                    self._send_json(200, {"status": 0})
                    return
                if event == "conversation_started":
                    _store_viber_user(postgres_config, payload.get("user"), subscribed=True)
                    self._send_json(
                        200,
                        {
                            "type": "text",
                            "text": bot_config.welcome_message,
                            "sender": {
                                "name": bot_config.bot_name,
                                "avatar": bot_config.avatar_url,
                            },
                        },
                    )
                    return
                if event == "message":
                    sender = payload.get("sender")
                    _store_viber_user(postgres_config, sender, subscribed=True)
                    self._send_json(200, {"status": 0})
                    return
            except Exception as exc:  # pragma: no cover - runtime safety
                self._send_json(500, {"status": "error", "detail": str(exc)})
                return

            self._send_json(200, {"status": 0})

        def log_message(self, format, *args):  # noqa: A003
            return

        def _send_json(self, status_code: int, payload: dict[str, Any]) -> None:
            response = json.dumps(payload).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)

    return ViberWebhookHandler


def _store_viber_user(postgres_config: PostgresConfig, user_payload: Any, subscribed: bool) -> None:
    if not isinstance(user_payload, dict):
        return
    subscriber_id = str(user_payload.get("id", "")).strip()
    if not subscriber_id:
        return
    upsert_viber_subscriber(
        postgres_config,
        subscriber_id=subscriber_id,
        subscriber_name=str(user_payload.get("name", "")).strip(),
        avatar_url=str(user_payload.get("avatar", "")).strip(),
        language=str(user_payload.get("language", "")).strip(),
        country=str(user_payload.get("country", "")).strip(),
        subscribed=subscribed,
    )


def _viber_headers(auth_token: str) -> dict[str, str]:
    return {
        "X-Viber-Auth-Token": auth_token,
        "Content-Type": "application/json",
    }
