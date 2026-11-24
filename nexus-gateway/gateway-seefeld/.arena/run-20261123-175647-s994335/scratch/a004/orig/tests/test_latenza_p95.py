"""
La Panoramica mostra la latenza P95 "analizzatore -> gestionale".

Il contatore teneva solo somma/minimo/massimo, da cui un percentile non si
puo' ricavare: serve la distribuzione. Ora conserva una finestra limitata di
campioni per destinazione, cosi' la memoria resta costante anche dopo mesi.

Perche' il P95 e non la media: un picco isolato sposta poco la media ma e'
esattamente il caso che fa scadere un referto. Il P95 dice "19 consegne su 20
stanno sotto questo tempo", che e' la domanda vera.
"""
from __future__ import annotations

from src.debug import PerformanceCounter


def test_senza_consegne_non_inventa_un_numero():
    assert PerformanceCounter().p95_ms() is None


def test_calcolo_su_distribuzione_nota():
    p = PerformanceCounter()
    for ms in range(1, 101):
        p.record("tomedo", float(ms), True)
    assert p.p95_ms() == 95.0


def test_si_puo_chiedere_una_singola_destinazione():
    p = PerformanceCounter()
    for ms in (10, 20, 30):
        p.record("tomedo", float(ms), True)
    for ms in (500, 600, 700):
        p.record("vitomed", float(ms), True)
    assert p.p95_ms("tomedo") == 30.0
    assert p.p95_ms("vitomed") == 700.0
    assert p.p95_ms("inesistente") is None


def test_la_finestra_e_limitata():
    """Memoria costante: un gateway acceso da mesi non deve accumulare."""
    p = PerformanceCounter()
    for i in range(PerformanceCounter._FINESTRA * 3):
        p.record("tomedo", float(i), True)
    assert len(p._campioni["tomedo"]) == PerformanceCounter._FINESTRA


def test_gli_aggregati_esistenti_continuano_a_funzionare():
    p = PerformanceCounter()
    p.record("tomedo", 10.0, True)
    p.record("tomedo", 30.0, False)
    s = p._stats["tomedo"]
    assert (s["count"], s["ok"], s["fail"]) == (2, 1, 1)
    assert s["min_ms"] == 10.0 and s["max_ms"] == 30.0


def test_la_latenza_e_pubblicata_nello_stato():
    """Senza questa riga la Panoramica non ha da dove leggerla."""
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "src" / "gateway.py").read_text(encoding="utf-8")
    assert '"latency_p95_ms": perf.p95_ms()' in src
