"""
Golden capture recorder + Frame Inspector compare.

Endpoints:
  POST /api/trace/<filename>/save-as-golden/<device_id>
    → copies logs/trace/<filename> to tests/fixtures/golden/<device_id>/
      so it becomes a regression fixture automatically

  GET  /api/sample/<a>/compare/<b>
    → returns a side-by-side diff of two conversion audits
"""
from __future__ import annotations

import shutil
from pathlib import Path

from flask import Blueprint, jsonify, render_template

from src.common.history import get_audit
from webui.blueprints._helpers import require_role

golden_bp = Blueprint("golden", __name__)


@golden_bp.route("/compare", methods=["GET"])
@require_role("admin")
def compare_page():
    return render_template("compare.html")


@golden_bp.route("/api/trace/<path:filename>/save-as-golden/<device_id>",
                  methods=["POST"])
@require_role("operator")
def save_as_golden(filename: str, device_id: str):
    if "/" in filename or ".." in filename or "\\" in filename:
        return jsonify({"ok": False, "error": "invalid filename",
                        "code": "E5001_CONFIG_INVALID"}), 400
    src = Path("logs/trace") / filename
    if not src.exists():
        return jsonify({"ok": False, "error": "trace file not found",
                        "code": "E1010_AUDIT_MISSING"}), 404
    dest_dir = Path("tests/fixtures/golden") / device_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{src.stem}.in.bin"
    shutil.copy2(src, dest)
    return jsonify({"ok": True, "saved_to": str(dest),
                    "next_step": "Run pytest tests/test_golden.py "
                                  f"-k {src.stem} to activate the fixture"})


@golden_bp.route("/api/sample/<a>/compare/<b>", methods=["GET"])
@require_role("operator")
def compare_samples(a: str, b: str):
    audit_a = get_audit(a)
    audit_b = get_audit(b)
    if not audit_a or not audit_b:
        return jsonify({"ok": False, "error": "one or both samples not found",
                        "code": "E1010_AUDIT_MISSING",
                        "found_a": bool(audit_a), "found_b": bool(audit_b)}), 404

    changes_a = {c["sent"]["code"]: c for c in audit_a["audit"]["changes"]}
    changes_b = {c["sent"]["code"]: c for c in audit_b["audit"]["changes"]}
    analytes = sorted(set(changes_a) | set(changes_b))
    diff = []
    for a_code in analytes:
        ca = changes_a.get(a_code)
        cb = changes_b.get(a_code)
        if ca and cb:
            diff.append({
                "analyte":    a_code,
                "value_a":    ca["sent"]["value"], "value_b": cb["sent"]["value"],
                "changed":    ca["sent"]["value"] != cb["sent"]["value"],
            })
        elif ca:
            diff.append({"analyte": a_code, "value_a": ca["sent"]["value"],
                          "value_b": None, "only_in": "a"})
        else:
            diff.append({"analyte": a_code, "value_a": None,
                          "value_b": cb["sent"]["value"], "only_in": "b"})
    return jsonify({
        "ok":       True,
        "sample_a": {"sample_id": a, "device": audit_a["device"], "ts": audit_a["ts"]},
        "sample_b": {"sample_id": b, "device": audit_b["device"], "ts": audit_b["ts"]},
        "diff":     diff,
        "warnings_a": audit_a["audit"].get("warnings", []),
        "warnings_b": audit_b["audit"].get("warnings", []),
    })
