"""Render / for a role+lang with fake data into a static html file."""
import sys, json, re, os
from datetime import datetime, timedelta
from pathlib import Path
PROJ = Path(sys.argv[1]).resolve(); OUT = Path(sys.argv[2]).resolve(); role = sys.argv[3]; lang = sys.argv[4]
scen = sys.argv[5] if len(sys.argv) > 5 else "mixed"
sys.path.insert(0, str(PROJ)); os.chdir(PROJ)
sys.path.insert(0, str(PROJ / "tests"))
import test_overview as T
from src.security import roles as _roles
_roles.is_setup_required = lambda: False
from webui import app as webapp
import tempfile
tmp = Path(tempfile.mkdtemp())
cfg = tmp / "gateway.yaml"; cfg.write_text(T.CFG, encoding="utf-8")
webapp.CONFIG_F = cfg; webapp.STATUS_F = tmp / "status.json"
webapp._service_status = lambda: "inactive" if scen == "off" else "active"
class H(T.FakeHistory):
    def daily_counts(self, days=7):
        vals = [12, 31, 27, 0, 44, 38, 23]
        return [{"date": (T.NOW - timedelta(days=i)).date().isoformat(), "total": vals[days-1-i], "ok": vals[days-1-i]} for i in range(days-1, -1, -1)]
rows = [T._row(5), T._row(10), T._row(20, device="Cobas b 101"), T._row(40, ok=("Archiv",), failed=("Tomedo",))] + [T._row(60+i) for i in range(19)]
if scen == "good":
    rows = [T._row(5)] + [T._row(30+i) for i in range(22)]
def fake(**kw):
    st = tmp / "status.json"; st.write_text(json.dumps({"running": True}), encoding="utf-8")
    c = cfg
    if scen == "good":
        c = tmp / "g2.yaml"; c.write_text(T.CFG.replace("/dev/missing", "/dev/present"), encoding="utf-8")
    return ORIG(status_file=st, config_file=c, service="inactive" if scen == "off" else "active",
        history=H(rows, {"Cobas b 101": (T.NOW - timedelta(days=1)).isoformat()}), dead_letters=lambda: [],
        now=T.NOW, path_exists=lambda p: "missing" not in p)
ORIG = webapp._overview.build_overview
webapp._overview.build_overview = fake
webapp.app.config["TESTING"] = True
c = webapp.app.test_client()
c.set_cookie("jmnx_lang", lang)
with c.session_transaction() as s:
    s.update(auth_id="x", auth_ip="127.0.0.1", username="Dr. Annamaria Bernasconi-Huber" if role!="admin" else "admin", role=role)
html = c.get("/").get_data(as_text=True)
i18n = c.get(f"/i18n/{lang}.js").get_data(as_text=True)
static = (PROJ / "webui" / "static").as_uri()
html = html.replace('src="/i18n/', 'data-x="').replace('<script src="/static/i18n.js', '<script>' + i18n + '</script><script src="/static/i18n.js')
html = re.sub(r"([\"'(])/static/", lambda m: m.group(1) + static + '/', html)
# fake the polled status so the pill shows a state
on = "false" if scen == "off" else "true"
html = html.replace("<head>", "<head><script>window.fetch=function(u){var on=%s;return Promise.resolve({ok:true,status:200,json:function(){return Promise.resolve(String(u).indexOf('/api/status')>=0?{service_systemd:on?'active':'inactive',running:on}:String(u).indexOf('dlq')>=0?{entries:[]}:{pending:[]});},text:function(){return Promise.reject()}});};</script>" % on, 1)
OUT.write_text(html, encoding="utf-8")
