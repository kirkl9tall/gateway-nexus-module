"""
Overview for doctors: "are my results arriving, and where are they going?"

``build_overview()`` turns the gateway's technical state (status.json,
history.db, the DLQ, gateway.yaml) into plain facts the pages can show
without any jargon:

    gateway       on / off
    machines      one entry per analyzer: online / idle / waiting / offline / paused
    destinations  one entry per practice software: good / warning / critical
    today, week   counts for the gauges and the 7-day chart
    headline      the single sentence at the top of the page

All the "is it up or down" rules live here, in one place, with tests
(tests/test_overview.py). Templates only display the result.

Routes:
    GET /overview/live     HTML fragment of the live area, swapped every 15 s
    GET /api/overview      the same data as JSON
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from flask import Blueprint, render_template

log = logging.getLogger("webui.overview")

# ── Thresholds ───────────────────────────────────────────────────────────────
ONLINE_RESULT_S = 4 * 3600        # a result in the last 4 h  → online
ONLINE_CONNECT_S = 10 * 60        # a connection in the last 10 min → online
FLOWING_S = 10 * 60               # data moved in the last 10 min → animate path
STATUS_STALE_S = 660              # status.json older than this → gateway not running

# Practice software products as the doctor knows them.
PRODUCT = {
    "tomedo": "Tomedo", "vitomed": "Vitomed", "curamed": "curaMED",
    "aeskulap": "Aeskulap", "axenita": "Axenita", "winmed": "WinMed",
    "dnamed": "DnaMed",
}

# What kind of machine it is, in words a doctor uses. Matched on the device
# id / model (lower case). First match wins.
_KINDS = [
    (("uc1000", "uc-1000", "clinitek", "uf1000", "uf4000", "uf5000", "dirui", "h800", "urin"), "Urine"),
    (("abl80", "i_stat", "i-stat", "istat"), "Emogas"),
    (("b101", "afinion", "dca", "d100", "hba1c", "ha8180", "h232"), "HbA1c e lipidi"),
    (("sysmex", "xq320", "xp300", "xn", "poch", "horiba", "microsemi", "mindray_bc",
      "bc5000", "hemocue", "pixcell", "haemat", "hamat", "hämat"), "Ematologia"),
    (("loc200", "loc-200", "smt120", "smt-120", "seamaty", "reflotron", "c111", "bs240",
      "au480", "xl200", "chem"), "Chimica clinica"),
    (("statstrip", "caresens", "glucose"), "Glicemia"),
]


def machine_kind(*names: str) -> str:
    key = " ".join(n for n in names if n).lower()
    for words, kind in _KINDS:
        if any(w in key for w in words):
            return kind
    return "Analizzatore"


def _parse_ts(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", ""))
    except ValueError:
        return None


def _age_s(ts: Optional[datetime], now: datetime) -> Optional[float]:
    return None if ts is None else (now - ts).total_seconds()


# ── Inputs (each one isolated so a broken piece never breaks the page) ───────

def _read_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _read_yaml(path: Path) -> Dict[str, Any]:
    try:
        import yaml
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _configured_devices(cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Analyzers the gateway opens, as plain dicts (id, name, how connected)."""
    try:
        from config.settings import GatewayConfig
        from src.devices.registry import resolve_devices
        defs = resolve_devices(GatewayConfig.model_validate(cfg))
    except Exception as exc:
        log.debug("resolve_devices failed: %s", exc)
        return []
    out = []
    for d in defs:
        if d.serial_port:
            link, where = "usb", d.serial_port
        elif d.listen_port:
            link, where = "network", d.listen_port
        elif d.watch_folder:
            link, where = "folder", d.watch_folder
        else:
            link, where = "unknown", None
        out.append({"id": d.id, "name": d.name, "model": d.model or "",
                    "link": link, "where": where,
                    "serial_port": d.serial_port})
    return out


# ── The rules ────────────────────────────────────────────────────────────────

def _gateway_state(service: str, status: Dict[str, Any], status_mtime: Optional[float],
                   now_epoch: float) -> Dict[str, Any]:
    if service == "active":
        on = True
    elif service in ("inactive", "failed", "deactivating"):
        on = False
    else:  # systemd not available (dev machine, container): trust status.json freshness
        on = bool(status.get("running")) and status_mtime is not None \
            and (now_epoch - status_mtime) < STATUS_STALE_S
    return {"on": on, "uptime_s": int(status.get("uptime_seconds") or 0) if on else 0}


