"""
One place to answer "where does the gateway install tree live?".

The gateway historically used ``Path("config/xxx")`` — relative to whatever
``os.getcwd()`` happened to be when the process started. That works when
systemd starts it with ``WorkingDirectory=/opt/jerumednexus`` but breaks
the moment anyone launches Python from another directory (installer, cron,
manual debug, unit test).

This module resolves the install root in three passes, first hit wins:

  1. ``JMNX_INSTALL_ROOT`` environment variable  (systemd unit sets this)
  2. The parent-of-parent-of-parent of this file (works from a repo checkout
     or from ``/opt/jerumednexus/src/common/paths.py``)
  3. ``/opt/jerumednexus`` (final fallback for legacy call sites)

Callers should always prefer:

    from src.common.paths import install_root, config_dir
    p = config_dir() / "webui_password.hash"

instead of ``Path("config/webui_password.hash")``.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

_ENV_VAR = "JMNX_INSTALL_ROOT"
_LEGACY_DEFAULT = Path("/opt/jerumednexus")


@lru_cache(maxsize=1)
def install_root() -> Path:
    """Absolute path to the project's install/checkout root."""
    env = os.environ.get(_ENV_VAR)
    if env:
        p = Path(env).expanduser().resolve()
        if p.is_dir():
            return p

    # src/common/paths.py  →  .parent = src/common
    #                        .parent = src
    #                        .parent = <project root>
    here = Path(__file__).resolve()
    candidate = here.parent.parent.parent
    if (candidate / "main.py").is_file() or (candidate / "pyproject.toml").is_file():
        return candidate

    return _LEGACY_DEFAULT


def config_dir() -> Path:
    """Anchor for everything under ``config/``. Ensured to exist."""
    d = install_root() / "config"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:
        # Read-only FS (tests) — callers still get a valid Path.
        pass
    return d


def logs_dir() -> Path:
    """Anchor for runtime logs / status / seen_samples / DLQ / WAL."""
    d = install_root() / "logs"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return d
