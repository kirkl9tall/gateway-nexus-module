"""
Shared framing helpers.

Every stream-based reader must cap its accumulation buffer so a misbehaving
device cannot exhaust RAM on the Raspberry Pi.
"""
from __future__ import annotations

import logging
from typing import Union

log = logging.getLogger("loc200.framing")

MAX_FRAME_BYTES = 256 * 1024   # 256 KiB -- larger than any realistic result frame


def guard_buffer(
    buf: Union[bytearray, bytes],
    tag: str = "reader",
    limit: int = MAX_FRAME_BYTES,
) -> bool:
    """
    Return True if buffer is within the cap; False if it overflowed
    (caller is responsible for clearing the buffer on False).
    """
    if len(buf) > limit:
        log.warning(
            "[%s] Frame buffer exceeded %d bytes (%d) -- dropping to avoid OOM.",
            tag, limit, len(buf),
        )
        return False
    return True


def guard_str_buffer(
    buf: str,
    tag: str = "reader",
    limit: int = MAX_FRAME_BYTES,
) -> bool:
    """Same check but for string buffers (utf-8 accumulators)."""
    if len(buf) > limit:
        log.warning(
            "[%s] Text buffer exceeded %d chars (%d) -- dropping to avoid OOM.",
            tag, limit, len(buf),
        )
        return False
    return True
