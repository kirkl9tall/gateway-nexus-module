"""
Results page: every result the gateway received, and where it was sent.

    GET /results                 the page
    GET /results/list?…          HTML fragment: the list (filters below)
    GET /results/<id>            HTML fragment: one result, values + delivery

Filters: q (patient or sample ID), period (today|yesterday|7d|30d|all),
device, status (all|ok|problem).
Fragments are rendered by the server so every word is translated.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, Optional, Tuple

from flask import Blueprint, abort, render_template, request

PERIODS = ("today", "yesterday", "7d", "30d", "all")


def period_range(period: str, today: Optional[date] = None) -> Tuple[str, str]:
    today = today or date.today()
    if period == "today":
        return today.isoformat(), ""
    if period == "yesterday":
        return (today - timedelta(days=1)).isoformat(), today.isoformat()
    if period == "7d":
        return (today - timedelta(days=6)).isoformat(), ""
    if period == "30d":
        return (today - timedelta(days=29)).isoformat(), ""
    return "", ""


def delivery_level(status: str) -> str:
    return {"OK": "good", "PARZIALE": "warning"}.get(status, "critical")


def value_level(o: Dict[str, Any]) -> str:
    """'high' / 'low' / '' for one observation, from the analyzer's flag or
    the reference range."""
    flag = str(o.get("flag") or "").upper().strip()
    if flag in ("H", "HH", ">"):
        return "high"
    if flag in ("L", "LL", "<"):
        return "low"
    try:
        v = float(o.get("value_num") if o.get("value_num") is not None else o.get("value"))
    except (TypeError, ValueError):
        return ""
    lo, hi = o.get("ref_low"), o.get("ref_high")
    if hi is not None and v > float(hi):
        return "high"
    if lo is not None and v < float(lo):
        return "low"
    return ""


def make_blueprint(require_auth) -> Blueprint:
    bp = Blueprint("results_view", __name__)

    @bp.app_template_filter("value_level")
    def _value_level(o):
        return value_level(o)

    @bp.route("/results/list")
    @require_auth
    def results_list():
        from src.common import history
        period = request.args.get("period", "today")
        if period not in PERIODS:
            period = "today"
        since, until = period_range(period)
        status = request.args.get("status", "")
        rows = history.list_results(
            q=request.args.get("q", "").strip()[:60],
            device=request.args.get("device", "")[:120],
            status="OK" if status == "ok" else ("problem" if status == "problem" else ""),
            since=since, until=until, limit=200)
        for r in rows:
            try:
                r["dt"] = datetime.fromisoformat(r["ts"])
            except ValueError:
                r["dt"] = None
            r["level"] = delivery_level(r["status"])
        return render_template("_results_list.html", rows=rows, period=period)

    @bp.route("/results/<int:entry_id>")
    @require_auth
    def result_detail(entry_id: int):
        from src.common import history
        e = history.get_entry(entry_id)
        if not e:
            abort(404)
        try:
            e["dt"] = datetime.fromisoformat(e["ts"])
        except ValueError:
            e["dt"] = None
        e["level"] = delivery_level(e.get("status", ""))
        obs = ((e.get("result") or {}).get("observations")) or []
        return render_template("_result_detail.html", e=e, observations=obs)

    return bp
