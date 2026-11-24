"""
Per-target HL7 rewriting rules.

Configuration file: config/rewrites/<target-name>.yaml

Example:
    - name: "strip Dr. prefix from patient name"
      apply_to: [PID]
      field: 5              # 1-based PID-5
      match: "^Dr\\. "
      replace: ""

    - name: "force sending_facility for Vitomed"
      apply_to: [MSH]
      field: 4
      set: "PRAXIS_XYZ"

    - name: "drop unit qualifier for curaMED"
      apply_to: [OBX]
      component: [6, 1]     # OBX-6, component 1
      match: "^(.*?)\\s*/.*$"
      replace: "\\1"

Rules run in order. Each rule can:
  * `set: <value>`  -> overwrite the field/component
  * `match: <regex> + replace: <text>` -> regex substitution
  * `remove: true`  -> blank the field/component
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

log = logging.getLogger("loc200.rewrites")

_RULES_DIR = Path("config/rewrites")


def _load(target_name: str) -> List[Dict[str, Any]]:
    path = _RULES_DIR / f"{target_name}.yaml"
    if not path.exists():
        return []
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    except Exception as exc:
        log.warning("rewrites: cannot read %s: %s", path, exc)
        return []
    if not isinstance(data, list):
        log.warning("rewrites: %s must be a YAML list of rule objects", path)
        return []
    return data


def apply_rewrites(hl7_text: str, target_name: str) -> str:
    """Apply the per-target rewriting rules to an HL7 message text (\\r-separated)."""
    rules = _load(target_name)
    if not rules:
        return hl7_text

    segments = hl7_text.split("\r")
    for rule in rules:
        try:
            _apply_rule(segments, rule, target_name)
        except Exception as exc:
            log.warning("rewrites[%s]: rule %r failed: %s",
                        target_name, rule.get("name", "?"), exc)
    return "\r".join(segments)


def _apply_rule(segments: List[str], rule: Dict[str, Any], target: str) -> None:
    apply_to = rule.get("apply_to") or []
    if isinstance(apply_to, str):
        apply_to = [apply_to]
    field_idx  = rule.get("field")
    comp_idx   = rule.get("component")   # int or [field, comp]
    set_value  = rule.get("set")
    match_re   = rule.get("match")
    replace    = rule.get("replace", "")
    remove     = bool(rule.get("remove", False))

    # component can be an integer, a [field, comp] pair, or None
    if isinstance(comp_idx, int) and field_idx is None:
        log.warning("rewrites: rule with component=%d needs a field:", comp_idx)
        return

    for i, seg in enumerate(segments):
        seg_name = seg.split("|", 1)[0]
        if seg_name not in apply_to:
            continue
        parts = seg.split("|")
        if field_idx is None:
            continue
        fi = int(field_idx)
        if fi >= len(parts):
            continue

        value = parts[fi]

        # Optional component split by "^"
        if comp_idx is not None:
            comps = value.split("^")
            ci = int(comp_idx) - 1
            if ci >= len(comps):
                comps += [""] * (ci - len(comps) + 1)
            sub = comps[ci]
            comps[ci] = _transform(sub, set_value, match_re, replace, remove)
            value = "^".join(comps)
        else:
            value = _transform(value, set_value, match_re, replace, remove)

        parts[fi] = value
        segments[i] = "|".join(parts)


def _transform(value: str, set_value: Optional[str],
               match_re: Optional[str], replace: str, remove: bool) -> str:
    if remove:
        return ""
    if set_value is not None:
        return str(set_value)
    if match_re:
        try:
            return re.sub(match_re, replace, value)
        except re.error as exc:
            log.warning("rewrites: bad regex %r: %s", match_re, exc)
            return value
    return value


def list_targets_with_rules() -> List[str]:
    if not _RULES_DIR.exists():
        return []
    return sorted(p.stem for p in _RULES_DIR.glob("*.yaml"))
