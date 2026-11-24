"""
First-run configuration wizard — 7 guided steps, zero terminal editing.

Design goals:
  * Every step has a large form + side panel with instructions
  * Every step tests something before allowing "Next" (no silent misconfig)
  * Progress bar always visible; Back/Next always visible
  * State persisted in session — browser refresh doesn't lose progress
  * All state saved to config/ on final "Enable & start" click

Steps:
  1. Language + clinic info      (facility name, city, timezone)
  2. Admin account               (password + optional TOTP)
  3. Network check               (LAN IP, gateway reachability)
  4. First device                (model dropdown, connection type, port, test)
  5. First target LIS/HIS        (type, host, port, test connection)
  6. Backup                      (NAS path OR skip)
  7. Verify & start              (systemctl-like start + /readyz)
"""
from __future__ import annotations

import socket
from pathlib import Path
from typing import Any

from flask import (Blueprint, abort, jsonify, make_response, redirect,
                   render_template, request,
                   session, url_for)

wizard_bp = Blueprint("wizard", __name__, url_prefix="/wizard")


@wizard_bp.before_request
def _solo_primo_avvio_o_admin():
    """
    La configurazione guidata E' il primo avvio, non una pagina del portale.

    Finche' non esiste nessun utente resta aperta a tutti: e' l'unico modo per
    creare il primo amministratore su un Raspberry appena installato. Appena un
    utente esiste, serve essere amministratori.

    Senza questo controllo il wizard non aveva NESSUNA protezione: chiunque
    raggiungesse la WebUI poteva rilanciarlo e, al passo 2, reimpostare la
    password di admin senza autenticarsi.
    """
    from src.security import roles as _roles

    if _roles.is_setup_required():
        return None
    if not session.get("auth_id"):
        return redirect(url_for("login"))
    if session.get("role") != "admin":
        abort(403)
    return None

TOTAL_STEPS = 7

# ── State plumbing ────────────────────────────────────────────────────────────

def _state() -> dict[str, Any]:
    if "wizard" not in session:
        session["wizard"] = {"step": 1, "data": {}}
    return session["wizard"]


def _save(data: dict[str, Any]) -> None:
    st = _state()
    st["data"].update(data)
    session["wizard"] = st
    session.modified = True


def _goto(step: int):
    st = _state()
    st["step"] = max(1, min(TOTAL_STEPS, step))
    session["wizard"] = st
    session.modified = True
    return redirect(url_for(f"wizard.step_{st['step']}"))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_device_templates() -> list[dict[str, str]]:
    root = Path("config/devices")
    out: list[dict[str, str]] = []
    if not root.exists():
        return out
    import yaml
    for f in sorted(root.glob("*.yaml")):
        try:
            data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
            out.append({
                "id":       data.get("id", f.stem),
                "display":  data.get("display_name", data.get("id", "")),
                "vendor":   data.get("vendor", ""),
                "model":    data.get("model", ""),
                "type":     data.get("type", ""),
                "template": f.name,
            })
        except Exception:
            continue
    return out


