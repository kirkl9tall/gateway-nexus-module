"""
Time-travel wire replay — re-execute any historical frame in a sandbox
and return a step-by-step trace of what the parser + builder produce.

The wire trace lives in `logs/trace/*.bin` (append-only ring buffer per
device, written by src.common.trace). We index by timestamp + device.

Replay is READ-ONLY:
  * Never touches the LIS
  * Never updates history.db
  * Never enqueues a real dispatch

Usage:
    result = replay(device="Sysmex XQ-320", index=42)
    # result = {'raw_bytes_hex': '...', 'parsed': {...}, 'hl7_out': 'MSH|...', 'audit': {...}}
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger("loc200.wire_replay")

_TRACE_ROOT = Path("logs/trace")


def list_captures(device: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    """Return recent captured frames — (device, timestamp, size, index)."""
    if not _TRACE_ROOT.exists():
        return []
    out: list[dict[str, Any]] = []
    pattern = f"{device.replace('/', '_')}*" if device else "*"
    for f in sorted(_TRACE_ROOT.glob(f"{pattern}.bin"),
                    key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
        st = f.stat()
        out.append({
            "device":   f.stem.rsplit("_", 1)[0] if "_" in f.stem else f.stem,
            "index":    f.stem.rsplit("_", 1)[-1] if "_" in f.stem else "0",
            "size":     st.st_size,
            "ts":       st.st_mtime,
            "filename": f.name,
        })
    return out


def replay(filename: str) -> dict[str, Any]:
    """
    Read the capture file and run it through the parser + builder in sandbox.
    Never touches production state.
    """
    p = _TRACE_ROOT / filename
    if not p.exists() or ".." in filename or "/" in filename or "\\" in filename:
        return {"ok": False, "error": "invalid or missing capture",
                "code": "E1010_AUDIT_MISSING"}
    raw = p.read_bytes()
    steps: list[dict[str, Any]] = []

    # Step 1: raw bytes
    steps.append({
        "step": 1, "label": "Raw payload received",
        "bytes_hex": raw[:512].hex(),
        "byte_count": len(raw),
    })

    # Step 2: try to decode as ASCII
    try:
        text = raw.decode("ascii", errors="replace")
        steps.append({"step": 2, "label": "ASCII decode",
                      "preview": text[:512]})
    except Exception as exc:
        steps.append({"step": 2, "label": "ASCII decode FAILED",
                      "error": str(exc)})
        text = ""

    # Step 3: try to parse with each known parser until one succeeds
    parsed = None
    for parser_name, parser in _known_parsers():
        try:
            r = parser(text)
            if r and r.get("observations"):
                parsed = r
                steps.append({"step": 3, "label": f"Parsed by {parser_name}",
                              "sample_id": r.get("sample_id", ""),
                              "analytes":  len(r["observations"])})
                break
        except Exception:
            continue
    else:
        steps.append({"step": 3, "label": "No parser produced observations"})

    # Step 4: HL7 build (if parsed)
    hl7_out = ""
    if parsed:
        try:
            from src.hl7.builder import build_hl7_message
            hl7_out = build_hl7_message(parsed)
            steps.append({"step": 4, "label": "HL7 v2 built",
                          "size": len(hl7_out),
                          "preview": hl7_out[:500].replace("\r", "\n")})
        except Exception as exc:
            steps.append({"step": 4, "label": "HL7 build FAILED",
                          "error": str(exc)})

    # Step 5: conversion audit
    audit = None
    if parsed:
        try:
            from src.common.conversion_audit import build_audit_for
            audit_json = build_audit_for(
                device=parsed.get("device", "?"),
                sample_raw=parsed.get("sample_id", ""),
                sample_sent=parsed.get("sample_id", ""),
                patient_raw=parsed.get("patient_id", ""),
                patient_sent=parsed.get("patient_id", ""),
                raw_payload=raw,
                observations=parsed.get("observations") or [],
            )
            audit = json.loads(audit_json)
            steps.append({"step": 5, "label": "Conversion audit built",
                          "warnings": audit.get("warnings", []),
                          "changes":  len(audit.get("changes", []))})
        except Exception as exc:
            steps.append({"step": 5, "label": "Audit failed", "error": str(exc)})

    return {
        "ok":       True,
        "filename": filename,
        "steps":    steps,
        "parsed":   parsed,
        "hl7_out":  hl7_out,
        "audit":    audit,
    }


def _known_parsers():
    """Yield (name, callable) tuples in order of preference."""
    try:
        from src.adapters.sysmex_reader import _parse_astm
        yield ("sysmex_astm", lambda t: _parse_astm(t, "replay"))
    except Exception:
        pass
    try:
        from src.adapters.reflotron_reader import _parse_line
        def _reflo(t):
            recs = []
            for line in t.splitlines():
                r = _parse_line(line, "replay")
                if r:
                    recs.append({
                        "analyte":   r["code"],
                        "value":     r["value"],
                        "value_num": r["value_num"],
                        "unit":      r["unit"],
                        "flag":      r["flag"],
                    })
            if not recs:
                return None
            return {"sample_id": "REPLAY", "patient_id": "REPLAY",
                    "observations": recs, "device": "Reflotron"}
        yield ("reflotron_serial", _reflo)
    except Exception:
        pass
