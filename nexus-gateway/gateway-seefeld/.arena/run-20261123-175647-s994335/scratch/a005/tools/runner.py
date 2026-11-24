"""Serve a project copy with fake data for layout checks. Usage: runner.py <projdir> <port>"""
import json, sys, tempfile
from datetime import datetime, timedelta
from pathlib import Path
proj = Path(sys.argv[1]).resolve(); port = int(sys.argv[2])
sys.path.insert(0, str(proj))
import os; os.chdir(proj)
from src.security import roles as _roles
_roles.is_setup_required = lambda: False
from webui import app as W, overview as O
from flask import request, session, redirect, make_response
tmp = Path(tempfile.mkdtemp())
NOW = datetime.now()
CFG_FULL = """
hl7: {sending_facility: Praxis Dr. Müller-Lüdenscheidt}
devices:
  - {id: sysmex_xq320, type: sysmex_astm, enabled: true, display_name: Sysmex XQ-320, listen_port: 5001}
  - {id: uc1000, type: uc1000_serial, enabled: true, display_name: Menarini UC-1000 Urinanalysegerät Labor 2, serial_port: /dev/missing}
  - {id: cobas_b101, type: cobas_poct, enabled: true, display_name: Cobas b 101, serial_port: /dev/present}
  - {id: smt120, type: mllp_hl7, enabled: true, display_name: Seamaty SMT-120, listen_port: 6000}
  - {id: horiba, type: mllp_hl7, enabled: true, display_name: Horiba Microsemi CRP, listen_port: 6001}
targets:
  - {name: Tomedo, type: tomedo, enabled: true, sftp_host: 10.0.0.2}
  - {name: Praxisarchiv-Netzwerkfreigabe, type: file_drop, enabled: true, watch_folder: /tmp}
"""
CFG_GOOD = """
hl7: {sending_facility: Studio Rossi}
devices:
  - {id: sysmex_xq320, type: sysmex_astm, enabled: true, display_name: Sysmex XQ-320, listen_port: 5001}
  - {id: cobas_b101, type: cobas_poct, enabled: true, display_name: Cobas b 101, serial_port: /dev/present}
targets:
  - {name: Tomedo, type: tomedo, enabled: true, sftp_host: 10.0.0.2}
"""
CFG_EMPTY = "hl7: {sending_facility: Studio Rossi}\n"
def row(mins, device="Sysmex XQ-320", ok=("Tomedo", "Praxisarchiv-Netzwerkfreigabe"), failed=()):
    return {"ts": (NOW - timedelta(minutes=mins)).isoformat(), "device": device,
            "status": "OK" if not failed else "ERRORE", "succeeded": list(ok), "failed": list(failed)}
class FH:
    def __init__(s, rows, big=False): s.rows = rows; s.big = big
    def activity_since(s, since): return [r for r in s.rows if r["ts"] >= since]
    def daily_counts(s, days=7):
        vals = [1234, 0, 87, 112, 1, 95, len(s.rows)] if s.big else [12, 0, 31, 28, 5, 40, len(s.rows)]
        return [{"date": (NOW - timedelta(days=days-1-i)).date().isoformat(), "total": vals[i], "ok": vals[i]} for i in range(days)]
    def device_last_seen(s): return {"Cobas b 101": (NOW - timedelta(days=1)).isoformat()}
    def last_activity(s): return s.rows[0] if s.rows else None
SCN = {
  "bad":  dict(cfg=CFG_FULL, svc="active", rows=[row(3)] * 20 + [row(4, ok=("Praxisarchiv-Netzwerkfreigabe",), failed=("Tomedo",))] * 3 + [row(30, device="Cobas b 101")] * 4, dlq=[{"targets": ["Tomedo"]}] * 3, big=True),
  "good": dict(cfg=CFG_GOOD, svc="active", rows=[row(3, ok=("Tomedo",))] * 23, dlq=[], big=False),
  "off":  dict(cfg=CFG_FULL, svc="inactive", rows=[row(300)] * 5, dlq=[], big=False),
  "empty":dict(cfg=CFG_EMPTY, svc="active", rows=[], dlq=[], big=False),
}
def cur():
    return SCN.get(request.cookies.get("scn", "bad"), SCN["bad"])
_orig = O.build_overview
def fake_build(**kw):
    s = cur()
    cfg = tmp / ("cfg_" + request.cookies.get("scn", "bad") + ".yaml"); cfg.write_text(s["cfg"], encoding="utf-8")
    st = tmp / "status.json"; st.write_text(json.dumps({"running": True}), encoding="utf-8")
    return _orig(status_file=st, config_file=cfg, service=s["svc"], history=FH(s["rows"], s["big"]),
                 dead_letters=lambda: list(s["dlq"]), path_exists=lambda p: "missing" not in p)
O.build_overview = fake_build
W._service_status = lambda: cur()["svc"]
W._read_status = lambda: {"running": True, "updated_at": NOW.isoformat(), "errors_today": 3, "results_total": 18234, "uptime_seconds": 90000, "targets": []}
W.CONFIG_F = tmp / "gw.yaml"; W.CONFIG_F.write_text(CFG_FULL, encoding="utf-8")
W.app.config["WTF_CSRF_ENABLED"] = False
@W.app.route("/__go")
def go():
    session.update(auth_id="x", auth_ip="127.0.0.1", username=request.args.get("user", "Dr. Anna Bernasconi-Müller"), role=request.args.get("role", "viewer"))
    r = make_response(redirect(request.args.get("next", "/")))
    r.set_cookie("jmnx_lang", request.args.get("lang", "it")); r.set_cookie("scn", request.args.get("scn", "bad"))
    return r
MEASURE = open(Path(__file__).with_name("measure.js")).read()
@W.app.after_request
def inject(resp):
    if resp.mimetype == "text/html" and request.args.get("m") and not resp.direct_passthrough:
        b = resp.get_data(as_text=True)
        resp.set_data(b.replace("</body>", "<script>" + MEASURE + "</script></body>"))
    return resp
W._client_ip = lambda: "127.0.0.1"
import webui.blueprints.dlq as _D
_D.list_dead_letters = lambda limit=100: [{"control_id": str(i), "targets": ["Tomedo"]} for i in range(len(cur()["dlq"]))][:limit]
W.app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)
