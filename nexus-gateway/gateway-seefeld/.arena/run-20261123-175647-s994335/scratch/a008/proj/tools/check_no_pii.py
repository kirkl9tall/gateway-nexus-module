"""Pre-commit hook that blocks obvious clear-text PII patterns."""
from __future__ import annotations

import re
import sys
from pathlib import Path

_PATTERNS = [
    (re.compile(r"\b(?:PAT|MRN|PID)[- ]?\d{4,}\b"), "patient/medical identifier"),
    (re.compile(r'\b(?:19|20)\d{2}[-/]\d{2}[-/]\d{2}\s+(?:F|M)\s+[A-Z][a-zA-Z]+'),
     "DOB + gender + name triple"),
]

# Files where fixture-style examples are allowed.
_ALLOW = ("tests/fixtures/", "docs/devices/RESEARCH.md", "docs/adr/",
          "CHANGELOG.md", "tools/check_no_pii.py")


def main(argv: list[str]) -> int:
    bad = []
    for arg in argv[1:]:
        p = Path(arg)
        if any(a in arg.replace("\\", "/") for a in _ALLOW):
            continue
        if not p.exists() or p.suffix not in {".py", ".md", ".yaml", ".yml"}:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for rx, label in _PATTERNS:
            for m in rx.finditer(text):
                bad.append((arg, m.start(), label, m.group(0)))
    if bad:
        print("PII check failed:", file=sys.stderr)
        for f, _off, label, hit in bad:
            print(f"  {f}: {label!r} → {hit!r}", file=sys.stderr)
        print("Replace with hashed IDs or move to tests/fixtures/.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
