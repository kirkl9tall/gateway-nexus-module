"""
mDNS / Bonjour advertise — the gateway announces itself on the LAN as
_jerumednexus._tcp.local so analyzer technicians see it in their IPU's
network scanner without typing the IP by hand.

Uses zeroconf if installed (pip install zeroconf), otherwise no-op with
a WARNING log. Non-blocking, runs in its own thread.
"""
from __future__ import annotations

import logging
import socket
import threading
from typing import Optional

log = logging.getLogger("loc200.mdns")

_ADVERTISER: Optional["MDNSAdvertiser"] = None


class MDNSAdvertiser:
    def __init__(
        self,
        service_type: str = "_jerumednexus._tcp.local.",
        instance_name: str = "JerumedNexus Gateway",
        port: int = 8088,
        facility: str = "PRAXIS",
        version: str = "1.3.0",
    ) -> None:
        self._service_type = service_type
        self._instance_name = instance_name
        self._port = port
        self._facility = facility
        self._version = version
        self._zc = None
        self._service_info = None

    def _lan_ip(self) -> str:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    def start(self) -> None:
        try:
            from zeroconf import ServiceInfo, Zeroconf
        except ImportError:
            log.warning("zeroconf not installed — mDNS advertise disabled. "
                        "pip install zeroconf to enable.")
            return
        ip = self._lan_ip()
        addr = socket.inet_aton(ip)
        info = ServiceInfo(
            type_=self._service_type,
            name=f"{self._instance_name}.{self._service_type}",
            addresses=[addr],
            port=self._port,
            properties={
                b"facility": self._facility.encode("utf-8"),
                b"version":  self._version.encode("utf-8"),
                b"path":     b"/",
            },
            server=f"{socket.gethostname()}.local.",
        )
        self._zc = Zeroconf()
        self._service_info = info
        self._zc.register_service(info)
        log.info("mDNS advertise: %s @ %s:%d as %s",
                 self._instance_name, ip, self._port, self._service_type)

    def stop(self) -> None:
        try:
            if self._zc and self._service_info:
                self._zc.unregister_service(self._service_info)
                self._zc.close()
        except Exception as exc:
            log.debug("mDNS shutdown: %s", exc)


def start_background(**kwargs) -> None:
    """Fire-and-forget. Safe to call at boot."""
    global _ADVERTISER
    _ADVERTISER = MDNSAdvertiser(**kwargs)
    t = threading.Thread(target=_ADVERTISER.start, daemon=True, name="mdns-advertise")
    t.start()


def stop() -> None:
    global _ADVERTISER
    if _ADVERTISER:
        _ADVERTISER.stop()
        _ADVERTISER = None
