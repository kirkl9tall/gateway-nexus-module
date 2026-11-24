"""
Server-side translations for the Web UI.

How it works
------------
* Italian is the source language: templates are written in Italian and wrap
  every visible text in ``{{ t("…") }}``. JavaScript uses ``T("…")``.
* ``webui/locale/<lang>.json`` maps the Italian text to its translation, one
  flat file per language (de, fr, en). Missing entries fall back to Italian.
* Placeholders use ``{name}``: ``t("Mancano {n} giorni", n=5)``.
* The chosen language lives in the ``jmnx_lang`` cookie, so it is the same on
  every page, including login, setup and the wizard (no session needed).
  Without a cookie: practice language from gateway.yaml (wizard step 1),
  then the browser's Accept-Language, then Italian.

The old ``static/i18n.js`` DOM-rewriting dictionary is kept only as a fallback
for pages not converted yet; it reads the same catalogs.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Callable, Dict, Optional
from urllib.parse import urlsplit

from flask import Flask, Response, make_response, redirect, request

log = logging.getLogger("webui.i18n")

LANGS: Dict[str, str] = {
    "it": "Italiano",
    "de": "Deutsch",
    "fr": "Français",
    "en": "English",
}
SOURCE_LANG = "it"
COOKIE = "jmnx_lang"
COOKIE_MAX_AGE = 365 * 24 * 3600
# Locale used by JavaScript for dates and times.
JS_LOCALE = {"it": "it-CH", "de": "de-CH", "fr": "fr-CH", "en": "en-GB"}

LOCALE_DIR = Path(__file__).resolve().parent / "locale"

_catalogs: Dict[str, Dict[str, str]] = {}
_catalog_mtime: Dict[str, float] = {}


def _catalog_path(lang: str) -> Path:
    return LOCALE_DIR / f"{lang}.json"


def catalog(lang: str) -> Dict[str, str]:
    """Translation table for ``lang`` (reloaded when the file changes)."""
    if lang == SOURCE_LANG or lang not in LANGS:
        return {}
    path = _catalog_path(lang)
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return {}
    if _catalog_mtime.get(lang) != mtime:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            _catalogs[lang] = {k: v for k, v in data.items()
                               if isinstance(v, str) and v and not k.startswith("__")}
            _catalog_mtime[lang] = mtime
        except Exception as exc:  # a broken catalog must never take the UI down
            log.error("Translation catalog %s unreadable: %s", path, exc)
            _catalogs.setdefault(lang, {})
    return _catalogs.get(lang, {})


def catalog_version(lang: str) -> str:
    try:
        return str(int(_catalog_path(lang).stat().st_mtime))
    except OSError:
        return "0"


class _SafeDict(dict):
    def __missing__(self, key: str) -> str:  # leave unknown placeholders visible
        return "{" + key + "}"


def translate(text: str, lang: str, **values) -> str:
    out = catalog(lang).get(text, text)
    if values:
        try:
            out = out.format_map(_SafeDict(values))
        except (ValueError, IndexError):
            pass
    return out


# ── Language resolution ──────────────────────────────────────────────────────

_practice_lang_getter: Optional[Callable[[], Optional[str]]] = None


def _normalise(code: Optional[str]) -> Optional[str]:
    if not code:
        return None
    code = str(code).strip().lower()[:2]
    return code if code in LANGS else None


def current_lang() -> str:
    """Language for the current request."""
    try:
        lang = _normalise(request.cookies.get(COOKIE))
        if lang:
            return lang
        if _practice_lang_getter:
            try:
                lang = _normalise(_practice_lang_getter())
            except Exception:
                lang = None
            if lang:
                return lang
        best = request.accept_languages.best_match(list(LANGS))
        return best or SOURCE_LANG
    except RuntimeError:  # outside a request
        return SOURCE_LANG


def t(text: str, **values) -> str:
    """Translate ``text`` (Italian source) into the request's language."""
    return translate(text, current_lang(), **values)


def set_lang_cookie(resp: Response, lang: str) -> Response:
    lang = _normalise(lang)
    if lang:
        resp.set_cookie(COOKIE, lang, max_age=COOKIE_MAX_AGE,
                        samesite="Lax", httponly=False, path="/")
    return resp


def _safe_next(target: Optional[str]) -> str:
    """Only same-site relative paths: no open redirect via ?next=."""
    if not target:
        target = request.referrer or "/"
    parts = urlsplit(target)
    if parts.netloc and parts.netloc != request.host:
        return "/"
    path = parts.path or "/"
    if not path.startswith("/") or path.startswith("//") or "\\" in path:
        return "/"
    return path + (("?" + parts.query) if parts.query else "")


# ── Flask wiring ─────────────────────────────────────────────────────────────

def init_app(app: Flask,
             practice_lang: Optional[Callable[[], Optional[str]]] = None) -> None:
    global _practice_lang_getter
    _practice_lang_getter = practice_lang

    app.jinja_env.globals.update(
        t=t,
        LANGS=LANGS,
        current_lang=current_lang,
        js_locale=lambda: JS_LOCALE.get(current_lang(), "it-CH"),
        i18n_version=lambda: catalog_version(current_lang()),
    )

    @app.route("/lang/<code>")
    def set_language(code: str):
        resp = make_response(redirect(_safe_next(request.args.get("next"))))
        return set_lang_cookie(resp, code)

    @app.route("/i18n/<code>.js")
    def i18n_catalog_js(code: str):
        lang = _normalise(code) or SOURCE_LANG
        body = ("window.I18N_LANG=%s;window.I18N_LOCALE=%s;window.I18N=%s;"
                % (json.dumps(lang), json.dumps(JS_LOCALE.get(lang, "it-CH")),
                   json.dumps(catalog(lang), ensure_ascii=False)))
        resp = make_response(body)
        resp.headers["Content-Type"] = "application/javascript; charset=utf-8"
        # URL carries ?v=<catalog mtime>, so it can be cached for a long time.
        resp.headers["Cache-Control"] = "public, max-age=86400"
        return resp
