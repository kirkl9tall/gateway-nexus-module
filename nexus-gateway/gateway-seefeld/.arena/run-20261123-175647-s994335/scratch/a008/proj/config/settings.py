"""
config/settings.py
Configuration loader with validation (Pydantic v2).
"""

from __future__ import annotations
from pathlib import Path
from typing import List, Literal, Optional
import yaml
from pydantic import BaseModel, Field, StringConstraints, field_validator
from typing_extensions import Annotated

from src.devices.base import DeviceDefinition


# ── LOC-200 (existing) ────────────────────────────────────────────────────────

class SerialConfig(BaseModel):
    port: str = "/dev/ttyUSB0"
    baudrate: int = 9600
    bytesize: int = 8
    parity: str = "N"
    stopbits: float = 1.0
    timeout: float = 10.0

class NetworkConfig(BaseModel):
    host: str = "192.168.1.100"
    port: int = 5000
    timeout: float = 10.0
    reconnect_delay: float = 5.0

class WiFiConfig(BaseModel):
    host: str = "192.168.1.101"
    port: int = 5000
    timeout: float = 15.0
    reconnect_delay: float = 5.0

class Loc200Config(BaseModel):
    connection_type: Literal["serial", "network", "wifi", "http"] = "http"
    http_port: int = 5003
    serial:  SerialConfig  = Field(default_factory=SerialConfig)
    network: NetworkConfig = Field(default_factory=NetworkConfig)
    wifi:    WiFiConfig    = Field(default_factory=WiFiConfig)
    debug_raw_frames: bool = False
    poll_interval: float = 1.0

# ── NEW: Sysmex XP-300 / XQ-320 / pocH-100i ──────────────────────────────────

class SysmexConfig(BaseModel):
    enabled: bool = False
    listen_host: str = "0.0.0.0"
    listen_port: int = 5000
    device_name: str = "SYSMEX Haematologie"
    strip_id_suffix: bool = True

class SysmexXQ320Config(BaseModel):
    enabled: bool = False
    listen_host: str = "0.0.0.0"
    listen_port: int = 5001
    device_name: str = "SYSMEX XQ320 Haematologie"
    strip_id_suffix: bool = True
    serial_port: str | None = None
    connection_type: str = "serial"
    baudrate: int = 9600

class SysmexPoch100iConfig(BaseModel):
    enabled: bool = False
    listen_host: str = "0.0.0.0"
    listen_port: int = 5002
    device_name: str = "POCH100I Haematologie"
    strip_id_suffix: bool = True

# ── NEW: UC-1000 ──────────────────────────────────────────────────────────────

class UC1000Config(BaseModel):
    enabled: bool = False
    serial_port: str = "/dev/ttyUSB1"
    baudrate: int = 9600
    device_name: str = "UC1000 Urinstatus"

# ── NEW: Seamaty SMT-120 / SD1 / SD3 ─────────────────────────────────────────

class SeamatyConfig(BaseModel):
    enabled: bool = False
    listen_host: str = "0.0.0.0"
    listen_port: int = 6000
    device_name: str = "Seamaty Chemie"
    device_type: str = "seamaty"

class SeamatySD1Config(BaseModel):
    enabled: bool = False
    listen_host: str = "0.0.0.0"
    listen_port: int = 6002
    device_name: str = "Seamaty SD1 POCT"
    device_type: str = "seamaty_sd1"

class SeamatySD3Config(BaseModel):
    enabled: bool = False
    listen_host: str = "0.0.0.0"
    listen_port: int = 6001
    device_name: str = "Seamaty SD3 POCT"
    device_type: str = "seamaty_sd3"

# ── NEW: Horiba Microsemi CRP ─────────────────────────────────────────────────

class HoribaConfig(BaseModel):
    enabled: bool = False
    listen_host: str = "0.0.0.0"
    listen_port: int = 5004
    device_name: str = "HORIBA Microsemi CRP"
    device_type: str = "horiba_microsemi"

# ── NEW: Roche Cobas b 101 ────────────────────────────────────────────────────

