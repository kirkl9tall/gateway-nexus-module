"""
File-lock based leader election for HA cluster mode.

Two (or more) Raspberry Pi run the gateway pointed at the same NFS/SMB
mount for `config/` and `logs/`. Only ONE actively dispatches; the other
runs in passive standby and takes over when the leader dies.

Design:
  * Each node writes a heartbeat to `logs/leader.lock` with its PID+hostname+ts
  * Leader refreshes every 5s; standby polls every 5s
  * If the lock file is stale (>15s), standby claims it via atomic replace
  * When the standby becomes leader, it starts dispatch; ex-leader shuts down
    gracefully

For a small clinic 1 Pi is enough; this is for hospitals wanting HA.
"""
from __future__ import annotations

import json
import logging
import os
import socket
import time
from pathlib import Path
from typing import Optional

log = logging.getLogger("loc200.leader")

_LOCK_FILE   = Path("logs/leader.lock")
_STALE_AFTER = 15.0     # seconds
_HEARTBEAT   = 5.0      # seconds


def _my_id() -> str:
    return f"{socket.gethostname()}#{os.getpid()}"


def _read_lock() -> Optional[dict]:
    try:
        return json.loads(_LOCK_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_lock(claim: str) -> bool:
    _LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"owner": claim, "ts": time.time()})
    tmp = _LOCK_FILE.with_suffix(".lock.tmp")
    try:
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, _LOCK_FILE)
        return True
    except OSError as exc:
        log.warning("lock write failed: %s", exc)
        return False


def try_acquire() -> bool:
    """
    Attempt to claim leadership. Returns True on success (either fresh or
    stealing a stale lock), False if another node still holds a fresh lock.
    """
    me = _my_id()
    current = _read_lock()
    now = time.time()
    if current:
        owner = current.get("owner", "")
        age = now - current.get("ts", 0)
        if owner == me:
            return _write_lock(me)     # refresh
        if age < _STALE_AFTER:
            return False               # someone else holds it, fresh
        log.warning("stealing stale lock from %s (age=%.1fs)", owner, age)
    return _write_lock(me)


def is_leader() -> bool:
    """Am I the current leader (based on the lock file)?"""
    c = _read_lock()
    return bool(c and c.get("owner") == _my_id())


def leader_id() -> Optional[str]:
    c = _read_lock()
    return c.get("owner") if c else None


def heartbeat_loop_forever(sleep_sec: float = _HEARTBEAT) -> None:
    """
    Call from a background thread. Refreshes the lock if we're leader; tries
    to grab it if it's stale.
    """
    while True:
        try:
            try_acquire()
        except Exception as exc:
            log.warning("heartbeat: %s", exc)
        time.sleep(sleep_sec)


def release() -> None:
    """Voluntarily give up leadership on shutdown."""
    if is_leader():
        try:
            _LOCK_FILE.unlink()
        except OSError:
            pass
