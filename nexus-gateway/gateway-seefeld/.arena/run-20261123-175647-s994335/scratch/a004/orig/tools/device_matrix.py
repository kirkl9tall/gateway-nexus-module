"""
tools/device_matrix.py — Print a compatibility matrix for all devices
in config/devices/, classified as VERIFIED-PROD / VERIFIED-DOC /
SPECULATIVE based on the metadata in docs/devices/RESEARCH.md.

Usage:
    python -m tools.device_matrix               # print table
    python -m tools.device_matrix --format=md   # markdown for docs
    python -m tools.device_matrix --format=json # machine-readable
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

# Force UTF-8 on Windows so the badges render regardless of code page.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", newline="")
    except Exception:
        pass

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML not installed", file=sys.stderr)
    sys.exit(1)


# Compiled from docs/devices/RESEARCH.md — keep in sync.
VERIFIED_PROD = {
    "sysmex_xq320", "cobas_b101", "uc1000", "loc200",
    "seamaty_sd1", "seamaty_sd3", "seamaty_smt120",
}
VERIFIED_DOC = {
    "afinion_2", "roche_cobas_c111", "horiba_microsemi",
    "biorad_d100", "roche_reflotron_plus", "mindray_bc5000",
    "pixcell_hemoscreen", "isens_caresens", "radiometer_abl80",
    "roche_cobas_h232", "sysmex_xn550", "sysmex_xn1000",
    "sysmex_xp300",
    # New — added after web research batch (Aug 2026):
    "abbott_i_stat", "beckman_au480", "nova_statstrip",
    "siemens_dca_vantage", "hemocue_hb_801", "hemocue_wbc_diff",
}


def _classify(device_id: str) -> str:
    if device_id in VERIFIED_PROD:
        return "VERIFIED-PROD"
    if device_id in VERIFIED_DOC:
        return "VERIFIED-DOC"
    return "SPECULATIVE"


def _load_all() -> list[dict]:
    root = Path(__file__).parent.parent / "config" / "devices"
    if not root.exists():
        return []
    out = []
    for f in sorted(root.glob("*.yaml")):
        try:
            data = yaml.safe_load(f.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                continue
            data["_file"] = f.name
            data["_status"] = _classify(data.get("id", f.stem))
            out.append(data)
        except Exception as exc:
            print(f"[WARN] {f.name}: {exc}", file=sys.stderr)
    return out


def _print_table(devices: list[dict]) -> None:
    fmt = "{:<26} {:<26} {:<20} {:<16}"
    print(fmt.format("ID", "Display", "Type", "Status"))
    print("-" * 90)
    for d in devices:
        print(fmt.format(
            (d.get("id") or "")[:26],
            (d.get("display_name") or "")[:26],
            (d.get("type") or "")[:20],
            d["_status"],
        ))
    counts = {}
    for d in devices:
        counts[d["_status"]] = counts.get(d["_status"], 0) + 1
    print("-" * 90)
    print(f"Totale: {len(devices)}   " +
          "   ".join(f"{k}={v}" for k, v in sorted(counts.items())))


def _print_markdown(devices: list[dict]) -> None:
    print("# Device compatibility matrix\n")
    print("| ID | Display name | Vendor | Type | Status |")
    print("|----|--------------|--------|------|--------|")
    for d in devices:
        badge = {
            "VERIFIED-PROD": "🟢 VERIFIED-PROD",
            "VERIFIED-DOC":  "🟡 VERIFIED-DOC",
            "SPECULATIVE":   "⚪ SPECULATIVE",
        }[d["_status"]]
        print(f"| `{d.get('id','')}` | {d.get('display_name','')} | "
              f"{d.get('vendor','')} | `{d.get('type','')}` | {badge} |")
    print("\n**Legend:**")
    print("- 🟢 **VERIFIED-PROD** — funzionante in cliniche reali DACH.")
    print("- 🟡 **VERIFIED-DOC** — protocollo confermato da vendor manual / middleware open-source.")
    print("- ⚪ **SPECULATIVE** — profilo derivato da materiale marketing; validare su hardware reale prima del deploy.")


def _print_json(devices: list[dict]) -> None:
    payload = [{
        "id":           d.get("id"),
        "display_name": d.get("display_name"),
        "vendor":       d.get("vendor"),
        "model":        d.get("model"),
        "type":         d.get("type"),
        "status":       d["_status"],
        "file":         d["_file"],
    } for d in devices]
    print(json.dumps({"devices": payload, "count": len(payload)}, indent=2))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--format", choices=["table", "md", "json"], default="table")
    args = ap.parse_args()

    devices = _load_all()
    if not devices:
        print("No devices found under config/devices/", file=sys.stderr)
        return 1
    if args.format == "md":
        _print_markdown(devices)
    elif args.format == "json":
        _print_json(devices)
    else:
        _print_table(devices)
    return 0


if __name__ == "__main__":
    sys.exit(main())
