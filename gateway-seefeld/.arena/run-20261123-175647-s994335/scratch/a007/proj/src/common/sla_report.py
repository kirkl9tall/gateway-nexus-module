"""
Monthly SLA report generator.

Reads dispatch history from SQLite (src.common.history) for a given month,
computes uptime, throughput, error rate and per-target latency, and renders
a standalone HTML report the customer can print / send / archive.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Tuple

from src.common.history import _get_conn


def _first_last(year: int, month: int) -> Tuple[datetime, datetime]:
    first = datetime(year, month, 1)
    if month == 12:
        last = datetime(year + 1, 1, 1) - timedelta(seconds=1)
    else:
        last = datetime(year, month + 1, 1) - timedelta(seconds=1)
    return first, last


def compute_month(year: int, month: int) -> Dict:
    first, last = _first_last(year, month)
    conn = _get_conn()
    rows = list(conn.execute(
        "SELECT ts, status, device, succeeded, failed FROM dispatches "
        "WHERE ts >= ? AND ts <= ? ORDER BY ts",
        (first.isoformat(), last.isoformat()),
    ))

    total = len(rows)
    ok      = sum(1 for r in rows if r[1] == "OK")
    partial = sum(1 for r in rows if r[1] == "PARZIALE")
    err     = sum(1 for r in rows if r[1] == "ERRORE")

    # Per target: sent (in any succeeded list) vs failed
    per_target: Dict[str, Dict[str, int]] = {}
    for _ts, _st, _dev, succ_json, fail_json in rows:
        try:
            succeeded = json.loads(succ_json or "[]")
            failed    = json.loads(fail_json or "[]")
        except Exception:
            succeeded, failed = [], []
        for t in succeeded:
            per_target.setdefault(t, {"ok": 0, "failed": 0})["ok"] += 1
        for t in failed:
            per_target.setdefault(t, {"ok": 0, "failed": 0})["failed"] += 1

    per_target_pct = []
    for name, stats in sorted(per_target.items()):
        s_total = stats["ok"] + stats["failed"]
        pct = (stats["ok"] / s_total * 100.0) if s_total else 0.0
        per_target_pct.append({
            "name":   name,
            "sent":   stats["ok"],
            "failed": stats["failed"],
            "total":  s_total,
            "success_pct": pct,
        })

    # Per device: message count
    per_device: Dict[str, int] = {}
    for _ts, _st, dev, _s, _f in rows:
        per_device[dev] = per_device.get(dev, 0) + 1

    return {
        "period":         f"{year:04d}-{month:02d}",
        "period_start":   first.isoformat(),
        "period_end":     last.isoformat(),
        "total_messages": total,
        "ok":             ok,
        "partial":        partial,
        "errored":        err,
        "success_rate":   (ok / total * 100.0) if total else 0.0,
        "per_target":     per_target_pct,
        "per_device":     sorted(({"name": k, "count": v} for k, v in per_device.items()),
                                 key=lambda x: -x["count"]),
    }


def render_html(report: Dict, facility: str = "PRAXIS", version: str = "1.3.0") -> str:
    def _rows_target(items):
        if not items:
            return "<tr><td colspan=4 style='color:#999'>(nessuna consegna nel periodo)</td></tr>"
        return "".join(
            f"<tr><td>{r['name']}</td><td style='text-align:right'>{r['sent']}</td>"
            f"<td style='text-align:right'>{r['failed']}</td>"
            f"<td style='text-align:right;color:{'#0a0' if r['success_pct']>=99 else '#a80'}'>"
            f"{r['success_pct']:.2f}%</td></tr>"
            for r in items
        )

    def _rows_device(items):
        if not items:
            return "<tr><td colspan=2 style='color:#999'>(nessun device nel periodo)</td></tr>"
        return "".join(
            f"<tr><td>{d['name']}</td><td style='text-align:right'>{d['count']}</td></tr>"
            for d in items
        )

    css = """
    body { font-family: -apple-system, Segoe UI, sans-serif; color:#222; padding:32px; max-width:900px; margin:auto; }
    h1 { margin:0 0 4px; font-size:22px; }
    h2 { margin-top:32px; font-size:16px; border-bottom:2px solid #eee; padding-bottom:6px; }
    .sub { color:#888; margin-bottom:24px; font-size:12px; }
    .grid { display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin:20px 0; }
    .kpi { border:1px solid #e0e0e0; border-radius:6px; padding:14px; text-align:center; }
    .kpi .v { font-size:24px; font-weight:700; }
    .kpi .l { font-size:11px; color:#888; text-transform:uppercase; letter-spacing:.05em; }
    table { width:100%; border-collapse:collapse; font-size:14px; }
    th,td { padding:8px 12px; border-bottom:1px solid #eee; text-align:left; }
    th { background:#f7f7f7; font-size:12px; text-transform:uppercase; letter-spacing:.05em; color:#666; }
    .footer { color:#aaa; margin-top:40px; font-size:11px; }
    """
    return f"""<!doctype html>
<html lang="it"><head>
  <meta charset="utf-8">
  <title>Report SLA {report['period']} — {facility}</title>
  <style>{css}</style>
</head><body>
  <h1>JerumedNexus Gateway — Report SLA</h1>
  <div class="sub">Struttura: <b>{facility}</b> · Periodo: <b>{report['period']}</b> · Generato: {datetime.now():%Y-%m-%d %H:%M}</div>

  <div class="grid">
    <div class="kpi"><div class="v">{report['total_messages']}</div><div class="l">Messaggi totali</div></div>
    <div class="kpi"><div class="v" style="color:#0a0">{report['ok']}</div><div class="l">Consegne OK</div></div>
    <div class="kpi"><div class="v" style="color:#a80">{report['partial']}</div><div class="l">Parziali</div></div>
    <div class="kpi"><div class="v" style="color:#c33">{report['errored']}</div><div class="l">Errori</div></div>
  </div>

  <div class="kpi" style="max-width:220px">
    <div class="v" style="color:{'#0a0' if report['success_rate']>=99 else '#c33'}">{report['success_rate']:.2f}%</div>
    <div class="l">Tasso di successo</div>
  </div>

  <h2>Per gestionale (PIS)</h2>
  <table><thead><tr><th>Target</th><th>Consegnati</th><th>Falliti</th><th>Success rate</th></tr></thead>
    <tbody>{_rows_target(report['per_target'])}</tbody>
  </table>

  <h2>Per analizzatore</h2>
  <table><thead><tr><th>Device</th><th>Messaggi ricevuti</th></tr></thead>
    <tbody>{_rows_device(report['per_device'])}</tbody>
  </table>

  <div class="footer">
    Report generato da JerumedNexus Gateway v{version}.
    Dati letti da <code>logs/history.db</code>.
    Verifica firma sul <code>.deb</code> installato con <code>debsigs --verify</code>.
  </div>
</body></html>"""


def save_report(year: int, month: int, out_dir: Path,
                facility: str = "PRAXIS", version: str = "1.3.0") -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    report = compute_month(year, month)
    html = render_html(report, facility=facility, version=version)
    dest = out_dir / f"sla-{year:04d}-{month:02d}.html"
    dest.write_text(html, encoding="utf-8")
    return dest
