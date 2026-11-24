"""
Sandbox / demo mode.

Enable with env var DEMO_MODE=1. In demo mode:
  * Every 30s a fake result is generated and dispatched to a fake in-memory target
  * Destructive endpoints (config write, service actions, users delete) are read-only
  * Dashboard shows a big banner "DEMO MODE"

Useful for:
  * Product demos at trade shows
  * Sales meetings without real hardware
  * Onboarding video recording
  * Public sandbox at demo.jerumed-nexus.ch
"""
from __future__ import annotations

import os
import random
import threading
import time
from datetime import datetime
from typing import Any, Dict


def is_demo() -> bool:
    return os.environ.get("DEMO_MODE", "").lower() in ("1", "true", "yes")


_DEVICES = ["Sysmex XN-550", "Cobas b101", "UC-1000", "Seamaty SMT-120", "LOC-200"]
_ANALYTES = [
    ("AST", "U/L", 15, 40),
    ("ALT", "U/L", 7,  40),
    ("GLU", "mmol/L", 3.9, 6.1),
    ("CHOL", "mmol/L", 0, 5.17),
    ("CREA", "umol/L", 44, 106),
    ("HGB", "g/dL", 12.0, 16.0),
    ("WBC", "10^3/uL", 4.0, 10.0),
    ("PLT", "10^3/uL", 150, 400),
]
_FIRST_NAMES = ["Anna", "Peter", "Maria", "Hans", "Lisa", "Klaus", "Sofia", "Marco"]
_LAST_NAMES  = ["Mueller", "Weber", "Bauer", "Fischer", "Meier", "Schmid", "Keller"]


def make_fake_result() -> Dict[str, Any]:
    device = random.choice(_DEVICES)
    sample_id = f"DEMO_{random.randint(1000, 9999)}"
    patient_id = f"PAT{random.randint(10, 99)}"
    obs = []
    for code, unit, lo, hi in random.sample(_ANALYTES, k=random.randint(3, 6)):
        val = round(random.uniform(lo * 0.7, hi * 1.3), 2)
        flag = "H" if val > hi else ("L" if val < lo else "")
        obs.append({
            "analyte":   code,
            "value":     str(val),
            "value_num": val,
            "flag":      flag,
            "ref_low":   lo,
            "ref_high":  hi,
            "unit":      unit,
        })
    return {
        "timestamp":    datetime.now(),
        "sample_id":    sample_id,
        "patient_id":   patient_id,
        "patient_name": f"{random.choice(_LAST_NAMES)} {random.choice(_FIRST_NAMES)}",
        "gender":       random.choice(["M", "F"]),
        "device":       device,
        "disc_name":    "DEMO_DISC",
        "lot_id":       "DEMO_LOT",
        "observations": obs,
    }


def start_demo_loop(queue, interval_sec: int = 30) -> None:
    """
    Start a background thread that pushes a fake result to `queue` every N sec.
    Call from Gateway.start() when demo mode is enabled.
    """
    if not is_demo():
        return

    def _loop():
        while True:
            try:
                r = make_fake_result()
                try:
                    queue.put_nowait(r)
                except Exception:
                    pass
            except Exception:
                pass
            time.sleep(interval_sec + random.uniform(-3, 3))

    t = threading.Thread(target=_loop, name="demo-loop", daemon=True)
    t.start()
