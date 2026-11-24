"""Dead-letter queue endpoints (operator+)."""
from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request, session

from src.common.dead_letter import list_dead_letters, read_dead_letter
from src.security.audit import AuditEvent, audit
from webui.blueprints._helpers import client_ip, csrf_check, require_role, run_async

log = logging.getLogger("webui.dlq")

dlq_bp = Blueprint("dlq", __name__)


@dlq_bp.route("/api/dlq", methods=["GET"])
@require_role("operator")
def api_dlq_list():
    return jsonify({"entries": list_dead_letters(
        limit=int(request.args.get("limit", 100)))})


@dlq_bp.route("/api/dlq/<control_id>", methods=["GET"])
@require_role("operator")
def api_dlq_get(control_id: str):
    body = read_dead_letter(control_id)
    if body is None:
        return jsonify({"ok": False, "error": "not found"}), 404
    return jsonify({"ok": True, "control_id": control_id, "hl7": body})


@dlq_bp.route("/api/dlq/<control_id>/replay", methods=["POST"])
@require_role("operator")
def api_dlq_replay(control_id: str):
    if not csrf_check():
        return jsonify({"ok": False, "error": "CSRF token invalido"}), 400
    body = read_dead_letter(control_id)
    if body is None:
        return jsonify({"ok": False, "error": "not found"}), 404

    body_json = request.get_json(silent=True) or {}
    only_targets = body_json.get("targets") or []

    # Load current config for the dispatcher instance we'll build.
    from pathlib import Path
    import yaml as _yaml
    from config.settings import GatewayConfig, _risolvi_segreti
    from src.hl7.builder import HL7Message
    from src.transport.dispatcher import Dispatcher

    try:
        cfg_raw = _yaml.safe_load(
            (Path("config/gateway.yaml").read_text(encoding="utf-8"))) or {}
        # I segreti possono essere dichiarati come nome di variabile
        # d'ambiente: senza risolverli il rispedisci partirebbe con una
        # password vuota e fallirebbe per un motivo che non c'entra.
        cfg_raw = _risolvi_segreti(cfg_raw)
    except Exception as exc:
        return jsonify({"ok": False, "error": f"config parse: {exc}"}), 500

    if only_targets:
        cfg_raw = {**cfg_raw,
                   "targets": [t for t in cfg_raw.get("targets", [])
                               if t.get("name") in only_targets]}
    # Tutto in un blocco solo: senza, qualunque eccezione diventava una
    # pagina HTML di errore, il browser provava a leggerla come JSON e
    # mostrava "SyntaxError: The string did not match the expected pattern".
    # Un messaggio che non dice niente a nessuno e che nascondeva la causa
    # vera -- nel nostro caso un referto che il validatore rifiutava.
    try:
        replay_cfg = GatewayConfig.model_validate(cfg_raw)
        segments = [s for s in body.split(chr(13)) if s.strip()]
        msg = HL7Message(segments, msh_control_id=control_id,
                         charset=replay_cfg.hl7.charset)
        dispatcher = Dispatcher(replay_cfg)
        summary = run_async(dispatcher.dispatch(msg, {
            "sample_id": f"REPLAY_{control_id}",
            "patient_id": "REPLAY",
            "device": "DLQ_REPLAY",
            "observations": [],
        }))
    except Exception as exc:
        log.exception("Rispedizione di %s non riuscita", control_id)
        return jsonify({"ok": False,
                        "error": f"{type(exc).__name__}: {exc}"}), 500

    audit(AuditEvent.SERVICE_ACTION, ip=client_ip(),
          actor=session.get("username", "?"),
          detail={"replay": control_id, "summary": summary.to_dict()})
    # Se nessun gestionale ha accettato il messaggio, il motivo sta negli
    # errori per-destinatario: va restituito, non lasciato solo nei log.
    errori = "; ".join(f"{nome}: {e}" for nome, e
                       in (summary.to_dict().get("errors") or {}).items())
    return jsonify({"ok": bool(summary.succeeded),
                    "error": errori or None,
                    "summary": summary.to_dict()})
