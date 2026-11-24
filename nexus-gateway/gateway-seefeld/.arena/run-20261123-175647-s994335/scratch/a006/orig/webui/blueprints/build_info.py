"""Build info endpoint — powers the /api/build call and README badges."""
from __future__ import annotations

import subprocess
import time
from pathlib import Path

from flask import Blueprint, jsonify

build_info_bp = Blueprint("build_info", __name__)


def _read_version() -> str:
    try:
        for line in Path("pyproject.toml").read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("version"):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return "unknown"


def _git_sha() -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                           capture_output=True, text=True, timeout=1)
        return r.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


@build_info_bp.route("/api/build", methods=["GET"])
def api_build():
    return jsonify({
        "version":   _read_version(),
        "git_sha":   _git_sha(),
        "product":   "jerumednexus-gateway",
        "vendor":    "Jerumed Nexus GmbH",
        "boot_ts":   time.time(),
    })


@build_info_bp.route("/api/build/badge.json", methods=["GET"])
def api_build_badge():
    """shields.io-compatible endpoint for README status badges."""
    return jsonify({
        "schemaVersion": 1,
        "label":         "gateway",
        "message":       _read_version(),
        "color":         "brightgreen",
    })
