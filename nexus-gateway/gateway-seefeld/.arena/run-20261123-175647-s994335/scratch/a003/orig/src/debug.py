"""
src/debug.py
─────────────────────────────────────────────────────────────────────
Strumenti di debug e diagnostica per JerumedNexus Gateway.

Modalità di attivazione:
  1. Via config:  log_level: "DEBUG"
  2. Via ENV:     LOG_LEVEL=DEBUG python main.py
  3. Via flag:    python main.py --debug
  4. Via WebUI:   Dashboard → impostazioni → "Modalità debug"

Cosa viene loggato in DEBUG vs INFO:
  DEBUG  → ogni byte ricevuto (debug_raw_frames: true)
           ogni campo del frame parsato
           ogni segmento HL7 costruito
           handshake MLLP completo (ACK grezzo)
           tempo di elaborazione per ogni analisi
           tentativi di riconnessione
  INFO   → connessioni aperte/chiuse
           ogni analisi ricevuta (sample ID, n. analiti)
           consegna a ogni gestionale (OK / fallita)
           riavvii del servizio
  WARNING→ frame senza analiti riconoscibili
           tentativo fallito (ma riprova)
           connessione persa (ma riconnessione in corso)
  ERROR  → errore di parsing non recuperabile
           tutti i tentativi di consegna esauriti
           errore di configurazione
  CRITICAL→ crash fatale del gateway
─────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations
import functools
import logging
import time
from typing import Any, Callable

import math
from collections import deque

log = logging.getLogger("loc200.debug")


def timed(logger: logging.Logger | None = None, level: int = logging.DEBUG):
    """Decorator: log execution time of async functions at DEBUG level."""
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs) -> Any:
            t0 = time.perf_counter()
            try:
                result = await fn(*args, **kwargs)
                elapsed = (time.perf_counter() - t0) * 1000
                (logger or log).log(level, "%s completed in %.1f ms", fn.__name__, elapsed)
                return result
            except Exception as exc:
                elapsed = (time.perf_counter() - t0) * 1000
                (logger or log).log(level, "%s raised %s after %.1f ms",
                                    fn.__name__, type(exc).__name__, elapsed)
                raise
        return wrapper
    return decorator


def log_frame(raw: bytes, source: str = "LOC-200") -> None:
    """Log a raw frame in readable hex+ASCII format (DEBUG only)."""
    if not log.isEnabledFor(logging.DEBUG):
        return
    lines = []
    for i in range(0, len(raw), 16):
        chunk = raw[i:i+16]
        hex_part  = " ".join(f"{b:02x}" for b in chunk)
        ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"  {i:04x}  {hex_part:<47}  {ascii_part}")
    log.debug("RAW FRAME from %s (%d bytes):\n%s", source, len(raw), "\n".join(lines))


def log_hl7(hl7_text: str, direction: str = "→") -> None:
    """Log a complete HL7 message segment by segment (DEBUG only)."""
    if not log.isEnabledFor(logging.DEBUG):
        return
    segments = [s.strip() for s in hl7_text.split("\r") if s.strip()]
    log.debug("HL7 message %s (%d segments):", direction, len(segments))
    for seg in segments:
        seg_type = seg[:3]
        log.debug("  %-4s %s", seg_type, seg)


def log_parse_result(result: dict) -> None:
    """Log a parsed LOC-200 result dict in readable form (DEBUG only)."""
    if not log.isEnabledFor(logging.DEBUG):
        return
    obs = result.get("observations", [])
    log.debug(
        "Parsed result:\n"
        "  Sample ID  : %s\n"
        "  Patient ID : %s\n"
        "  Patient    : %s  age=%s  gender=%s\n"
        "  Disc       : %s  lot=%s\n"
        "  Analytes   : %d",
        result.get("sample_id", "—"),
        result.get("patient_id", "—"),
        result.get("patient_name", "—"),
        result.get("age", "—"),
        result.get("gender", "—"),
        result.get("disc_name", "—"),
        result.get("lot_id", "—"),
        len(obs),
    )
    for o in obs:
        flag = f" [{o['flag']}]" if o.get("flag") else ""
        ref  = f"  ref={o['ref_low']}-{o['ref_high']}" if o.get("ref_low") is not None else ""
        log.debug("    %-10s = %-10s %s%s%s",
                  o["analyte"], o["value"], o.get("unit", ""), flag, ref)


def log_mllp_ack(ack_raw: bytes, target: str) -> None:
    """Log the raw MLLP ACK received from a PIS (DEBUG only)."""
    if not log.isEnabledFor(logging.DEBUG):
        return
    ack_text = ack_raw.decode("utf-8", errors="replace")
    log.debug("MLLP ACK from %s (%d bytes):\n%s", target, len(ack_raw), ack_text)


class PerformanceCounter:
    """Track rolling stats: count, avg/min/max latency per target.

    Oltre agli aggregati tiene una finestra degli ultimi campioni per target,
    perche' il percentile non si puo' ricavare da somma/min/max: serve la
    distribuzione. La finestra e' limitata, quindi la memoria resta costante
    anche dopo mesi di esercizio.
    """

    _FINESTRA = 500          # campioni conservati per target

    def __init__(self) -> None:
        self._stats: dict[str, dict] = {}
        self._campioni: dict[str, deque] = {}

    def p95_ms(self, target: str | None = None) -> float | None:
        """95esimo percentile delle consegne recenti, in millisecondi.

        Senza `target` considera tutte le destinazioni insieme: e' il numero
        che la Panoramica mostra come "latenza analizzatore -> gestionale".
        Restituisce None finche' non c'e' nemmeno una consegna.
        """
        if target is not None:
            valori = list(self._campioni.get(target, ()))
        else:
            valori = [v for d in self._campioni.values() for v in d]
        if not valori:
            return None
        valori.sort()
        # "nearest rank": il campione in posizione ceil(95% * n)
        i = max(0, math.ceil(0.95 * len(valori)) - 1)
        return round(valori[i], 1)

    def record(self, target: str, elapsed_ms: float, success: bool) -> None:
        if target not in self._stats:
            self._stats[target] = {
                "count": 0, "ok": 0, "fail": 0,
                "sum_ms": 0.0, "min_ms": float("inf"), "max_ms": 0.0
            }
        s = self._stats[target]
        s["count"] += 1
        if success:
            s["ok"] += 1
        else:
            s["fail"] += 1
        s["sum_ms"] += elapsed_ms
        s["min_ms"] = min(s["min_ms"], elapsed_ms)
        s["max_ms"] = max(s["max_ms"], elapsed_ms)
        self._campioni.setdefault(target, deque(maxlen=self._FINESTRA)).append(elapsed_ms)

    def summary(self) -> str:
        if not self._stats:
            return "No delivery statistics yet."
        lines = ["Delivery performance summary:"]
        for tgt, s in self._stats.items():
            avg = s["sum_ms"] / s["count"] if s["count"] else 0
            lines.append(
                f"  {tgt:<18} {s['ok']:>4} ok  {s['fail']:>3} fail"
                f"  avg={avg:.0f}ms  min={s['min_ms']:.0f}ms  max={s['max_ms']:.0f}ms"
            )
        return "\n".join(lines)

# Global instance
perf = PerformanceCounter()
