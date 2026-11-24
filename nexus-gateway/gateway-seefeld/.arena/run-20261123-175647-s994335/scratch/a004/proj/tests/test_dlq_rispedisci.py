"""
Il rispedisci deve dire PERCHE' non e' riuscito.

L'endpoint non aveva alcuna gestione degli errori: qualunque eccezione
diventava una pagina HTML, il browser provava a leggerla come JSON e
mostrava

    errore: SyntaxError: The string did not match the expected pattern.

Un messaggio che non dice niente a nessuno, e che nascondeva la causa vera --
nel nostro caso un referto rifiutato dal validatore. Undici referti in coda e
nessun modo di sapere da dove ricominciare.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from flask import Flask

RADICE = Path(__file__).resolve().parents[1]
DLQ_HTML = RADICE / "webui" / "templates" / "dlq.html"


@pytest.fixture()
def client(monkeypatch):
    from src.security import roles as _roles
    monkeypatch.setattr(_roles, "is_setup_required", lambda: False)
    monkeypatch.setattr(_roles, "require_role", lambda have, want: True)

    from webui.blueprints.dlq import dlq_bp

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.secret_key = "test"
    app.register_blueprint(dlq_bp)
    c = app.test_client()
    with c.session_transaction() as s:
        s["auth_id"] = "test-user"
        s["role"] = "operator"
        s["_csrf"] = "tok"
    return c


def _rispedisci(client, cid="ABC123"):
    return client.post(f"/api/dlq/{cid}/replay", headers={"X-CSRF-Token": "tok"})


def test_un_guasto_interno_resta_json(client, monkeypatch):
    """
    Il caso reale: qualcosa esplode a meta' e il browser riceve HTML.
    Deve ricevere JSON, sempre, cosi' il messaggio arriva all'operatore.
    """
    import webui.blueprints.dlq as mod
    monkeypatch.setattr(mod, "read_dead_letter", lambda cid: "MSH|^~&|X|Y")

    def _esplode(*a, **k):
        raise RuntimeError("il validatore ha rifiutato il messaggio")

    monkeypatch.setattr("config.settings.GatewayConfig.model_validate", _esplode)

    r = _rispedisci(client)
    assert r.status_code == 500
    assert r.mimetype == "application/json", r.data[:200]
    dati = json.loads(r.data)
    assert dati["ok"] is False
    assert "il validatore ha rifiutato" in dati["error"]


def test_il_messaggio_porta_il_tipo_dell_errore(client, monkeypatch):
    """Serve a distinguere un guasto di rete da uno di configurazione."""
    import webui.blueprints.dlq as mod
    monkeypatch.setattr(mod, "read_dead_letter", lambda cid: "MSH|^~&|X|Y")
    monkeypatch.setattr("config.settings.GatewayConfig.model_validate",
                        lambda *a, **k: (_ for _ in ()).throw(ValueError("boom")))
    dati = json.loads(_rispedisci(client).data)
    assert dati["error"].startswith("ValueError:")


def test_messaggio_inesistente_resta_un_404_json(client, monkeypatch):
    import webui.blueprints.dlq as mod
    monkeypatch.setattr(mod, "read_dead_letter", lambda cid: None)
    r = _rispedisci(client)
    assert r.status_code == 404
    assert json.loads(r.data)["error"] == "not found"


def test_senza_csrf_non_si_rispedisce(client):
    r = client.post("/api/dlq/ABC/replay")
    assert r.status_code == 400
    assert json.loads(r.data)["ok"] is False


# ── il lato browser ───────────────────────────────────────────────────────

def test_la_pagina_non_fa_json_diretto():
    """
    r.json() su una pagina HTML produce il SyntaxError illeggibile. Tutte le
    letture devono passare dall'aiutante che sa gestire quel caso.
    """
    # Si guarda il codice, non i commenti: qui sopra la frase e' citata
    # apposta per spiegare il difetto.
    righe = [r for r in DLQ_HTML.read_text(encoding="utf-8").splitlines()
             if not r.lstrip().startswith("//")]
    codice = chr(10).join(righe)
    assert "_leggiJson" in codice
    assert "r.json()" not in codice, (
        "una lettura diretta e' tornata: su una risposta HTML mostrera' di "
        "nuovo 'SyntaxError: The string did not match the expected pattern'"
    )


def test_la_pagina_mostra_il_motivo_del_fallimento():
    """Undici 'non riusciti' senza spiegazione non dicono da dove ripartire."""
    html = DLQ_HTML.read_text(encoding="utf-8")
    assert "motivi" in html
    assert "motivi[0]" in html


def test_l_aiutante_riporta_lo_stato_http():
    html = DLQ_HTML.read_text(encoding="utf-8")
    assert "r.status" in html and "r.statusText" in html


# ── i segreti valgono anche qui ───────────────────────────────────────────

def test_il_rispedisci_risolve_i_segreti():
    """
    Legge la configurazione da disco: se il segreto e' dichiarato come nome
    di variabile d'ambiente, senza risolverlo partirebbe con una password
    vuota e fallirebbe per un motivo che non c'entra con il referto.
    """
    import inspect

    import webui.blueprints.dlq as mod

    sorgente = inspect.getsource(mod.api_dlq_replay)
    assert "_risolvi_segreti" in sorgente
