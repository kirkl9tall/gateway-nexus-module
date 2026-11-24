"""
Cambiare collegamento a un apparecchio non deve lasciare dentro il vecchio.

Modificando un device da USB a TCP, la WebUI riscriveva il modulo intero e
`serial_port` restava nel file accanto a `listen_port`. I lettori guardano
prima la seriale:

    if self._serial_port: apri_seriale() else: apri_tcp()

Quindi il Sysmex riconfigurato in rete continuava ad aprire /dev/ttyUSB1 --
rubando il cavo all'UC-1000 che stava sulla stessa porta -- mentre la 5006
restava muta. Dal di fuori sembrava soltanto che non arrivasse niente: il
sintomo peggiore, quello senza errori.
"""
from __future__ import annotations

import logging


from webui.app import _pulisci_campi_trasporto


def _modulo_tcp() -> dict:
    """Cio' che il modulo manda quando si passa un apparecchio a TCP."""
    return {
        "id": "sysmex_xq320",
        "type": "sysmex_astm",
        "transport": "tcp",
        "display_name": "SYSMEX XQ320 Haematologie",
        "enabled": True,
        "serial_port": "/dev/ttyUSB1",   # residuo della configurazione USB
        "baudrate": 9600,                # residuo
        "listen_host": "0.0.0.0",
        "listen_port": 5006,
        "overwrite": True,
    }


def test_passando_a_tcp_la_porta_seriale_sparisce():
    voce = _pulisci_campi_trasporto(_modulo_tcp(), "tcp")
    assert "serial_port" not in voce, (
        "la porta seriale resta e il lettore aprira' quella invece della rete"
    )
    assert "baudrate" not in voce
    assert voce["listen_port"] == 5006


def test_passando_a_usb_la_porta_di_ascolto_sparisce():
    voce = _pulisci_campi_trasporto({
        "id": "uc1000", "type": "uc1000_serial", "transport": "usb",
        "serial_port": "/dev/ttyUSB1", "baudrate": 9600,
        "listen_host": "0.0.0.0", "listen_port": 5006,
    }, "usb")
    assert "listen_port" not in voce
    assert "listen_host" not in voce
    assert voce["serial_port"] == "/dev/ttyUSB1"


def test_i_campi_del_modulo_non_finiscono_nella_configurazione():
    """
    `transport` e' un concetto della pagina e non esiste nello schema;
    `overwrite` e' un comando di salvataggio, non una proprieta'
    dell'apparecchio. Scritti nel file diventano chiavi ignorate in silenzio.
    """
    voce = _pulisci_campi_trasporto(_modulo_tcp(), "tcp")
    assert "transport" not in voce
    assert "overwrite" not in voce


def test_quello_che_serve_resta():
    voce = _pulisci_campi_trasporto(_modulo_tcp(), "tcp")
    assert voce["id"] == "sysmex_xq320"
    assert voce["type"] == "sysmex_astm"
    assert voce["display_name"] == "SYSMEX XQ320 Haematologie"
    assert voce["enabled"] is True


def test_una_voce_gia_pulita_non_cambia():
    prima = {"id": "x", "type": "sysmex_astm", "listen_port": 5006}
    assert _pulisci_campi_trasporto(dict(prima), "tcp") == prima


# ── la difesa per i file scritti a mano ───────────────────────────────────

def test_un_collegamento_ambiguo_viene_segnalato(caplog):
    """
    Chi modifica il YAML a mano puo' comunque lasciare i due campi insieme.
    Il guasto e' invisibile, quindi almeno va detto nei log.
    """
    from src.devices.base import DeviceDefinition

    with caplog.at_level(logging.WARNING, logger="loc200.devices"):
        DeviceDefinition.model_validate({
            "id": "sysmex_xq320", "type": "sysmex_astm",
            "serial_port": "/dev/ttyUSB1", "listen_port": 5006,
        })
    assert any("serial_port" in r.message and "listen_port" in r.message
               for r in caplog.records), caplog.text


