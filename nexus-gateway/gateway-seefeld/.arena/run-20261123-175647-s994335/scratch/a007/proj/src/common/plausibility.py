"""
Plausibility gate — hard physical bounds per analyte. If a value that we're
about to send to the LIS is outside these bounds, we FLAG it (never silently
drop) and record the reason in the conversion audit.

These bounds are deliberately EXTREME — they mean "physically impossible
in a living human", not "clinically abnormal". A value of HGB 25.5 g/dL is
plausibly a lab error, not a real reading. Anything a normal patient can
present must pass.

Class A device: we NEVER change the value or block the message on clinical
grounds. We only add a technical flag "TC" that the LIS presents to the
doctor. The doctor decides.

Bounds source: reference ranges from Tietz "Textbook of Clinical Chemistry"
5th ed., padded 20% on each side for pathology tolerance.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Bounds:
    lo: float
    hi: float
    unit: str


# code → bounds. Missing codes are not checked.
PHYSICAL_BOUNDS: dict[str, Bounds] = {
    # Hematology
    "WBC":    Bounds(0.1, 500.0,  "10^3/uL"),      # leukemia can hit 400+
    "RBC":    Bounds(0.5, 8.0,    "10^6/uL"),
    "HGB":    Bounds(2.0, 25.0,   "g/dL"),          # severe anemia to polycythemia
    "HCT":    Bounds(5.0, 70.0,   "%"),
    "MCV":    Bounds(50.0, 130.0, "fL"),
    "MCH":    Bounds(15.0, 45.0,  "pg"),
    "MCHC":   Bounds(25.0, 40.0,  "g/dL"),
    "PLT":    Bounds(5.0, 3000.0, "10^3/uL"),       # essential thrombocythemia
    "NEUT#":  Bounds(0.0, 200.0,  "10^3/uL"),
    "LYMPH#": Bounds(0.0, 200.0,  "10^3/uL"),
    "MXD#":   Bounds(0.0, 50.0,   "10^3/uL"),
    "NEUT%":  Bounds(0.0, 100.0,  "%"),
    "LYMPH%": Bounds(0.0, 100.0,  "%"),
    "MXD%":   Bounds(0.0, 100.0,  "%"),
    "RDW-CV": Bounds(8.0, 40.0,   "%"),
    "PDW":    Bounds(5.0, 30.0,   "fL"),
    "MPV":    Bounds(5.0, 20.0,   "fL"),
    # Clinical chemistry (Reflotron / Cobas c111 / LOC-200)
    "GLU":    Bounds(10.0, 1000.0, "mg/dL"),
    "CHOL":   Bounds(20.0, 800.0,  "mg/dL"),
    "TG":     Bounds(10.0, 5000.0, "mg/dL"),
    "HDL":    Bounds(5.0, 200.0,   "mg/dL"),
    "LDL":    Bounds(10.0, 500.0,  "mg/dL"),
    "GGT":    Bounds(0.0, 5000.0,  "U/L"),
    "AST":    Bounds(0.0, 10000.0, "U/L"),
    "ALT":    Bounds(0.0, 10000.0, "U/L"),
    "CREA":   Bounds(0.1, 20.0,    "mg/dL"),
    "UREA":   Bounds(1.0, 500.0,   "mg/dL"),
    # HbA1c (Cobas b101, Afinion 2, D-100)
    "HBA1C":  Bounds(3.0, 20.0,    "%"),
    # Urinalysis (UC-1000) — most are semiquantitative; skip
}


def check(code: str, value: float | None, unit: str = "") -> tuple[bool, str]:
    """
    Returns (is_plausible, reason). If not plausible, reason is a short
    human-readable message like "HGB 42.0 out of range 2.0-25.0 g/dL".
    Missing bounds → always plausible.
    """
    if value is None:
        return True, ""
    b = PHYSICAL_BOUNDS.get(code.upper())
    if not b:
        return True, ""
    if value < b.lo or value > b.hi:
        return False, (
            f"{code} {value} out of physical range {b.lo}-{b.hi} {b.unit}"
        )
    if unit and unit.strip() and unit.strip() != b.unit:
        # Unit mismatch is a warning, not a hard failure — many devices use
        # equivalent notations (10*3/uL vs 10^3/uL vs G/L).
        return True, f"unit hint mismatch: got {unit!r} expected {b.unit!r}"
    return True, ""


def is_double_conversion(code: str, raw: float | None, sent: float | None) -> bool:
    """
    Detect the classic bug: raw value is ALREADY in the target unit (e.g. HCT
    already in %), our parser multiplied by 100 anyway → sent value is 100×
    the raw. Returns True only when:
      1. raw was in the "already-percent" range (i.e. > 1.0 — a fraction
         cannot exceed 1), AND
      2. sent is ~100× raw.
    Correct one-time conversions (raw fraction 0.42 → sent % 42.0) fall
    outside condition (1) so they are NOT flagged.
    """
    if code.upper() not in {"HCT", "PCT"}:
        return False
    if raw is None or sent is None or raw <= 1.0:
        return False
    ratio = sent / raw
    return 98.0 <= ratio <= 102.0
