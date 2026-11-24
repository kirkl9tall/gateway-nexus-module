"""
Expand legacy per-device blocks in gateway.yaml into unified DeviceDefinition list.
Keeps existing installations working without config migration.
"""

from __future__ import annotations

from typing import List

from config.settings import GatewayConfig
from src.devices.base import DeviceDefinition


def expand_legacy_devices(config: GatewayConfig) -> List[DeviceDefinition]:
    """Convert legacy ``sysmex:``, ``uc1000:``, … blocks to device definitions."""
    devices: List[DeviceDefinition] = []

    if config.sysmex.enabled:
        devices.append(DeviceDefinition(
            id="sysmex_xp300",
            type="sysmex_astm",
            enabled=True,
            display_name=config.sysmex.device_name,
            vendor="Sysmex",
            model="XP-300",
            listen_host=config.sysmex.listen_host,
            listen_port=config.sysmex.listen_port,
            strip_id_suffix=config.sysmex.strip_id_suffix,
        ))

    if config.sysmex_xq320.enabled:
        devices.append(DeviceDefinition(
            id="sysmex_xq320",
            type="sysmex_astm",
            enabled=True,
            display_name=config.sysmex_xq320.device_name,
            vendor="Sysmex",
            model="XQ-320",
            listen_host=config.sysmex_xq320.listen_host,
            listen_port=config.sysmex_xq320.listen_port,
            serial_port=config.sysmex_xq320.serial_port,
            baudrate=config.sysmex_xq320.baudrate,
            strip_id_suffix=config.sysmex_xq320.strip_id_suffix,
        ))

    if config.sysmex_poch100i.enabled:
        devices.append(DeviceDefinition(
            id="sysmex_poch100i",
            type="sysmex_astm",
            enabled=True,
            display_name=config.sysmex_poch100i.device_name,
            vendor="Sysmex",
            model="pocH-100i",
            listen_host=config.sysmex_poch100i.listen_host,
            listen_port=config.sysmex_poch100i.listen_port,
            strip_id_suffix=config.sysmex_poch100i.strip_id_suffix,
        ))

    if config.uc1000.enabled:
        devices.append(DeviceDefinition(
            id="uc1000",
            type="uc1000_serial",
            enabled=True,
            display_name=config.uc1000.device_name,
            vendor="Menarini",
            model="UC-1000",
            serial_port=config.uc1000.serial_port,
            baudrate=config.uc1000.baudrate,
        ))

    for key, cfg, vendor, model, dtype in (
        ("seamaty",     config.seamaty,     "Seamaty", "SMT-120",        "seamaty"),
        ("seamaty_sd3", config.seamaty_sd3, "Seamaty", "SD3",            "seamaty_sd3"),
        ("seamaty_sd1", config.seamaty_sd1, "Seamaty", "SD1",            "seamaty_sd1"),
        ("horiba",      config.horiba,      "Horiba",  "Microsemi CRP",  "horiba_microsemi"),
    ):
        if cfg.enabled:
            devices.append(DeviceDefinition(
                id=key,
                type="mllp_hl7",
                enabled=True,
                display_name=cfg.device_name,
                vendor=vendor,
                model=model,
                listen_host=cfg.listen_host,
                listen_port=cfg.listen_port,
                device_type=cfg.device_type or dtype,
            ))

    if config.cobas.enabled:
        devices.append(DeviceDefinition(
            id="cobas_b101",
            type="cobas_poct",
            enabled=True,
            display_name=config.cobas.device_name,
            vendor="Roche",
            model="Cobas b 101",
            serial_port=config.cobas.serial_port,
            baudrate=config.cobas.baudrate,
            watch_folder=config.cobas.watch_folder,
            poll_interval=config.cobas.poll_interval,
        ))

    return devices
