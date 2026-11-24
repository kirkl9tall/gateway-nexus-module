"""
Fuzzy device recognition from HL7 MSH-3 (Sending Application).

When a LIS sends us "Sysmex_XQ-320" or "SYSMEX XQ 320" or "SysmexXQ320",
we map to our canonical device_id "sysmex_xq320".
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

import yaml

_KNOWN_CACHE: dict[str, str] | None = None


def _normalize(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "", s.lower())
    return s


def _load_known() -> dict[str, str]:
    global _KNOWN_CACHE
    if _KNOWN_CACHE is not None:
        return _KNOWN_CACHE
    out: dict[str, str] = {}
    root = Path("config/devices")
    if root.exists():
        for f in root.glob("*.yaml"):
            try:
                data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
                dev_id = data.get("id")
                if not dev_id:
                    continue
                # Register: id itself, display_name, model, vendor+model
                for cand in (dev_id, data.get("display_name", ""),
                              data.get("model", ""),
                              f"{data.get('vendor', '')}{data.get('model', '')}"):
                    if cand:
                        out[_normalize(cand)] = dev_id
            except Exception:
                continue
    _KNOWN_CACHE = out
    return out


def recognize(raw: str, min_similarity: float = 0.75) -> Optional[str]:
    """Return canonical device_id or None if no confident match."""
    if not raw:
        return None
    normalized = _normalize(raw)
    known = _load_known()
    # Exact hit first
    if normalized in known:
        return known[normalized]
    # Fuzzy fallback
    best_id, best_score = None, 0.0
    for norm_key, dev_id in known.items():
        score = SequenceMatcher(None, normalized, norm_key).ratio()
        if score > best_score:
            best_score, best_id = score, dev_id
    return best_id if best_score >= min_similarity else None
