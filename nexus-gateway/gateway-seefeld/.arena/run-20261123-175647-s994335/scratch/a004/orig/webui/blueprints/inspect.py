"""
Frame Inspector — side-by-side view of raw device payload vs HL7 sent to
the LIS, plus every conversion transform and plausibility warning.

Answers the operator's question: "come faccio a sapere se il gateway ha
cambiato qualcosa senza che nessuno se ne accorga?"

Endpoints (all require operator role — the raw payload contains PHI):
    GET  /api/sample/<sample_id>/audit           JSON audit trail
    GET  /api/sample/<sample_id>/audit/download  JSON with attachment header
    GET  /inspect/<sample_id>                    HTML side-by-side inspector
    GET  /inspect                                Search box + recent samples list
    POST /api/sample/<sample_id>/resend          Re-dispatch a sample to the PIS

    POST /api/ingest      HL7 v2 or JSON payload with Idempotency-Key header
                          (RFC-9110-compatible: safe retry — same key + same
                          body returns the recorded response)
"""
from __future__ import annotations

import json
from datetime import datetime

from flask import Blueprint, Response, jsonify, render_template, request, session

from src.common.history import get_audit, get_payload, search
from src.common.idempotency import get as idem_get, store as idem_store
from src.security.audit import AuditEvent, audit as security_audit
from webui.blueprints._helpers import client_ip, csrf_check, require_role, run_async

inspect_bp = Blueprint("inspect", __name__)


@inspect_bp.route("/api/sample/<path:sample_id>/audit", methods=["GET"])
@require_role("operator")
def api_sample_audit(sample_id: str):
    data = get_audit(sample_id)
    if not data:
        return jsonify({"ok": False, "error": "not found",
                        "code": "E1010_AUDIT_MISSING"}), 404
    # Record who inspected which sample (PHI adjacent).  audit() accepts a
    # plain string as well as an AuditEvent member, and there is no enum
    # member for this one; the previous AuditEvent(action=...) call raised
    # TypeError on every request and the except swallowed it, so nobody was
    # ever traced.
    security_audit("frame.inspect",
                   actor=session.get("username", "?"),
                   ip=client_ip(),
                   detail={"sample_id": sample_id})
    return jsonify({"ok": True, **data})


@inspect_bp.route("/inspect", methods=["GET"])
@require_role("operator")
def inspect_index():
    recent = search(limit=25)
    return render_template("frame_inspector_index.html", recent=recent)


@inspect_bp.route("/inspect/<path:sample_id>", methods=["GET"])
@require_role("operator")
def inspect_sample(sample_id: str):
    data = get_audit(sample_id)
    return render_template("frame_inspector.html",
                           sample_id=sample_id,
                           data=data)


