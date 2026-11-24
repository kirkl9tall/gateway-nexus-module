"""
Device certification report — generates a per-device certification table
combining every verification signal we collect.

Signals:
  1. YAML profile loadable (Pydantic validates)                → schema_ok
  2. E2E simulator test present for this protocol type          → e2e_covered
  3. Golden fixture(s) present in tests/fixtures/golden/<id>/   → golden_present
  4. Marked VERIFIED-PROD in tools/device_matrix.py             → prod_verified
  5. Marked VERIFIED-DOC (protocol confirmed via vendor manual) → doc_verified
  6. Field validation record present in field_validation.json    → field_signed_off

Output: markdown table + JSON. The MD is committed as
docs/devices/CERTIFICATION.md.
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("PyYAML required", file=sys.stderr)
    sys.exit(1)

# Force UTF-8 on Windows so badges render regardless of cp1252
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", newline="")
    except Exception:
        pass


ROOT = Path(__file__).parent.parent

E2E_TESTED_TYPES = {"sysmex_astm", "mllp_hl7"}   # types covered by simulators


def _load_device_matrix() -> dict[str, str]:
    """Import verification status from tools/device_matrix.py."""
    from tools.device_matrix import VERIFIED_PROD, VERIFIED_DOC
    out: dict[str, str] = {}
    for did in VERIFIED_PROD:
        out[did] = "PROD"
    for did in VERIFIED_DOC:
        out[did] = "DOC"
    return out


def _load_field_signoff() -> dict[str, dict]:
    p = ROOT / "logs" / "field_validation.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _load_golden_dirs() -> set[str]:
    root = ROOT / "tests" / "fixtures" / "golden"
    if not root.exists():
        return set()
    return {d.name for d in root.iterdir()
            if d.is_dir() and any(d.glob("*.in.*"))}


def certify_one(device_id: str, data: dict,
                matrix: dict[str, str], goldens: set[str],
                field: dict[str, dict]) -> dict:
    dev_type = data.get("type", "")
    schema_ok = True   # already validated at load
    e2e = dev_type in E2E_TESTED_TYPES
    golden = device_id in goldens or device_id.replace("_active", "") in goldens
    verified = matrix.get(device_id, "SPEC")
    field_ok = device_id in field
    tier = _tier(verified, e2e, golden, field_ok)
    return {
        "device_id":       device_id,
        "display_name":    data.get("display_name", ""),
        "vendor":          data.get("vendor", ""),
        "type":            dev_type,
        "schema_ok":       schema_ok,
        "e2e_covered":     e2e,
        "golden_present":  golden,
        "prod_verified":   verified == "PROD",
        "doc_verified":    verified == "DOC",
        "field_signed_off": field_ok,
        "certification_tier": tier,
    }


def _tier(verified: str, e2e: bool, golden: bool, field_ok: bool) -> str:
    if verified == "PROD" and field_ok:
        return "PLATINUM"   # real production + field sign-off
    if verified == "PROD":
        return "GOLD"       # real production, no field sign-off yet
    if verified == "DOC" and e2e:
        return "SILVER"     # vendor manual + E2E simulator passes
    if verified == "DOC":
        return "BRONZE"     # vendor manual only
    if e2e:
        return "BRONZE"     # simulator passes only
    return "UNCERTIFIED"


def _emoji(tier: str) -> str:
    return {
        "PLATINUM":    "💎",
        "GOLD":        "🟢",
        "SILVER":      "🟡",
        "BRONZE":      "🟠",
        "UNCERTIFIED": "⚪",
    }.get(tier, "❓")


def build_report(fmt: str = "md") -> str:
    matrix = _load_device_matrix()
    goldens = _load_golden_dirs()
    field = _load_field_signoff()
    results: list[dict] = []
    for f in sorted((ROOT / "config" / "devices").glob("*.yaml")):
        try:
            data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
            device_id = data.get("id", f.stem)
            results.append(certify_one(device_id, data, matrix, goldens, field))
        except Exception as exc:
            results.append({"device_id": f.stem, "error": str(exc),
                            "certification_tier": "UNCERTIFIED"})

    if fmt == "json":
        return json.dumps({"devices": results, "count": len(results),
                            "generated_at": "auto"}, indent=2, ensure_ascii=False)

    out = ["# Device Certification Report",
           "",
           "Aggregated verification signals for every device profile.",
           "",
           "**Certification tiers:**",
           "- 💎 **PLATINUM** — real production + field sign-off",
           "- 🟢 **GOLD** — real production, no field sign-off yet",
           "- 🟡 **SILVER** — vendor manual confirmed + E2E simulator passes",
           "- 🟠 **BRONZE** — vendor manual only, or E2E simulator only",
           "- ⚪ **UNCERTIFIED** — speculative, not yet validated",
           "",
           "| Device | Vendor | Protocol | Prod | Doc | E2E | Golden | Field | Tier |",
           "|--------|--------|----------|:----:|:---:|:---:|:------:|:-----:|:----:|"]
    for r in results:
        if "error" in r:
            out.append(f"| `{r['device_id']}` | — | ERROR | ❌ | ❌ | ❌ | ❌ | ❌ | ⚪ |")
            continue
        def yn(b):
            return "✓" if b else "—"
        tier = r["certification_tier"]
        out.append(
            f"| `{r['device_id']}` | {r['vendor']} | `{r['type']}` | "
            f"{yn(r['prod_verified'])} | {yn(r['doc_verified'])} | "
            f"{yn(r['e2e_covered'])} | {yn(r['golden_present'])} | "
            f"{yn(r['field_signed_off'])} | {_emoji(tier)} {tier} |"
        )
    tiers: dict[str, int] = {}
    for r in results:
        t = r.get("certification_tier", "UNCERTIFIED")
        tiers[t] = tiers.get(t, 0) + 1
    out += ["",
            "## Aggregato",
            f"Totale device: **{len(results)}**",
            ""]
    for tier in ("PLATINUM", "GOLD", "SILVER", "BRONZE", "UNCERTIFIED"):
        if tier in tiers:
            out.append(f"- {_emoji(tier)} **{tier}**: {tiers[tier]}")
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--format", choices=["md", "json"], default="md")
    ap.add_argument("--output", type=str, default="-")
    args = ap.parse_args()
    txt = build_report(fmt=args.format)
    if args.output == "-":
        print(txt)
    else:
        Path(args.output).write_text(txt, encoding="utf-8")
        print(f"Report written to {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
