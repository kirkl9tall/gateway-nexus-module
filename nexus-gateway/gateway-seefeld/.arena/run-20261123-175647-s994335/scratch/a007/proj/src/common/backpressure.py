"""
Backpressure-aware queue helpers.

Instead of ``queue.put_nowait(item)`` (which silently loses data when the
queue is full) callers use ``await safe_put(queue, item, ...)`` which:

- blocks up to ``timeout`` seconds waiting for space,
- if still full, DROPS the item, increments the ``queue_full`` counter,
  logs a warning, and optionally invokes ``on_drop(item)`` so the caller
  can persist to a dead-letter store.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable, Optional

log = logging.getLogger("loc200.backpressure")

# Global counter (Prometheus reads this from a getter below).
queue_full_events: int = 0


def _incr() -> None:
    global queue_full_events
    queue_full_events += 1


async def safe_put(
    queue: "asyncio.Queue[Any]",
    item: Any,
    *,
    timeout: float = 5.0,
    tag: str = "reader",
    on_drop: Optional[Callable[[Any], Awaitable[None]]] = None,
) -> bool:
    """
    Enqueue ``item`` with backpressure.

    Returns True on success, False if the item was dropped.
    """
    try:
        await asyncio.wait_for(queue.put(item), timeout=timeout)
        return True
    except asyncio.TimeoutError:
        _incr()
        log.warning(
            "[%s] Queue full (size=%d/%d) -- dropping item after %.1fs wait.",
            tag, queue.qsize(), queue.maxsize, timeout,
        )
        if on_drop:
            try:
                await on_drop(item)
            except Exception as exc:  # pragma: no cover
                log.error("[%s] on_drop handler failed: %s", tag, exc)
        return False


def safe_put_sync(
    queue: "asyncio.Queue[Any]",
    item: Any,
    tag: str = "reader",
) -> bool:
    """
    Synchronous variant for callbacks that cannot await
    (asyncio.Protocol.data_received, threading executor).

    Uses put_nowait -- on QueueFull we drop and log, matching the async path.
    """
    try:
        queue.put_nowait(item)
        return True
    except asyncio.QueueFull:
        _incr()
        log.warning(
            "[%s] Queue full (size=%d/%d) -- dropping item.",
            tag, queue.qsize(), queue.maxsize,
        )
        return False


def get_and_reset_counter() -> int:
    """Read + reset the counter (used by metrics endpoint)."""
    global queue_full_events
    n = queue_full_events
    queue_full_events = 0
    return n
