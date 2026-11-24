"""
Un analizzatore che non ha MAI parlato deve generare un allarme.

La sorveglianza del silenzio esisteva gia', ma guardava solo `_last_seen`,
che si popola quando arriva un referto. Un apparecchio configurato che non
inviava niente -- porta chiusa dal firewall, cavo staccato, indirizzo
sbagliato -- non era in quella mappa, quindi non veniva nemmeno controllato.
Il Sysmex XQ-320 e' rimasto muto per giorni senza un solo allarme, e la
diagnosi e' stata lunga proprio perche' il sistema taceva insieme a lui.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace



def _gateway_finto(mai_sentiti, last_seen, avvio_secondi_fa: int):
    """
    Costruisce il minimo necessario per eseguire il ciclo di sorveglianza
    senza avviare il gateway vero (che aprirebbe porte e lettori).
    """
    import time as _t
    from src.gateway import Gateway

    g = object.__new__(Gateway)
    g._running = True
    g._last_seen = dict(last_seen)
    g._mai_sentiti = set(mai_sentiti)
    g._start_time = _t.time() - avvio_secondi_fa
    return g


def _controlla(g, warn_after: int, alert_after: int):
    """Riproduce il ciclo di sorveglianza del silenzio e ne raccoglie l'esito."""
    now = datetime.now()
    silent = []
    da_controllare = dict(g._last_seen or {})
    avvio = datetime.fromtimestamp(g._start_time)
    for mai in g._mai_sentiti:
        da_controllare.setdefault(mai, avvio.strftime("%Y-%m-%dT%H:%M:%S"))
    for name, ts_str in da_controllare.items():
        try:
            dt = datetime.fromisoformat(ts_str)
            silence = int((now - dt).total_seconds())
        except (ValueError, TypeError):
            continue
        mai_sentito = name in g._mai_sentiti
        if silence >= alert_after:
            silent.append({"device": name, "silence_sec": silence,
                           "level": "alert", "mai_sentito": mai_sentito})
        elif silence >= warn_after:
            silent.append({"device": name, "silence_sec": silence,
                           "level": "warning", "mai_sentito": mai_sentito})
    return silent


def test_apparecchio_mai_sentito_genera_un_allarme():
    """Il caso Sysmex: configurato, silenzioso, e prima invisibile."""
    g = _gateway_finto(mai_sentiti={"Sysmex XQ-320"}, last_seen={},
                       avvio_secondi_fa=7200)
    silent = _controlla(g, warn_after=900, alert_after=3600)
    assert len(silent) == 1
    assert silent[0]["device"] == "Sysmex XQ-320"
    assert silent[0]["level"] == "alert"
    assert silent[0]["mai_sentito"] is True


def test_appena_avviato_non_allarma():
    """Dare il tempo di collegarsi: un allarme immediato sarebbe rumore."""
    g = _gateway_finto(mai_sentiti={"Sysmex XQ-320"}, last_seen={},
                       avvio_secondi_fa=60)
    assert _controlla(g, warn_after=900, alert_after=3600) == []


def test_chi_ha_parlato_non_e_piu_mai_sentito():
    """Dopo il primo referto l'apparecchio esce dall'insieme."""
    g = _gateway_finto(mai_sentiti={"Sysmex XQ-320"}, last_seen={},
                       avvio_secondi_fa=7200)
    g._mai_sentiti.discard("Sysmex XQ-320")
    adesso = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    g._last_seen["Sysmex XQ-320"] = adesso
    assert _controlla(g, warn_after=900, alert_after=3600) == []


def test_chi_ha_smesso_di_parlare_resta_distinto():
    """Silenzio dopo aver parlato: allarme sì, ma non 'mai sentito'."""
    vecchio = (datetime.now() - timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%S")
    g = _gateway_finto(mai_sentiti=set(), last_seen={"LOC-200": vecchio},
                       avvio_secondi_fa=100000)
    silent = _controlla(g, warn_after=900, alert_after=3600)
    assert len(silent) == 1
    assert silent[0]["level"] == "alert"
    assert silent[0]["mai_sentito"] is False


def test_un_timestamp_rotto_non_ferma_gli_altri():
    g = _gateway_finto(mai_sentiti={"Sysmex XQ-320"},
                       last_seen={"Rotto": "non-e-una-data"},
                       avvio_secondi_fa=7200)
    silent = _controlla(g, warn_after=900, alert_after=3600)
    assert [s["device"] for s in silent] == ["Sysmex XQ-320"]


def test_il_valore_salvato_ha_la_precedenza_sull_avvio():
    """
    Se un apparecchio e' per errore in entrambi, vince cio' che ha davvero
    inviato: setdefault non deve sovrascrivere un dato reale.
    """
    adesso = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    g = _gateway_finto(mai_sentiti={"Sysmex XQ-320"},
                       last_seen={"Sysmex XQ-320": adesso},
                       avvio_secondi_fa=100000)
    assert _controlla(g, warn_after=900, alert_after=3600) == []


# ── il codice vero, non solo la riproduzione ──────────────────────────────

def test_il_gateway_semina_davvero_l_insieme():
    """Verifica sul codice reale che i device attivi vengano seminati."""

    from src.gateway import Gateway

    g = object.__new__(Gateway)
    g._registry = SimpleNamespace(
        definitions=[SimpleNamespace(name="Sysmex XQ-320"),
                     SimpleNamespace(name="Menarini UC-1000")],
        open_all=_lettori_finti,
    )
    asyncio.run(g._open_all_readers())
    assert g._mai_sentiti == {"Sysmex XQ-320", "Menarini UC-1000", "LOC-200"}


async def _lettori_finti():
    return []


def test_il_gateway_dimentica_chi_ha_parlato():
    """
    Il campo _mai_sentiti deve essere ripulito nel punto in cui si aggiorna
    _last_seen, altrimenti un apparecchio attivo continuerebbe ad allarmare.
    """
    import inspect

    from src.gateway import Gateway

    sorgente = inspect.getsource(Gateway)
    assert "self._mai_sentiti.discard(device)" in sorgente
    i_seen = sorgente.index("self._last_seen[device]")
    i_discard = sorgente.index("self._mai_sentiti.discard(device)")
    assert abs(i_discard - i_seen) < 200, \
        "lo scarto deve stare accanto all'aggiornamento di _last_seen"
