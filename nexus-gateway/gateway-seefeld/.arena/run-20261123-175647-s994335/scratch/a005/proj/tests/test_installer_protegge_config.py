"""
L'installer non deve mai cancellare lo stato di un impianto gia' funzionante.

Sotto config/ vivono la configurazione dello studio, le credenziali, gli
utenti, le chiavi, i certificati TLS e i profili dei device aggiunti dalla
Web UI. Nessuno di questi file esiste nel sorgente, quindi un
"rsync --delete" senza protezione li spazza via.

La versione precedente elencava le esclusioni una per una e ne aveva
dimenticate parecchie: webui_users.json, known_hosts, dlq_key, i certificati.
Un semplice "install.sh --upgrade" cancellava TUTTI gli utenti; e senza utenti
is_setup_required() torna vero e la configurazione guidata si riapre a
chiunque raggiunga la Web UI.

L'installazione da capo era anche peggio: nessuna esclusione affatto.
"""
from __future__ import annotations

import re
from pathlib import Path

_INSTALL = Path(__file__).resolve().parents[1] / "scripts" / "install.sh"


def _script() -> str:
    return _INSTALL.read_text(encoding="utf-8")


def test_config_e_protetta_dalla_cancellazione():
    assert "--filter='P /config/***'" in _script(), (
        "REGRESSIONE: config/ non e' piu' protetta da rsync --delete. "
        "Un aggiornamento cancellerebbe utenti, chiavi e configurazione."
    )


def test_ogni_rsync_che_cancella_e_protetto():
    """
    Prima c'erano due rsync diversi e quello dell'installazione da capo non
    escludeva nulla. Oggi le chiamate sono due per un motivo preciso -- la
    seconda porta i nuovi profili del catalogo senza toccare quelli esistenti
    -- ma la regola resta: chi puo' cancellare deve proteggere config/.
    """
    s = _script()
    chiamate = re.findall(r'^\s*rsync\b[^\n]*(?:\\\n[^\n]*)*', s, re.M)
    assert chiamate, "nessuna chiamata rsync trovata"
    for c in chiamate:
        if "--delete" in c or "RSYNC_OPTS" in c:
            assert "P /config/***" in c or "RSYNC_OPTS" in c, (
                f"questa rsync puo' cancellare senza proteggere config/:\n{c}"
            )


def test_il_catalogo_analizzatori_non_viene_sovrascritto():
    """
    config/devices/ e' insieme libreria di profili e stato dell'operatore: la
    pagina Analizzatori scrive li' quando si accende un apparecchio.
    Sovrascriverlo a ogni aggiornamento azzerava quelle scelte e
    l'analizzatore smetteva di partire senza che nessuno l'avesse toccato.
    """
    s = _script()
    assert "--exclude='config/devices/'" in s, (
        "il catalogo non e' escluso dalla copia principale: un aggiornamento "
        "riporterebbe i profili allo stato di fabbrica"
    )
    assert "--ignore-existing" in s, (
        "senza --ignore-existing i profili nuovi non arriverebbero mai "
        "sulle installazioni esistenti"
    )


def test_nessun_profilo_del_catalogo_parte_da_solo():
    """
    I 33 profili sono una libreria di modelli, non una configurazione. Uno
    acceso di fabbrica farebbe partire un lettore in studi che non hanno
    quell'apparecchio, con allarmi di silenzio a ripetizione.
    """
    from pathlib import Path

    import yaml

    cartella = Path(__file__).resolve().parents[1] / "config" / "devices"
    accesi = []
    for f in sorted(cartella.glob("*.yaml")):
        try:
            d = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        if d.get("enabled") is True:
            accesi.append(f.name)
    assert accesi == [], f"profili accesi di fabbrica: {accesi}"


def test_logs_e_venv_restano_fuori():
    s = _script()
    for atteso in ("--exclude='logs/'", "--exclude='.venv/'"):
        assert atteso in s, f"manca {atteso}"


def test_avvisa_se_si_reinstalla_sopra_una_configurazione():
    s = _script()
    assert 'if [ -f "$INSTALL_DIR/config/gateway.yaml" ]' in s or \
           'elif [ -f "$INSTALL_DIR/config/gateway.yaml" ]' in s, (
        "l'installazione da capo deve avvisare se trova gia' una configurazione"
    )
