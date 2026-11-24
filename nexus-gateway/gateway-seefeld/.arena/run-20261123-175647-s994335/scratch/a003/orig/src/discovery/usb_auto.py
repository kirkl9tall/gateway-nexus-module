"""
USB auto-discovery — detects known analyzer vendors when a USB serial cable
is plugged in and proposes the matching device profile via the Web UI.

Vendor IDs come from /sys/bus/usb/devices/*/idVendor on Linux. We match
against a curated map, then look at the product string ('SYSMEX', 'COBAS',
'Menarini' etc.) to narrow the model. If we recognize a model that is
already in the catalog (config/devices/*.yaml), we push a suggestion to
the Web UI which pops up a "Do you want to enable this?" toast.

Zero-config target: plug a cable → 10 seconds later a suggestion appears.
"""
from __future__ import annotations

import json
import logging
import subprocess
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable

log = logging.getLogger("loc200.usb_auto")

# Vendor ID → (vendor name, default protocol type, port hint list)
VENDOR_MAP: dict[str, tuple[str, str, list[str]]] = {
    "1a86": ("QinHeng / Menarini / generic CH340 UART", "uc1000_serial",
             ["UC-1000", "Menarini"]),
    "0403": ("FTDI (used by Sysmex, Roche cobas b101 dock, LOC-200)",
             "sysmex_astm", ["Sysmex", "Cobas", "LOC-200"]),
    "10c4": ("Silicon Labs CP210x (Reflotron, HemoCue, Afinion)",
             "reflotron_serial", ["Reflotron", "HemoCue", "Afinion"]),
    "067b": ("Prolific PL2303 (older analyzers)", "sysmex_astm", ["Sysmex XP"]),
    "1546": ("u-blox (some POCT dockers)", "cobas_poct", ["POCT"]),
}


@dataclass
class UsbDevice:
    tty_path:      str        # /dev/ttyUSB0 or /dev/ttyACM0
    vendor_id:     str
    product_id:    str
    vendor_name:   str
    product_name:  str
    suggested_type: str       # DeviceType candidate
    model_hints:   list[str]


def _read_sysfs(p: Path) -> str:
    try:
        return p.read_text().strip()
    except Exception:
        return ""


def scan_linux() -> list[UsbDevice]:
    """Return every USB-serial-like device currently plugged in."""
    out: list[UsbDevice] = []
    # Every tty in /sys/class/tty that has ../device/../idVendor
    tty_root = Path("/sys/class/tty")
    if not tty_root.exists():
        return out
    for tty in sorted(tty_root.glob("tty*")):
        dev = tty / "device"
        if not dev.exists():
            continue
        # Walk up the parent chain to find idVendor
        cur = dev.resolve()
        vid = pid = ""
        for _ in range(6):
            if (cur / "idVendor").exists():
                vid = _read_sysfs(cur / "idVendor").lower()
                pid = _read_sysfs(cur / "idProduct").lower()
                break
            cur = cur.parent
        if not vid:
            continue
        info = VENDOR_MAP.get(vid, ("Unknown vendor", "sysmex_astm", []))
        vname, suggested_type, hints = info
        product = _read_sysfs(cur / "product") or ""
        out.append(UsbDevice(
            tty_path=f"/dev/{tty.name}",
            vendor_id=vid,
            product_id=pid,
            vendor_name=vname,
            product_name=product,
            suggested_type=suggested_type,
            model_hints=hints,
        ))
    return out


def scan_windows() -> list[UsbDevice]:
    """Best-effort on Windows via PowerShell WMI. Empty list if unavailable."""
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-WmiObject Win32_SerialPort | Select-Object DeviceID, PNPDeviceID | ConvertTo-Json"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode != 0 or not r.stdout.strip():
            return []
        data = json.loads(r.stdout)
        if isinstance(data, dict):
            data = [data]
        out: list[UsbDevice] = []
        for e in data:
            pnp = e.get("PNPDeviceID", "")
            # Extract VID_XXXX&PID_YYYY
            import re
            m = re.search(r"VID_([0-9A-F]{4})&PID_([0-9A-F]{4})", pnp, re.I)
            if not m:
                continue
            vid, pid = m.group(1).lower(), m.group(2).lower()
            info = VENDOR_MAP.get(vid, ("Unknown vendor", "sysmex_astm", []))
            vname, suggested_type, hints = info
            out.append(UsbDevice(
                tty_path=str(e.get("DeviceID", "")),
                vendor_id=vid, product_id=pid,
                vendor_name=vname, product_name="",
                suggested_type=suggested_type, model_hints=hints,
            ))
        return out
    except Exception as exc:
        log.debug("windows scan failed: %s", exc)
        return []


def scan() -> list[UsbDevice]:
    import platform
    if platform.system() == "Windows":
        return scan_windows()
    return scan_linux()


def snapshot_to_disk(devices: Iterable[UsbDevice]) -> None:
    p = Path("logs/discovered_usb.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "scanned_at": time.time(),
        "devices": [asdict(d) for d in devices],
    }, indent=2, ensure_ascii=False), encoding="utf-8")


def start_background(interval_sec: int = 30) -> None:
    """Poll USB every 30s and refresh the snapshot the Web UI reads."""
    import threading

    def _loop() -> None:
        prev: list[UsbDevice] = []
        while True:
            try:
                curr = scan()
                snapshot_to_disk(curr)
                # Simple diff: log new arrivals
                curr_keys = {(d.vendor_id, d.tty_path) for d in curr}
                prev_keys = {(d.vendor_id, d.tty_path) for d in prev}
                new = curr_keys - prev_keys
                if new:
                    for d in curr:
                        if (d.vendor_id, d.tty_path) in new:
                            log.info("USB auto-discovery: new device %s (%s) → suggest %s",
                                     d.tty_path, d.vendor_name, d.suggested_type)
                prev = curr
            except Exception as exc:
                log.debug("USB auto-discovery loop failure: %s", exc)
            time.sleep(interval_sec)

    t = threading.Thread(target=_loop, daemon=True, name="usb-auto-discovery")
    t.start()
