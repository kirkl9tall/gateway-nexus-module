"""
firewall-sync.sh deve aprire le porte TCP degli analizzatori.

Perche' questo test esiste: un Sysmex XQ-320 configurato su 5006 e' rimasto
muto per giorni perche' ufw e' in "default deny incoming" e nessuno apriva la
porta. Il gateway non logga niente in quel caso -- il pacchetto non arriva mai
fino a lui. Se questo script si rompe, il guasto torna invisibile.

Lo script chiede la lista dei device al gateway stesso, con resolve_devices():
prima leggeva solo gateway.yaml e quindi NON vedeva gli analizzatori creati
dalla pagina Analizzatori, che scrive in config/devices/. Era lo stesso
difetto che aveva reso muto il Sysmex, in un altro punto -- due codici con due
idee diverse di quali device esistano.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

RADICE_REPO = Path(__file__).resolve().parents[1]
SCRIPT = RADICE_REPO / "scripts" / "firewall-sync.sh"

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="serve bash")


def _esegui(tmp_path: Path, gateway_yaml: str,
            catalogo: dict | None = None) -> tuple[str, list[str]]:
    """
    Lancia lo script con un ufw finto; torna (stdout, righe registrate).

    `catalogo` sono i file che la pagina Analizzatori scrive in
    config/devices/: lo script DEVE vederli, perche' e' li' che finiscono
    gli apparecchi aggiunti dal browser.
    """
    radice = tmp_path / "opt"
    (radice / "config" / "devices").mkdir(parents=True)
    cfg = radice / "config" / "gateway.yaml"
    cfg.write_text(gateway_yaml, encoding="utf-8")
    for nome, testo in (catalogo or {}).items():
        (radice / "config" / "devices" / f"{nome}.yaml").write_text(
            testo, encoding="utf-8")

    finto = tmp_path / "bin"
    finto.mkdir()
    registro = tmp_path / "ufw.log"
    (finto / "ufw").write_text(
        '#!/usr/bin/env bash\necho "$@" >> "%s"\n' % registro.as_posix(),
        encoding="utf-8")
    (finto / "ufw").chmod(0o755)

    env = dict(os.environ)
    env["PATH"] = f"{finto.as_posix()}{os.pathsep}{env['PATH']}"
    env["INSTALL_DIR"] = radice.as_posix()
    env["PYTHONPATH"] = str(RADICE_REPO)

    res = subprocess.run(["bash", str(SCRIPT), str(cfg)],
                         capture_output=True, text=True, env=env, timeout=120)
    assert res.returncode == 0, res.stderr
    righe = registro.read_text(encoding="utf-8").splitlines() if registro.exists() else []
    return res.stdout, righe


def _aperte(righe: list[str]) -> list[str]:
    return [r for r in righe if "allow" in r]


# ── il caso che ci e' costato giorni ──────────────────────────────────────

def test_apre_la_porta_di_un_device_tcp(tmp_path):
    _, righe = _esegui(tmp_path, """
devices:
  - id: sysmex_xq320
    display_name: Sysmex XQ-320
    type: sysmex_astm
    enabled: true
    listen_host: "0.0.0.0"
    listen_port: 5006
""")
    assert any("allow 5006/tcp" in r for r in righe), righe


def test_vede_i_device_creati_dalla_pagina_analizzatori(tmp_path):
    """
    Il difetto che ha fatto rispondere "Nessuna porta di ascolto configurata"
    subito dopo aver aggiunto il Sysmex dal browser: la pagina scrive nel
    catalogo, lo script leggeva solo gateway.yaml.
    """
    _, righe = _esegui(tmp_path, "devices: []\n", catalogo={
        "sysmex_xq320": """
id: sysmex_xq320
display_name: SYSMEX XQ320 Haematologie
type: sysmex_astm
enabled: true
listen_host: "0.0.0.0"
listen_port: 5006
""",
    })
    assert any("allow 5006/tcp" in r for r in righe), (
        "la porta del device creato dalla WebUI non viene aperta", righe)


def test_il_nome_dell_apparecchio_finisce_nel_commento(tmp_path):
    """Serve a capire, mesi dopo, perche' quella porta e' aperta."""
    _, righe = _esegui(tmp_path, "devices: []\n", catalogo={
        "sysmex_xq320": """
id: sysmex_xq320
display_name: SYSMEX XQ320 Haematologie
type: sysmex_astm
enabled: true
listen_port: 5006
""",
    })
    assert any("SYSMEX XQ320 Haematologie" in r for r in righe), righe


# ── quello che NON va aperto ──────────────────────────────────────────────

def test_ignora_i_device_disabilitati(tmp_path):
    """Aprire la porta di un apparecchio spento espone la rete per niente."""
    _, righe = _esegui(tmp_path, """
devices:
  - {id: spento, type: sysmex_astm, enabled: false, listen_port: 5099}
  - {id: acceso, type: sysmex_astm, enabled: true,  listen_port: 5006}
""")
    assert not any("5099" in r for r in righe), righe
    assert any("5006/tcp" in r for r in righe), righe


def test_ignora_i_device_seriali(tmp_path):
    """
    Un apparecchio su USB non ha porte di rete da aprire. Il LOC-200 va messo
    esplicitamente su seriale: senza il blocco loc200 vale il valore
    predefinito, che e' HTTP sulla 5003 -- e quella porta va aperta davvero.
    """
    out, righe = _esegui(tmp_path, """
loc200:
  connection_type: serial
  serial:
    port: /dev/ttyUSB9
devices:
  - id: uc1000
    type: uc1000_serial
    enabled: true
    serial_port: /dev/ttyUSB0
""")
    assert _aperte(righe) == [], righe
    assert "Nessuna porta" in out


def test_una_porta_sola_anche_con_due_device(tmp_path):
    _, righe = _esegui(tmp_path, """
devices:
  - {id: a, type: sysmex_astm, enabled: true, listen_port: 5006}
  - {id: b, type: sysmex_astm, enabled: true, listen_port: 5006}
  - {id: c, type: sysmex_astm, enabled: true, listen_port: 5007}
""")
    assert len([r for r in _aperte(righe) if "5006/tcp" in r]) == 1, righe
    assert any("5007/tcp" in r for r in _aperte(righe)), righe


# ── la porta HTTP del LOC-200 ─────────────────────────────────────────────

def test_apre_anche_la_porta_http_del_loc200(tmp_path):
    """Il LOC-200 in HTTP ascolta su una porta come gli altri."""
    _, righe = _esegui(tmp_path, """
loc200:
  connection_type: http
  http_port: 5003
devices: []
""")
    assert any("allow 5003/tcp" in r for r in righe), righe


def test_loc200_su_seriale_non_apre_niente(tmp_path):
    out, righe = _esegui(tmp_path, """
loc200:
  connection_type: serial
  serial:
    port: /dev/ttyUSB0
devices: []
""")
    assert _aperte(righe) == [], righe


# ── robustezza ────────────────────────────────────────────────────────────

def test_configurazione_non_valida_non_fa_cadere_lo_script(tmp_path):
    out, righe = _esegui(tmp_path, "devices: [ questo non e' yaml")
    assert _aperte(righe) == []


def test_config_assente_non_e_un_errore(tmp_path):
    """L'installer lo chiama prima che il wizard scriva la configurazione."""
    res = subprocess.run(["bash", str(SCRIPT), str(tmp_path / "non-esiste.yaml")],
                         capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, res.stderr
