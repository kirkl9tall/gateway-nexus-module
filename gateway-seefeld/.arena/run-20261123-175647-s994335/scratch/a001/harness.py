"""Render harness: serve a project copy with fake data, auto-login by ?as=role,
and inject a layout checker. Usage: python harness.py <proj_dir> <port>"""
import json, sys, os
from datetime import datetime, timedelta
from pathlib import Path

proj = Path(sys.argv[1]).resolve(); port = int(sys.argv[2])
sys.path.insert(0, str(proj)); os.chdir(proj)
tmp = Path(__file__).resolve().parent / ("data_%d" % port); tmp.mkdir(exist_ok=True)

from src.security import roles as _roles
_roles.is_setup_required = lambda: False
from webui import app as W
from flask import request, session

CFG = """
devices:
  - {id: sysmex_xq320, type: sysmex_astm, enabled: true, display_name: Sysmex XQ-320, listen_port: 5001}
  - {id: uc1000, type: uc1000_serial, enabled: true, display_name: UC-1000, serial_port: /dev/missing}
  - {id: cobas_b101, type: cobas_poct, enabled: true, display_name: Cobas b 101, serial_port: /dev/null}
  - {id: smt120, type: mllp_hl7, enabled: true, display_name: Seamaty SMT-120 Chemie-Analysegeraet, listen_port: 6000}
targets:
  - {name: Tomedo, type: tomedo, enabled: true, sftp_host: 10.0.0.2}
  - {name: Praxisarchiv-Netzwerkfreigabe, type: file_drop, enabled: true, watch_folder: /tmp}
praxis: {name: Test}
"""
(tmp / "gateway.yaml").write_text(CFG)
W.CONFIG_F = tmp / "gateway.yaml"; W.STATUS_F = tmp / "status.json"
NOW = datetime.now()
W.STATUS_F.write_text(json.dumps({"running": True, "updated_at": NOW.isoformat(), "errors_today": 2,
                                  "results_total": 1234, "uptime_seconds": 99999}))
STATE = {"svc": "active", "fail": False, "dlq": 0, "empty": False}
W._service_status = lambda: STATE["svc"]

from src.common import history as H, dead_letter as DL
def rows():
    if STATE["empty"]: return []
    out = []
    for i in range(23):
        failed = ["Tomedo"] if (STATE["fail"] and i < 3) else []
        ok = ["Praxisarchiv-Netzwerkfreigabe"] + ([] if failed else ["Tomedo"])
        out.append({"ts": (NOW - timedelta(minutes=5 + i * 9)).isoformat(),
                    "device": "Sysmex XQ-320" if i % 3 else "Cobas b 101",
                    "status": "ERRORE" if failed else "OK", "succeeded": ok, "failed": failed})
    return out
H.activity_since = lambda since: [r for r in rows() if r["ts"] >= since]
H.daily_counts = lambda days=7: [{"date": (NOW - timedelta(days=i)).date().isoformat(),
                                  "total": [0, 31, 48, 12, 0, 57, 23][i % 7] if not STATE["empty"] else 0, "ok": 0}
                                 for i in range(days - 1, -1, -1)]
H.device_last_seen = lambda: {"Sysmex XQ-320": NOW.isoformat(), "Cobas b 101": NOW.isoformat()}
H.last_activity = lambda: (rows() or [None])[0]
DL.list_dead_letters = lambda limit=1000: [{"targets": ["Tomedo"]}] * STATE["dlq"]

CHECK = """<script>
addEventListener('load', function(){ setTimeout(function(){
 var out=[], vw=document.documentElement.clientWidth;
 if (document.documentElement.scrollWidth > vw) out.push('HSCROLL '+document.documentElement.scrollWidth+'>'+vw);
 function vis(e){var r=e.getBoundingClientRect();return r.width>0&&r.height>0&&getComputedStyle(e).visibility!='hidden';}
 var hdr=[].slice.call(document.querySelectorAll('.topbar > *')).filter(vis);
 for(var i=0;i<hdr.length;i++)for(var j=i+1;j<hdr.length;j++){var a=hdr[i].getBoundingClientRect(),b=hdr[j].getBoundingClientRect();
   if(a.left<b.right-1&&b.left<a.right-1&&a.top<b.bottom-1&&b.top<a.bottom-1)out.push('OVERLAP '+(hdr[i].className||hdr[i].id)+' x '+(hdr[j].className||hdr[j].id));}
 document.querySelectorAll('body *').forEach(function(e){ if(!vis(e))return; var r=e.getBoundingClientRect();
   if(r.right>vw+1&&!e.closest('svg'))out.push('OUT '+e.tagName+'.'+e.className+' right='+Math.round(r.right));
   var cs=getComputedStyle(e); if(e.scrollWidth>e.clientWidth+1&&cs.overflowX!='auto'&&cs.overflowX!='scroll'&&e.clientWidth>0&&!e.closest('svg')&&e.tagName!='SELECT'&&!/ellipsis/.test(cs.textOverflow))out.push('CLIP '+e.tagName+'.'+e.className+' '+e.scrollWidth+'>'+e.clientWidth+' "'+(e.textContent||'').trim().slice(0,30)+'"');});
 var p=document.createElement('pre');p.id='__r';p.textContent='RESULT['+(out.length?out.join(' | '):'OK')+']';(window.parent!==window?parent.document:document).body.appendChild(parent.document.importNode(p,true));
},400);});
</script>"""

@W.app.before_request
def _fake():
    a = request.args
    if "as" in a:
        session.update(auth_id="x", auth_ip=request.remote_addr or "127.0.0.1", username=a.get("user", "dr.anna.musterfrau"), role=a["as"])
    for k in ("svc", ):
        if k in a: STATE[k] = a[k]
    STATE["fail"] = a.get("fail") == "1"; STATE["dlq"] = int(a.get("dlq", 0)); STATE["empty"] = a.get("empty") == "1"

@W.app.after_request
def _inject(resp):
    if resp.mimetype == "text/html" and request.args.get("check") == "1":
        resp.set_data(resp.get_data(as_text=True).replace("</body>", CHECK + "</body>"))
    return resp

@W.app.route("/__frame")
def _frame():
    w = int(request.args.get("w", 360)); q = request.query_string.decode()
    return '<!doctype html><body style="margin:0"><iframe style="border:0;width:%dpx;height:%dpx" src="/?%s"></iframe></body>' % (w, int(request.args.get("h", 1400)), q)

W.app.config["TESTING"] = True
W.app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)
