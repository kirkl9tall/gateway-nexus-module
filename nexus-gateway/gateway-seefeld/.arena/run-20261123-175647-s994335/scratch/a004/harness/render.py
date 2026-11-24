"""Render the Overview for many scenarios/langs/roles into a static site.

usage: python render.py <project_dir> <out_site_dir>
"""
import json, shutil, sys, tempfile
from datetime import datetime, timedelta
from pathlib import Path

proj = Path(sys.argv[1]).resolve()
out = Path(sys.argv[2]).resolve()
sys.path.insert(0, str(proj))

from src.security import roles as _roles  # noqa
_roles.is_setup_required = lambda: False
from webui import app as webapp  # noqa
from webui import overview as ovmod  # noqa

tmp = Path(tempfile.mkdtemp())
(tmp / "gateway.yaml").write_text("hl7:\n  sending_facility: Praxis Test\n")
(tmp / "status.json").write_text(json.dumps({"running": True, "results_total": 5000, "errors_today": 2, "uptime_seconds": 7200, "latency_p95_ms": 840, "targets": []}))
webapp.CONFIG_F = tmp / "gateway.yaml"
webapp.STATUS_F = tmp / "status.json"
webapp._service_status = lambda: "active"
webapp.app.config["TESTING"] = True

NOW = datetime.now().replace(microsecond=0)


def week(vals):
    return [{"date": (NOW - timedelta(days=6 - i)).date().isoformat(), "total": v, "ok": v}
            for i, v in enumerate(vals)]


def mach(name, state, today=0, kind="Ematologia", link="usb"):
    lvl = ovmod.MACHINE_LEVEL[state]
    return {"id": name.lower(), "name": name, "model": "", "link": link, "where": None,
            "serial_port": None, "last_result": NOW - timedelta(minutes=12) if state in ("online", "idle") else None,
            "last_connect": None, "today": today, "kind": kind, "state": state, "level": lvl}


def dest(name, product, state, delivered=0, waiting=0):
    lvl = {"receiving": "good", "waiting": "warning", "unreachable": "critical",
           "paused": "neutral", "ready": "neutral"}[state]
    return {"name": name, "product": product, "type": "", "delivered": delivered, "failed": 0,
            "waiting": waiting, "last_ok": NOW - timedelta(minutes=3) if delivered else None,
            "level": lvl, "state": state}


def base_ov(**kw):
    d = {"generated_at": NOW, "gateway": {"on": True, "uptime_s": 3600},
         "headline": {"level": "good", "key": "all_good", "dest": "Tomedo"},
         "flowing": True, "last": {"ts": NOW - timedelta(minutes=3), "device": "Sysmex XQ-320"},
         "machines": [], "machines_up": 0, "destinations": [],
         "today": {"total": 0, "ok": 0, "not_ok": 0, "waiting": 0}, "week": week([0] * 7)}
    d.update(kw)
    return d


SCEN = {
    "allgood": base_ov(
        machines=[mach("Sysmex XQ-320", "online", 14), mach("UC-1000", "online", 6, "Urine"),
                  mach("Cobas b 101", "idle", 0, "HbA1c e lipidi")],
        machines_up=3, destinations=[dest("Tomedo", "Tomedo", "receiving", 20)],
        headline={"level": "good", "key": "all_good", "dest": "Tomedo"},
        today={"total": 20, "ok": 20, "not_ok": 0, "waiting": 0},
        week=week([31, 28, 0, 0, 35, 40, 20])),
    "off": base_ov(
        gateway={"on": False, "uptime_s": 0}, flowing=False,
        machines=[mach("Sysmex XQ-320", "paused"), mach("UC-1000", "paused", 0, "Urine")],
        machines_up=0, destinations=[dest("Tomedo", "Tomedo", "paused")],
        headline={"level": "critical", "key": "gateway_off"},
        today={"total": 4, "ok": 4, "not_ok": 0, "waiting": 0}, week=week([12, 9, 0, 0, 14, 11, 4])),
    "trouble": base_ov(
        flowing=True,
        machines=[mach("Sysmex XQ-320 Hämatologie Erdgeschoss", "offline", 0),
                  mach("Seamaty SMT-120 Klinische Chemie", "waiting", 0, "Chimica clinica", "network"),
                  ] + [mach("Analysegerät Nummer %d Labor" % i, "online", 10 + i, "Analizzatore", "network") for i in range(8)],
        machines_up=8,
        destinations=[dest("Tomedo Praxis Dr. Müller-Lüdenscheidt", "Tomedo", "unreachable", 0, 0),
                      dest("Archiv-Ordner Sekretariat", "folder", "waiting", 40, 12),
                      dest("Vitomed", "Vitomed", "receiving", 131)],
        headline={"level": "critical", "key": "destination_down", "name": "Tomedo Praxis Dr. Müller-Lüdenscheidt"},
        today={"total": 1234, "ok": 1100, "not_ok": 134, "waiting": 12},
        week=week([1520, 1388, 12, 0, 1600, 1712, 1234])),
    "empty": base_ov(flowing=False, last={"ts": None, "device": ""},
                     headline={"level": "warning", "key": "no_destination"}),
}

site = out
if site.exists():
    shutil.rmtree(site)
(site / "p").mkdir(parents=True)
shutil.copytree(proj / "webui" / "static", site / "static")
(site / "i18n").mkdir()
c = webapp.app.test_client()
for lang in ("it", "de", "fr", "en"):
    (site / "i18n" / f"{lang}.js").write_text(c.get(f"/i18n/{lang}.js").get_data(as_text=True))

checker = (Path(__file__).parent / "checker.js").read_text()
for name, ov in SCEN.items():
    ovmod.build_overview = (lambda ov=ov: (lambda **kw: ov))()
    for lang in ("it", "de", "fr", "en"):
        for role in ("viewer", "admin"):
            c = webapp.app.test_client()
            c.set_cookie("jmnx_lang", lang)
            with c.session_transaction() as s:
                s.update(auth_id="x", auth_ip="127.0.0.1", username="Dr. Anna Müller-Lüdenscheidt", role=role)
            r = c.get("/")
            assert r.status_code == 200, (name, lang, role, r.status_code)
            html = r.get_data(as_text=True)
            html = html.replace("</body>", "<script>" + checker + "</script></body>")
            (site / "p" / f"{name}-{lang}-{role}.html").write_text(html)
            if lang == "it" and role == "viewer":
                live = c.get("/overview/live").get_data(as_text=True)
                (site / "p" / f"{name}-live.html").write_text(live)
(site / "wrap.html").write_text("""<!doctype html><html><body style="margin:0"><script>
var q=new URLSearchParams(location.search);var f=document.createElement('iframe');
f.style.cssText='border:0;display:block;width:'+q.get('w')+'px;height:'+(q.get('h')||900)+'px';
f.src=q.get('u')+location.hash;document.body.appendChild(f);
addEventListener('message',function(e){var p=document.createElement('pre');p.id='__chk';p.textContent=e.data;document.body.appendChild(p);});
</script></body></html>""")
print("rendered", len(list((site / 'p').glob('*.html'))))
