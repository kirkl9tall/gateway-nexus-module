"""
Outbound alerting.

Two sinks (both optional):

* Webhook: POST JSON to a URL (Slack incoming webhook, Teams, Opsgenie, etc.).
* SMTP:    plain-text email via a relay host.

Both are configured in gateway.yaml and gated by a rate-limit so a flapping
device does not spam the on-call channel.
"""
from __future__ import annotations

import json
import logging
import smtplib
import ssl
import threading
import time
from email.mime.text import MIMEText
from typing import Any, Dict, Optional
from urllib import request as _url_request

log = logging.getLogger("loc200.alerting")

# Per-key rate limit: at most one alert of the same key per DEDUP_WINDOW_SEC.
DEDUP_WINDOW_SEC = 300
_last_sent: Dict[str, float] = {}
_lock = threading.Lock()


def _should_send(key: str) -> bool:
    now = time.time()
    with _lock:
        prev = _last_sent.get(key, 0.0)
        if now - prev < DEDUP_WINDOW_SEC:
            return False
        _last_sent[key] = now
    return True


class AlertClient:
    def __init__(
        self,
        webhook_url: str = "",
        smtp_host: str = "",
        smtp_port: int = 25,
        smtp_from: str = "",
        smtp_to: str = "",
        smtp_user: Optional[str] = None,
        smtp_pass: Optional[str] = None,
        smtp_starttls: bool = False,
    ) -> None:
        self._webhook_url = webhook_url
        self._smtp_host   = smtp_host
        self._smtp_port   = smtp_port
        self._smtp_from   = smtp_from
        self._smtp_to     = [x.strip() for x in smtp_to.split(",") if x.strip()]
        self._smtp_user   = smtp_user
        self._smtp_pass   = smtp_pass
        self._smtp_starttls = smtp_starttls

    def send(
        self,
        *,
        level: str,
        title: str,
        message: str,
        dedup_key: str = "",
        details: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Send an alert to every configured sink. Non-blocking failure -- returns True
        if at least one sink accepted. Returns False if rate-limited.
        """
        key = dedup_key or f"{level}:{title}"
        if not _should_send(key):
            log.debug("alert deduped: %s", key)
            return False

        payload = {
            "level":   level,
            "title":   title,
            "message": message,
            "details": details or {},
            "source":  "jerumednexus-gateway",
        }
        sent = False
        if self._webhook_url:
            sent = self._send_webhook(payload) or sent
        if self._smtp_host and self._smtp_from and self._smtp_to:
            sent = self._send_email(payload) or sent
        if not sent:
            log.debug("alert had no configured sink: %s", title)
        return sent

    def _send_webhook(self, payload: Dict[str, Any]) -> bool:
        try:
            data = json.dumps(payload).encode("utf-8")
            req  = _url_request.Request(
                self._webhook_url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with _url_request.urlopen(req, timeout=5) as resp:
                if 200 <= resp.status < 300:
                    return True
                log.warning("webhook returned %d", resp.status)
        except Exception as exc:
            log.warning("webhook alert failed: %s", exc)
        return False

    def _send_email(self, payload: Dict[str, Any]) -> bool:
        try:
            body_lines = [
                f"Level: {payload['level']}",
                f"Title: {payload['title']}",
                "",
                payload["message"],
                "",
                "Details:",
                json.dumps(payload.get("details") or {}, indent=2),
            ]
            body = "\n".join(body_lines)
            mime = MIMEText(body, "plain", "utf-8")
            mime["From"] = self._smtp_from
            mime["To"]   = ", ".join(self._smtp_to)
            mime["Subject"] = f"[jerumednexus-gateway/{payload['level'].upper()}] {payload['title']}"
            with smtplib.SMTP(self._smtp_host, self._smtp_port, timeout=10) as s:
                if self._smtp_starttls:
                    s.starttls(context=ssl.create_default_context())
                if self._smtp_user and self._smtp_pass:
                    s.login(self._smtp_user, self._smtp_pass)
                s.sendmail(self._smtp_from, self._smtp_to, mime.as_string())
            return True
        except Exception as exc:
            log.warning("SMTP alert failed: %s", exc)
        return False


_global_client: Optional[AlertClient] = None


def configure_from(config) -> None:
    """Instantiate the singleton alert client from GatewayConfig."""
    global _global_client
    _global_client = AlertClient(
        webhook_url=getattr(config, "alerts_webhook_url", "") or "",
        smtp_host=getattr(config, "alerts_smtp_host", "") or "",
        smtp_port=getattr(config, "alerts_smtp_port", 25),
        smtp_from=getattr(config, "alerts_smtp_from", "") or "",
        smtp_to=getattr(config, "alerts_smtp_to", "") or "",
    )


def send(**kwargs) -> bool:
    if _global_client is None:
        return False
    return _global_client.send(**kwargs)
