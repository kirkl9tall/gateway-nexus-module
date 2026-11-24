"""Dev server for screenshots: fake data, auto-login. Usage: serve.py PROJ PORT ROLE LANG SCENARIO"""
import sys, json, os
from datetime import datetime, timedelta
from pathlib import Path
proj, port, role, lang, scen = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4], sys.argv[5]
sys.path.insert(0, proj); os.chdir(proj)
tmp = Path(f"/tmp/claude-1000/a002srv-{port}"); tmp.mkdir(parents=True, exist_ok=True)
from src.security import roles as _roles
_roles.is_setup_required = lambda: False
from webui import app as webapp, overview
import webui.app
CFG = f"""
praxis: {{language: {lang}}}
devices:
  - {{id: sysmex_xq320, type: sysmex_astm, enabled: true, display_name: Sysmex XQ-320, listen_port: 5001}}
  - {{id: uc1000, type: uc1000_serial, enabled: true, display_name: UC-1000 Urinanalysegerät, serial_port: /dev/missing}}
  - {{id: cobas_b101, type: cobas_poct, enabled: true, display_name: Cobas b 101, serial_port: /dev/present}}
  - {{id: smt120, type: mllp_hl7, enabled: true, display_name: Seamaty SMT-120, listen_port: 6000}}
targets:
  - {{name: Tomedo, type: tomedo, enabled: true, sftp_host: 10.0.0.2}}
  - {{name: Praxisarchiv Netzwerkordner, type: file_drop, enabled: true, watch_folder: /tmp}}
"""
cfgf = tmp / "gateway.yaml"; cfgf.write_text(CFG)
stf = tmp / "status.json"; stf.write_text(json.dumps({"running": True, "errors_today": 1, "results_total": 18234, "uptime_seconds": 90000, "latency_p95_ms": 420}))
webapp.CONFIG_F = cfgf; webapp.STATUS_F = stf
webapp._service_status = lambda: "inactive" if scen == "off" else "active"
NOW = datetime.now()
def row(m, device="Sysmex XQ-320", ok=("Tomedo", "Praxisarchiv Netzwerkordner"), failed=()):
    return {"ts": (NOW - timedelta(minutes=m)).isoformat(), "device": device,
            "status": "OK" if not failed else "ERRORE", "succeeded": list(ok), "failed": list(failed)}
class H:
    rows = [row(3), row(20), row(40, "Cobas b 101"), row(70)] + [row(90 + i * 5) for i in range(20)]
    if scen == "down":
        rows = [row(2, ok=("Praxisarchiv Netzwerkordner",), failed=("Tomedo",))] + rows
    def activity_since(self, s): return [r for r in self.rows if r["ts"] >= s]
    def daily_counts(self, days=7):
        vals = [31, 44, 0, 0, 52, 38, len(self.rows)]
        return [{"date": (NOW - timedelta(days=i)).date().isoformat(), "total": vals[days-1-i], "ok": vals[days-1-i]} for i in range(days - 1, -1, -1)]
    def device_last_seen(self): return {"Cobas b 101": (NOW - timedelta(days=1)).isoformat()}
    def last_activity(self): return self.rows[0] if self.rows else None
_orig = overview.build_overview
def fake(**kw):
    kw.update(history=H(), dead_letters=lambda: ([{"targets": ["Tomedo"]}]*3 if scen == "waiting" else []),
              path_exists=lambda p: "missing" not in p)
    return _orig(**kw)
overview.build_overview = fake
app = webapp.app
app.config["TESTING"] = True
from flask import session, request
@app.before_request
def _auto():
    if request.path.startswith("/static") or request.path.startswith("/i18n"): return
    session.update(auth_id="x", auth_ip=request.remote_addr, username="Dr. Anna Bernasconi-Müller", role=role)
    try:
        from webui.app import _client_ip
        session["auth_ip"] = _client_ip()
    except Exception: pass
app.run(port=port, debug=False, use_reloader=False)
