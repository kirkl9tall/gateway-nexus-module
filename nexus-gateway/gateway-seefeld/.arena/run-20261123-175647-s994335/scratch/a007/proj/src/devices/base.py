"""
Device plugin base types.

A device is defined by a YAML profile (config/devices/) or legacy gateway.yaml
blocks. The registry maps ``type`` to the appropriate adapter class.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field, model_validator

_log = logging.getLogger("loc200.devices")


DeviceType = Literal[
    "sysmex_astm",
    "mllp_hl7",
    "uc1000_serial",
    "cobas_poct",
    "reflotron_serial",
    "loc200_serial",   # additional LOC-200 units beyond the `loc200:` section
    "universal_dsl",   # runtime DSL-driven (config/protocols/<id>.yaml)
]


class DeviceDefinition(BaseModel):
    """Unified device configuration — add analyzers without editing gateway.py."""

    id: str
    type: DeviceType
    enabled: bool = False
    display_name: str = ""
    vendor: str = ""
    model: str = ""

    # Connection parameters (interpretation depends on type)
    listen_host: str = "0.0.0.0"
    listen_port: Optional[int] = None
    serial_port: Optional[str] = None
    baudrate: int = 9600
    watch_folder: Optional[str] = None
    poll_interval: float = 5.0

    # ENQ / read timeout in seconds (per-device — Roche c111 = 15s, Sysmex = 5-30s).
    # Default 30s applies to bidirectional flows; adapters override sensibly.
    read_timeout_seconds: float = 30.0

    # ── Sysmex-specific protocol options ────────────────────────────────────
    # ASTM data-link mode over TCP/IP. Per XQ-Series Host Interface Spec §6.4:
    #   "1381-02" = full framing (ENQ/ACK, [STX][F#][Text][ETX][CHK1][CHK2][CR][LF], EOT)
    #   "1381-95" = raw records only (no ENQ/ACK/EOT, records terminated by CR)
    # If unsure, "1381-02" is the interoperable choice — technician chooses this
    # in the Sysmex IPU service menu.
    astm_mode: Literal["1381-02", "1381-95"] = "1381-02"

    # If True, this device is send-only (e.g. Sysmex XP-300): the gateway must
    # NOT reply to Q records with a synthetic "no order" response, and must not
    # try to initiate a query cycle.
    unidirectional: bool = False

    # Keep the TCP connection alive between samples — Sysmex opens ONE session
    # and holds it for hours. Default 300s idle timeout; -1 means no timeout.
    idle_timeout_seconds: float = 300.0

    # Parser / protocol options
    device_type: str = "seamaty"       # mllp_hl7 test-map key
    strip_id_suffix: bool = True

    # Free-form overrides (future YAML parser profiles)
    options: Dict[str, Any] = Field(default_factory=dict)

    # Nota descrittiva del profilo, per chi legge il file. Dichiararla qui
    # evita che finisca fra le chiavi sconosciute segnalate sotto.
    notes: str = ""

    @model_validator(mode="before")
    @classmethod
    def _segnala_chiavi_sconosciute(cls, dati: Any) -> Any:
        """
        Avvisa su una chiave che non esiste, invece di scartarla in silenzio.

        `name` e' una proprieta' calcolata, non un campo: scrivere
        `name: "Sysmex XQ-320"` in un file di configurazione sembrava
        funzionare e non faceva niente. Lo stesso vale per qualsiasi refuso.
        Si avvisa senza rifiutare, perche' rifiutare farebbe cadere il
        gateway su configurazioni che oggi funzionano.
        """
        if isinstance(dati, dict):
            sconosciute = set(dati) - set(cls.model_fields)
            if sconosciute:
                _log.warning(
                    "[%s] chiavi ignorate nella configurazione: %s. "
                    "Il nome visualizzato si scrive 'display_name'.",
                    dati.get("id", "?"), ", ".join(sorted(sconosciute)))
        return dati

    @model_validator(mode="after")
    def _segnala_collegamento_ambiguo(self) -> "DeviceDefinition":
        """
        Avvisa se un apparecchio ha sia una porta seriale sia una di ascolto.

        I lettori guardano prima la seriale:

            if self._serial_port: apri_seriale() else: apri_tcp()

        Un Sysmex riconfigurato da USB a TCP, ma con il vecchio serial_port
        rimasto nel file, continuava quindi ad aprire /dev/ttyUSB1 -- rubando
        il cavo a un altro apparecchio -- mentre la porta 5006 restava muta.
        Dal di fuori sembrava solo che non arrivasse niente.
        """
        if self.serial_port and self.listen_port:
            _log.warning(
                "[%s] ha sia serial_port (%s) sia listen_port (%s): vale la "
                "seriale, la porta di rete resta chiusa. Togli il campo del "
                "collegamento che non usi.",
                self.name, self.serial_port, self.listen_port)
        return self

    @property
    def name(self) -> str:
        return self.display_name or self.id