class CobasConfig(BaseModel):
    enabled: bool = False
    watch_folder: str = "/tmp/cobas_export"
    serial_port: str = "/dev/ttyACM0"
    baudrate: int = 9600
    poll_interval: float = 5.0
    device_name: str = "COBAS B101 POCT"

# ── HL7 / PIS targets ─────────────────────────────────────────────────────────

_NonEmpty20 = Annotated[str, StringConstraints(min_length=1, max_length=20)]
_NonEmpty180 = Annotated[str, StringConstraints(min_length=1, max_length=180)]


class HL7Config(BaseModel):
    # Any of 2.3, 2.4, 2.5, 2.5.1, 2.6, 2.7, 2.8 supported.
    # 2.3 + ISO-8859/1 is the format Tomedo actually imported from this gateway
    # (confirmed against an archived, successfully-imported file).
    version: str = "2.3"
    # MSH-3 / MSH-5 are capped at 20 chars per HL7 v2.5
    sending_application:   _NonEmpty20 = "JMNX_GW"
    sending_facility:      _NonEmpty180 = "PRAXIS"
    receiving_application: _NonEmpty20 = "LIS"
    receiving_facility:    _NonEmpty180 = "PRAXIS"
    loinc_map_path: str = "config/loinc_map.yaml"

    @field_validator("sending_facility", "receiving_facility")
    @classmethod
    def _not_placeholder(cls, v: str) -> str:
        if v.strip().upper() in ("PRAXIS", "PRAXIS_NAME"):
            # Not an error -- but banner logic in UI can flag it
            import logging as _l
            _l.getLogger("loc200.config").warning(
                "sending/receiving_facility still uses the placeholder %r -- "
                "change it in config/gateway.yaml before production.", v,
            )
        return v

    # MSH-18 charset — must match the byte-level encoding of the payload.
    # "UNICODE UTF-8" pairs with utf-8 wire encoding (default, safe for German).
    # "8859/1" pairs with iso-8859-1 wire encoding (legacy LIS only).
    charset: Literal["UNICODE UTF-8", "8859/1", "ASCII"] = "8859/1"

    # Include %z offset in HL7 timestamps (e.g. 20250825120000+0200)
    include_timezone: bool = True

class PISTarget(BaseModel):
    name: str
    type: Literal[
        "vitomed", "curamed", "aeskulap", "axenita",
        "winmed", "dnamed", "tomedo", "generic_hl7_mllp",
        "file_drop", "fhir_r4"
    ]
    enabled: bool = True
    host: Optional[str] = None
    port: Optional[int] = None
    mllp_timeout: float = 10.0
    watch_folder: Optional[str] = None
    file_encoding: str = "utf-8"
    file_extension: str = ".hl7"
    sftp_host: Optional[str] = None
    sftp_port: int = 22
    sftp_user: Optional[str] = None
    sftp_pass: Optional[str] = None
    sftp_remote_path: Optional[str] = None
    # FHIR R4 targets
    fhir_endpoint: Optional[str] = None       # e.g. https://fhir.hospital.example/
    fhir_verify_tls: bool = True
    fhir_token: Optional[str] = None          # loaded from <NAME>_FHIR_TOKEN secret

    @field_validator("host", "port", mode="before")
    @classmethod
    def _pass_through(cls, v, info):
        return v

# ── Main config ───────────────────────────────────────────────────────────────

