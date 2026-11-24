"""
Shadow mode — process every frame end-to-end but DO NOT send to the LIS.

Activated by setting in gateway.yaml:
    shadow_mode:
      enabled: true
      log_dir: logs/shadow/       # each would-be dispatch dropped here as JSON
      compare_with: /mnt/lis/hl7  # optional: incumbent middleware output dir

Used for zero-risk migration from a competing gateway. The clinic keeps
the incumbent running; JerumedNexus receives the same frames in parallel;
after N days of comparison, they cut over with one flag flip.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

log = logging.getLogger("loc200.shadow_mode")


@dataclass
class ShadowConfig:
    enabled:      bool = False
    log_dir:      Path = Path("logs/shadow")
    compare_with: Path | None = None


_CFG: ShadowConfig = ShadowConfig()


def configure(cfg_dict: dict[str, Any] | None) -> None:
    global _CFG
    if not cfg_dict:
        _CFG = ShadowConfig(enabled=False)
        return
    _CFG = ShadowConfig(
        enabled=bool(cfg_dict.get("enabled", False)),
        log_dir=Path(cfg_dict.get("log_dir", "logs/shadow")),
        compare_with=Path(cfg_dict["compare_with"]) if cfg_dict.get("compare_with") else None,
    )
    if _CFG.enabled:
        _CFG.log_dir.mkdir(parents=True, exist_ok=True)
        log.warning("SHADOW MODE ENABLED — no HL7 will be sent to LIS. "
                    "Dropping would-be messages to %s", _CFG.log_dir)


def is_enabled() -> bool:
    return _CFG.enabled


def record(sample_id: str, target_name: str, hl7_body: str) -> None:
    """Drop a would-be dispatch as JSON in the shadow log."""
    if not _CFG.enabled:
        return
    ts = time.time()
    fname = f"{int(ts * 1000)}_{target_name}_{sample_id}.json"
    p = _CFG.log_dir / fname
    p.write_text(json.dumps({
        "ts":          ts,
        "target":      target_name,
        "sample_id":   sample_id,
        "hl7_body":    hl7_body,
        "shadow":      True,
    }, ensure_ascii=False, indent=2), encoding="utf-8")


def compare_recent(hours: int = 24) -> dict[str, Any]:
    """
    Cross-check shadow drops vs incumbent output directory.
    Returns match/mismatch/only-shadow/only-incumbent counts.
    """
    if not _CFG.compare_with or not _CFG.compare_with.exists():
        return {"error": "no compare_with path"}
    cutoff = time.time() - hours * 3600
    shadow = {p.stem.split("_")[-1]: p for p in _CFG.log_dir.glob("*.json")
              if p.stat().st_mtime >= cutoff}
    incumbent = {p.stem: p for p in _CFG.compare_with.glob("*.hl7")
                 if p.stat().st_mtime >= cutoff}
    matches = mismatches = 0
    for sid, _sp in shadow.items():
        if sid in incumbent:
            matches += 1  # crude: could also byte-compare
        else:
            mismatches += 1
    return {
        "shadow_count":    len(shadow),
        "incumbent_count": len(incumbent),
        "matched":         matches,
        "only_in_shadow":  mismatches,
        "only_in_incumbent": len(incumbent) - matches,
    }
