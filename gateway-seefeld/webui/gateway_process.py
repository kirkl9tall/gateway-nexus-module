"""
Start / stop the gateway when it is NOT installed as a systemd service.

On a Raspberry Pi installed with the .deb, the gateway runs as the
`jerumednexus-gateway` systemd unit and the Web UI uses systemctl. On a
development PC, a demo box or a manual install there is no unit: the switch
on the Overview then manages the gateway process directly:

    start   → runs `<python> main.py` from the install root, detached,
              output in logs/gateway.stdout.log
    stop    → SIGTERM to the gateway process(es) of THIS install root only
              (matched on /proc/<pid>/cmdline and cwd), so nothing else
              on the machine can be touched

The gateway writes running=false to status.json on a clean stop, so the
Overview shows "off" right away.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parent.parent
UNIT = "jerumednexus-gateway"


_unit_cache = {"at": 0.0, "value": False}


def systemd_unit_installed() -> bool:
    """Cached for 60 s: called on every status poll."""
    now = time.time()
    if now - _unit_cache["at"] < 60:
        return _unit_cache["value"]
    try:
        r = subprocess.run(["systemctl", "list-unit-files", f"{UNIT}.service"],
                           capture_output=True, text=True, timeout=5)
        value = f"{UNIT}.service" in r.stdout
    except Exception:
        value = False
    _unit_cache.update(at=now, value=value)
    return value


def status() -> str:
    """'active' or 'stopped', for installs without the systemd unit."""
    return "active" if gateway_pids() else "stopped"


def gateway_pids() -> List[int]:
    """PIDs of `main.py` processes running from this install root."""
    pids = []
    me = os.getpid()
    for d in Path("/proc").glob("[0-9]*"):
        try:
            pid = int(d.name)
            if pid == me:
                continue
            argv = (d / "cmdline").read_bytes().split(b"\0")
            if not any(a.endswith(b"main.py") for a in argv[:3]):
                continue
            if Path(os.readlink(d / "cwd")).resolve() != ROOT:
                continue
            if not any(b"python" in a for a in argv[:1]):
                continue
            pids.append(pid)
        except (OSError, ValueError):
            continue
    return pids


def start() -> tuple[bool, str]:
    if gateway_pids():
        return True, ""
    log_dir = ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    out = open(log_dir / "gateway.stdout.log", "ab")
    subprocess.Popen([sys.executable, str(ROOT / "main.py")], cwd=str(ROOT),
                     stdout=out, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                     start_new_session=True)
    # The gateway writes status.json within a few seconds of starting.
    for _ in range(20):
        time.sleep(0.25)
        if gateway_pids():
            return True, ""
    return False, "the gateway process did not start (see logs/gateway.stdout.log)"


def stop() -> tuple[bool, str]:
    pids = gateway_pids()
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    deadline = time.time() + 20          # the gateway drains its queue on stop
    while time.time() < deadline and gateway_pids():
        time.sleep(0.25)
    left = gateway_pids()
    return (not left), ("" if not left else f"still running: {left}")


def action(name: str) -> tuple[bool, str]:
    if name == "start":
        return start()
    if name == "stop":
        return stop()
    if name == "restart":
        ok, err = stop()
        return start() if ok else (ok, err)
    return False, "invalid action"