@inspect_bp.route("/api/sample/<path:sample_id>/audit/download", methods=["GET"])
@require_role("operator")
def api_sample_audit_download(sample_id: str):
    """Return audit as downloadable JSON — attach to support tickets."""
    data = get_audit(sample_id)
    if not data:
        return jsonify({"ok": False, "error": "not found",
                        "code": "E1010_AUDIT_MISSING"}), 404
    filename = f"audit-{sample_id}.json"
    body = json.dumps(data, ensure_ascii=False, indent=2)
    return Response(
        body,
        mimetype="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@inspect_bp.route("/api/sample/<path:sample_id>/resend", methods=["POST"])
@require_role("operator")
def api_sample_resend(sample_id: str):
    """
    Re-dispatch a sample that the PIS never picked up.

    Two modes, chosen automatically:
      * ``rebuilt``  -- the parsed result was kept, so the message is built
        again with the CURRENT gateway.yaml. This is what you want after a
        header/format fix: the resent message carries the corrections.
      * ``verbatim`` -- only the original HL7 survives, so the exact same
        bytes go out again. Use when the file was simply lost in transit.

    Rows recorded before this feature existed have neither and return 409 --
    better an explicit refusal than a half-reconstructed message.

    Optional JSON body: ``{"targets": ["tomedo"]}`` limits the fan-out.
    """
    if not csrf_check():
        return jsonify({"ok": False, "error": "CSRF token invalido"}), 400

    payload = get_payload(sample_id)
    if not payload:
        return jsonify({"ok": False, "error": f"sample {sample_id!r} non trovato",
                        "code": "E1010_AUDIT_MISSING"}), 404
    if not payload.get("result") and not payload.get("hl7"):
        return jsonify({
            "ok": False,
            "code": "E1011_PAYLOAD_NOT_KEPT",
            "error": "Questo sample è stato registrato prima che il gateway "
                     "conservasse il messaggio: non c'è nulla da reinviare. "
                     "I risultati elaborati d'ora in poi saranno reinviabili.",
        }), 409

    from pathlib import Path as _P
    import yaml as _yaml
    from config.settings import GatewayConfig
    from src.hl7.builder import HL7Builder, HL7Message
    from src.transport.dispatcher import Dispatcher

    try:
        cfg_raw = _yaml.safe_load(
            _P("config/gateway.yaml").read_text(encoding="utf-8")) or {}
    except Exception as exc:
        return jsonify({"ok": False, "error": f"config parse: {exc}"}), 500

    only_targets = (request.get_json(silent=True) or {}).get("targets") or []
    if only_targets:
        cfg_raw = {**cfg_raw,
                   "targets": [t for t in cfg_raw.get("targets", [])
                               if t.get("name") in only_targets]}
    try:
        cfg = GatewayConfig.model_validate(cfg_raw)
    except Exception as exc:
        return jsonify({"ok": False, "error": f"config non valida: {exc}"}), 500
    if not cfg.targets:
        return jsonify({"ok": False,
                        "error": "nessun gestionale abilitato in gateway.yaml"}), 409

    result = payload.get("result")
    if result:
        # JSON round-trip turned the timestamp into a string; give the builder
        # a datetime back so the resent message keeps the ORIGINAL sample time
        # instead of silently becoming "now".
        ts = result.get("timestamp")
        if isinstance(ts, str):
            try:
                result["timestamp"] = datetime.fromisoformat(ts)
            except ValueError:
                result.pop("timestamp", None)
        msg = HL7Builder(cfg.hl7).build_oru_r01(result)
        mode = "rebuilt"
    else:
        segments = [seg for seg in payload["hl7"].split(chr(13)) if seg.strip()]
        msg = HL7Message(segments,
                         msh_control_id=payload.get("control_id") or "",
                         charset=cfg.hl7.charset)
        result = {
            "sample_id":    sample_id,
            "patient_id":   payload.get("patient_id", ""),
            "device":       payload.get("device", ""),
            "observations": [],
        }
        mode = "verbatim"

    summary = run_async(Dispatcher(cfg).dispatch(msg, result))
    security_audit(AuditEvent.SERVICE_ACTION, ip=client_ip(),
                   actor=session.get("username", "?"),
                   detail={"resend": sample_id, "mode": mode,
                           "summary": summary.to_dict()})
    return jsonify({"ok": bool(summary.succeeded), "mode": mode,
                    "sample_id": sample_id, "summary": summary.to_dict()})


@inspect_bp.route("/api/ingest", methods=["POST"])
@require_role("operator")
def api_ingest():
    """
    Ingest an HL7 v2 message or JSON payload via HTTP. Honors the
    Idempotency-Key header (RFC 9110) so client retries do not cause
    duplicate dispatches.
    """
    key = request.headers.get("Idempotency-Key", "").strip()
    body = request.get_data(cache=True) or b""

    if key:
        prev = idem_get(key, body)
        if prev is not None:
            status, response = prev
            return jsonify({**response, "idempotent_replay": True}), status

    # Minimal ingest surface — the real dispatch pipeline is queue-driven
    # from adapters. HTTP ingest is here for order-side APIs and testing.
    try:
        if request.mimetype == "application/json":
            payload = request.get_json(force=True, silent=False)
        else:
            payload = {"hl7": body.decode("utf-8", errors="replace")}
        # Questo endpoint accetta e restituisce l'eco: NON instrada ancora
        # niente. Rispondeva "ok": true senza dirlo, e un chiamante poteva
        # credere che il messaggio fosse stato consegnato. `routed` lo dice.
        response = {"ok": True, "routed": False, "received_bytes": len(body),
                    "content_type": request.mimetype,
                    "fields": len(payload) if isinstance(payload, dict) else 0,
                    "sha_hint": (body[:80].hex() if body else "")}
        status = 202
    except Exception as exc:
        response = {"ok": False, "error": "bad payload",
                    "code": "E5001_CONFIG_INVALID", "detail": str(exc)}
        status = 400

    if key:
        idem_store(key, body, status, response)
    return jsonify(response), status
