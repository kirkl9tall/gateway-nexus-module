"""
List every translation key used by the Web UI and report what each catalog
is missing.

    python tools/i18n_keys.py            # missing keys per language
    python tools/i18n_keys.py --all      # every key in use

Keys are the Italian source strings passed to t("…") in templates/Python and
T("…") in JavaScript.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEBUI = ROOT / "webui"
LANGS = ("de", "fr", "en")

# t("…") / t('…') / T("…") / T('…') / _t('…'), first argument only.
_CALL = re.compile(r"""(?<![\w.])_?[tT]\(\s*(?:"((?:[^"\\]|\\.)*)"|'((?:[^'\\]|\\.)*)')""")


def _unescape(s: str) -> str:
    return s.replace("\\'", "'").replace('\\"', '"')


def keys_in(text: str) -> set[str]:
    out = set()
    for m in _CALL.finditer(text):
        k = m.group(1) if m.group(1) is not None else m.group(2)
        if k:
            out.add(_unescape(k))
    return out


def used_keys() -> set[str]:
    keys: set[str] = set()
    files = list((WEBUI / "templates").rglob("*.html")) + list(WEBUI.rglob("*.py"))
    for f in files:
        if f.name == "i18n.py":
            continue
        keys |= keys_in(f.read_text(encoding="utf-8"))
    # Lists translated with t(list[i]) in templates
    keys |= {"Studio", "Amministratore", "Rete", "Analizzatore", "Gestionale",
             "Backup", "Verifica"}
    # Keys built at run time (t(variable)) in webui/overview.py and check_view.py
    sys.path.insert(0, str(ROOT))
    from webui import check_view, overview
    keys |= {kind for _, kind in overview._KINDS} | {"Analizzatore"}
    keys |= set(overview.WEEKDAYS)
    keys |= {q for _, q in check_view.GROUPS}
    # Results page filters, t(label) in a loop (templates/results.html)
    keys |= {"Oggi", "Ieri", "Ultimi 7 giorni", "Ultimi 30 giorni", "Tutto",
             "Tutti", "Recapitati", "Non recapitati"}
    return keys


def load(lang: str) -> dict:
    p = WEBUI / "locale" / f"{lang}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def main() -> int:
    keys = used_keys()
    if "--all" in sys.argv:
        print(json.dumps(sorted(keys), ensure_ascii=False, indent=1))
        return 0
    bad = 0
    for lang in LANGS:
        cat = load(lang)
        missing = sorted(k for k in keys if not cat.get(k))
        bad += len(missing)
        print(f"{lang}: {len(keys) - len(missing)}/{len(keys)} translated")
        for k in missing:
            print("   missing:", k)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
