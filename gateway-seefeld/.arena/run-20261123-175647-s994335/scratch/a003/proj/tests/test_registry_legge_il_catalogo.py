"""
Un analizzatore acceso dalla WebUI deve essere davvero aperto dal gateway.

La pagina Analizzatori scrive in config/devices/<id>.yaml, ma resolve_devices()
leggeva soltanto la lista `devices:` di gateway.yaml. Risultato: ogni device
aggiunto o abilitato dal browser veniva ignorato in silenzio -- nessun log,
nessun errore, semplicemente non si apriva. Il Sysmex XQ-320 e' rimasto muto
per giorni per questo motivo, e la diagnosi e' stata lunga proprio perche' il
sintomo era l'assenza totale di tracce.
"""
from __future__ import annotations

import pytest
import yaml

from config.settings import GatewayConfig


@pytest.fixture()
def catalogo(tmp_path, monkeypatch):
    """Sposta il catalogo in una cartella temporanea per questo test."""
    import src.devices.registry as reg
    d = tmp_path / "devices"
    d.mkdir()
    monkeypatch.setattr(reg, "_CATALOG_DIR", d)
    return d


def _scrivi(cartella, dev_id: str, **campi) -> None:
    voce = {"id": dev_id, "type": "mllp_hl7", "enabled": True,
            "listen_host": "0.0.0.0", "listen_port": 5100}
    voce.update(campi)
    (cartella / f"{dev_id}.yaml").write_text(
        yaml.safe_dump(voce, sort_keys=False), encoding="utf-8")


def _risolvi(cfg_dict):
    from src.devices.registry import resolve_devices
    return resolve_devices(GatewayConfig.model_validate(cfg_dict))


def test_un_device_acceso_nel_catalogo_viene_aperto(catalogo):
    """Il caso del Sysmex: configurato dalla WebUI, ignorato dal gateway."""
    _scrivi(catalogo, "sysmex_xq320", listen_port=5006)
    attivi = _risolvi({})
    assert [d.id for d in attivi] == ["sysmex_xq320"]
    assert attivi[0].listen_port == 5006


def test_un_profilo_spento_resta_spento(catalogo):
    """Il catalogo e' una libreria: i profili non accesi non devono partire."""
    _scrivi(catalogo, "abbott_i_stat", enabled=False)
    assert _risolvi({}) == []


def test_gateway_yaml_ha_l_ultima_parola(catalogo):
    """Chi ha personalizzato devices: a mano non deve essere scavalcato."""
    _scrivi(catalogo, "sysmex_xq320", listen_port=5006)
    attivi = _risolvi({"devices": [
        {"id": "sysmex_xq320", "type": "mllp_hl7", "enabled": True,
         "listen_host": "0.0.0.0", "listen_port": 9999},
    ]})
    assert len(attivi) == 1
    assert attivi[0].listen_port == 9999, "il catalogo ha sovrascritto gateway.yaml"


def test_un_device_disabilitato_in_gateway_yaml_non_torna_dal_catalogo(catalogo):
    """Spegnerlo in gateway.yaml deve spegnerlo, non farlo rientrare di lato."""
    _scrivi(catalogo, "sysmex_xq320")
    attivi = _risolvi({"devices": [
        {"id": "sysmex_xq320", "type": "mllp_hl7", "enabled": False,
         "listen_host": "0.0.0.0", "listen_port": 5006},
    ]})
    assert attivi == []


def test_le_due_fonti_si_sommano(catalogo):
    # Come il profilo reale: un device seriale non ha campi di ascolto.
    (catalogo / "uc1000.yaml").write_text(yaml.safe_dump({
        "id": "uc1000", "type": "uc1000_serial", "enabled": True,
        "serial_port": "/dev/ttyUSB1", "baudrate": 9600,
    }, sort_keys=False), encoding="utf-8")
    attivi = _risolvi({"devices": [
        {"id": "sysmex_xq320", "type": "mllp_hl7", "enabled": True,
         "listen_host": "0.0.0.0", "listen_port": 5006},
    ]})
    assert sorted(d.id for d in attivi) == ["sysmex_xq320", "uc1000"]


def test_i_blocchi_storici_restano_il_ripiego(catalogo):
    """Senza devices: e senza catalogo acceso, valgono ancora i blocchi vecchi."""
    attivi = _risolvi({"uc1000": {"enabled": True, "serial_port": "/dev/ttyUSB1"}})
    assert [d.id for d in attivi] == ["uc1000"]


def test_un_profilo_illeggibile_non_ferma_gli_altri(catalogo):
    (catalogo / "rotto.yaml").write_text("{ questo non e' yaml", encoding="utf-8")
    _scrivi(catalogo, "sysmex_xq320", listen_port=5006)
    assert [d.id for d in _risolvi({})] == ["sysmex_xq320"]
