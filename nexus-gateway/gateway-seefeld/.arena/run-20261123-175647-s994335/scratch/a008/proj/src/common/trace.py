"""
Live protocol trace ring buffer.

Each reader can record raw frames (bytes) it receives; the Web UI reads the
buffer via /api/trace/<device> for on-site debugging without needing SSH +
`journalctl`.

- Thread-safe (multiple readers can write concurrently).
- Bounded per device (default 100 frames, 8 KiB each max).
- Never persisted -- reset on process restart. Sensitive PII does NOT hit disk.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any, Dict, List, Optional

_MAX_FRAMES_PER_DEVICE = 100
_MAX_FRAME_PREVIEW     = 8 * 1024  # truncate stored frame at 8 KiB

_lock = threading.Lock()
_store: Dict[str, deque] = {}


def record(device: str, direction: str, data: bytes) -> None:
    """
    Record one frame observed on the wire.

    direction: "in" (from device to gateway) or "out" (ACK/reply from gateway).
    """
    if not device:
        return
    payload = data[:_MAX_FRAME_PREVIEW]
    entry = {
        "ts":         time.time(),
        "direction":  direction,
        "size":       len(data),
        "truncated":  len(data) > _MAX_FRAME_PREVIEW,
        "hex":        payload.hex(),
        "text":       payload.decode("utf-8", errors="replace"),
    }
    with _lock:
        dq = _store.get(device)
        if dq is None:
            dq = deque(maxlen=_MAX_FRAMES_PER_DEVICE)
            _store[device] = dq
        dq.append(entry)


def snapshot(device: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
    """Return the last `limit` frames, newest first."""
    with _lock:
        if device:
            dq = _store.get(device)
            if dq is None:
                return []
            items = list(dq)[-limit:]
        else:
            # All devices interleaved -- flatten and sort by ts
            items = []
            for dev, dq in _store.items():
                for e in list(dq)[-limit:]:
                    items.append({**e, "device": dev})
            items.sort(key=lambda e: e["ts"], reverse=True)
            items = items[:limit]
    return list(reversed(items))  # oldest first for display


def devices() -> List[str]:
    with _lock:
        return sorted(_store.keys())


def clear(device: Optional[str] = None) -> None:
    with _lock:
        if device:
            _store.pop(device, None)
        else:
            _store.clear()
