"""
Chi crea la configurazione da zero non deve ricreare il guasto.

La pagina Configurazione era stata corretta per tenere distinti MSH-4 e
MSH-6, ma i DUE punti che creano la configurazione su un impianto nuovo --
l'installer e il wizard di primo avvio -- continuavano a scrivere lo stesso
nome in entrambi. Un'installazione pulita riportava quindi esattamente il
guasto da cui eravamo partiti: il gestionale riceve i file, li legge, e non
li assegna piu' a nessun paziente.

Il wizard aveva anche due valori predefiniti sbagliati, 2.5 e UTF-8, cioe'
la combinazione che l'installer stesso documenta come da non usare mai
perche' Tomedo archivia il file e lo rifiuta.
"""
from __future__ import annotations

import re
from pathlib import Path

RADICE = Path(__file__).resolve().parents[1]
INSTALL = RADICE / "scripts" / "install.sh"
STEP1 = RADICE / "webui" / "templates" / "wizard" / "step_1.html"


def _fonde(dati: dict, esistente: dict | None = None) -> dict:
    from webui.blueprints.wizard import _merge_wizard_into_config
    return _merge_wizard_into_config(esistente or {}, dati)


# ── il wizard di primo avvio ──────────────────────────────────────────────

def test_il_wizard_non_copia_il_mittente_nel_destinatario():
    cfg = _fonde({"facility_name": "Altstetten",
                  "recipient_name": "Dr. A Abuawad"})
    assert cfg["hl7"]["sending_facility"] == "Altstetten"
    assert cfg["hl7"]["receiving_facility"] == "Dr. A Abuawad"


def test_senza_destinatario_il_wizard_lascia_vuoto():
    """
    Un destinatario sbagliato e' peggio di uno mancante: sembra configurato.
    Vuoto viene segnalato da Verifica impianto come guasto.
    """
    cfg = _fonde({"facility_name": "Altstetten"})
    assert cfg["hl7"]["receiving_facility"] == ""
    assert cfg["hl7"]["sending_facility"] == "Altstetten"


def test_il_wizard_non_propone_piu_2_5_e_utf8():
    """
    La combinazione che Tomedo rifiuta. L'installer la documenta da anni
    come da non usare, e il wizard la impostava come predefinita.
    """
    cfg = _fonde({"facility_name": "X", "recipient_name": "Y"})
    assert cfg["hl7"]["version"] == "2.3"
    assert cfg["hl7"]["charset"] == "8859/1"


def test_il_wizard_non_accende_il_fuso_orario():
    """+0200 nei timestamp: Tomedo smette di riconoscere i referti."""
    cfg = _fonde({"facility_name": "X", "recipient_name": "Y"})
    assert cfg["hl7"]["include_timezone"] is False


def test_il_wizard_non_sovrascrive_valori_gia_scelti():
    """Chi ha gia' configurato a mano non deve essere riportato ai default."""
    cfg = _fonde({"facility_name": "X", "recipient_name": "Y"},
                 {"hl7": {"version": "2.5", "charset": "UNICODE UTF-8",
                          "include_timezone": True}})
    assert cfg["hl7"]["version"] == "2.5"
    assert cfg["hl7"]["charset"] == "UNICODE UTF-8"
    assert cfg["hl7"]["include_timezone"] is True


def test_il_wizard_conserva_i_device_esistenti():
    cfg = _fonde({"facility_name": "X", "recipient_name": "Y"},
                 {"devices": [{"id": "sysmex", "type": "sysmex_astm"}]})
    assert cfg["devices"][0]["id"] == "sysmex"


def test_il_modulo_del_wizard_chiede_il_destinatario():
    html = STEP1.read_text(encoding="utf-8")
    assert 'name="recipient_name"' in html, (
        "il wizard non chiede il destinatario: resterebbe sempre vuoto"
    )


# ── l'installer ───────────────────────────────────────────────────────────

def _script() -> str:
    return INSTALL.read_text(encoding="utf-8")


def test_l_installer_chiede_il_destinatario():
    assert "RECIPIENT_NAME" in _script(), (
        "l'installer non chiede il destinatario del referto"
    )


def test_l_installer_non_copia_il_mittente_nel_destinatario():
    s = _script()
    assert 'receiving_facility: "${RECIPIENT}"' in s, (
        "REGRESSIONE: l'installer scrive di nuovo il nome dello studio anche "
        "in MSH-6. Un'installazione pulita ricrea il guasto che ha fermato "
        "le consegne."
    )
    assert 'receiving_facility: "${FACILITY}"' not in s


def test_l_installer_non_accende_il_fuso_orario():
    assert re.search(r"^\s*include_timezone:\s*false", _script(), re.M), (
        "l'installer genera include_timezone: true -- Tomedo smette di "
        "riconoscere i referti"
    )


def test_l_installer_avvisa_se_manca_il_destinatario():
    """Un campo vuoto senza avviso passa inosservato fino al primo test."""
    s = _script()
    assert "Destinatario (MSH-6) non indicato" in s


def test_installer_e_wizard_concordano_sul_formato():
    """
    I due punti che creano la configurazione devono proporre gli stessi
    valori: se divergono, il risultato dipende da quale dei due hai usato.
    """
    cfg = _fonde({"facility_name": "X", "recipient_name": "Y"})
    s = _script()
    assert f'version: "{cfg["hl7"]["version"]}"' in s
    assert f'charset: "{cfg["hl7"]["charset"]}"' in s