def test_un_collegamento_chiaro_non_fa_rumore(caplog):
    from src.devices.base import DeviceDefinition

    with caplog.at_level(logging.WARNING, logger="loc200.devices"):
        DeviceDefinition.model_validate({
            "id": "sysmex_xq320", "type": "sysmex_astm", "listen_port": 5006,
        })
    assert not [r for r in caplog.records if "serial_port" in r.message]


def test_la_seriale_vince_ancora_sulla_rete():
    """
    Documenta la precedenza da cui nasce tutto: non la cambiamo, perche'
    cambiarla romperebbe gli impianti che oggi funzionano. La si rende
    visibile, e si evita di produrre configurazioni ambigue.
    """
    import inspect

    from src.adapters.sysmex_reader import SysmexReader

    sorgente = inspect.getsource(SysmexReader.open)
    assert "if self._serial_port" in sorgente


# ── la pagina deve mostrare il collegamento VERO ──────────────────────────

def _catalogo(tmp_path, voci: dict):
    """Prepara un catalogo finto e torna cio' che la pagina mostrerebbe."""
    import yaml as _y
    cartella = tmp_path / "config" / "devices"
    cartella.mkdir(parents=True)
    for nome, dati in voci.items():
        (cartella / f"{nome}.yaml").write_text(
            _y.safe_dump(dati, sort_keys=False), encoding="utf-8")
    return cartella


def _transport_mostrato(voce: dict) -> tuple[str, bool]:
    """
    Riproduce la regola della pagina Configurazione. Deve seguire la stessa
    precedenza dei lettori, altrimenti la pagina dice una cosa e il gateway
    ne fa un'altra -- ed e' cosi' che il Sysmex "in TCP" apriva un cavo USB.
    """
    if voce.get("serial_port") and voce.get("listen_port"):
        return "usb", True
    if voce.get("serial_port"):
        return "usb", False
    if voce.get("listen_port"):
        return "tcp", False
    return ("usb" if voce.get("type") in ("uc1000_serial", "cobas_poct")
            else "tcp"), False


def test_con_entrambe_le_porte_la_pagina_dice_usb():
    """
    Il caso reale: la pagina mostrava "TCP - listen 0.0.0.0:5006" mentre il
    gateway apriva /dev/ttyUSB1. L'operatore sceglieva TCP, la pagina
    confermava TCP, e succedeva un'altra cosa.
    """
    trasporto, ambiguo = _transport_mostrato({
        "type": "sysmex_astm",
        "serial_port": "/dev/ttyUSB1",
        "listen_port": 5006,
    })
    assert trasporto == "usb"
    assert ambiguo is True


def test_solo_rete_e_tcp():
    assert _transport_mostrato(
        {"type": "sysmex_astm", "listen_port": 5006}) == ("tcp", False)


def test_solo_seriale_e_usb():
    assert _transport_mostrato(
        {"type": "sysmex_astm", "serial_port": "/dev/ttyUSB1"}) == ("usb", False)


def test_senza_porte_si_ricade_sul_tipo():
    assert _transport_mostrato({"type": "uc1000_serial"}) == ("usb", False)
    assert _transport_mostrato({"type": "sysmex_astm"}) == ("tcp", False)


def test_la_pagina_usa_davvero_questa_regola():
    """Se la pagina torna a dedurlo dal tipo, questo test cade."""
    import inspect

    import webui.app as app_mod

    sorgente = inspect.getsource(app_mod.config_page)
    assert '_ambiguo' in sorgente
    assert 'd.get("serial_port") and d.get("listen_port")' in sorgente


def test_l_avviso_compare_nel_template():
    from pathlib import Path as _P
    html = (_P(__file__).resolve().parents[1] / "webui" / "templates"
            / "config.html").read_text(encoding="utf-8")
    assert "collegamento ambiguo" in html
