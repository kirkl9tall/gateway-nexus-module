"""
DiscoveryService — orchestrates USB + TCP probes, persists results.

Persistence:
  logs/discovered.json   -- current state, read by the Web UI
                            (list of DiscoveredDevice as dicts)

Lifecycle:
  * ``scan_once()`` runs one full sweep (USB enumerate + probe + TCP scan).
  * ``notify_added(devnode)`` runs when udev emits an add event.
  * ``notify_removed(devnode)`` marks a device gone.
  * ``activate(key, target_type)`` promotes a discovered device to
    ``config/gateway.yaml`` by adding it to the ``devices:`` list.
"""
from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from src.discovery.probes import (
    DiscoveredDevice,
    USB_FINGERPRINTS,
    fingerprint_serial,
    fingerprint_tcp,
    list_usb_serial_ports,
    stable_serial_path,
)

log = logging.getLogger("loc200.discovery.service")

_STATE_FILE   = Path("logs/discovered.json")
_CONFIG_FILE  = Path("config/gateway.yaml")


def _now() -> str:
    return datetime.now().isoformat()


class DiscoveryService:
    """
    Held by the WebUI process, but also spawnable standalone for periodic scans.
    """

    def __init__(self, config_file: Path = _CONFIG_FILE,
                 state_file: Path = _STATE_FILE) -> None:
        self._config_file = config_file
        self._state_file  = state_file
        self._state: Dict[str, DiscoveredDevice] = {}
        self._lock = asyncio.Lock()
        self._load_state()

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load_state(self) -> None:
        if not self._state_file.exists():
            return
        try:
            data = json.loads(self._state_file.read_text())
            for row in data:
                dev = DiscoveredDevice(**row)
                self._state[dev.key()] = dev
        except Exception as exc:
            log.warning("Cannot load %s: %s", self._state_file, exc)

    def _save_state(self) -> None:
        try:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            payload = [d.to_dict() for d in self._state.values()]
            tmp = self._state_file.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, indent=2))
            import os as _os
            _os.replace(tmp, self._state_file)
        except Exception as exc:
            log.warning("Cannot save %s: %s", self._state_file, exc)

    # ── Public API ────────────────────────────────────────────────────────────

    def snapshot(self) -> List[Dict]:
        return [d.to_dict() for d in sorted(
            self._state.values(),
            key=lambda x: (-x.confidence, x.key()),
        )]

    def pending(self) -> List[Dict]:
        return [d.to_dict() for d in self._state.values()
                if not d.activated and d.confidence >= 40]

    async def scan_once(self, tcp_range: Optional[List[str]] = None,
                        tcp_ports: Optional[List[int]] = None) -> List[Dict]:
        """Run a full discovery sweep. Returns snapshot after scan."""
        async with self._lock:
            present = await self._scan_usb()
            # Drop USB ports that are no longer physically connected, so a scan
            # reflects what's plugged in NOW — otherwise unplugging every device
            # and rescanning still listed them all (they were only ever added,
            # never removed).
            for key in [k for k in list(self._state)
                        if k.startswith("usb:") and k not in present]:
                del self._state[key]
            if tcp_range and tcp_ports:
                await self._scan_tcp(tcp_range, tcp_ports)
            self._save_state()
        return self.snapshot()

    async def notify_added(self, devnode: str) -> None:
        async with self._lock:
            if self._e_occupata(devnode, self.porte_gia_in_uso()):
                log.debug("Porta %s gia' in uso da un lettore: non la sondo", devnode)
                return
            await self._probe_serial_device(devnode)
            self._save_state()

    def notify_removed(self, devnode: str) -> None:
        # Physically unplugged → remove it from the list immediately (before we
        # only set confidence=0, but the port kept showing).
        key = f"usb:{devnode}"
        if key in self._state:
            del self._state[key]
            self._save_state()

    async def activate(self, key: str, device_type: Optional[str] = None,
                       display_name: Optional[str] = None) -> bool:
        """
        Add the discovered device to gateway.yaml under ``devices:``.
        Returns True on success.

        ``display_name`` is the friendly machine name chosen from the "Scegli
        il tuo apparecchio" menu (e.g. "Urine UC-1000"). It becomes the device
        name that appears in every HL7 message (MSH-3) → the gestionale shows
        "Urine UC-1000 <facility>" instead of the internal id "auto_usb_…".
        """
        if key not in self._state:
            return False
        dev = self._state[key]
        dtype = device_type or dev.device_type
        if not dtype:
            log.warning("Cannot activate %s: unknown device_type", key)
            return False
        friendly = (display_name or "").strip() or dev.display_name

        cfg = {}
        if self._config_file.exists():
            try:
                cfg = yaml.safe_load(self._config_file.read_text()) or {}
            except Exception as exc:
                log.error("Config unreadable: %s", exc)
                return False

        cfg.setdefault("devices", [])
        new_id = f"auto_{dev.source}_{dev.location}".replace("/", "_").replace(":", "_")
        entry = {
            "id":           new_id,
            "type":         dtype,
            "enabled":      True,
            "display_name": friendly or new_id,
            "vendor":       dev.vendor or "",
            "model":        dev.model or "",
        }
        if dev.source == "usb":
            # Persist a stable path (by serial-no / physical port), NOT the
            # volatile /dev/ttyUSBx — otherwise a hub or reboot can remap it.
            entry["serial_port"] = stable_serial_path(dev.location)
            entry["baudrate"]    = 9600
        elif dev.source == "tcp":
            host, port = dev.location.rsplit(":", 1)
            entry["listen_host"] = host
            entry["listen_port"] = int(port)

        # De-duplicate: update the existing entry (type + friendly name) instead
        # of leaving a stale one — so re-assigning from the menu fixes the name.
        for existing in cfg["devices"]:
            if (existing.get("serial_port") == entry.get("serial_port")
                and existing.get("serial_port") is not None) \
               or (existing.get("listen_port") == entry.get("listen_port")
                   and existing.get("listen_port") is not None):
                existing["type"] = dtype
                if friendly:
                    existing["display_name"] = friendly
                existing["enabled"] = True
                tmp = self._config_file.with_suffix(".yaml.tmp")
                tmp.write_text(yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True))
                import os as _os
                _os.replace(tmp, self._config_file)
                dev.activated = True
                self._save_state()
                log.info("Updated existing device %s -> %s (%s)",
                         entry.get("serial_port") or entry.get("listen_port"),
                         friendly, dtype)
                return True

        cfg["devices"].append(entry)
        tmp = self._config_file.with_suffix(".yaml.tmp")
        tmp.write_text(yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True))
        import os as _os
        _os.replace(tmp, self._config_file)

        dev.activated = True
        dev.notes.append(f"activated at {_now()} as {new_id}")
        self._save_state()
        log.info("Activated %s as %s (%s)", key, new_id, dtype)
        return True

    # ── Internal probes ───────────────────────────────────────────────────────

    def porte_gia_in_uso(self) -> set:
        """
        Porte seriali che un lettore configurato e attivo sta gia' usando.

        Su Linux aprire una porta seriale gia' aperta di solito RIESCE: non
        c'e' un blocco esclusivo. Sondarla significa quindi leggere dallo
        stesso flusso del lettore vero e rubargli dei byte -- un referto puo'
        arrivare mutilato, o non arrivare affatto, senza alcun errore.
        Vengono considerati anche i percorsi stabili by-id/by-path, che
        puntano allo stesso dispositivo con un nome diverso.
        """
        in_uso: set = set()
        try:
            cfg = yaml.safe_load(self._config_file.read_text(encoding="utf-8")) or {}
        except Exception:
            return in_uso
        candidati = list(cfg.get("devices") or [])
        # Blocchi per-device storici (loc200:, cobas:, ...) accanto a devices:
        for valore in cfg.values():
            if isinstance(valore, dict):
                candidati.append(valore)
        for d in candidati:
            if not isinstance(d, dict) or d.get("enabled") is False:
                continue
            porta = d.get("serial_port") or d.get("port")
            seriale = d.get("serial")
            if isinstance(seriale, dict):
                porta = porta or seriale.get("port")
            if not porta or not isinstance(porta, str) or not porta.startswith("/dev/"):
                continue
            in_uso.add(porta)
            try:
                reale = Path(porta).resolve()
                in_uso.add(str(reale))
            except Exception:
                pass
        return in_uso

    async def _scan_usb(self) -> set:
        """Probe every currently-present USB serial port. Returns the set of
        state keys (``usb:<devnode>``) seen this sweep so scan_once can prune
        ports that have since been unplugged."""
        present: set = set()
        occupate = self.porte_gia_in_uso()
        for info in list_usb_serial_ports():
            devnode = info["device"]
            present.add(f"usb:{devnode}")
            if self._e_occupata(devnode, occupate):
                # Gia' in mano a un lettore: non la si apre, perche' sondarla
                # ruberebbe byte al referto in transito. La si mostra comunque
                # nell'elenco: saltarla del tutto la faceva sparire dalla
                # scansione, e l'operatore vedeva una cartella vuota senza
                # capire se l'apparecchio fosse collegato o no.
                log.debug("Porta %s gia' in uso da un lettore: non la sondo", devnode)
                self._registra_occupata(devnode, info, occupate)
                continue
            await self._probe_serial_device(devnode, info)
        return present

    def _registra_occupata(self, devnode: str, info: dict, occupate: set) -> None:
        """
        Segna la porta come presente e gia' assegnata, senza aprirla.

        Serve perche' l'operatore possa vedere che l'apparecchio e' collegato.
        Il nome del device che la occupa viene letto dalla configurazione, non
        dalla porta: nessun byte sottratto al lettore.
        """
        from src.discovery.probes import DiscoveredDevice

        chiave = f"usb:{devnode}"
        adesso = _now()
        nome = self._nome_di_chi_occupa(devnode, occupate) or "un apparecchio configurato"
        esistente = self._state.get(chiave)
        if esistente is not None:
            esistente.last_seen = adesso
            esistente.activated = True
            return
        self._state[chiave] = DiscoveredDevice(
            source="usb",
            location=devnode,
            confidence=100,          # non e' un'ipotesi: e' configurato
            display_name=nome,
            vendor=info.get("vendor", ""),
            usb_id=f"{info.get('vid','')}:{info.get('pid','')}".strip(":"),
            chip=info.get("chip"),
            first_seen=adesso,
            last_seen=adesso,
            activated=True,
            notes=[f"gia' in uso da {nome}: non viene sondata"],
        )

    def _nome_di_chi_occupa(self, devnode: str, occupate: set) -> str:
        """Nome del device configurato che tiene questa porta, se si trova."""
        import yaml as _yaml
        try:
            cfg = _yaml.safe_load(self._config_file.read_text(encoding="utf-8")) or {}
        except Exception:
            return ""
        try:
            reale = str(Path(devnode).resolve())
        except Exception:
            reale = devnode
        for d in (cfg.get("devices") or []):
            if not isinstance(d, dict):
                continue
            porta = d.get("serial_port") or d.get("port") or ""
            if not isinstance(porta, str):
                continue
            try:
                porta_reale = str(Path(porta).resolve())
            except Exception:
                porta_reale = porta
            if porta in (devnode, reale) or porta_reale in (devnode, reale):
                return str(d.get("display_name") or d.get("id") or "")
        return ""

    @staticmethod
    def _e_occupata(devnode: str, occupate: set) -> bool:
        if devnode in occupate:
            return True
        try:
            return str(Path(devnode).resolve()) in occupate
        except Exception:
            return False

    async def _probe_serial_device(self, devnode: str,
                                    info: Optional[Dict[str, str]] = None) -> None:
        key = f"usb:{devnode}"
        existing = self._state.get(key)
        info = info or {}
        vid = info.get("vid", "")
        pid = info.get("pid", "")
        fp = USB_FINGERPRINTS.get(f"{vid}:{pid}") if vid and pid else None

        result = await fingerprint_serial(devnode)
        confidence = 0
        display = None
        device_type = None
        protocol = None
        sample = ""
        if result:
            protocol = result["protocol"]
            device_type = result["device_type"]
            display = result["display_name"]
            sample = result["sample"]
            confidence = 80 if device_type else 40
        if fp:
            confidence = min(100, confidence + 20) if confidence else 60
            display = display or fp["family"]

        dev = DiscoveredDevice(
            source="usb",
            location=devnode,
            confidence=confidence,
            device_type=device_type,
            display_name=display,
            usb_id=f"{vid}:{pid}" if vid else None,
            chip=(fp or {}).get("chip"),
            protocol=protocol,
            first_seen=existing.first_seen if existing else _now(),
            last_seen=_now(),
            sample_bytes=sample,
            activated=existing.activated if existing else False,
        )
        self._state[key] = dev
        log.info("USB probe %s: confidence=%d protocol=%s",
                 devnode, confidence, protocol)

    async def _scan_tcp(self, cidrs: List[str], ports: List[int]) -> None:
        hosts: List[str] = []
        for cidr in cidrs:
            try:
                net = ipaddress.ip_network(cidr, strict=False)
                if net.num_addresses > 4096:
                    log.warning("Refusing to scan %s (too large)", cidr)
                    continue
                hosts.extend(str(a) for a in net.hosts())
            except ValueError:
                # single host
                hosts.append(cidr.strip())

        sem = asyncio.Semaphore(64)  # limit parallelism
        tasks = []

        async def probe(h: str, p: int) -> None:
            async with sem:
                r = await fingerprint_tcp(h, p, timeout=1.0)
                if r is None:
                    return
                key = f"tcp:{h}:{p}"
                existing = self._state.get(key)
                conf = 80 if r["device_type"] else 40
                self._state[key] = DiscoveredDevice(
                    source="tcp",
                    location=f"{h}:{p}",
                    confidence=conf,
                    device_type=r["device_type"],
                    display_name=r["display_name"],
                    protocol=r["protocol"],
                    first_seen=existing.first_seen if existing else _now(),
                    last_seen=_now(),
                    sample_bytes=r["sample"],
                    activated=existing.activated if existing else False,
                )

        for h in hosts:
            for p in ports:
                tasks.append(probe(h, p))
        await asyncio.gather(*tasks, return_exceptions=True)
        log.info("TCP scan complete: %d host(s) × %d port(s)", len(hosts), len(ports))
