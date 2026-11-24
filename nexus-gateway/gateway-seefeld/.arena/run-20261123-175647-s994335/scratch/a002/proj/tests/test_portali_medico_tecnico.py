"""
Il gateway espone due portali distinti:

  MEDICO   (ruolo operator)  Panoramica, Analizzatori, Risultati, Frame Inspector
  TECNICO  (ruolo admin)     tutto il resto: configurazione, log, utenti, licenza...

Prima la separazione era solo grafica: le pagine tecniche erano protette da
CSS, e chi scriveva l'indirizzo a mano ci entrava lo stesso. In piu' un
interruttore "Studio / Tecnico" salvava la scelta nel browser e scavalcava il
ruolo deciso dal server.

Caso a parte la configurazione guidata: non aveva NESSUNA protezione, e al
passo 2 reimposta la password di admin. Chiunque raggiungesse la WebUI poteva
rilanciarla senza autenticarsi.

Questi test bloccano il ritorno di tutte e tre le situazioni.
"""
from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_BASE_HTML = _ROOT / "webui" / "templates" / "base.html"
_WIZARD = _ROOT / "webui" / "blueprints" / "wizard.py"

# pagina -> ruolo minimo richiesto
_TECNICHE = ["config_page", "logs_page", "license_page", "trace_page",
             "support", "dlq_page", "replay_index", "topology_page", "compare_page"]
_MEDICO_OPERATOR = ["inspect_index"]
_MEDICO_AUTENTICATO = ["dashboard", "analyzers", "results_page"]


def _protezione(funzione: str) -> str:
    """Ruolo richiesto dal decoratore che precede `def <funzione>(`."""
    sorgenti = [_ROOT / "webui" / "app.py"] + sorted((_ROOT / "webui" / "blueprints").glob("*.py"))
    pat = re.compile(
        r'@_?require_role\("([a-z]+)"\)\s*\ndef ' + funzione + r'\('
        r'|@_?require_auth\s*\ndef ' + funzione + r'\(', re.M)
    for f in sorgenti:
        m = pat.search(f.read_text(encoding="utf-8"))
        if m:
            return m.group(1) or "auth"
    raise AssertionError(f"nessun decoratore di protezione trovato per {funzione}")


def test_le_pagine_tecniche_richiedono_admin():
    for fn in _TECNICHE:
        assert _protezione(fn) == "admin", (
            f"{fn} non richiede admin: un medico puo' aprirla scrivendo l'indirizzo"
        )


def test_il_frame_inspector_resta_accessibile_al_medico():
    """Il medico ha ruolo operator e deve poter reinviare i referti."""
    for fn in _MEDICO_OPERATOR:
        assert _protezione(fn) == "operator"


def test_le_pagine_cliniche_restano_aperte_a_chi_ha_fatto_login():
    for fn in _MEDICO_AUTENTICATO:
        assert _protezione(fn) in ("auth", "viewer", "operator")


def test_la_configurazione_guidata_e_protetta():
    src = _WIZARD.read_text(encoding="utf-8")
    assert "@wizard_bp.before_request" in src, (
        "REGRESSIONE: il wizard e' di nuovo senza protezione, e al passo 2 "
        "reimposta la password di admin"
    )
    assert "is_setup_required()" in src, "il primo avvio deve restare possibile"
    assert 'session.get("role") != "admin"' in src


def test_la_configurazione_guidata_non_e_una_voce_di_menu():
    assert 'href="/wizard"' not in _BASE_HTML.read_text(encoding="utf-8"), (
        "il setup guidato e' il primo avvio, non una pagina del portale"
    )


def test_menu_del_medico_semplice_frame_inspector_al_tecnico():
    """
    Decisione del 2026-11-23 (SPRINT-UI-SIMPLE.md, story H1): il medico vede
    quattro voci (Panoramica, Apparecchi, Verifica impianto, Risultati); il
    Frame Inspector e' uno strumento tecnico e sta nella parte tech-only.
    La pagina resta protetta lato server dal ruolo operator.
    """
    html = _BASE_HTML.read_text(encoding="utf-8")
    nav = html[html.index('<aside class="sidebar">'):html.index('<div class="sidebar-footer">')]
    taglio = nav.index('<div class="tech-only')
    parte_medico, parte_tecnico = nav[:taglio], nav[taglio:]
    for voce in ('href="/"', 'href="/analyzers"', 'href="/verifica"', 'href="/results"'):
        assert voce in parte_medico, voce
    assert 'href="/inspect"' in parte_tecnico
    assert 'href="/inspect"' not in parte_medico


def test_niente_interruttore_studio_tecnico():
    html = _BASE_HTML.read_text(encoding="utf-8")
    assert "view-seg" not in html, "REGRESSIONE: torna l'interruttore fra i due portali"
    assert "setView" not in html


def test_la_vista_dipende_dal_ruolo_non_dal_browser():
    html = _BASE_HTML.read_text(encoding="utf-8")
    assert "jerumednexus-view" not in html, (
        "REGRESSIONE: il browser sovrascrive di nuovo il ruolo deciso dal server"
    )
    assert "'tech' if current_role == 'admin' else 'studio'" in html
