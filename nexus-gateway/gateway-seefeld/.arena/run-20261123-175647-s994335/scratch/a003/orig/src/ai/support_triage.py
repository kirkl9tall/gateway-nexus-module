"""
Support bundle triage — reads a support bundle produced by
`jerumednexus support-bundle`, extracts the last 100 log lines +
breakers + health, and returns a structured triage report.

Two backends:
  1. LLM-based (Anthropic/OpenAI): sends redacted log excerpt to a
     small model and asks for cause + severity + runbook.
  2. Rules-based (default, no external deps): pattern-matches known
     error signatures against a rulebook.

Both go through PII redaction FIRST — patient IDs and sample IDs are
hashed before leaving the Pi.
"""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

log = logging.getLogger("loc200.support_triage")


# ── PII redaction ──────────────────────────────────────────────────────────

_PII_PATTERNS = [
    (re.compile(r"\b(PAT|MRN|PID)[- ]?\d{3,}\b", re.I), r"<REDACTED-PATIENT-ID>"),
    (re.compile(r"\bSN\d{4,}[A-Z]?\b"),               r"<REDACTED-SAMPLE-ID>"),
    (re.compile(r"\b\d{2}\.\d{2}\.(19|20)\d{2}\b"),   r"<REDACTED-DOB>"),
]


def redact(text: str) -> str:
    for pat, replacement in _PII_PATTERNS:
        text = pat.sub(replacement, text)
    return text


# ── Rules-based triage ──────────────────────────────────────────────────────

_RULES: list[tuple[re.Pattern, str, str, str]] = [
    (re.compile(r"E1381-95.*No data received", re.I),
     "Sysmex IPU is in E1381-95 mode but gateway expects ENQ",
     "S2",
     "docs/runbooks/sysmex-xq320-tcp-timeout.md"),
    (re.compile(r"NAK on frame|checksum mismatch", re.I),
     "Serial line noise or wrong baud rate on device",
     "S2",
     "docs/runbooks/sysmex-xq320-tcp-timeout.md"),
    (re.compile(r"breaker open.*(?:tomedo|vitomed|winmed|curamed)", re.I),
     "LIS unreachable — network cable or LIS service down",
     "S1",
     "docs/runbooks/lis-unreachable.md"),
    (re.compile(r"DLQ backlog \d+", re.I),
     "Dead-letter queue growing — retry after LIS recovers",
     "S2",
     "docs/runbooks/dlq-growth.md"),
    (re.compile(r"disk.*full|no space left", re.I),
     "Pi SD card full — logrotate + retention purge",
     "S1",
     "docs/runbooks/disk-full.md"),
    (re.compile(r"MSA\|AE", re.I),
     "LIS returned error ACK — check MSH-4 or data format",
     "S2",
     "docs/runbooks/msa-ae.md"),
]


def triage_rules(logs: str) -> dict[str, Any]:
    """Return the highest-severity match, or a generic 'unknown' result."""
    redacted = redact(logs)
    matches: list[dict[str, Any]] = []
    for pat, cause, severity, runbook in _RULES:
        m = pat.search(redacted)
        if m:
            matches.append({"cause": cause, "severity": severity,
                             "runbook": runbook, "matched_line": m.group(0)[:200]})
    if not matches:
        return {"cause": "No known signature found — manual review needed",
                "severity": "S3", "runbook": "docs/SUPPORT.md",
                "matches": []}
    matches.sort(key=lambda m: m["severity"])
    top = matches[0]
    top["matches"] = matches
    return top


# ── Support bundle triage ──────────────────────────────────────────────────

def triage_bundle(bundle_path: Path) -> dict[str, Any]:
    """Read a support bundle directory and produce a triage report."""
    if not bundle_path.exists():
        return {"error": f"bundle not found: {bundle_path}",
                "code": "E1010_AUDIT_MISSING"}
    result: dict[str, Any] = {"redacted": True}
    logs_file = bundle_path / "gateway.log"
    if logs_file.exists():
        text = logs_file.read_text(encoding="utf-8", errors="replace")
        result["log_lines"] = text.count("\n")
        result["triage"] = triage_rules(text[-50_000:])
    else:
        result["triage"] = {"cause": "no gateway.log in bundle",
                             "severity": "S3", "runbook": ""}
    return result


# ── LLM backend (optional) ─────────────────────────────────────────────────

def triage_llm(logs: str, model: str = "claude-haiku-4-5-20251001") -> dict[str, Any]:
    """
    Send REDACTED logs to Claude Haiku and get a triage report.
    Requires ANTHROPIC_API_KEY env var. Falls back to rules-based on error.
    """
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return {"error": "ANTHROPIC_API_KEY not set — using rules fallback",
                **triage_rules(logs)}
    try:
        import anthropic
    except ImportError:
        return {"error": "anthropic package not installed",
                **triage_rules(logs)}
    redacted = redact(logs[-20_000:])
    try:
        client = anthropic.Anthropic()
        msg = client.messages.create(
            model=model, max_tokens=512,
            system=("You are a JerumedNexus support engineer. Read the "
                     "redacted gateway log excerpt and produce a JSON with "
                     "keys: cause, severity (S1|S2|S3|S4), runbook (path)."),
            messages=[{"role": "user", "content": redacted}],
        )
        text = msg.content[0].text if msg.content else "{}"
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = {"cause": text[:200], "severity": "S3", "runbook": ""}
        parsed["model"] = model
        return parsed
    except Exception as exc:
        return {"error": str(exc), **triage_rules(logs)}
