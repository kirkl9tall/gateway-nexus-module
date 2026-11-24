"""
Device plugin system.

Only ``DeviceDefinition`` is eagerly exported here because
``config.settings`` imports it while building its own module.
``DeviceRegistry`` etc. are available via ``src.devices.registry``.
"""

from src.devices.base import DeviceDefinition

__all__ = ["DeviceDefinition"]