def _machine_state(m: Dict[str, Any], gateway_on: bool, now: datetime,
                   path_exists: Callable[[str], bool]) -> str:
    if not gateway_on:
        return "paused"
    if m["link"] == "usb" and m.get("serial_port") and not path_exists(m["serial_port"]):
        return "offline"
    res_age = _age_s(m.get("last_result"), now)
    con_age = _age_s(m.get("last_connect"), now)
    if (res_age is not None and res_age <= ONLINE_RESULT_S) or \
       (con_age is not None and con_age <= ONLINE_CONNECT_S):
        return "online"
    if m.get("last_result") or m.get("last_connect"):
        return "idle"
    return "waiting"


# Level used for colour + icon: good / warning / critical / neutral
MACHINE_LEVEL = {"online": "good", "idle": "neutral", "waiting": "warning",
                 "offline": "critical", "paused": "neutral"}


def build_overview(*, status_file: Path, config_file: Path, service: str,
                   history=None, dead_letters: Optional[Callable[[], list]] = None,
                   now: Optional[datetime] = None,
                   path_exists: Callable[[str], bool] = lambda p: Path(p).exists(),
                   ) -> Dict[str, Any]:
    now = now or datetime.now()
    now_epoch = now.timestamp()
    status = _read_json(status_file)
    try:
        status_mtime = status_file.stat().st_mtime
    except OSError:
        status_mtime = None
    cfg = _read_yaml(config_file)

    if history is None:
        from src.common import history as history  # noqa: PLW0127
    if dead_letters is None:
        from src.common.dead_letter import list_dead_letters
        dead_letters = lambda: list_dead_letters(limit=1000)  # noqa: E731

    gateway = _gateway_state(service, status, status_mtime, now_epoch)

    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    try:
        today_rows = history.activity_since(midnight.isoformat())
    except Exception:
        today_rows = []
    try:
        week = history.daily_counts(7)
    except Exception:
        week = []
    try:
        seen_ever = history.device_last_seen()
    except Exception:
        seen_ever = {}
    try:
        dlq = dead_letters() or []
    except Exception:
        dlq = []

    # ── Machines ──
    live_seen = status.get("last_seen") or {}
    live_conn = status.get("connected") or {}
    machines = _configured_devices(cfg)
    names = {m["name"] for m in machines}
    # LOC-200 is always opened by the gateway; show it only if it ever spoke,
    # otherwise practices without one see a machine they don't own.
    if "LOC-200" not in names and ("LOC-200" in live_seen or "LOC-200" in live_conn
                                   or "LOC-200" in seen_ever):
        machines.insert(0, {"id": "loc200", "name": "LOC-200", "model": "LOC-200",
                            "link": "network", "where": None, "serial_port": None})
        names.add("LOC-200")
    today_by_device: Dict[str, int] = {}
    latest_today: Dict[str, str] = {}
    for r in today_rows:
        today_by_device[r["device"]] = today_by_device.get(r["device"], 0) + 1
        if r["ts"] > latest_today.get(r["device"], ""):
            latest_today[r["device"]] = r["ts"]
    for m in machines:
        last_result = max(filter(None, [_parse_ts(live_seen.get(m["name"])),
                                        _parse_ts(seen_ever.get(m["name"])),
                                        _parse_ts(latest_today.get(m["name"]))]),
                          default=None)
        m["last_result"] = last_result
        m["last_connect"] = _parse_ts(live_conn.get(m["name"]))
        m["today"] = today_by_device.get(m["name"], 0)
        m["kind"] = machine_kind(m["id"], m["model"], m["name"])
        m["state"] = _machine_state(m, gateway["on"], now, path_exists)
        m["level"] = MACHINE_LEVEL[m["state"]]
    order = {"offline": 0, "waiting": 1, "online": 2, "idle": 3, "paused": 4}
    machines.sort(key=lambda m: (order[m["state"]], m["name"].lower()))
    up = sum(1 for m in machines if m["state"] in ("online", "idle"))

    # ── Destinations ──
    breakers = {b.get("name"): (b.get("breaker") or {}).get("state", "closed")
                for b in (status.get("breakers") or []) if isinstance(b, dict)}
    waiting_by_target: Dict[str, int] = {}
    for e in dlq:
        for t in (e.get("targets") or []):
            waiting_by_target[t] = waiting_by_target.get(t, 0) + 1
    destinations = []
    for t in (cfg.get("targets") or []):
        if not isinstance(t, dict) or not t.get("enabled", True):
            continue
        name = str(t.get("name") or "?")
        typ = str(t.get("type") or "")
        delivered = sum(1 for r in today_rows if name in r["succeeded"])
        failed = sum(1 for r in today_rows if name in r["failed"])
        last_ok = next((_parse_ts(r["ts"]) for r in today_rows if name in r["succeeded"]), None)
        last_fail = next((_parse_ts(r["ts"]) for r in today_rows if name in r["failed"]), None)
        waiting = waiting_by_target.get(name, 0)
        if not gateway["on"]:
            level, state = "neutral", "paused"
        elif breakers.get(name) == "open" or (last_fail and (not last_ok or last_fail > last_ok)):
            level, state = "critical", "unreachable"
        elif waiting:
            level, state = "warning", "waiting"
        elif last_ok:
            level, state = "good", "receiving"
        else:
            level, state = "neutral", "ready"
        if typ in PRODUCT:
            product = PRODUCT[typ]
        elif typ == "fhir_r4":
            product = "FHIR"
        elif typ == "file_drop" or t.get("watch_folder"):
            product = "folder"
        else:
            product = "software"
        destinations.append({"name": name, "product": product, "type": typ,
                             "delivered": delivered, "failed": failed,
                             "waiting": waiting, "last_ok": last_ok,
                             "level": level, "state": state})

    # ── Today & week ──
    total_today = len(today_rows)
    ok_today = sum(1 for r in today_rows if r["status"] == "OK")
    waiting_total = len(dlq)
    last = today_rows[0] if today_rows else None
    if last is None:
        try:
            last = history.last_activity()
        except Exception:
            last = None
    last_ts = _parse_ts(last["ts"]) if last else None
    flowing = bool(gateway["on"] and last_ts and _age_s(last_ts, now) <= FLOWING_S)

    # ── Headline: the most important thing, one sentence ──
    dest_names = ", ".join(d["name"] for d in destinations)
    broken = [d for d in destinations if d["level"] == "critical"]
    offline = [m for m in machines if m["state"] == "offline"]
    if not gateway["on"]:
        headline = {"level": "critical", "key": "gateway_off"}
    elif not destinations:
        headline = {"level": "warning", "key": "no_destination"}
    elif broken:
        headline = {"level": "critical", "key": "destination_down",
                    "name": broken[0]["name"]}
    elif waiting_total:
        headline = {"level": "warning", "key": "waiting", "n": waiting_total}
    elif offline:
        headline = {"level": "warning", "key": "machine_offline",
                    "name": offline[0]["name"]}
    elif not machines:
        headline = {"level": "neutral", "key": "no_machine"}
    else:
        headline = {"level": "good", "key": "all_good", "dest": dest_names}

    return {
        "generated_at": now,
        "gateway": gateway,
        "headline": headline,
        "flowing": flowing,
        "last": {"ts": last_ts, "device": last["device"] if last else ""},
        "machines": machines,
        "machines_up": up,
        "destinations": destinations,
        "today": {"total": total_today, "ok": ok_today,
                  "not_ok": total_today - ok_today, "waiting": waiting_total},
        "week": week,
    }


