"""
The language chosen in the Web UI must hold on every page.

Before: translations were done in the browser by swapping exact Italian
sentences from an 89-entry JavaScript dictionary. About 8% of the visible text
was covered, login/setup/wizard did not load the script at all, so changing
page "fell back" to Italian.

Now pages are rendered translated by the server (webui/i18n.py) and these
tests stop the problem coming back:

* every t("…")/T("…") key has a DE, FR and EN translation, with the same
  {placeholders};
* converted pages contain no hard-coded visible text outside t();
* the language is kept in a cookie and applies to login, setup, wizard and
  dashboard, without any JavaScript.

To convert a new page: wrap its text in t()/T(), add it to CONVERTED, run
``python tools/i18n_keys.py`` and fill the missing entries.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "webui" / "templates"
LOCALE = ROOT / "webui" / "locale"
sys.path.insert(0, str(ROOT / "tools"))

import i18n_keys  # noqa: E402

LANGS = ("de", "fr", "en")

# Pages fully converted to t(). Each sprint story adds its pages here.
CONVERTED = [
    "base.html",
    "login.html",
    "setup.html",
    "dashboard.html",
    "wizard/base.html",
    "_lang_select.html",
    "_overview_live.html",
    "_machine_card.html",
    "_ui.html",
    "_check_result.html",
    "verifica.html",
    "device_form.html",
    "analyzers.html",
    "results.html",
    "_results_list.html",
    "_result_detail.html",
    # Technician pages
    "dlq.html", "logs.html", "frame_inspector_index.html", "frame_inspector.html",
    "config.html", "users.html", "license.html", "topology.html", "wire_replay.html",
    "device_archive.html",
]

# Visible text that is the same in every language (names, codes, contacts).
ALLOWED = {
    "JerumedNexus", "GW", "Gateway", "HL7 v2.5 · MLLP · ASTM", "Frame Inspector",
    "Wire Replay", "+41 78 402 05 99", "info@jerumed-nexus.ch",
    "jerumed-nexus.ch", "2026 Jerumed Nexus GmbH", "Jerumed Nexus GmbH",
    "Jerumed Nexus Connect —", "MSH-10:", "MSH-3", "MSH-4", "MSH-6", "MSH-12", "MSH-18", "SHA-256", "— Gateway HL7", "JerumedNexus Gateway —", "ms —",
}


def _catalog(lang: str) -> dict:
    return json.loads((LOCALE / f"{lang}.json").read_text(encoding="utf-8"))


# ── Catalogs ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("lang", LANGS)
def test_every_key_in_use_is_translated(lang):
    cat = _catalog(lang)
    missing = sorted(k for k in i18n_keys.used_keys() if not cat.get(k))
    assert not missing, f"{lang}.json is missing {len(missing)} entries: {missing[:10]}"


@pytest.mark.parametrize("lang", LANGS)
def test_placeholders_match_the_italian_text(lang):
    ph = re.compile(r"\{(\w+)\}")
    wrong = [k for k, v in _catalog(lang).items()
             if not k.startswith("__") and set(ph.findall(k)) != set(ph.findall(v))]
    assert not wrong, f"{lang}: placeholders differ in {wrong}"


# ── No hard-coded text left in converted pages ───────────────────────────────

def _visible_text(html: str) -> list[str]:
    html = re.sub(r"<script.*?</script>|<style.*?</style>|<!--.*?-->",
                  " ", html, flags=re.S)
    html = re.sub(r"\{#.*?#\}|\{%.*?%\}|\{\{.*?\}\}", " ", html, flags=re.S)
    html = re.sub(r"<svg.*?</svg>", " ", html, flags=re.S)
    html = re.sub(r"&[#\w]+;", " ", html)
    out = []
    for chunk in re.findall(r">([^<>]+)<", html):
        chunk = " ".join(chunk.split())
        if re.search(r"[A-Za-zÀ-ÿ]{2}", chunk) and chunk not in ALLOWED:
            out.append(chunk)
    return out


@pytest.mark.parametrize("page", CONVERTED)
def test_converted_page_has_no_hardcoded_text(page):
    left = _visible_text((TEMPLATES / page).read_text(encoding="utf-8"))
    assert not left, f"{page}: text not wrapped in t(): {left}"


# ── Behaviour ────────────────────────────────────────────────────────────────

@pytest.fixture()
def app(monkeypatch, tmp_path):
    from src.security import roles as _roles
    monkeypatch.setattr(_roles, "is_setup_required", lambda: False)
    from webui import app as webapp
    monkeypatch.setattr(webapp, "CONFIG_F", tmp_path / "gateway.yaml")
    monkeypatch.setattr(webapp, "STATUS_F", tmp_path / "status.json")
    webapp.app.config["TESTING"] = True
    return webapp


def _login(client):
    with client.session_transaction() as s:
        s["auth_id"] = "x"
        s["auth_ip"] = "127.0.0.1"
        s["username"] = "admin"
        s["role"] = "admin"


def test_lang_route_sets_cookie_and_returns_to_the_page(app):
    c = app.app.test_client()
    r = c.get("/lang/de?next=/analyzers")
    assert r.status_code == 302
    assert r.headers["Location"].endswith("/analyzers")
    assert "jmnx_lang=de" in r.headers.get("Set-Cookie", "")


@pytest.mark.parametrize("evil", ["//evil.example/x", "https://evil.example/", "\\\\evil"])
def test_lang_route_is_not_an_open_redirect(app, evil):
    r = app.app.test_client().get("/lang/de", query_string={"next": evil})
    loc = r.headers["Location"]
    assert "evil" not in loc


def test_unknown_language_is_ignored(app):
    r = app.app.test_client().get("/lang/xx?next=/")
    assert "jmnx_lang" not in r.headers.get("Set-Cookie", "")


def test_login_page_follows_the_cookie(app):
    c = app.app.test_client()
    c.set_cookie("jmnx_lang", "de")
    html = c.get("/login").get_data(as_text=True)
    assert "Anmelden" in html and "Accedi" not in html
    assert '<html lang="de">' in html


def test_browser_language_is_used_without_cookie(app):
    c = app.app.test_client()
    html = c.get("/login", headers={"Accept-Language": "fr-CH,fr;q=0.9"}).get_data(as_text=True)
    assert "Se connecter" in html


def test_practice_language_beats_browser_language(app):
    app.CONFIG_F.write_text("praxis:\n  language: en\n", encoding="utf-8")
    c = app.app.test_client()
    html = c.get("/login", headers={"Accept-Language": "de"}).get_data(as_text=True)
    assert "Sign in" in html


def test_language_holds_across_pages(app):
    c = app.app.test_client()
    c.get("/lang/fr?next=/")
    _login(c)
    html = c.get("/").get_data(as_text=True)
    visible = " ".join(_visible_text(html))
    assert "Aperçu" in html                    # menu
    assert "Vos appareils" in html             # dashboard body
    assert "Panoramica" not in visible
    # Catalog for JavaScript text is served for the same language
    assert '/i18n/fr.js' in html


def test_wrong_password_message_is_translated(app):
    c = app.app.test_client()
    c.set_cookie("jmnx_lang", "en")
    html = c.post("/login", data={"username": "nobody", "password": "x"}).get_data(as_text=True)
    assert "Wrong username or password" in html


def test_js_catalog(app):
    body = app.app.test_client().get("/i18n/de.js").get_data(as_text=True)
    assert body.startswith('window.I18N_LANG="de"')
    assert '"Tutto funziona.": "Alles funktioniert."' in body


def test_wizard_language_choice_applies_to_the_interface(monkeypatch, app):
    from src.security import roles as _roles
    monkeypatch.setattr(_roles, "is_setup_required", lambda: True)
    c = app.app.test_client()
    r = c.post("/wizard/1", data={"language": "fr", "facility_name": "Cabinet Test"})
    assert "jmnx_lang=fr" in r.headers.get("Set-Cookie", "")


def test_fallback_translator_cannot_loop_on_itself():
    """
    Regression (2026-11-23): the fallback translator in static/i18n.js
    re-translated its own edits. A translation equal to its source
    ("Gateway" -> "Gateway") fired the MutationObserver forever and froze the
    browser tab ("Page unresponsive") 15 s after load, at the first refresh.
    Both guards must stay: skip identical translations, and disconnect the
    observer while translating.
    """
    js = (ROOT / "webui" / "static" / "i18n.js").read_text(encoding="utf-8")
    assert "out === txt ? null : out" in js
    assert "observer.disconnect();" in js and "observer.observe(document.body, OPTS);" in js
