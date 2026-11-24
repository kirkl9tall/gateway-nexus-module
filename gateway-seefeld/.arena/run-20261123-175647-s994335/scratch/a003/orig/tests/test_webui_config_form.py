"""
La pagina Configurazione deve tenere DISTINTI i due nomi:

    MSH-4  sending_facility    -- da dove parte il referto   (es. "Altstetten")
    MSH-6  receiving_facility  -- a chi e indirizzato        (es. "Dr. A Rossi")

Una versione della pagina aveva un solo campo "Nome studio" e lo scriveva in
entrambi (``out.hl7.receiving_facility = out.hl7.sending_facility``). Bastava
un salvataggio per cancellare il destinatario, e il gestionale smetteva di
assegnare i referti ai pazienti: arrivavano, venivano letti, ma restavano in
attesa. Diagnosticarlo ha richiesto due giorni.

Questi test bloccano il ritorno del difetto.
"""
from __future__ import annotations

from pathlib import Path

_CONFIG_HTML = Path(__file__).resolve().parents[1] / "webui" / "templates" / "config.html"


def _merge():
    from webui.app import _merge_form_into_yaml
    return _merge_form_into_yaml


def test_le_due_facility_restano_distinte():
    """Salvando nomi diversi, entrambi arrivano nella config senza sovrascriversi."""
    merged = _merge()(
        {"hl7": {"sending_facility": "VECCHIO", "receiving_facility": "Dr. A Rossi"}},
        {"hl7": {"sending_facility": "Altstetten", "receiving_facility": "Dr. A Rossi"}},
    )
    assert merged["hl7"]["sending_facility"] == "Altstetten"
    assert merged["hl7"]["receiving_facility"] == "Dr. A Rossi"


def test_receiving_facility_vuoto_non_cancella_quello_esistente():
    """Campo lasciato vuoto: si conserva il valore gia in produzione."""
    merged = _merge()(
        {"hl7": {"sending_facility": "Altstetten", "receiving_facility": "Dr. A Rossi"}},
        {"hl7": {"sending_facility": "Altstetten", "receiving_facility": ""}},
    )
    assert merged["hl7"]["receiving_facility"] == "Dr. A Rossi"


def test_il_form_espone_due_campi_separati():
    html = _CONFIG_HTML.read_text(encoding="utf-8")
    assert 'id="hl7-facility"' in html, "manca il campo del nome studio (MSH-4)"
    assert 'id="hl7-recv-facility"' in html, "manca il campo del destinatario (MSH-6)"


def test_il_salvataggio_non_copia_un_campo_nellaltro():
    html = _CONFIG_HTML.read_text(encoding="utf-8")
    assert "out.hl7.receiving_facility = out.hl7.sending_facility" not in html, (
        "REGRESSIONE: la pagina copia di nuovo MSH-4 in MSH-6"
    )
    assert "out.hl7.receiving_facility = _val('hl7-recv-facility')" in html


def test_il_template_riceve_il_valore_attuale_del_destinatario():
    """Senza questa variabile il campo si presenta vuoto e il salvataggio
    successivo perde il destinatario gia configurato."""
    app_py = (Path(__file__).resolve().parents[1] / "webui" / "app.py").read_text(encoding="utf-8")
    assert "cfg_receiving_facility=" in app_py
    assert "{{ cfg_receiving_facility }}" in _CONFIG_HTML.read_text(encoding="utf-8")


# ── i tre campi che prima si potevano cambiare solo a mano sul Raspberry ──

def test_il_fuso_orario_si_puo_spegnere_dalla_pagina():
    """
    include_timezone e' stato uno dei tre fattori del blackout su Tomedo:
    aggiungeva +0200 ai timestamp e il gestionale smetteva di riconoscere i
    referti. Spegnerlo richiedeva di modificare gateway.yaml a mano.
    Un booleano falso non deve essere scartato come "campo vuoto".
    """
    merged = _merge()({"hl7": {"include_timezone": True}},
                      {"hl7": {"include_timezone": False}})
    assert merged["hl7"]["include_timezone"] is False


def test_il_fuso_orario_si_puo_riaccendere():
    merged = _merge()({"hl7": {"include_timezone": False}},
                      {"hl7": {"include_timezone": True}})
    assert merged["hl7"]["include_timezone"] is True


def test_versione_e_codifica_arrivano_in_configurazione():
    merged = _merge()({}, {"hl7": {"version": "2.5", "charset": "UNICODE UTF-8"}})
    assert merged["hl7"]["version"] == "2.5"
    assert merged["hl7"]["charset"] == "UNICODE UTF-8"


def test_i_tre_campi_sono_nella_pagina():
    html = _CONFIG_HTML.read_text(encoding="utf-8")
    for campo in ("hl7-version", "hl7-charset", "hl7-timezone"):
        assert f'id="{campo}"' in html, f"campo {campo} assente dalla pagina"
    assert "out.hl7.include_timezone" in html, "il modulo non lo invia"
