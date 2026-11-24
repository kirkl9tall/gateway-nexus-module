"""
I segreti devono poter stare fuori da gateway.yaml.

Finche' la password SFTP stava dentro il file di configurazione, quel file
non poteva entrare nel repository -- ed e' per questo che le configurazioni
di produzione esistevano solo sul Raspberry, senza storia, senza copia e
senza modo di confrontare "prima" e "dopo" quando qualcosa smetteva di
funzionare. Dichiarando il nome della variabile d'ambiente, la
configurazione di uno studio diventa versionabile.
"""
from __future__ import annotations

import pytest

from config.settings import _risolvi_segreti, load_config


def test_la_password_arriva_dall_ambiente(monkeypatch):
    monkeypatch.setenv("TOMEDO_SFTP_PASS", "segreta")
    raw = {"targets": [{"name": "tomedo", "type": "tomedo",
                        "sftp_user": "jerumed",
                        "sftp_pass_env": "TOMEDO_SFTP_PASS"}]}
    risolto = _risolvi_segreti(raw)
    assert risolto["targets"][0]["sftp_pass"] == "segreta"
    # Il campo indiretto non deve restare: lo schema non lo conosce.
    assert "sftp_pass_env" not in risolto["targets"][0]


def test_variabile_mancante_e_un_errore_rumoroso(monkeypatch):
    """
    Meglio non partire che partire con una password vuota: il gateway
    accumulerebbe referti in coda e nessuno capirebbe perche'.
    """
    monkeypatch.delenv("TOMEDO_SFTP_PASS", raising=False)
    raw = {"targets": [{"name": "tomedo", "sftp_pass_env": "TOMEDO_SFTP_PASS"}]}
    with pytest.raises(ValueError, match="TOMEDO_SFTP_PASS"):
        _risolvi_segreti(raw)


def test_il_messaggio_dice_dove_metterla(monkeypatch):
    monkeypatch.delenv("X_PASS", raising=False)
    with pytest.raises(ValueError, match="secrets.env"):
        _risolvi_segreti({"targets": [{"name": "t", "sftp_pass_env": "X_PASS"}]})


def test_una_password_scritta_a_mano_continua_a_funzionare():
    """Compatibilita': le installazioni esistenti non devono cambiare nulla."""
    raw = {"targets": [{"name": "tomedo", "sftp_pass": "diretta"}]}
    assert _risolvi_segreti(raw)["targets"][0]["sftp_pass"] == "diretta"


def test_vale_anche_per_il_token_fhir(monkeypatch):
    monkeypatch.setenv("OSPEDALE_FHIR", "abc123")
    raw = {"targets": [{"name": "osp", "fhir_token_env": "OSPEDALE_FHIR"}]}
    assert _risolvi_segreti(raw)["targets"][0]["fhir_token"] == "abc123"


def test_una_configurazione_senza_target_non_esplode():
    assert _risolvi_segreti({}) == {}
    assert _risolvi_segreti({"targets": None}) == {"targets": None}


def test_giro_completo_dal_file(tmp_path, monkeypatch):
    """La risoluzione deve avvenire dentro load_config, non solo a parte."""
    monkeypatch.setenv("TOMEDO_SFTP_PASS", "dal-file-di-segreti")
    cfg = tmp_path / "gateway.yaml"
    cfg.write_text(
        "targets:\n"
        "  - name: tomedo\n"
        "    type: tomedo\n"
        "    enabled: true\n"
        "    sftp_host: 192.168.2.215\n"
        "    sftp_user: jerumed\n"
        "    sftp_pass_env: TOMEDO_SFTP_PASS\n"
        "    sftp_remote_path: /Users/jerumed/ldt\n",
        encoding="utf-8")
    conf = load_config(cfg)
    assert conf.targets[0].sftp_pass == "dal-file-di-segreti"