def _tcp_probe(host: str, port: int, timeout: float = 2.0) -> tuple[bool, str]:
    """Return (reachable, message)."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, f"{host}:{port} raggiungibile"
    except socket.timeout:
        return False, f"timeout su {host}:{port}"
    except OSError as exc:
        return False, f"{host}:{port} non raggiungibile ({exc})"


def _lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


# ── Router ────────────────────────────────────────────────────────────────────

@wizard_bp.route("", methods=["GET"])
def index():
    st = _state()
    return redirect(url_for(f"wizard.step_{st['step']}"))


@wizard_bp.route("/reset", methods=["POST"])
def reset():
    session.pop("wizard", None)
    return redirect(url_for("wizard.index"))


# ── Step 1: Language + clinic info ────────────────────────────────────────────

@wizard_bp.route("/1", methods=["GET", "POST"])
def step_1():
    if request.method == "POST":
        _save({
            "language":      request.form.get("language", "de"),
            "facility_name": request.form.get("facility_name", "").strip(),
            "recipient_name": request.form.get("recipient_name", "").strip(),
            "facility_city": request.form.get("facility_city", "").strip(),
            "timezone":      request.form.get("timezone", "Europe/Zurich"),
        })
        # The language picked here is the interface language: apply it right
        # away (it used to be stored and never used).
        from webui.i18n import set_lang_cookie
        return set_lang_cookie(make_response(_goto(2)),
                               request.form.get("language", "de"))
    return render_template("wizard/step_1.html",
                           step=1, total=TOTAL_STEPS, data=_state()["data"])


# ── Step 2: Admin account ────────────────────────────────────────────────────

@wizard_bp.route("/2", methods=["GET", "POST"])
def step_2():
    error = None
    if request.method == "POST":
        pw = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        if len(pw) < 10:
            error = "La password deve avere almeno 10 caratteri."
        elif pw != confirm:
            error = "Le due password non coincidono."
        else:
            try:
                from src.security.auth import save_password
                from src.security import roles as _roles
                save_password(pw)
                # save_password() writes the legacy hash file, which roles._load()
                # auto-migrates as an admin user. So by the time we get here, admin
                # already "exists" -- we must update instead of trying to create.
                if _roles.user_exists("admin"):
                    _roles.update_password("admin", pw)
                else:
                    _roles.create_user("admin", pw, "admin")
                _save({"admin_created": True, "admin_username": "admin"})
                return _goto(3)
            except Exception as exc:
                error = f"Errore nella creazione dell'utente: {exc}"
    return render_template("wizard/step_2.html",
                           step=2, total=TOTAL_STEPS,
                           data=_state()["data"], error=error)


# ── Step 3: Network check ────────────────────────────────────────────────────

@wizard_bp.route("/3", methods=["GET", "POST"])
def step_3():
    if request.method == "POST":
        _save({
            "pi_ip":          request.form.get("pi_ip", _lan_ip()),
            "lis_hint":       request.form.get("lis_hint", "").strip(),
            "network_confirmed": True,
        })
        return _goto(4)
    return render_template("wizard/step_3.html",
                           step=3, total=TOTAL_STEPS,
                           data=_state()["data"], detected_ip=_lan_ip())


# ── Step 4: First device ─────────────────────────────────────────────────────

@wizard_bp.route("/4", methods=["GET", "POST"])
def step_4():
    templates = _load_device_templates()
    if request.method == "POST":
        # SKIP path: user chose to add devices later via the plug-and-play
        # dashboard tile (recommended). Either the skip button was clicked,
        # or the dropdown was left empty.
        skip = request.form.get("skip") == "1" or not request.form.get("template", "").strip()
        if skip:
            _save({"first_device": None, "first_device_skipped": True})
            return _goto(5)
        chosen = request.form.get("template", "")
        listen_port = int(request.form.get("listen_port", "5006"))
        display_name = request.form.get("display_name", "").strip()
        # Copy the template into a live enabled device profile.
        import yaml
        src = Path("config/devices") / chosen
        if not src.exists():
            return render_template("wizard/step_4.html",
                                   step=4, total=TOTAL_STEPS,
                                   templates=templates, data=_state()["data"],
                                   error=f"Template {chosen!r} non trovato")
        data = yaml.safe_load(src.read_text(encoding="utf-8")) or {}
        data["enabled"]      = True
        data["listen_port"]  = listen_port
        if display_name:
            data["display_name"] = display_name
        target = Path("config/devices") / f"{data['id']}_active.yaml"
        target.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
        _save({"first_device": data["id"], "first_device_port": listen_port})
        return _goto(5)
    return render_template("wizard/step_4.html",
                           step=4, total=TOTAL_STEPS,
                           templates=templates, data=_state()["data"])


# ── Step 5: First target LIS/HIS ────────────────────────────────────────────

@wizard_bp.route("/5", methods=["GET", "POST"])
def step_5():
    if request.method == "POST":
        _save({
            "target_kind": request.form.get("target_kind", "mllp_hl7"),
            "target_host": request.form.get("target_host", "").strip(),
            "target_port": int(request.form.get("target_port", "2575")),
            "target_name": request.form.get("target_name", "").strip() or "LIS",
        })
        return _goto(6)
    return render_template("wizard/step_5.html",
                           step=5, total=TOTAL_STEPS,
                           data=_state()["data"])


# ── Step 6: Backup ───────────────────────────────────────────────────────────

@wizard_bp.route("/6", methods=["GET", "POST"])
def step_6():
    if request.method == "POST":
        _save({
            "backup_kind":   request.form.get("backup_kind", "none"),
            "backup_path":   request.form.get("backup_path", "").strip(),
            "backup_gpg":    request.form.get("backup_gpg", "").strip(),
        })
        return _goto(7)
    return render_template("wizard/step_6.html",
                           step=6, total=TOTAL_STEPS,
                           data=_state()["data"])


# ── Step 7: Verify & start ───────────────────────────────────────────────────

# Wizard "target_kind" (UI dropdown value) → PISTarget.type (schema literal).
# PISTarget only accepts the closed set defined in config.settings; anything
# outside it would make load_config() fail and the gateway refuse to boot.
_TARGET_KIND_TO_TYPE = {
    "mllp_hl7":        "generic_hl7_mllp",
    "generic_hl7":     "generic_hl7_mllp",
    "generic_hl7_mllp": "generic_hl7_mllp",
    "vitomed":         "vitomed",
    "curamed":         "curamed",
    "aeskulap":        "aeskulap",
    "axenita":         "axenita",
    "winmed":          "winmed",
    "dnamed":          "dnamed",
    "tomedo":          "tomedo",
    "file_drop":       "file_drop",
    "fhir":            "fhir_r4",
    "fhir_r4":         "fhir_r4",
}


def _merge_wizard_into_config(existing: dict, data: dict) -> dict:
    """
    Overlay the wizard's answers on top of whatever config the installer
    (or a previous wizard run) already wrote. Preserves keys the wizard
    doesn't touch: ``devices:``, retention, breakers, etc.
    """
    cfg = dict(existing or {})

    # HL7 section — facility name lives here per GatewayConfig schema.
    hl7 = dict(cfg.get("hl7") or {})
    # MSH-4 e MSH-6 sono DUE COSE DIVERSE: da chi arriva il referto, e a chi
    # e' indirizzato. Scrivere il primo in entrambi e' il guasto che ha
    # fermato le consegne per due giorni -- il gestionale riceve i file, li
    # legge, e non li assegna piu' a nessun paziente.
    facility = (data.get("facility_name") or "").strip() or "PRAXIS"
    destinatario = (data.get("recipient_name") or "").strip()
    hl7["sending_facility"] = facility
    # Se il destinatario non e' stato indicato si lascia vuoto, invece di
    # copiarvi il mittente: un valore sbagliato e' peggio di uno mancante,
    # perche' sembra configurato. Verifica impianto lo segnala subito.
    hl7["receiving_facility"] = destinatario

    # 2.3 + 8859/1 e' il formato che Tomedo importa davvero, verificato
    # contro un file archiviato e assegnato. I valori precedenti erano
    # 2.5 + UTF-8, cioe' esattamente la combinazione che l'installer stesso
    # documenta come da non usare mai: Tomedo archivia il file e lo rifiuta.
    hl7.setdefault("version",               "2.3")
    hl7.setdefault("sending_application",   "JMNX_GW")
    hl7.setdefault("receiving_application", "LIS")
    hl7.setdefault("charset",               "8859/1")
    # +0200 nei timestamp: Tomedo con questo attivo smette di riconoscere i
    # referti. Si accende dalla pagina Configurazione se serve davvero.
    hl7.setdefault("include_timezone",      False)
    cfg["hl7"] = hl7

    # Wizard-specific fields (not part of GatewayConfig — pydantic ignores
    # unknown top-level keys, so keeping them is harmless and lets the UI
    # remember the operator's choices without spinning up another store).
    cfg["praxis"] = {
        "name":     facility,
        "city":     data.get("facility_city", ""),
        "timezone": data.get("timezone", "Europe/Zurich"),
        "language": data.get("language", "de"),
        "pi_ip":    data.get("pi_ip", ""),
    }

    # Targets — map the wizard's `target_kind` label onto a schema-legal
    # PISTarget.type. Preserve any pre-existing targets, replacing only
    # the wizard-managed name.
    kind = str(data.get("target_kind", "mllp_hl7"))
    target_type = _TARGET_KIND_TO_TYPE.get(kind, "generic_hl7_mllp")
    target_name = (data.get("target_name") or "").strip() or "LIS"

    new_target: dict = {
        "name":    target_name,
        "type":    target_type,
        "enabled": True,
    }
    if target_type in ("file_drop", "winmed", "tomedo"):
        new_target["watch_folder"] = data.get("target_host", "").strip() or "/tmp/lis_import"
        new_target["file_extension"] = ".hl7"
    else:
        new_target["host"] = data.get("target_host", "").strip() or "127.0.0.1"
        try:
            new_target["port"] = int(data.get("target_port", 2575))
        except (TypeError, ValueError):
            new_target["port"] = 2575

    existing_targets = list(cfg.get("targets") or [])
    existing_targets = [t for t in existing_targets if t.get("name") != target_name]
    existing_targets.append(new_target)
    cfg["targets"] = existing_targets

    # Backup block — kept only when the operator opted in.
    if data.get("backup_kind") and data["backup_kind"] != "none":
        cfg["backup"] = {
            "kind":          data["backup_kind"],
            "path":          data.get("backup_path", ""),
            "gpg_recipient": data.get("backup_gpg", ""),
        }
    elif "backup" in cfg:
        cfg.pop("backup", None)

    return cfg


@wizard_bp.route("/7", methods=["GET", "POST"])
def step_7():
    if request.method == "POST":
        data = _state()["data"]
        try:
            import yaml
            cfg_path = Path("config/gateway.yaml")
            existing: dict = {}
            if cfg_path.exists():
                try:
                    existing = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
                except Exception:
                    existing = {}
            cfg = _merge_wizard_into_config(existing, data)
            cfg_path.parent.mkdir(parents=True, exist_ok=True)
            cfg_path.write_text(
                yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

        # Setup is finished — force operator through the login page so the
        # session gets the right role + audit-log entry.
        session.pop("wizard", None)
        return redirect(url_for("login"))

    return render_template("wizard/step_7.html",
                           step=7, total=TOTAL_STEPS,
                           data=_state()["data"])


# ── Test endpoints (AJAX called from side panels) ─────────────────────────────

@wizard_bp.route("/test/tcp", methods=["POST"])
def test_tcp():
    body = request.get_json(force=True, silent=True) or {}
    host = str(body.get("host", "")).strip()
    port = int(body.get("port", 0) or 0)
    if not host or not port:
        return jsonify({"ok": False, "message": "host e porta obbligatori"}), 400
    ok, msg = _tcp_probe(host, port)
    return jsonify({"ok": ok, "message": msg})


@wizard_bp.route("/test/self", methods=["POST"])
def test_self():
    """Test the Pi's own reachability by hitting our own WebUI port."""
    # The port we're listening on is whatever the current request came in
    # over — that's the ground truth, regardless of HTTP/HTTPS or the value
    # env overrides may have set.
    import os as _os
    port = 0
    try:
        port = int(request.host.split(":")[-1])
    except (ValueError, AttributeError):
        pass
    if not port:
        try:
            port = int(_os.environ.get("WEBUI_PORT", "8080"))
        except ValueError:
            port = 8080
    ok, msg = _tcp_probe("127.0.0.1", port, timeout=1.0)
    return jsonify({"ok": ok, "message": msg,
                    "lan_ip": _lan_ip(),
                    "port": port})
