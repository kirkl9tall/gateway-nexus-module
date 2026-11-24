"""
La Verifica impianto deve riconoscere i guasti che ci sono davvero costati.

Ogni test qui corrisponde a un guasto realmente accaduto, e tutti avevano lo
stesso sintomo: nessun errore da nessuna parte, i referti semplicemente non
arrivavano. Se la verifica smette di riconoscerli, torniamo a diagnosticare
a mano per giorni.
"""
from __future__ import annotations

import json
import socket
import time


from src.common.verifica_impianto import (
    ATTENZIONE,
    GUASTO,
    IGNOTO,
    OK,
    controlla_destinatari,
    controlla_intestazione_hl7,
    controlla_servizio,
    controlla_spazio,
    esegui,
)


def _stati(esiti) -> list:
    return [e.stato for e in esiti]


def _per_nome(esiti, frammento):
    trovati = [e for e in esiti if frammento in e.nome]
    assert trovati, f"nessun esito con {frammento!r} in {[e.nome for e in esiti]}"
    return trovati[0]


# ── il servizio ───────────────────────────────────────────────────────────

def test_stato_mai_scritto_e_un_guasto(tmp_path):
    e = controlla_servizio(tmp_path / "mai-esistito.json")
    assert e.stato == GUASTO
    assert "systemctl start" in e.rimedio


def test_stato_vecchio_e_un_guasto(tmp_path):
    """Il processo bloccato e' peggio di quello morto: la pagina mostra
    numeri vecchi come se fossero attuali."""
    f = tmp_path / "status.json"
    f.write_text("{}", encoding="utf-8")
    import os
    vecchio = time.time() - 3600
    os.utime(f, (vecchio, vecchio))
    e = controlla_servizio(f)
    assert e.stato == GUASTO
    assert "60 minuti" in e.dettaglio


def test_stato_fresco_va_bene(tmp_path):
    f = tmp_path / "status.json"
    f.write_text("{}", encoding="utf-8")
    assert controlla_servizio(f).stato == OK


# ── l'identita HL7: il guasto che e' costato due giorni ───────────────────

def test_mittente_uguale_a_destinatario_e_un_guasto():
    """Il blackout su Tomedo: MSH-4 copiato in MSH-6."""
    esiti = controlla_intestazione_hl7({"hl7": {
        "sending_application": "LOC200",
        "sending_facility": "Altstetten",
        "receiving_facility": "Altstetten",
    }})
    e = _per_nome(esiti, "MSH-4 e MSH-6")
    assert e.stato == GUASTO
    assert "non li assegna" in e.dettaglio


def test_destinatario_mancante_e_un_guasto():
    esiti = controlla_intestazione_hl7({"hl7": {
        "sending_application": "LOC200",
        "sending_facility": "Altstetten",
    }})
    assert _per_nome(esiti, "MSH-6").stato == GUASTO


def test_identita_corretta_passa():
    """I valori che funzionavano davvero in produzione ad Altstetten."""
    esiti = controlla_intestazione_hl7({"hl7": {
        "sending_application": "LOC200",
        "sending_facility": "Altstetten",
        "receiving_facility": "Dr. A Abuawad",
    }})
    assert set(_stati(esiti)) == {OK}


def test_nome_del_sistema_mancante_e_un_guasto():
    esiti = controlla_intestazione_hl7({"hl7": {
        "sending_facility": "Altstetten",
        "receiving_facility": "Dr. A Abuawad",
    }})
    assert _per_nome(esiti, "MSH-3").stato == GUASTO


# ── i destinatari ─────────────────────────────────────────────────────────

def test_nessun_destinatario_attivo_e_un_guasto():
    """Il caso in cui un salvataggio cancellava i gestionali."""
    e = controlla_destinatari({"targets": []})[0]
    assert e.stato == GUASTO
    assert "non vanno da nessuna parte" in e.dettaglio


def test_destinatario_senza_host_e_un_guasto():
    esiti = controlla_destinatari({"targets": [
        {"name": "vitomed", "type": "vitomed", "enabled": True},
    ]})
    assert esiti[0].stato == GUASTO
    assert "mancanti" in esiti[0].dettaglio


def test_destinatario_irraggiungibile_e_un_guasto():
    esiti = controlla_destinatari({"targets": [
        # Porta di scarto: nessuno ascolta mai qui.
        {"name": "vitomed", "type": "vitomed", "enabled": True,
         "host": "127.0.0.1", "port": 9},
    ]}, timeout=0.3)
    assert esiti[0].stato == GUASTO
    assert "coda" in esiti[0].dettaglio


