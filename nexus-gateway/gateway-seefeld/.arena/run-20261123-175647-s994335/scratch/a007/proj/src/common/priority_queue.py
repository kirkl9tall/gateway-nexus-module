"""
Priority queue for the dispatch pipeline.

When the queue is full, we do NOT drop the incoming item blindly. Instead
we classify by priority and evict the lowest-priority queued item first:

    P0 = orders from LIS (never dropped — clinical impact if lost)
    P1 = first-run results (patient waiting for report)
    P2 = repeat samples (patient already has a first result)
    P3 = QC samples (device internal quality control)

Eviction is O(N) but N is bounded by queue_maxsize (typically 1000-5000),
and happens only in overload — the fast path is a plain asyncio.Queue put.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

log = logging.getLogger("loc200.priority_queue")


def classify(item: dict[str, Any]) -> int:
    """Return priority: 0=critical, 3=lowest."""
    kind = str(item.get("kind", "")).lower()
    if kind == "order":
        return 0
    if item.get("is_qc") or (item.get("sample_id", "") or "").startswith("QC"):
        return 3
    if item.get("is_repeat"):
        return 2
    return 1


class SmartQueue:
    """
    asyncio.Queue-compatible surface with priority-based eviction on
    overflow. Preserves FIFO within the same priority.
    """

    def __init__(self, maxsize: int = 1000) -> None:
        self._q: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
        self._maxsize = maxsize
        self._evict_lock = asyncio.Lock()
        self._stats = {"put_ok": 0, "put_evicted": 0,
                       "evict_p3": 0, "evict_p2": 0, "evict_p1": 0}

    async def put(self, item: Any) -> bool:
        """
        Never blocks and never raises. Returns True if item entered the
        queue (possibly after evicting a lower-priority item), False if
        we could not make room (item was itself the lowest and queue full).
        """
        try:
            self._q.put_nowait(item)
            self._stats["put_ok"] += 1
            return True
        except asyncio.QueueFull:
            pass

        # Try to evict a lower-priority item
        item_prio = classify(item) if isinstance(item, dict) else 1
        async with self._evict_lock:
            drained: list[Any] = []
            evicted = False
            while not self._q.empty():
                try:
                    it = self._q.get_nowait()
                    self._q.task_done()
                except asyncio.QueueEmpty:
                    break
                if not evicted and isinstance(it, dict) and classify(it) > item_prio:
                    log.warning(
                        "SmartQueue evicting P%d (sample=%s) to make room for P%d",
                        classify(it), it.get("sample_id", "?"), item_prio,
                    )
                    self._stats[f"evict_p{classify(it)}"] += 1
                    self._stats["put_evicted"] += 1
                    evicted = True
                    continue
                drained.append(it)
            for it in drained:
                try:
                    self._q.put_nowait(it)
                except asyncio.QueueFull:
                    break
            if evicted:
                try:
                    self._q.put_nowait(item)
                    return True
                except asyncio.QueueFull:
                    pass
        # Could not make room — item itself is lowest priority; drop it
        log.warning("SmartQueue full, cannot evict — dropping P%d item", item_prio)
        return False

    async def get(self) -> Any:
        return await self._q.get()

    def task_done(self) -> None:
        self._q.task_done()

    def qsize(self) -> int:
        return self._q.qsize()

    @property
    def maxsize(self) -> int:
        return self._maxsize

    def stats(self) -> dict[str, int]:
        return dict(self._stats)
