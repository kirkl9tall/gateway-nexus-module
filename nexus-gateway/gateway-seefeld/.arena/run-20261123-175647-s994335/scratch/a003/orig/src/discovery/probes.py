"""
Discovery probes — recognise a lab device by USB VID/PID or by sniffing
the first bytes of its protocol on serial / TCP.

Strategy
─────────
A device is described by a ``DiscoveredDevice`` with a *confidence* score:
  100  = certain (matched USB fingerprint + valid protocol probe)
   80  = matched protocol probe alone
   60  = matched USB VID/PID alone
   40  = generic serial adapter, unknown protocol
    0  = nothing found

The Web UI shows any device with confidence >= 40 as "detected", and only
suggests auto-activation when confidence >= 80.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("loc200.discovery")


def stable_serial_path(devnode: str) -> str:
    """Return a PERSISTENT path for a USB serial device.

    /dev/ttyUSB0, ttyUSB1 … are handed out in enumeration order, so a USB hub
    with several analyzers (or a simple reboot) can swap them around and the
    gateway would then talk to the wrong device. Every save must therefore
    store a name that never moves. Preference order:
      1) /dev/jerumednexus/<family>-<serial>  — our udev rules (per serial no.)
      2) /dev/serial/by-id/<…>                — standard udev, needs a serial
      3) /dev/serial/by-path/<…>              — physical hub port, no serial
      4) the original /dev/ttyUSBx            — last resort (volatile)
    """
    try:
        real = os.path.realpath(devnode)
    except OSError:
        return devnode
    for base in ("/dev/jerumednexus", "/dev/serial/by-id", "/dev/serial/by-path"):
        d = Path(base)
        if not d.is_dir():
            continue
        for link in sorted(d.iterdir()):
            try:
                if os.path.realpath(str(link)) == real:
                    return str(link)
            except OSError:
                continue
    return devnode


# ── Known USB serial adapters commonly used with lab analyzers ───────────────
USB_FINGERPRINTS: Dict[str, Dict[str, str]] = {
    "0403:6001": {"chip": "FTDI FT232",  "family": "generic-rs232"},
    "0403:6015": {"chip": "FTDI FT230X", "family": "generic-rs232"},
    "067b:2303": {"chip": "PL2303",      "family": "generic-rs232"},
    "1a86:7523": {"chip": "CH340",       "family": "generic-rs232"},
    "10c4:ea60": {"chip": "CP210x",      "family": "generic-rs232"},
    # Direct-USB analyzer examples (populate per real hardware):
    # "0483:5740": {"chip": "STM32 CDC",  "family": "loc200-usb-cdc"},
}

# ── Protocol fingerprints ────────────────────────────────────────────────────
# Each entry: (name, matcher_regex, device_type_hint, display_name)
PROTOCOL_FINGERPRINTS = [
    ("hl7_mllp",  re.compile(rb"^\x0B?MSH\|\^~\\&"),                "mllp_hl7",       "HL7 v2 (MLLP)"),
    ("hl7_plain", re.compile(rb"MSH\|"),                            "mllp_hl7",       "HL7 v2 (plain)"),
    ("astm",      re.compile(rb"^\x05|^\x02H\|"),                   "sysmex_astm",    "ASTM E1381"),
    ("loc200",    re.compile(rb"(Sample ID|Disc Name|Kit)\s*[:\|]"), "loc200_native", "LOC-200 native"),
    ("uc1000",    re.compile(rb"^UC-1000|UC1000", re.MULTILINE),    "uc1000_serial",  "UC-1000 urinstatus"),
    ("cobas",     re.compile(rb"^H\|.*Cobas|^H\|.*Roche", re.I),    "cobas_poct",     "Cobas b101"),
]


@dataclass
class DiscoveredDevice:
    """One device the discovery service has detected."""

    source: str                     # "usb" | "tcp" | "manual"
    location: str                   # /dev/ttyUSB0 or host:port
    confidence: int                 # 0..100
    device_type: Optional[str] = None
    display_name: Optional[str] = None
    vendor: Optional[str] = None
    model: Optional[str] = None
    usb_id: Optional[str] = None
    chip: Optional[str] = None
    protocol: Optional[str] = None
    first_seen: str = ""
    last_seen: str = ""
    sample_bytes: str = ""          # hex-preview of first probe response
    activated: bool = False
    notes: List[str] = field(default_factory=list)

    def key(self) -> str:
        return f"{self.source}:{self.location}"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ── USB enumeration (Linux) ──────────────────────────────────────────────────

def _read_sysfs(path: Path) -> str:
    try:
        return path.read_text().strip()
    except OSError:
        return ""


def list_usb_serial_ports() -> List[Dict[str, str]]:
    """
    Enumerate /dev/ttyUSB* and /dev/ttyACM* + resolve their VID/PID via sysfs.

    Returns list of {device, vid, pid, chip, family, serial, symlink}.
    Also includes symlinks under /dev/jerumednexus/ populated by udev rules.
    """
    devices: List[Dict[str, str]] = []
    tty_dev = Path("/dev")
    if not tty_dev.exists():
        return devices  # non-Linux dev env

    candidates: List[Path] = []
    candidates += sorted(tty_dev.glob("ttyUSB*"))
    candidates += sorted(tty_dev.glob("ttyACM*"))
    loc200_dir = tty_dev / "jerumednexus"
    if loc200_dir.is_dir():
        for link in loc200_dir.iterdir():
            try:
                target = link.resolve()
                if target.exists():
                    candidates.append(target)
            except OSError:
                pass

    seen = set()
    for dev in candidates:
        if str(dev) in seen:
            continue
        seen.add(str(dev))
        info = {"device": str(dev)}
        # Walk sysfs backwards until we find idVendor/idProduct
        sys_link = Path("/sys/class/tty") / dev.name / "device"
        p = sys_link.resolve() if sys_link.exists() else None
        while p and p != Path("/"):
            vid_f = p / "idVendor"
            pid_f = p / "idProduct"
            if vid_f.exists() and pid_f.exists():
                vid = _read_sysfs(vid_f)
                pid = _read_sysfs(pid_f)
                info["vid"] = vid
                info["pid"] = pid
                fp = USB_FINGERPRINTS.get(f"{vid}:{pid}")
                if fp:
                    info["chip"] = fp["chip"]
                    info["family"] = fp["family"]
                serial_f = p / "serial"
                if serial_f.exists():
                    info["serial"] = _read_sysfs(serial_f)
                break
            p = p.parent
        devices.append(info)
    return devices


# ── Serial protocol probe ────────────────────────────────────────────────────

async def fingerprint_serial(port: str, baudrate: int = 9600,
                             timeout: float = 3.0) -> Optional[Dict[str, str]]:
    """
    Open a serial port briefly and read up to 512 bytes. Match against known
    protocol signatures. Returns {protocol, device_type, display_name, sample}
    or None if nothing matched.
    """
    try:
        import serial_asyncio
    except ImportError:
        log.debug("pyserial-asyncio not installed — cannot probe serial")
        return None

    try:
        reader, writer = await asyncio.wait_for(
            serial_asyncio.open_serial_connection(url=port, baudrate=baudrate),
            timeout=timeout,
        )
    except Exception as exc:
        log.debug("Cannot open %s: %s", port, exc)
        return None

    try:
        try:
            data = await asyncio.wait_for(reader.read(512), timeout=timeout)
        except asyncio.TimeoutError:
            data = b""
        writer.close()

        if not data:
            return None

        for name, pattern, dev_type, display in PROTOCOL_FINGERPRINTS:
            if pattern.search(data):
                return {
                    "protocol": name,
                    "device_type": dev_type,
                    "display_name": display,
                    "sample": data[:120].hex(),
                }
        return {
            "protocol": "unknown",
            "device_type": None,
            "display_name": "unknown serial stream",
            "sample": data[:120].hex(),
        }
    finally:
        try:
            await writer.wait_closed()
        except Exception:
            pass


# ── TCP protocol probe ───────────────────────────────────────────────────────

async def fingerprint_tcp(host: str, port: int,
                          timeout: float = 2.0) -> Optional[Dict[str, str]]:
    """
    Try to open a TCP connection. If it succeeds, read up to 512 bytes.
    Match protocol signature. Also accepts "silent" ports (no unsolicited data)
    with device_type=None but confidence=40 to be shown as "unknown listener".
    """
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=timeout,
        )
    except Exception:
        return None
    try:
        try:
            data = await asyncio.wait_for(reader.read(512), timeout=timeout)
        except asyncio.TimeoutError:
            data = b""
        writer.close()
        for name, pattern, dev_type, display in PROTOCOL_FINGERPRINTS:
            if data and pattern.search(data):
                return {
                    "protocol": name,
                    "device_type": dev_type,
                    "display_name": display,
                    "sample": data[:120].hex(),
                }
        if data:
            return {
                "protocol": "unknown-tcp",
                "device_type": None,
                "display_name": f"unknown TCP stream on {host}:{port}",
                "sample": data[:120].hex(),
            }
        return {
            "protocol": "silent-tcp",
            "device_type": None,
            "display_name": f"listener on {host}:{port} (no banner)",
            "sample": "",
        }
    finally:
        try:
            await writer.wait_closed()
        except Exception:
            pass
