"""
Device registry — loads device profiles and instantiates adapters.

Devices can be defined in:
  1. ``devices:`` list in gateway.yaml (preferred)
  2. YAML files in config/devices/ (catalog + optional auto-load)
  3. Legacy per-device blocks (backward compatible)
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import yaml

from config.settings import GatewayConfig
from src.devices.base import DeviceDefinition
from src.devices.legacy import expand_legacy_devices

log = logging.getLogger("loc200.devices")

_CATALOG_DIR = Path("config/devices")


def load_device_catalog() -> List[DeviceDefinition]:
    """Load all device profile templates from config/devices/*.yaml."""
    profiles: List[DeviceDefinition] = []
    if not _CATALOG_DIR.exists():
        return profiles
    for path in sorted(_CATALOG_DIR.glob("*.yaml")):
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            raw.setdefault("id", path.stem)
            profiles.append(DeviceDefinition.model_validate(raw))
        except Exception as exc:
            log.warning("Skipping device profile %s: %s", path.name, exc)
    return profiles


def resolve_devices(config: GatewayConfig) -> List[DeviceDefinition]:
    """
    Elenco dei device che il gateway deve davvero aprire.

    Priorita':
      1. ``devices:`` in gateway.yaml -- ha sempre l'ultima parola
      2. i profili abilitati in config/devices/*.yaml
      3. i blocchi per-device storici, se non c'e' nient'altro

    Il punto 2 mancava, ed era un guasto serio: la pagina Analizzatori scrive
    in config/devices/<id>.yaml, ma questa funzione leggeva solo devices:.
    Ogni analizzatore aggiunto o abilitato dalla WebUI veniva quindi ignorato
    dal gateway, in silenzio -- niente log, niente errore, semplicemente non
    si apriva. Il Sysmex XQ-320 e' rimasto muto cosi'.

    Il catalogo e' una libreria di profili quasi tutti ``enabled: false``:
    entrano solo quelli che l'operatore ha effettivamente acceso. Un id gia'
    presente in devices: non viene mai sovrascritto dal catalogo, cosi' chi
    ha personalizzato gateway.yaml a mano mantiene il controllo.
    """
    attivi: List[DeviceDefinition] = [d for d in config.devices if d.enabled]
    visti = {d.id for d in config.devices}

    for profilo in load_device_catalog():
        if profilo.id in visti or not profilo.enabled:
            continue
        log.info("[%s] Device abilitato dal catalogo (config/devices/%s.yaml)",
                 profilo.id, profilo.id)
        attivi.append(profilo)

    if attivi:
        return attivi
    return [d for d in expand_legacy_devices(config) if d.enabled]


class DeviceRegistry:
    """Factory for laboratory device adapters."""

    def __init__(
        self,
        config: GatewayConfig,
        queue: asyncio.Queue,
        on_connect: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._config = config
        self._queue = queue
        self._on_connect = on_connect
        self._definitions = resolve_devices(config)
        self._readers: List[Any] = []
        self._http_server = None

    @property
    def definitions(self) -> List[DeviceDefinition]:
        return list(self._definitions)

    @property
    def http_server(self):
        return self._http_server

    async def open_all(self) -> List[Any]:
        """
        Open LOC-200 (always tried, never fatal) + all enabled plugin devices.

        A missing physical device (unplugged serial, unreachable TCP) MUST NOT
        take down the gateway: the WebUI, discovery service and HTTP ingest
        must stay up so the operator can see what's going on and assign
        devices from the browser.
        """
        readers: List[Any] = []

        # LOC-200 remains the primary biochemistry analyzer entry point,
        # but a failed .open() only logs a warning and keeps the gateway alive.
        try:
            from src.adapters.loc200_reader import Loc200Reader
            loc200 = Loc200Reader(self._config.loc200, self._queue,
                                  device_name="LOC-200")
            await loc200.open()
            readers.append(loc200)
            log.info("[LOC-200] Reader active (mode=%s)",
                     self._config.loc200.connection_type)
        except Exception as exc:
            log.warning("[LOC-200] Reader not started: %s -- gateway continues, "
                        "assign a device from the Web UI when ready.", exc)

        if self._config.loc200.connection_type == "http":
            try:
                from src.http_server import Loc200HttpServer
                self._http_server = Loc200HttpServer(
                    self._queue,
                    host="0.0.0.0",
                    port=self._config.loc200.http_port,
                )
                await self._http_server.start()
                log.info("[LOC-200] HTTP server on port %d",
                         self._config.loc200.http_port)
            except Exception as exc:
                log.warning("[LOC-200] HTTP server not started: %s", exc)

        for defn in self._definitions:
            try:
                reader = await self._create_reader(defn)
                readers.append(reader)
                log.info("[%s] active (type=%s)", defn.name, defn.type)
            except Exception as exc:
                log.warning("Device %s (%s) not started: %s -- open from Web UI later.",
                            defn.id, defn.type, exc)

        self._readers = readers
        return readers

    async def _create_reader(self, defn: DeviceDefinition) -> Any:
        if defn.type == "sysmex_astm":
            from src.adapters.sysmex_reader import SysmexReader
            r = SysmexReader(
                host=defn.listen_host,
                port=defn.listen_port or 5000,
                queue=self._queue,
                device_name=defn.name,
                strip_id_suffix=defn.strip_id_suffix,
                on_connect=lambda n=defn.name: self._fire_connect(n),
                serial_port=defn.serial_port,
                baudrate=defn.baudrate,
                read_timeout_seconds=defn.read_timeout_seconds,
                astm_mode=defn.astm_mode,
                unidirectional=defn.unidirectional,
                idle_timeout_seconds=defn.idle_timeout_seconds,
            )
            await r.open()
            return r

        if defn.type == "mllp_hl7":
            from src.adapters.mllp_reader import MLLPReader
            r = MLLPReader(
                host=defn.listen_host,
                port=defn.listen_port or 6000,
                queue=self._queue,
                device_name=defn.name,
                device_type=defn.device_type,
                on_connect=lambda n=defn.name: self._fire_connect(n),
            )
            await r.open()
            return r

        if defn.type == "uc1000_serial":
            from src.adapters.uc1000_reader import UC1000Reader
            r = UC1000Reader(
                port=defn.serial_port or "/dev/ttyUSB1",
                baudrate=defn.baudrate,
                queue=self._queue,
                device_name=defn.name,
            )
            await r.open()
            return r

        if defn.type == "loc200_serial":
            # Additional LOC-200 analyzers beyond the primary one in the
            # `loc200:` section — lets a practice run 2+ LOC-200 units, each
            # on its own USB-serial port.
            from config.settings import Loc200Config, SerialConfig
            from src.adapters.loc200_reader import Loc200Reader
            lcfg = Loc200Config(
                connection_type="serial",
                serial=SerialConfig(port=defn.serial_port or "/dev/ttyUSB0",
                                    baudrate=defn.baudrate),
                debug_raw_frames=self._config.loc200.debug_raw_frames,
            )
            r = Loc200Reader(lcfg, self._queue, device_name=defn.name)
            await r.open()
            return r

        if defn.type == "reflotron_serial":
            from src.adapters.reflotron_reader import ReflotronReader
            r = ReflotronReader(
                port=defn.serial_port or "/dev/ttyUSB4",
                baudrate=defn.baudrate,
                queue=self._queue,
                device_name=defn.name,
            )
            await r.open()
            return r

        if defn.type == "cobas_poct":
            from src.adapters.cobas_reader import CobasReader
            r = CobasReader(
                serial_port=defn.serial_port or "/dev/ttyACM0",
                queue=self._queue,
                poll_interval=defn.poll_interval,
                device_name=defn.name,
                baudrate=defn.baudrate,
            )
            await r.open()
            return r

        if defn.type == "universal_dsl":
            # Uses a user-provided YAML spec under config/protocols/<id>.yaml
            from pathlib import Path as _P
            from src.adapters.universal_dsl import load_spec, parse_message
            spec_name = (defn.options or {}).get("spec", defn.id) or defn.id
            spec_path = _P("config/protocols") / f"{spec_name}.yaml"
            if not spec_path.exists():
                raise FileNotFoundError(f"DSL spec not found: {spec_path}")
            spec = load_spec(spec_path)
            # Reuse SysmexReader's TCP plumbing for read-only receipt,
            # but override _dispatch_buffer to call the DSL parser.
            from src.adapters.sysmex_reader import SysmexReader

            class _DSLReader(SysmexReader):
                async def _dispatch_buffer(self_inner, buf, addr) -> None:
                    text = buf.decode("ascii", errors="ignore")
                    result = parse_message(spec, text)
                    if result:
                        from src.common.backpressure import safe_put_sync
                        safe_put_sync(self_inner._queue, result,
                                       tag=self_inner._device_name)

            r = _DSLReader(
                host=defn.listen_host, port=defn.listen_port or 5100,
                queue=self._queue, device_name=defn.name,
                astm_mode="1381-95",   # DSL doesn't do framing handshake
                idle_timeout_seconds=defn.idle_timeout_seconds,
            )
            await r.open()
            return r

        raise ValueError(f"Unknown device type: {defn.type}")

    def _fire_connect(self, name: str) -> None:
        if self._on_connect:
            self._on_connect(name)

    async def close_all(self) -> None:
        for reader in self._readers:
            try:
                await reader.close()
            except Exception as exc:
                log.warning("Error closing %s: %s", reader.__class__.__name__, exc)
        if self._http_server:
            await self._http_server.stop()

    def reader_status(self) -> List[Dict[str, Any]]:
        """Summary for status.json / Web UI."""
        items = [{"name": "LOC-200", "mode": self._config.loc200.connection_type}]
        for d in self._definitions:
            entry: Dict[str, Any] = {"name": d.name, "type": d.type, "id": d.id}
            if d.serial_port:
                entry["port"] = d.serial_port
            elif d.listen_port:
                entry["port"] = d.listen_port
            elif d.watch_folder:
                entry["port"] = d.watch_folder
            items.append(entry)
        return items
