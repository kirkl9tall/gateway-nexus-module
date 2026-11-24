"""
Lo scanner di rilevamento non deve aprire una porta gia' in uso.

Su Linux aprire una porta seriale gia' aperta di solito riesce: non c'e' un
blocco esclusivo. Lo scanner apriva ogni /dev/ttyUSB* e leggeva fino a 512
byte per 3 secondi, anche quando un lettore configurato stava ricevendo un
referto su quella stessa porta. I byte letti dallo scanner non arrivano al
lettore: il referto puo' risultare mutilato, o non arrivare affatto, e nei log
non compare alcun errore.
"""
from __future__ import annotations

import asyncio

import pytest

from src.discovery.service import DiscoveryService


@pytest.fixture()
def servizio(tmp_path):
    cfg = tmp_path / "gateway.yaml"
    cfg.write_text("devices: []\n", encoding="utf-8")
    return DiscoveryService(config_file=cfg, state_file=tmp_path / "stato.json")


def _scrivi(servizio, testo: str) -> None:
    servizio._config_file.write_text(testo, encoding="utf-8")


def test_riconosce_la_porta_di_un_device_attivo(servizio):
    _scrivi(servizio, """
devices:
  - id: boson
    name: Boson
    transport: serial
    serial_port: /dev/ttyUSB0
""")
    assert "/dev/ttyUSB0" in servizio.porte_gia_in_uso()


def test_ignora_i_device_disabilitati(servizio):
    """Un device spento non tiene la porta: sondarla e' lecito."""
    _scrivi(servizio, """
devices:
  - {id: boson, transport: serial, serial_port: /dev/ttyUSB0, enabled: false}
""")
    assert "/dev/ttyUSB0" not in servizio.porte_gia_in_uso()


def test_riconosce_anche_i_blocchi_per_device_storici(servizio):
    """loc200:, cobas: ... convivono ancora con devices:."""
    _scrivi(servizio, """
loc200:
  enabled: true
  serial:
    port: /dev/ttyUSB1
""")
    assert "/dev/ttyUSB1" in servizio.porte_gia_in_uso()


def test_configurazione_illeggibile_non_fa_cadere_la_scansione(servizio):
    _scrivi(servizio, "devices: [ questo: non e' yaml valido")
    assert servizio.porte_gia_in_uso() == set()


def test_la_porta_occupata_non_viene_sondata(servizio, monkeypatch):
    _scrivi(servizio, """
devices:
  - {id: boson, transport: serial, serial_port: /dev/ttyUSB0}
""")
    monkeypatch.setattr(
        "src.discovery.service.list_usb_serial_ports",
        lambda: [{"device": "/dev/ttyUSB0", "vid": "", "pid": ""},
                 {"device": "/dev/ttyUSB9", "vid": "", "pid": ""}],
    )
    sondate: list = []

    async def _finta(self, devnode, info=None):
        sondate.append(devnode)

    monkeypatch.setattr(DiscoveryService, "_probe_serial_device", _finta)
    presenti = asyncio.run(servizio._scan_usb())

    assert sondate == ["/dev/ttyUSB9"], sondate
    # Resta comunque elencata fra quelle presenti, altrimenti scan_once la
    # cancellerebbe dallo stato come se fosse stata staccata.
    assert "usb:/dev/ttyUSB0" in presenti


def test_l_evento_udev_rispetta_la_stessa_regola(servizio, monkeypatch):
    _scrivi(servizio, """
devices:
  - {id: boson, transport: serial, serial_port: /dev/ttyUSB0}
""")
    sondate: list = []

    async def _finta(self, devnode, info=None):
        sondate.append(devnode)

    monkeypatch.setattr(DiscoveryService, "_probe_serial_device", _finta)
    asyncio.run(servizio.notify_added("/dev/ttyUSB0"))
    assert sondate == []
    asyncio.run(servizio.notify_added("/dev/ttyUSB9"))
    assert sondate == ["/dev/ttyUSB9"]


# ── una porta occupata deve restare VISIBILE ──────────────────────────────

def test_la_porta_occupata_compare_comunque_nell_elenco(servizio, monkeypatch):
    """
    Saltare la porta per non rubare byte e' giusto; farla sparire dalla
    scansione no. L'operatore vedeva una cartella vuota e non capiva se
    l'apparecchio fosse collegato.
    """
    _scrivi(servizio, """
devices:
  - {id: boson, display_name: Boson QDS-300B, transport: serial, serial_port: /dev/ttyUSB0}
""")
    monkeypatch.setattr(
        "src.discovery.service.list_usb_serial_ports",
        lambda: [{"device": "/dev/ttyUSB0", "vid": "10c4", "pid": "ea60"}],
    )
    sondate: list = []

    async def _finta(self, devnode, info=None):
        sondate.append(devnode)

    monkeypatch.setattr(DiscoveryService, "_probe_serial_device", _finta)
    asyncio.run(servizio._scan_usb())

    assert sondate == [], "la porta occupata non va aperta"
    elenco = servizio.snapshot()
    porte = [d["location"] for d in elenco]
    assert "/dev/ttyUSB0" in porte, f"la porta e' sparita dall'elenco: {elenco}"


def test_la_porta_occupata_dice_chi_la_usa(servizio, monkeypatch):
    _scrivi(servizio, """
devices:
  - {id: boson, display_name: Boson QDS-300B, transport: serial, serial_port: /dev/ttyUSB0}
""")
    monkeypatch.setattr(
        "src.discovery.service.list_usb_serial_ports",
        lambda: [{"device": "/dev/ttyUSB0", "vid": "", "pid": ""}],
    )
    monkeypatch.setattr(DiscoveryService, "_probe_serial_device",
                        lambda self, d, info=None: None)
    asyncio.run(servizio._scan_usb())
    voce = [d for d in servizio.snapshot() if d["location"] == "/dev/ttyUSB0"][0]
    assert "Boson QDS-300B" in (voce["display_name"] or ""), voce
    assert voce["activated"] is True, "non va proposta come nuova da attivare"


def test_la_porta_occupata_non_finisce_fra_quelle_da_attivare(servizio, monkeypatch):
    """`pending()` elenca cio' che l'operatore puo' ancora aggiungere."""
    _scrivi(servizio, """
devices:
  - {id: boson, display_name: Boson, transport: serial, serial_port: /dev/ttyUSB0}
""")
    monkeypatch.setattr(
        "src.discovery.service.list_usb_serial_ports",
        lambda: [{"device": "/dev/ttyUSB0", "vid": "", "pid": ""}],
    )
    monkeypatch.setattr(DiscoveryService, "_probe_serial_device",
                        lambda self, d, info=None: None)
    asyncio.run(servizio._scan_usb())
    assert servizio.pending() == []
