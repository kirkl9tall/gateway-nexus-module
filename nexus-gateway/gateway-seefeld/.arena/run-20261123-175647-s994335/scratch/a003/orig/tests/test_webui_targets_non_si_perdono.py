"""
Un salvataggio della pagina Configurazione non deve cancellare i gestionali.

Il backend ricostruisce la lista `targets` a ogni salvataggio -- scelta voluta,
perche' altrimenti non si potrebbe disattivare un gestionale. Ma la pagina
precompilava SOLO i campi di Tomedo: per Vitomed, curaMED, Aeskulap, Axenita,
DnaMed e WinMed la casella "abilitato" ripartiva spenta e host/cartella vuoti.
Bastava aprire /config, cambiare il nome dello studio e salvare: il gestionale
configurato sparuiva da gateway.yaml e il gateway smetteva di consegnare, senza
un errore da nessuna parte.

Due difese, entrambe verificate qui:
  1. il modulo dichiara in `targets_managed` cosa controlla, e il server
     conserva tutto il resto;
  2. la pagina ripresenta i valori salvati, cosi' un salvataggio senza
     modifiche e' davvero senza modifiche.
"""
from __future__ import annotations

import re
from pathlib import Path

_CONFIG_HTML = Path(__file__).resolve().parents[1] / "webui" / "templates" / "config.html"


def _merge():
    from webui.app import _merge_form_into_yaml
    return _merge_form_into_yaml


def _vitomed_configurato() -> dict:
    return {
        "targets": [
            {"name": "vitomed", "type": "vitomed", "enabled": True,
             "host": "10.0.0.5", "port": 6661},
        ]
    }


# ── 1. la rete di sicurezza del server ────────────────────────────────────

def test_un_target_non_gestito_dal_modulo_sopravvive():
    """Il caso reale: pagina che non sa mostrare Vitomed, salvataggio, e Vitomed resta."""
    merged = _merge()(
        _vitomed_configurato(),
        {"hl7": {"sending_facility": "Altstetten"},
         "targets": [], "targets_managed": ["tomedo"]},
    )
    nomi = [t["name"] for t in merged["targets"]]
    assert "vitomed" in nomi, merged["targets"]
    sopravvissuto = next(t for t in merged["targets"] if t["name"] == "vitomed")
    assert sopravvissuto["host"] == "10.0.0.5"
    assert sopravvissuto["port"] == 6661


def test_deselezionare_un_gestionale_lo_rimuove_davvero():
    """L'altra meta': se il modulo lo gestisce e non lo invia, e' stato spento."""
    merged = _merge()(
        _vitomed_configurato(),
        {"targets": [], "targets_managed": ["vitomed", "tomedo"]},
    )
    assert [t["name"] for t in merged["targets"]] == []


def test_modulo_che_non_dichiara_niente_non_cancella_nulla():
    """Compatibilita': un client vecchio gestisce solo cio' che invia."""
    merged = _merge()(
        _vitomed_configurato(),
        {"targets": [{"name": "tomedo", "type": "tomedo", "enabled": True,
                      "sftp_host": "192.168.2.215", "sftp_user": "jerumed",
                      "sftp_pass": "x", "sftp_remote_path": "/import"}]},
    )
    nomi = sorted(t["name"] for t in merged["targets"])
    assert nomi == ["tomedo", "vitomed"], merged["targets"]


def test_un_gestionale_gestito_viene_aggiornato_non_duplicato():
    merged = _merge()(
        _vitomed_configurato(),
        {"targets": [{"name": "vitomed", "type": "vitomed", "enabled": True,
                      "host": "10.0.0.99", "port": 6661}],
         "targets_managed": ["vitomed"]},
    )
    vitomed = [t for t in merged["targets"] if t["name"] == "vitomed"]
    assert len(vitomed) == 1, merged["targets"]
    assert vitomed[0]["host"] == "10.0.0.99"


def test_la_password_sftp_non_si_perde_col_segnaposto():
    merged = _merge()(
        {"targets": [{"name": "tomedo", "type": "tomedo", "enabled": True,
                      "sftp_host": "192.168.2.215", "sftp_user": "jerumed",
                      "sftp_pass": "segreta", "sftp_remote_path": "/import"}]},
        {"targets": [{"name": "tomedo", "type": "tomedo", "enabled": True,
                      "sftp_host": "192.168.2.215", "sftp_user": "jerumed",
                      "sftp_pass": "********", "sftp_remote_path": "/import"}],
         "targets_managed": ["tomedo"]},
    )
    assert merged["targets"][0]["sftp_pass"] == "segreta"


def test_winmed_salva_la_cartella():
    """WinMed e' un file-drop: senza watch_folder la validazione lo rifiuta."""
    merged = _merge()(
        {},
        {"targets": [{"name": "winmed", "type": "winmed", "enabled": True,
                      "watch_folder": "//SERVER/Laboreingang"}],
         "targets_managed": ["winmed"]},
    )
    assert merged["targets"][0]["watch_folder"] == "//SERVER/Laboreingang"
    from webui.app import _validate_target_form
    assert _validate_target_form(merged["targets"][0]) == []


# ── 2. la pagina ripresenta i valori salvati ──────────────────────────────

def _html() -> str:
    return _CONFIG_HTML.read_text(encoding="utf-8")


def test_la_casella_abilitato_riflette_la_configurazione():
    html = _html()
    assert re.search(r'id="t-\{\{ tid \}\}-enabled".*?\{% if attivo %\}checked',
                     html, re.S), "la casella riparte sempre spenta"


def test_host_porta_e_cartella_sono_precompilati():
    html = _html()
    for campo, chiave in (("host", "host"), ("port", "port"), ("folder", "watch_folder")):
        blocco = re.search(r'id="t-\{\{ tid \}\}-' + campo + r'"(.{0,200})', html, re.S)
        assert blocco, f"campo {campo} non trovato"
        assert "salvato.get" in blocco.group(1), \
            f"il campo {campo} non ripresenta il valore salvato ({chiave})"


def test_la_password_sftp_non_torna_in_chiaro_al_browser():
    """Il template riceve il segnaposto, non il segreto."""
    import webui.app as app_mod
    sorgente = Path(app_mod.__file__).read_text(encoding="utf-8")
    assert "'********' if _t.get('sftp_pass') else ''" in sorgente


def test_una_sola_tabella_dei_gestionali():
    """Template e JavaScript devono leggere la stessa lista, non due copie."""
    html = _html()
    assert "ui_targets|tojson" in html, "il JS non usa la tabella del server"
    assert "_MLLP_TARGETS" not in html, "la vecchia tabella duplicata e' tornata"
    from webui.app import UI_TARGETS
    assert {t["id"] for t in UI_TARGETS} >= {"vitomed", "winmed", "tomedo"}


def test_il_modulo_dichiara_cosa_gestisce():
    assert "out.targets_managed" in _html()
