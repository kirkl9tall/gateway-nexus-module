"""Render harness: python serve.py <project dir> <port>
Scenario via query ?scen=good|problems|off|empty&role=viewer|operator|admin (stored in session)."""
import json, sys, os, tempfile
from datetime import datetime, timedelta
from pathlib import Path

proj = Path(sys.argv[1]).resolve()
port = int(sys.argv[2])
sys.path.insert(0, str(proj))
os.chdir(proj)

from src.security import roles as _roles
_roles.is_setup_required = lambda: False
from webui import app as webapp, overview
from flask import request, session

tmp = Path(tempfile.mkdtemp())
CFG = """
hl7: {sending_facility: Praxis Dr. Muster}
devices:
  - {id: sysmex_xq320, type: sysmex_astm, enabled: true, display_name: Sysmex XQ-320, listen_port: 5001}
  - {id: uc1000, type: uc1000_serial, enabled: true, display_name: Menarini UC-1000, serial_port: /dev/missing}
  - {id: cobas_b101, type: cobas_poct, enabled: true, display_name: Roche Cobas b 101, serial_port: /dev/present}
  - {id: smt120, type: mllp_hl7, enabled: true, display_name: Seamaty SMT-120 Chemie-Analysator, listen_port: 6000}
targets:
  - {name: Tomedo, type: tomedo, enabled: true, sftp_host: 10.0.0.2}
  - {name: Archiv Praxisserver, type: file_drop, enabled: true, watch_folder: /tmp}
"""
cfgf = tmp / "gateway.yaml"; cfgf.write_text(CFG)
stf = tmp / "status.json"; stf.write_text(json.dumps({"running": True, "errors_today": 2, "results_total": 4211, "uptime_seconds": 90000}))
webapp.CONFIG_F = cfgf
webapp.STATUS_F = stf

NOW = datetime.now()

class FakeHistory:
    def __init__(self, rows, seen): self.rows, self.seen = rows, seen
    def activity_since(self, since): return [r for r in self.rows if r["ts"] >= since]
    def daily_counts(self, days=7):
        vals = [31, 44, 12, 0, 38, 41, len(self.rows)]
        return [{"date": (NOW - timedelta(days=i)).date().isoformat(), "total": vals[days-1-i], "ok": vals[days-1-i]} for i in range(days-1, -1, -1)]
    def device_last_seen(self): return dict(self.seen)
    def last_activity(self): return self.rows[0] if self.rows else None

def row(mins, device="Sysmex XQ-320", ok=("Tomedo", "Archiv Praxisserver"), failed=()):
    return {"ts": (NOW - timedelta(minutes=mins)).isoformat(), "device": device,
            "status": "OK" if not failed else "ERRORE", "succeeded": list(ok), "failed": list(failed)}

_orig = overview.build_overview
def fake_build(**kw):
    scen = session.get("scen", "good")
    rows = [row(3 + i * 7) for i in range(min(23, max(0, (NOW.hour * 60 + NOW.minute - 5) // 7)))] or [row(1)]
    seen = {"Roche Cobas b 101": (NOW - timedelta(days=1)).isoformat()}
    dlq = []
    path_exists = lambda p: True
    svc = "active"
    if scen == "problems":
        rows = [row(2, ok=("Archiv Praxisserver",), failed=("Tomedo",))] + rows
        path_exists = lambda p: "missing" not in p
        dlq = [{"targets": ["Tomedo"]}] * 3
    elif scen == "off":
        svc = "inactive"
    elif scen == "empty":
        cfgf2 = tmp / "empty.yaml"; cfgf2.write_text("devices: []\ntargets: []\n")
        kw["config_file"] = cfgf2; rows = []; seen = {}
    kw["service"] = svc
    return _orig(status_file=kw.get("status_file", stf), config_file=kw.get("config_file", cfgf), service=svc,
                 history=FakeHistory(rows, seen), dead_letters=lambda: dlq, now=NOW, path_exists=path_exists)
overview.build_overview = fake_build
webapp._service_status = lambda: "inactive" if session.get("scen") == "off" else "active"

@webapp.app.before_request
def _auto():
    if request.args.get("scen"): session["scen"] = request.args["scen"]
    if request.args.get("role"): session["role"] = request.args["role"]
    session.setdefault("role", "viewer")
    session["auth_id"] = "x"; session["auth_ip"] = request.remote_addr; session["username"] = "dr.muster"

CHECK = (Path(__file__).parent / "check.js").read_text()
@webapp.app.after_request
def _inject(resp):
    if resp.mimetype == "text/html" and request.path == "/" and request.args.get("check"):
        body = resp.get_data(as_text=True).replace("</body>", "<script>" + CHECK + "</script></body>")
        resp.set_data(body)
    return resp

@webapp.app.route("/__frame")
def _frame():
    w = int(request.args.get("w", 360)); u = request.args.get("u", "/")
    return ('<!doctype html><html><head><title>f</title><style>body{margin:0}</style></head><body>'
            '<iframe id="f" src="%s" style="width:%dpx;height:%dpx;border:0;display:block"></iframe>'
            '<script>addEventListener("message",function(e){var p=document.createElement("pre");p.textContent=e.data;document.body.appendChild(p);});</script>'
            '</body></html>') % (u, w, int(request.args.get("h", 3000)))

webapp.app.run(host="127.0.0.1", port=port, debug=False)
