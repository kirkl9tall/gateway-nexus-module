"""
Operator alerts — fire an outbound webhook / email when a plausibility
warning or other critical event happens.

Configured via gateway.yaml:
    alerts:
      webhook_url:  "https://hooks.slack.com/services/..."
      email:        ["ops@clinic.example"]
      min_severity: "warning"   # info | warning | critical

Non-blocking: if the webhook / SMTP fails, we log and continue — the
dispatch is never held up by alerting.
"""
from __future__ import annotations

import json
import logging
import os
import ssl
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

log = logging.getLogger("loc200.alerts")

_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="alerts")

_CONFIG_CACHE: dict[str, Any] | None = None


def _load_config() -> dict[str, Any]:
    global _CONFIG_CACHE
    if _CONFIG_CACHE is not None:
        return _CONFIG_CACHE
    try:
        import yaml
        p = Path("config/gateway.yaml")
        if p.exists():
            data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            _CONFIG_CACHE = data.get("alerts") or {}
            return _CONFIG_CACHE
    except Exception as exc:
        log.debug("alerts config load failed: %s", exc)
    _CONFIG_CACHE = {}
    return _CONFIG_CACHE


_SEVERITY_ORDER = {"info": 0, "warning": 1, "critical": 2}


def fire(
    severity: str,
    kind: str,
    message: str,
    detail: dict[str, Any] | None = None,
) -> None:
    """
    Fire an alert asynchronously. Safe to call from the hot path.

    severity: "info" | "warning" | "critical"
    kind:     short slug like "plausibility" | "dlq_growth" | "device_offline"
    """
    cfg = _load_config()
    min_sev = str(cfg.get("min_severity", "warning")).lower()
    if _SEVERITY_ORDER.get(severity, 0) < _SEVERITY_ORDER.get(min_sev, 1):
        return
    payload = {
        "severity": severity,
        "kind":     kind,
        "message":  message,
        "detail":   detail or {},
        "source":   "jerumednexus-gateway",
        "hostname": os.uname().nodename if hasattr(os, "uname") else "windows",
    }
    _POOL.submit(_send, cfg, payload)


def _send(cfg: dict[str, Any], payload: dict[str, Any]) -> None:
    url = cfg.get("webhook_url")
    if url:
        try:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            req = urllib.request.Request(url, data=body, method="POST",
                                          headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=3,
                                    context=ssl.create_default_context())
            log.info("Alert sent to webhook: %s/%s", payload["severity"], payload["kind"])
        except Exception as exc:
            log.warning("Webhook alert failed: %s", exc)

    # Slack — separate URL because it has a specific payload format
    slack_url = cfg.get("slack_webhook_url")
    if slack_url:
        _send_slack(slack_url, payload)


def _send_slack(url: str, payload: dict[str, Any]) -> None:
    emoji = {"info": ":information_source:", "warning": ":warning:",
              "critical": ":rotating_light:"}.get(payload["severity"], ":bell:")
    color = {"info": "#3b82f6", "warning": "#f59e0b",
              "critical": "#dc2626"}.get(payload["severity"], "#64748b")
    slack_body = {
        "attachments": [{
            "color": color,
            "author_name": "JerumedNexus Gateway",
            "title": f"{emoji} {payload['kind']}",
            "text": payload["message"],
            "fields": [
                {"title": k, "value": str(v), "short": True}
                for k, v in (payload.get("detail") or {}).items()
            ][:8],
            "footer": payload.get("hostname", ""),
            "ts": int(__import__("time").time()),
        }],
    }
    try:
        body = json.dumps(slack_body).encode("utf-8")
        req = urllib.request.Request(url, data=body, method="POST",
                                      headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=3,
                                context=ssl.create_default_context())
        log.info("Slack alert sent: %s/%s", payload["severity"], payload["kind"])
    except Exception as exc:
        log.warning("Slack alert failed: %s", exc)