def test_destinatario_raggiungibile_passa():
    """Apriamo davvero una porta e verifichiamo che venga vista."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        porta = s.getsockname()[1]
        esiti = controlla_destinatari({"targets": [
            {"name": "finto", "type": "vitomed", "enabled": True,
             "host": "127.0.0.1", "port": porta},
        ]}, timeout=1.0)
    assert esiti[0].stato == OK


def test_cartella_non_scrivibile_e_un_guasto(tmp_path):
    esiti = controlla_destinatari({"targets": [
        {"name": "winmed", "type": "winmed", "enabled": True,
         "watch_folder": str(tmp_path / "non-esiste")},
    ]})
    assert esiti[0].stato == GUASTO


def test_cartella_scrivibile_passa(tmp_path):
    esiti = controlla_destinatari({"targets": [
        {"name": "winmed", "type": "winmed", "enabled": True,
         "watch_folder": str(tmp_path)},
    ]})
    assert esiti[0].stato == OK


def test_un_destinatario_spento_non_viene_controllato():
    assert controlla_destinatari({"targets": [
        {"name": "vitomed", "enabled": False, "host": "x", "port": 1},
    ]})[0].stato == GUASTO  # nessuno attivo -> e' comunque un guasto


# ── lo spazio ─────────────────────────────────────────────────────────────

def test_spazio_abbondante_passa(tmp_path):
    assert controlla_spazio(tmp_path, minimo_mb=1).stato == OK


def test_spazio_esaurito_e_un_guasto(tmp_path, monkeypatch):
    import shutil as _sh
    from collections import namedtuple
    Uso = namedtuple("Uso", "total used free")
    monkeypatch.setattr(_sh, "disk_usage", lambda p: Uso(0, 0, 10 * 1024 * 1024))
    e = controlla_spazio(tmp_path, minimo_mb=200)
    assert e.stato == GUASTO
    assert e.dati["libero_mb"] == 10


# ── l'esecuzione completa ─────────────────────────────────────────────────

def test_un_controllo_che_esplode_non_ferma_gli_altri(tmp_path, monkeypatch):
    """Una verifica interrotta a meta' e' peggio di una che ammette un buco."""
    import src.common.verifica_impianto as vi

    def _esplode(_cfg):
        raise RuntimeError("boom")

    monkeypatch.setattr(vi, "controlla_analizzatori", _esplode)
    cfg = tmp_path / "gateway.yaml"
    cfg.write_text("hl7: {sending_application: X, sending_facility: A, "
                   "receiving_facility: B}\ntargets: []\n", encoding="utf-8")
    r = vi.esegui(config_file=cfg, stato_file=tmp_path / "assente.json")
    stati = [e["stato"] for e in r["esiti"]]
    assert IGNOTO in stati
    assert OK in stati, "gli altri controlli devono essere comunque eseguiti"


def test_lo_stato_generale_e_il_peggiore(tmp_path):
    cfg = tmp_path / "gateway.yaml"
    cfg.write_text("hl7: {sending_application: X, sending_facility: A, "
                   "receiving_facility: B}\ntargets: []\n", encoding="utf-8")
    r = esegui(config_file=cfg, stato_file=tmp_path / "assente.json")
    assert r["stato_generale"] == GUASTO


def test_il_risultato_e_serializzabile_in_json(tmp_path):
    """La pagina lo riceve via JSON: niente oggetti non convertibili."""
    cfg = tmp_path / "gateway.yaml"
    cfg.write_text("targets: []\n", encoding="utf-8")
    r = esegui(config_file=cfg, stato_file=tmp_path / "assente.json")
    json.dumps(r)  # non deve sollevare
    assert set(r) == {"stato_generale", "conteggio", "esiti", "eseguito_alle"}


def test_ogni_guasto_porta_un_rimedio(tmp_path):
    """Un guasto senza rimedio lascia l'operatore fermo: non e' accettabile."""
    cfg = tmp_path / "gateway.yaml"
    cfg.write_text("targets: []\n", encoding="utf-8")
    r = esegui(config_file=cfg, stato_file=tmp_path / "assente.json")
    senza = [e["nome"] for e in r["esiti"]
             if e["stato"] == GUASTO and not e["rimedio"].strip()]
    assert senza == [], f"guasti senza rimedio: {senza}"


# ── lo spegnimento non e' un guasto ───────────────────────────────────────

def _invecchia(f, secondi: float) -> None:
    import os
    quando = time.time() - secondi
    os.utime(f, (quando, quando))


def test_dopo_uno_spegnimento_lungo_non_si_grida_al_blocco(tmp_path, monkeypatch):
    """
    Il Raspberry e' stato spento venti ore. Il file di stato e' vecchio di
    venti ore e NON c'e' niente di rotto. Il controllo annunciava comunque
    "il processo e' fermo o bloccato", mandando a cercare un guasto
    inesistente -- e facendo perdere di vista quello vero.
    """
    import src.common.verifica_impianto as vi
    f = tmp_path / "status.json"
    f.write_text("{}", encoding="utf-8")
    _invecchia(f, 20 * 3600)                      # file di ieri
    monkeypatch.setattr(vi, "_secondi_dall_avvio", lambda: 30.0)  # acceso ora
    e = vi.controlla_servizio(f)
    assert e.stato == ATTENZIONE, e
    assert "non ha ancora scritto" in e.dettaglio
    assert "bloccato" not in e.dettaglio


def test_acceso_da_un_pezzo_senza_stato_e_un_guasto(tmp_path, monkeypatch):
    """Se la macchina e' su da mezz'ora e il gateway tace, non e' partito."""
    import src.common.verifica_impianto as vi
    f = tmp_path / "status.json"
    f.write_text("{}", encoding="utf-8")
    _invecchia(f, 20 * 3600)
    monkeypatch.setattr(vi, "_secondi_dall_avvio", lambda: 1800.0)
    e = vi.controlla_servizio(f)
    assert e.stato == GUASTO
    assert "non e' partito" in e.dettaglio
    assert "journalctl" in e.rimedio