# ── Flask wiring ─────────────────────────────────────────────────────────────

def _json_default(o):
    return o.isoformat() if isinstance(o, datetime) else str(o)


def make_blueprint(require_auth, get_inputs: Callable[[], Dict[str, Any]]) -> Blueprint:
    """``get_inputs`` returns the keyword arguments for build_overview()."""
    bp = Blueprint("overview", __name__)

    @bp.route("/overview/live")
    @require_auth
    def live():
        return render_template("_overview_live.html", ov=build_overview(**get_inputs()))

    @bp.route("/api/overview")
    @require_auth
    def api():
        data = build_overview(**get_inputs())
        return bp_json(data)

    def bp_json(data):
        from flask import current_app
        return current_app.response_class(json.dumps(data, default=_json_default),
                                          mimetype="application/json")

    return bp


# ── Template helpers ─────────────────────────────────────────────────────────

WEEKDAYS = ["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"]


def when(value: Any, now: Optional[datetime] = None) -> str:
    """'oggi alle 10:42' / 'ieri alle 17:05' / 'il 12.11. alle 09:00', translated."""
    from webui.i18n import t
    ts = value if isinstance(value, datetime) else _parse_ts(value)
    if ts is None:
        return t("mai")
    now = now or datetime.now()
    ora = ts.strftime("%H:%M")
    days = (now.date() - ts.date()).days
    if days == 0:
        return t("oggi alle {ora}", ora=ora)
    if days == 1:
        return t("ieri alle {ora}", ora=ora)
    return t("il {data} alle {ora}", data=ts.strftime("%d.%m."), ora=ora)


def weekday(iso_date: str) -> str:
    from webui.i18n import t
    try:
        return t(WEEKDAYS[datetime.fromisoformat(iso_date).weekday()])
    except ValueError:
        return iso_date


def register_filters(app) -> None:
    app.jinja_env.filters["when"] = when
    app.jinja_env.filters["weekday"] = weekday