class GatewayConfig(BaseModel):
    log_level: str = "INFO"
    log_file: Optional[str] = "logs/gateway.log"

    loc200:  Loc200Config = Field(default_factory=Loc200Config)
    hl7:     HL7Config    = Field(default_factory=HL7Config)
    targets: List[PISTarget] = Field(default_factory=list)

    # Unified device list (preferred over legacy per-device blocks)
    devices: List[DeviceDefinition] = Field(default_factory=list)

    queue_maxsize: int = 500
    retry_max_attempts: int = 5
    retry_delay_seconds: float = 5.0

    # Circuit breaker per target
    breaker_threshold: int = 5             # consecutive failures before OPEN
    breaker_recovery_seconds: float = 60.0  # OPEN -> HALF-OPEN after this delay

    # Reader watchdog -- warn when a reader has been silent this many seconds
    reader_silence_warning_seconds: int = 900   # 15 min
    reader_silence_alert_seconds: int   = 3600  # 1 h

    # Enqueue backpressure -- readers wait this long before dropping to DLQ
    enqueue_timeout_seconds: float = 5.0

    # Structured logging: "text" (default) or "json"
    log_format: str = "text"

    # Bidirectional orders (LIS -> gateway -> analyzer)
    order_receiver_enabled: bool = False
    order_receiver_host: str = "0.0.0.0"
    order_receiver_port: int = 5500

    # Data retention (nDSG / GDPR Art. 5(1)(e)) -- days
    retention: dict = Field(default_factory=lambda: {
        "history_days":       90,
        "dlq_days":           30,
        "orders_days":        7,
        "gateway_log_days":   30,
        "audit_days":         730,
        "seen_samples_days":  7,
    })

    # DLQ at-rest encryption
    dlq_encryption_enabled: bool = True

    # Outbound alerting
    alerts_webhook_url: str = ""      # POST JSON on high-severity events
    alerts_smtp_host: str = ""        # optional SMTP relay
    alerts_smtp_port: int = 25
    alerts_smtp_from: str = ""
    alerts_smtp_to: str = ""

    # New analyzers
    sysmex:           SysmexConfig          = Field(default_factory=SysmexConfig)
    sysmex_xq320:     SysmexXQ320Config     = Field(default_factory=SysmexXQ320Config)
    sysmex_poch100i:  SysmexPoch100iConfig   = Field(default_factory=SysmexPoch100iConfig)
    uc1000:           UC1000Config          = Field(default_factory=UC1000Config)
    seamaty:          SeamatyConfig         = Field(default_factory=SeamatyConfig)
    seamaty_sd1:      SeamatySD1Config      = Field(default_factory=SeamatySD1Config)
    seamaty_sd3:      SeamatySD3Config      = Field(default_factory=SeamatySD3Config)
    horiba:           HoribaConfig          = Field(default_factory=HoribaConfig)
    cobas:            CobasConfig           = Field(default_factory=CobasConfig)

# ── Loader ────────────────────────────────────────────────────────────────────

_SEGRETI_DAI_ENV = {
    "sftp_pass":  "sftp_pass_env",
    "fhir_token": "fhir_token_env",
}


def _risolvi_segreti(raw: dict) -> dict:
    """
    Sostituisce i segreti dichiarati per nome di variabile d'ambiente.

        targets:
          - name: tomedo
            sftp_user: jerumed
            sftp_pass_env: TOMEDO_SFTP_PASS   # il valore sta in secrets.env

    Serve per poter versionare la configurazione di uno studio. Finche' la
    password stava dentro gateway.yaml, quel file non poteva entrare nel
    repository -- ed e' per questo che le configurazioni di produzione
    esistevano solo sul Raspberry, senza storia e senza copia.

    Una variabile dichiarata ma assente e' un errore rumoroso: meglio non
    partire che partire con una password vuota e accumulare referti in coda
    senza capire perche'.
    """
    import os

    for t in (raw.get("targets") or []):
        if not isinstance(t, dict):
            continue
        for campo, campo_env in _SEGRETI_DAI_ENV.items():
            nome_var = t.pop(campo_env, None)
            if not nome_var:
                continue
            valore = os.environ.get(str(nome_var))
            if valore is None:
                raise ValueError(
                    f"[{t.get('name', '?')}] {campo_env} punta a {nome_var}, "
                    f"ma quella variabile d'ambiente non esiste. "
                    f"Impostala in config/secrets.env."
                )
            t[campo] = valore
    return raw


def load_config(path: Path) -> GatewayConfig:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    raw = _risolvi_segreti(raw or {})
    config = GatewayConfig.model_validate(raw or {})
    import logging
    enabled = [t.name for t in config.targets if t.enabled]
    logging.getLogger("loc200.config").info(
        "Loaded. Connection: %s | Targets: %s",
        config.loc200.connection_type,
        enabled or ["(none)"],
    )
    return config