def test_processo_bloccato_resta_un_guasto(tmp_path, monkeypatch):
    """
    Macchina accesa da ore, il gateway ha scritto ma poi ha smesso: quello
    si' che e' un blocco, e va ancora segnalato come tale.
    """
    import src.common.verifica_impianto as vi
    f = tmp_path / "status.json"
    f.write_text("{}", encoding="utf-8")
    _invecchia(f, 3600)
    monkeypatch.setattr(vi, "_secondi_dall_avvio", lambda: 10 * 3600)
    e = vi.controlla_servizio(f)
    assert e.stato == GUASTO
    assert "si e' bloccato" in e.dettaglio


def test_senza_informazione_sull_avvio_si_comporta_come_prima(tmp_path, monkeypatch):
    """Fuori da Linux /proc/uptime non esiste: non si deve cadere."""
    import src.common.verifica_impianto as vi
    f = tmp_path / "status.json"
    f.write_text("{}", encoding="utf-8")
    _invecchia(f, 3600)
    monkeypatch.setattr(vi, "_secondi_dall_avvio", lambda: None)
    assert vi.controlla_servizio(f).stato == GUASTO


def test_stato_fresco_resta_a_posto(tmp_path, monkeypatch):
    import src.common.verifica_impianto as vi
    f = tmp_path / "status.json"
    f.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(vi, "_secondi_dall_avvio", lambda: 10 * 3600)
    assert vi.controlla_servizio(f).stato == OK


def test_cinque_minuti_di_quiete_non_sono_un_blocco(tmp_path, monkeypatch):
    """
    Il gateway riscrive status.json ogni cinque minuti. Con la vecchia soglia
    di due minuti, uno studio senza esami vedeva "il processo si e' bloccato"
    a ogni verifica -- e un allarme che suona sempre smette di dire qualcosa.
    """
    import src.common.verifica_impianto as vi
    f = tmp_path / "status.json"
    f.write_text("{}", encoding="utf-8")
    _invecchia(f, 5 * 60 + 30)
    monkeypatch.setattr(vi, "_secondi_dall_avvio", lambda: 10 * 3600)
    assert vi.controlla_servizio(f).stato == OK


def test_due_cicli_mancati_sono_un_blocco(tmp_path, monkeypatch):
    import src.common.verifica_impianto as vi
    f = tmp_path / "status.json"
    f.write_text("{}", encoding="utf-8")
    _invecchia(f, 15 * 60)
    monkeypatch.setattr(vi, "_secondi_dall_avvio", lambda: 10 * 3600)
    assert vi.controlla_servizio(f).stato == GUASTO


def test_il_gateway_riscrive_lo_stato_a_intervalli():
    """
    Il controllo sopra ha senso solo se status.json viene davvero riscritto
    periodicamente. Prima non lo era, ed e' questo che rendeva il controllo
    inutile: verifichiamo che la scrittura stia nel ciclo di salute.
    """
    import inspect

    from src.gateway import Gateway

    sorgente = inspect.getsource(Gateway._health_check)
    assert "_write_status()" in sorgente, (
        "status.json non viene piu' riscritto dal ciclo di salute: la sua "
        "eta' torna a non dire niente sulla vita del gateway"
    )
