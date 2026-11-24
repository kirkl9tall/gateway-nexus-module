#!/usr/bin/env python3
"""
tools/discover.py -- standalone plug-and-play discovery CLI.

Usage:
    python -m tools.discover                                # USB scan
    python -m tools.discover --tcp 192.168.1.0/24 --port 5000,6000
    python -m tools.discover --json                         # machine-readable output
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Make top-level packages importable when run directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.discovery.service import DiscoveryService


def _parse_ports(s: str) -> list[int]:
    return [int(x.strip()) for x in s.split(",") if x.strip()]


async def main() -> int:
    ap = argparse.ArgumentParser(description="JerumedNexus Gateway device discovery")
    ap.add_argument("--tcp", action="append", default=[],
                    help="CIDR or IP to scan (can be repeated)")
    ap.add_argument("--port", default="",
                    help="Comma-separated TCP ports to probe")
    ap.add_argument("--json", action="store_true", help="JSON output")
    ap.add_argument("--state-file", default="logs/discovered.json",
                    help="Where to persist state")
    args = ap.parse_args()

    svc = DiscoveryService(state_file=Path(args.state_file))
    ports = _parse_ports(args.port) if args.port else None
    tcp_range = args.tcp if args.tcp else None
    snap = await svc.scan_once(tcp_range=tcp_range, tcp_ports=ports)

    if args.json:
        print(json.dumps(snap, indent=2))
        return 0

    if not snap:
        print("No devices detected.")
        return 0

    print(f"{'Source':<6}  {'Location':<28}  {'Conf':<5}  {'Protocol':<12}  Display name")
    print("-" * 90)
    for d in snap:
        print(f"{d['source']:<6}  {d['location']:<28}  {d['confidence']:<5}"
              f"  {(d.get('protocol') or '—'):<12}  {d.get('display_name') or ''}")
    print()
    pending = [d for d in snap if not d.get("activated") and d["confidence"] >= 40]
    if pending:
        print(f"{len(pending)} device(s) awaiting activation.")
        print("Activate via the Web UI (/analyzers) or:")
        print("  curl -X POST http://localhost:8080/api/devices/activate \\")
        print("       -H 'Authorization: Bearer <session>' \\")
        print("       -d '{\"key\":\"<source>:<location>\",\"device_type\":\"<type>\"}'")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
