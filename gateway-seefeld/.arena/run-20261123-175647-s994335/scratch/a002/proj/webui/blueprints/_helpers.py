"""
Helpers shared by blueprints.

We avoid importing from ``webui.app`` to keep blueprints stand-alone; the
app registers session/CSRF helpers on the ``current_app.config`` at start,
and blueprints read them from there.
"""
from __future__ import annotations

import asyncio
import hmac
import threading
from functools import wraps
from typing import Optional  # noqa: F401 -- used in type hints below

from flask import abort, jsonify, redirect, request, session, url_for


def client_ip() -> str:
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.remote_addr or "unknown"


def csrf_check() -> bool:
    supplied = request.form.get("_csrf") or request.headers.get("X-CSRF-Token", "")
    expected = session.get("_csrf", "")
    return bool(expected) and hmac.compare_digest(str(supplied), str(expected))


def logged_in() -> bool:
    return bool(session.get("auth_id"))


def current_role() -> str:
    return session.get("role", "viewer")


def require_role(needed: str):
    from src.security import roles as _roles

    def deco(f):
        @wraps(f)
        def wrapped(*a, **kw):
            if _roles.is_setup_required():
                return redirect(url_for("setup"))
            if not logged_in():
                return redirect(url_for("login"))
            if not _roles.require_role(current_role(), needed):
                if request.path.startswith("/api/"):
                    return jsonify({"ok": False, "error": "forbidden: role too low"}), 403
                abort(403)
            return f(*a, **kw)
        return wrapped
    return deco


def require_local(f):
    @wraps(f)
    def wrapped(*a, **kw):
        ip = client_ip()
        if ip not in ("127.0.0.1", "::1", "localhost"):
            abort(403)
        return f(*a, **kw)
    return wrapped


# Persistent worker loop -- one thread per Flask process, one asyncio loop.
# Coroutines from Flask handlers are submitted to this loop, avoiding a
# thread + loop spin-up per request.
_worker_loop: Optional[asyncio.AbstractEventLoop] = None
_worker_thread: Optional[threading.Thread] = None
_worker_lock = threading.Lock()


def _ensure_worker() -> asyncio.AbstractEventLoop:
    global _worker_loop, _worker_thread
    with _worker_lock:
        if _worker_loop is not None and _worker_thread and _worker_thread.is_alive():
            return _worker_loop
        loop = asyncio.new_event_loop()

        def _run():
            asyncio.set_event_loop(loop)
            loop.run_forever()

        t = threading.Thread(target=_run, name="webui-async-worker", daemon=True)
        t.start()
        _worker_loop = loop
        _worker_thread = t
        return loop


def run_async(coro):
    """
    Submit a coroutine to the persistent webui worker loop and wait for it.
    Safer + cheaper than spinning a fresh thread/loop per request.
    """
    loop = _ensure_worker()
    fut = asyncio.run_coroutine_threadsafe(coro, loop)
    return fut.result()
