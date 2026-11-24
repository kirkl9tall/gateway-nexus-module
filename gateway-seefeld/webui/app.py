"""
webui/app.py
Flask web server — serves the configuration UI, dashboard and REST API.
Runs on port 8080 on the Raspberry Pi.
Access: http://<raspberry-pi-ip>:8080

Auth: bcrypt password (see src/security/auth.py).
First-run: /setup wizard when no password hash is present.
Sessions: signed by persistent secret key, 8h lifetime.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import platform
import re
import subprocess
import sys
import time
import uuid
from collections import defaultdict, deque
from datetime import date as _date
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path
from typing import Any, Dict

from flask import (
    Flask, abort, jsonify, redirect, render_template, request, session, url_for,
)
from werkzeug.middleware.proxy_fix import ProxyFix

BASE_DIR = Path(__file__).parent.parent

# ensure "src" and "config" imports work when invoked from anywhere
sys.path.insert(0, str(BASE_DIR))

from src.security.auth import (  # noqa: E402
    MIN_PASSWORD_LEN,
    generate_session_token,
    get_or_create_secret_key,
    save_password,
)
from src.security.audit import (  # noqa: E402
    AuditEvent,
    audit,
)
from src.security import roles as _roles  # noqa: E402
from webui.blueprints import (  # noqa: E402
    build_info_bp, bulk_dlq_bp, dlq_bp, discovery_bp, fleet_bp, golden_bp,
    inspect_bp, metrics_bp, qr_bp, topology_bp, users_bp, verifica_bp,
    wire_replay_bp, wizard_bp,
)


def is_setup_required():
    """Setup is required only when no user exists in the roles store."""
    return _roles.is_setup_required()


def validate_login(username, password):
    return _roles.validate_login(username, password)

# Anchor persistent files to install_root() so the WebUI works from any CWD
# and every test can override JMNX_INSTALL_ROOT to get isolated state.
from src.common.paths import config_dir as _config_dir, logs_dir as _logs_dir
CONFIG_F  = _config_dir() / "gateway.yaml"
LICENSE_F = _config_dir() / "license.json"
STATUS_F  = _logs_dir()   / "status.json"

app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = get_or_create_secret_key()
# If deployed behind a reverse proxy (Caddy / nginx), honour X-Forwarded-*.
# Configure the proxy count in env if you have multiple hops.
_proxy_hops = int(os.environ.get("WEBUI_PROXY_HOPS", "1"))
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=_proxy_hops, x_proto=_proxy_hops,
                        x_host=_proxy_hops, x_prefix=_proxy_hops)
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=8)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
# Set SESSION_COOKIE_SECURE=true when serving behind TLS
if os.environ.get("WEBUI_HTTPS", "").lower() in ("1", "true", "yes"):
    app.config["SESSION_COOKIE_SECURE"] = True

# ── Rate limiting (in-memory, per-IP) ─────────────────────────────────────────

_LOGIN_ATTEMPTS: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=20))
_LOGIN_WINDOW_SEC = 300      # 5 min
_LOGIN_MAX_ATTEMPTS = 5
_LOGIN_LOCKOUT_SEC = 900     # 15 min lockout after threshold
_LOGIN_LOCKED_UNTIL: dict[str, float] = {}


def _client_ip() -> str:
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.remote_addr or "unknown"


def _login_check_rate() -> tuple[bool, int]:
    ip = _client_ip()
    now = time.time()
    lock_until = _LOGIN_LOCKED_UNTIL.get(ip, 0)
    if lock_until > now:
        return False, int(lock_until - now)
    attempts = _LOGIN_ATTEMPTS[ip]
    while attempts and now - attempts[0] > _LOGIN_WINDOW_SEC:
        attempts.popleft()
    return True, 0


def _login_record_failure() -> None:
    ip = _client_ip()
    now = time.time()
    attempts = _LOGIN_ATTEMPTS[ip]
    attempts.append(now)
    if len(attempts) >= _LOGIN_MAX_ATTEMPTS:
        _LOGIN_LOCKED_UNTIL[ip] = now + _LOGIN_LOCKOUT_SEC
        attempts.clear()


def _login_record_success() -> None:
    ip = _client_ip()
    _LOGIN_ATTEMPTS.pop(ip, None)
    _LOGIN_LOCKED_UNTIL.pop(ip, None)


# ── CSRF (double-submit token) ────────────────────────────────────────────────

def _csrf_token() -> str:
    tok = session.get("_csrf")
    if not tok:
        tok = generate_session_token()
        session["_csrf"] = tok
    return tok


def _csrf_check() -> bool:
    supplied = request.form.get("_csrf") or request.headers.get("X-CSRF-Token", "")
    expected = session.get("_csrf", "")
    return bool(expected) and hmac.compare_digest(str(supplied), str(expected))


def _read_version() -> str:
    """Single source of truth: pyproject.toml. Fallback constant if unreadable."""
    try:
        from pathlib import Path as _P
        for line in _P("pyproject.toml").read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("version") and "=" in line:
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return "1.3.0"


GATEWAY_VERSION = _read_version()


# ── Translations ──────────────────────────────────────────────────────────────
from webui import i18n as _i18n  # noqa: E402
from webui.i18n import t  # noqa: E402

_praxis_lang_cache: dict = {"mtime": None, "lang": None}


def _practice_language():
    """Language chosen in wizard step 1 (gateway.yaml → praxis.language).
    Cached on the file's mtime: this runs on every request."""
    try:
        mtime = CONFIG_F.stat().st_mtime
    except OSError:
        return None
    if _praxis_lang_cache["mtime"] != mtime:
        lang = None
        try:
            import yaml as _yaml
            cfg = _yaml.safe_load(CONFIG_F.read_text(encoding="utf-8")) or {}
            lang = (cfg.get("praxis") or {}).get("language")
        except Exception:
            pass
        _praxis_lang_cache.update(mtime=mtime, lang=lang)
    return _praxis_lang_cache["lang"]


_i18n.init_app(app, practice_lang=_practice_language)


@app.context_processor
def _inject_globals():
    # Detect placeholder facility so the UI can show a warning banner
    warn_placeholder = False
    try:
        import yaml as _yaml
        cfg = _yaml.safe_load(_read_yaml_raw()) or {}
        fac = (cfg.get("hl7") or {}).get("sending_facility", "")
        if str(fac).strip().upper() in ("", "PRAXIS", "PRAXIS_NAME"):
            warn_placeholder = True
    except Exception:
        pass
    from src.common.sandbox import is_demo
    return {
        "csrf_token":       _csrf_token if session.get("auth_id") else lambda: "",
        "gateway_version":  GATEWAY_VERSION,
        "warn_placeholder": warn_placeholder,
        "current_user":     session.get("username", ""),
        "current_role":     session.get("role", ""),
        "demo_mode":        is_demo(),
    }


# ── Auth helpers ──────────────────────────────────────────────────────────────

def _logged_in() -> bool:
    return bool(session.get("auth_id"))


def _current_role() -> str:
    return session.get("role", "viewer")


def _session_ip_matches() -> bool:
    """
    Optional session hijack mitigation: if session was created from IP X, only
    that IP may keep using it. Disabled when clients are behind a NAT or a
    load balancer without X-Forwarded-For.
    """
    if os.environ.get("WEBUI_STICKY_IP", "1").lower() in ("0", "false", "no"):
        return True
    return session.get("auth_ip") == _client_ip()


def _require_auth(f):
    @wraps(f)
    def wrapped(*a, **kw):
        if is_setup_required():
            return redirect(url_for("setup"))
        if not _logged_in():
            return redirect(url_for("login"))
        if not _session_ip_matches():
            audit(AuditEvent.LOGIN_FAILURE, ip=_client_ip(),
                  detail={"reason": "session_ip_mismatch",
                          "expected": session.get("auth_ip","?")})
            session.clear()
            return redirect(url_for("login"))
        return f(*a, **kw)
    return wrapped


def _require_role(needed: str):
    """Decorator: require the session user to be at least ``needed`` (viewer|operator|admin)."""
    def deco(f):
        @wraps(f)
        def wrapped(*a, **kw):
            if is_setup_required():
                return redirect(url_for("setup"))
            if not _logged_in():
                return redirect(url_for("login"))
            if not _session_ip_matches():
                session.clear()
                return redirect(url_for("login"))
            if not _roles.require_role(_current_role(), needed):
                if request.path.startswith("/api/"):
                    return jsonify({"ok": False, "error": "forbidden: role too low"}), 403
                abort(403)
            return f(*a, **kw)
        return wrapped
    return deco


def _require_local(f):
    """Restrict to localhost — used for privileged endpoints."""
    @wraps(f)
    def wrapped(*a, **kw):
        ip = _client_ip()
        if ip not in ("127.0.0.1", "::1", "localhost"):
            abort(403)
        return f(*a, **kw)
    return wrapped


# ── YAML / status / service helpers ───────────────────────────────────────────

def _read_yaml_raw() -> str:
    if CONFIG_F.exists():
        return CONFIG_F.read_text(encoding="utf-8")
    example = BASE_DIR / "config" / "gateway.yaml.example"
    return example.read_text(encoding="utf-8") if example.exists() else ""


def _write_yaml(content: str) -> None:
    CONFIG_F.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_F.write_text(content, encoding="utf-8")


def _read_status() -> Dict[str, Any]:
    if STATUS_F.exists():
        try:
            return json.loads(STATUS_F.read_text())
        except Exception:
            pass
    return {
        "running": False, "last_result": None,
        "results_today": 0, "results_total": 0,
        "connection_status": "unknown", "targets": [],
        "uptime_seconds": 0, "errors_today": 0,
    }


def _configured_targets() -> list:
    """The gestionali the operator has configured in gateway.yaml — the source
    of truth for *which* targets exist (independent of whether the gateway
    process is currently running)."""
    import yaml as _yaml
    try:
        cfg = _yaml.safe_load(_read_yaml_raw()) or {}
    except Exception:
        return []
    return [t for t in (cfg.get("targets") or []) if isinstance(t, dict)]


def _dashboard_targets(live_targets: Any) -> list:
    """Merge configured gestionali (gateway.yaml) with live status from the
    running gateway's status file. Previously the dashboard showed ONLY the
    live list, so a gestionale you had configured and saved stayed invisible
    ("Nessun gestionale configurato") until the gateway happened to publish
    it — the config, not the runtime snapshot, is what the operator sees."""
    live_by_name = {t.get("name"): t for t in (live_targets or [])
                    if isinstance(t, dict)}
    merged: list = []
    seen: set = set()
    for ct in _configured_targets():
        name = ct.get("name")
        lv = live_by_name.get(name, {})
        merged.append({
            "name":    name,
            "type":    ct.get("type", ""),
            "enabled": ct.get("enabled", True),
            "last_ok": lv.get("last_ok"),
            "error":   lv.get("error"),
        })
        seen.add(name)
    # Keep any live-only targets that aren't in the config (defensive).
    for name, lv in live_by_name.items():
        if name not in seen:
            merged.append(lv)
    return merged


def _read_license() -> Dict[str, Any]:
    if LICENSE_F.exists():
        try:
            return json.loads(LICENSE_F.read_text())
        except Exception:
            pass
    return {"activated": False, "key": "", "customer": "", "expires": ""}


def _service_action(action: str) -> tuple[bool, str]:
    """
    Run ``systemctl <action> jerumednexus-gateway`` and return (ok, error_msg).

    Splitting into a tuple lets the API surface the *real* systemd error
    ("Failed to restart jerumednexus-gateway.service: Unit not found",
    "Permission denied", "Job for jerumednexus-gateway.service failed
    because the control process exited with error code") instead of the
    useless "Errore: sconosciuto" the UI used to show.
    """
    # No systemd unit (PC, demo box, manual install): manage the process.
    from webui import gateway_process as _gp
    if not _gp.systemd_unit_installed():
        return _gp.action(action)
    try:
        subprocess.run(
            ["sudo", "systemctl", action, "jerumednexus-gateway"],
            check=True, capture_output=True, text=True, timeout=15,
        )
        return True, ""
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or "").strip() or (exc.stdout or "").strip()
        return False, detail or f"systemctl {action} exit={exc.returncode}"
    except subprocess.TimeoutExpired:
        return False, f"Timeout: systemctl {action} non risponde entro 15s"
    except FileNotFoundError:
        return False, "systemctl non trovato — questo Pi ha systemd installato?"
    except PermissionError:
        return False, "Permesso negato — verifica /etc/sudoers.d/jerumednexus-gateway"
    except Exception as exc:
        return False, f"Errore inatteso: {exc}"


def _service_status() -> str:
    from webui import gateway_process as _gp
    if not _gp.systemd_unit_installed():
        return _gp.status()          # no unit: is the process really running?
    try:
        r = subprocess.run(["systemctl", "is-active", "jerumednexus-gateway"],
                           capture_output=True, text=True, timeout=5)
        return r.stdout.strip()
    except Exception:
        return "unknown"


def _get_serial() -> str:
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.startswith("Serial"):
                    return line.split(":")[1].strip()
    except Exception:
        pass
    return str(uuid.getnode())


def _read_recent_logs(n: int = 60) -> list:
    log_f = BASE_DIR / "logs" / "gateway.log"
    if not log_f.exists():
        try:
            r = subprocess.run(
                ["journalctl", "-u", "jerumednexus-gateway", "-n", str(n),
                 "--no-pager", "--output=short-iso"],
                capture_output=True, text=True, timeout=5)
            return r.stdout.splitlines()
        except Exception:
            return []
    lines = log_f.read_text(errors="replace").splitlines()
    return lines[-n:]


def _days_left(expires_str: str):
    try:
        exp = _date.fromisoformat(expires_str)
        return (exp - _date.today()).days
    except Exception:
        return None


# ── Setup wizard ──────────────────────────────────────────────────────────────

@app.route("/setup", methods=["GET", "POST"])
def setup():
    if not is_setup_required():
        return redirect(url_for("login"))
    # First-run: redirect straight to the guided wizard.
    if request.args.get("legacy") != "1":
        return redirect(url_for("wizard.index"))
    error = None
    if request.method == "POST":
        pw = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        if len(pw) < MIN_PASSWORD_LEN:
            error = t("La password deve avere almeno {n} caratteri.", n=MIN_PASSWORD_LEN)
        elif pw != confirm:
            error = t("Le password non coincidono.")
        else:
            try:
                # Legacy compatibility: also seed the old single-hash file so
                # scripts/install.sh / older tooling keep working.
                save_password(pw)
                _roles.create_user("admin", pw, "admin")
                audit(AuditEvent.SETUP_COMPLETE, ip=_client_ip())
                return redirect(url_for("login"))
            except ValueError as exc:
                error = str(exc)
    return render_template("setup.html", error=error, min_len=MIN_PASSWORD_LEN)


# ── Login / logout ────────────────────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    if is_setup_required():
        return redirect(url_for("setup"))
    from src.security import totp as _totp
    error = None
    require_otp = False
    otp_username = ""
    if request.method == "POST":
        ok, wait = _login_check_rate()
        if not ok:
            audit(AuditEvent.LOGIN_FAILURE, ip=_client_ip(),
                  detail={"reason": "rate_limited", "wait_sec": wait})
            error = t("Troppi tentativi — riprova tra {m}m {s}s.", m=wait // 60, s=wait % 60)
        else:
            username = (request.form.get("username", "") or "admin").strip()
            pw = request.form.get("password", "")
            otp = request.form.get("otp", "").strip()
            role = validate_login(username, pw)
            if role:
                # Second factor: if the user has TOTP enrolled, an OTP code
                # must accompany the password. Otherwise fall through to the
                # OTP prompt without spending the "session" cookie.
                if _totp.has_totp(username):
                    if not otp:
                        require_otp = True
                        otp_username = username
                    elif not _totp.verify_login(username, otp):
                        _login_record_failure()
                        audit(AuditEvent.LOGIN_FAILURE, ip=_client_ip(),
                              detail={"username": username[:32], "reason": "otp"})
                        require_otp = True
                        otp_username = username
                        error = t("Codice OTP non valido")
                if not require_otp and error is None:
                    session.clear()
                    session["auth_id"]  = generate_session_token()
                    session["auth_ip"]  = _client_ip()
                    session["username"] = username
                    session["role"]     = role
                    session.permanent = True
                    _login_record_success()
                    audit(AuditEvent.LOGIN_SUCCESS, actor=username, ip=_client_ip(),
                          detail={"role": role,
                                  "otp": _totp.has_totp(username)})
                    return redirect(url_for("dashboard"))
            else:
                _login_record_failure()
                audit(AuditEvent.LOGIN_FAILURE, ip=_client_ip(),
                      detail={"username": username[:32]})
                error = t("Credenziali errate")
    return render_template("login.html", error=error,
                           require_otp=require_otp, otp_username=otp_username)


@app.route("/logout")
def logout():
    if _logged_in():
        audit(AuditEvent.LOGOUT, ip=_client_ip())
    session.clear()
    return redirect(url_for("login"))


# ── Pages ─────────────────────────────────────────────────────────────────────

@app.route("/")
@_require_auth
def dashboard():
    lic = _read_license()
    dl  = _days_left(lic.get("expires", "")) if lic.get("activated") else None
    status = _read_status()
    # Show CONFIGURED gestionali (from gateway.yaml), not just whatever the
    # running gateway last published — otherwise a saved target stays hidden.
    status["targets"] = _dashboard_targets(status.get("targets"))
    ov = _overview.build_overview(**_overview_inputs())
    return render_template("dashboard.html", ov=ov,
        status=status, license=lic,
        service=_service_status(), serial=_get_serial(),
        hostname=platform.node(), days_left=dl,
    )


@app.route("/config")
@_require_role("admin")
def config_page():
    import yaml as _yaml
    raw = _read_yaml_raw()
    try:
        cfg = _yaml.safe_load(raw) or {}
    except Exception:
        cfg = {}
    az_keys = ['sysmex','sysmex_xq320','sysmex_poch100i','horiba',
               'uc1000','seamaty','seamaty_sd3','seamaty_sd1','cobas']
    az_enabled = {k: cfg.get(k, {}).get('enabled', False) for k in az_keys}
    targets = cfg.get('targets', [])
    tomedo = next((t for t in targets if t.get('name') == 'tomedo'), {})

    # Valori salvati di OGNI gestionale, non solo di Tomedo. Senza questi la
    # pagina ridisegnava i campi vuoti e la casella "abilitato" spenta: al
    # primo salvataggio il target configurato veniva ricostruito senza host,
    # o perso del tutto. La password non torna mai al browser: si manda il
    # segnaposto, che il salvataggio interpreta come "tieni quella di prima".
    cfg_targets = {}
    for _t in targets:
        if not isinstance(_t, dict):
            continue
        _nome = str(_t.get('name', '')).strip()
        if not _nome:
            continue
        cfg_targets[_nome] = {
            'enabled':          bool(_t.get('enabled', True)),
            'host':             _t.get('host') or '',
            'port':             _t.get('port') or '',
            'watch_folder':     _t.get('watch_folder') or '',
            'sftp_host':        _t.get('sftp_host') or '',
            'sftp_port':        _t.get('sftp_port') or 22,
            'sftp_user':        _t.get('sftp_user') or '',
            'sftp_pass':        '********' if _t.get('sftp_pass') else '',
            'sftp_remote_path': _t.get('sftp_remote_path') or '',
        }

    # Load device catalog dynamically from config/devices/*.yaml
    from pathlib import Path as _P
    device_catalog = []
    dev_dir = _P("config/devices")
    if dev_dir.is_dir():
        for f in sorted(dev_dir.glob("*.yaml")):
            try:
                d = _yaml.safe_load(f.read_text(encoding="utf-8")) or {}
                d.setdefault("id", f.stem)
                # Il collegamento si ricava dai campi configurati, con la
                # STESSA precedenza che usano i lettori:
                #     if serial_port: apri_seriale() else: apri_tcp()
                # Prima lo si deduceva dal tipo di apparecchio, e la pagina
                # mostrava "TCP - listen 0.0.0.0:5006" per un device che
                # aveva anche serial_port e in realta' apriva il cavo USB.
                # L'operatore sceglieva TCP, la pagina confermava TCP, e il
                # gateway faceva un'altra cosa.
                if d.get("serial_port") and d.get("listen_port"):
                    d["_transport"] = "usb"
                    d["_ambiguo"] = True      # mostrato come avviso accanto
                elif d.get("serial_port"):
                    d["_transport"] = "usb"
                elif d.get("listen_port"):
                    d["_transport"] = "tcp"
                else:
                    d["_transport"] = ("usb"
                                       if d.get("type") in ("uc1000_serial",
                                                            "cobas_poct")
                                       else "tcp")
                device_catalog.append(d)
            except Exception:
                continue

    from flask import make_response
    resp = make_response(render_template("config.html",
        yaml_content=raw,
        license=_read_license(),
        az_enabled=az_enabled,
        device_catalog=device_catalog,
        cfg_connection_type=cfg.get('loc200',{}).get('connection_type','http'),
        cfg_http_port=cfg.get('loc200',{}).get('http_port',5003),
        cfg_sending_app=cfg.get('hl7',{}).get('sending_application',''),
        cfg_sending_facility=cfg.get('hl7',{}).get('sending_facility',''),
        cfg_receiving_facility=cfg.get('hl7',{}).get('receiving_facility',''),
        cfg_serial_port=cfg.get('loc200',{}).get('serial',{}).get('port','/dev/ttyUSB0'),
        cfg_serial_baud=cfg.get('loc200',{}).get('serial',{}).get('baudrate',9600),
        cfg_serial_parity=cfg.get('loc200',{}).get('serial',{}).get('parity','N'),
        cfg_tomedo_enabled=tomedo.get('enabled', False),
        cfg_tomedo_sftp_host=tomedo.get('sftp_host', ''),
        cfg_tomedo_sftp_port=tomedo.get('sftp_port', 22),
        cfg_tomedo_sftp_user=tomedo.get('sftp_user', ''),
        cfg_tomedo_sftp_pass="********" if tomedo.get('sftp_pass') else "",
        cfg_tomedo_sftp_path=tomedo.get('sftp_remote_path', ''),
        ui_targets=UI_TARGETS,
        cfg_targets=cfg_targets,
        cfg_hl7_version=cfg.get('hl7', {}).get('version', '2.3'),
        cfg_hl7_charset=cfg.get('hl7', {}).get('charset', '8859/1'),
        cfg_hl7_timezone=cfg.get('hl7', {}).get('include_timezone', True),
    ))
    # Never let Safari's back-forward cache serve a stale copy of this
    # page: after Save the operator must see the values they just saved.
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


@app.route("/logs")
@_require_role("admin")
def logs_page():
    return render_template("logs.html",
        log_lines=_read_recent_logs(100),
        license=_read_license(),
    )


def _device_catalog() -> list:
    """Profiles in config/devices/*.yaml, as the 'Add machine' page shows them."""
    from pathlib import Path as _P
    import yaml as _y
    from webui.overview import machine_kind
    out = []
    for f in sorted(_P("config/devices").glob("*.yaml")):
        try:
            d = _y.safe_load(f.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        dev_id = str(d.get("id") or f.stem)
        out.append({
            "id": dev_id,
            "name": str(d.get("display_name") or dev_id),
            "vendor": str(d.get("vendor") or ""),
            "model": str(d.get("model") or ""),
            "type": str(d.get("type") or "mllp_hl7"),
            "kind": machine_kind(dev_id, str(d.get("model") or ""), str(d.get("display_name") or "")),
            "link": "usb" if d.get("serial_port") else "network",
            "listen_port": d.get("listen_port"),
            "serial_port": d.get("serial_port") or "",
            "baudrate": d.get("baudrate") or 9600,
            "enabled": bool(d.get("enabled")),
        })
    out.sort(key=lambda x: (x["vendor"].lower(), x["name"].lower()))
    return out


def _ports_in_use(exclude_id: str = "") -> list:
    """TCP ports already taken by enabled machines (and the LOC-200 HTTP port)."""
    used = set()
    for d in _device_catalog():
        if d["enabled"] and d["id"] != exclude_id and d["listen_port"]:
            used.add(int(d["listen_port"]))
    try:
        import yaml as _y
        cfg = _y.safe_load(_read_yaml_raw()) or {}
        for d in cfg.get("devices") or []:
            if d.get("enabled") and d.get("id") != exclude_id and d.get("listen_port"):
                used.add(int(d["listen_port"]))
        used.add(int((cfg.get("loc200") or {}).get("http_port") or 5003))
    except Exception:
        pass
    return sorted(used)


def _gateway_address() -> str:
    """The address a machine on the practice network must send to."""
    host = (request.host or "").split(":")[0]
    if host and host not in ("localhost", "127.0.0.1", "::1"):
        return host
    import socket as _s
    try:
        with _s.socket(_s.AF_INET, _s.SOCK_DGRAM) as sock:
            sock.connect(("192.0.2.1", 9))      # no packet is sent (UDP connect)
            return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def _device_form(editing: bool, device: dict):
    return render_template("device_form.html", editing=editing, device=device,
                           catalog=_device_catalog(),
                           ports_in_use=_ports_in_use(device.get("id", "")),
                           gateway_address=_gateway_address(),
                           license=_read_license())


@app.route("/devices/new")
@_require_role("admin")
def device_new_page():
    return _device_form(False, {})


@app.route("/devices/edit/<dev_id>")
@_require_role("admin")
def device_edit_page(dev_id: str):
    from pathlib import Path as _P
    import yaml as _y
    if not re.fullmatch(r"[a-z0-9_-]{2,40}", dev_id):
        abort(404)
    path = _P("config/devices") / f"{dev_id}.yaml"
    if not path.exists():
        abort(404)
    d = _y.safe_load(path.read_text(encoding="utf-8")) or {}
    d.setdefault("id", dev_id)
    return _device_form(True, d)


@app.route("/api/devices/<dev_id>/connect", methods=["POST"])
@_require_role("admin")
def api_devices_connect(dev_id: str):
    """
    Connect a machine that already has a profile in config/devices/ (picked
    from the catalog on the 'Add machine' page, or edited later).

    MERGES into the profile instead of replacing it: protocol details that
    only the profile knows (astm_mode, unidirectional, timeouts, notes…)
    must survive. Only the connection, the name and `enabled` change.

    Body: {transport: "usb"|"tcp", serial_port, baudrate, listen_host,
           listen_port, display_name, enabled (default true)}
    """
    if not _csrf_check():
        return jsonify({"ok": False, "error": "CSRF token invalido"}), 400
    if not re.fullmatch(r"[a-z0-9_-]{2,40}", dev_id):
        return jsonify({"ok": False, "error": "id invalido"}), 400
    from pathlib import Path as _P
    import yaml as _y
    path = _P("config/devices") / f"{dev_id}.yaml"
    if not path.exists():
        return jsonify({"ok": False, "error": "device not found"}), 404
    body = request.get_json(force=True) or {}
    transport = body.get("transport")
    if transport not in ("usb", "tcp"):
        return jsonify({"ok": False, "error": "transport must be 'usb' or 'tcp'"}), 400
    d = _y.safe_load(path.read_text(encoding="utf-8")) or {}
    d["id"] = dev_id
    d["enabled"] = bool(body.get("enabled", True))
    name = str(body.get("display_name") or "").strip()
    if name:
        d["display_name"] = name[:80]
    if transport == "usb":
        sp = str(body.get("serial_port") or d.get("serial_port") or "").strip()
        if not sp.startswith("/dev/"):
            return jsonify({"ok": False, "error": "serial_port must be a /dev/ path"}), 400
        try:
            from src.discovery.probes import stable_serial_path as _stable
            sp = _stable(sp)
        except Exception:
            pass
        d["serial_port"] = sp
        d["baudrate"] = int(body.get("baudrate") or d.get("baudrate") or 9600)
    else:
        try:
            port = int(body.get("listen_port") or d.get("listen_port") or 0)
        except (TypeError, ValueError):
            port = 0
        if not 1024 <= port <= 65535:
            return jsonify({"ok": False, "error": "listen_port must be 1024-65535"}), 400
        if port in _ports_in_use(dev_id):
            return jsonify({"ok": False, "error": f"port {port} already used", "code": "port_in_use"}), 409
        d["listen_port"] = port
        d["listen_host"] = str(body.get("listen_host") or d.get("listen_host") or "0.0.0.0")
    d = _pulisci_campi_trasporto(d, transport)
    path.write_text(_y.safe_dump(d, sort_keys=False, allow_unicode=True), encoding="utf-8")
    audit(AuditEvent.DEVICE_CONNECTED, ip=_client_ip(),
          actor=session.get("username", "?"),
          detail={"connected": dev_id, "transport": transport})
    _try_reload_gateway()
    return jsonify({"ok": True, "id": dev_id})


@app.route("/devices/archive")
@_require_role("admin")
def device_archive_page():
    return render_template("device_archive.html", license=_read_license())


@app.route("/dlq")
@_require_role("admin")
def dlq_page():
    return render_template("dlq.html", license=_read_license())


@app.route("/users")
@_require_role("admin")
def users_page():
    return render_template("users.html", license=_read_license())


@app.route("/analyzers")
@_require_auth
def analyzers():
    st = _read_status()
    # Load the device catalog dynamically so newly-added devices appear
    catalog = []
    try:
        from pathlib import Path as _P
        import yaml as _y
        catalog_dir = _P("config/devices")
        if catalog_dir.is_dir():
            for f in sorted(catalog_dir.glob("*.yaml")):
                try:
                    d = _y.safe_load(f.read_text()) or {}
                    d["_id"] = d.get("id", f.stem)
                    catalog.append(d)
                except Exception:
                    continue
    except Exception:
        pass
    return render_template("analyzers.html",
        ov=_overview.build_overview(**_overview_inputs()),
        catalog_by_id={d["id"]: d for d in _device_catalog()},
        license=_read_license(),
        service=_service_status(),
        active_readers=[r["name"] for r in st.get("active_readers", [])],
        last_seen=st.get("last_seen", {}),
        connected=st.get("connected", {}),
        device_catalog=catalog,
    )


@app.route("/results")
@_require_auth
def results_page():
    try:
        from src.common.history import devices_seen
        devices = devices_seen()
    except Exception:
        devices = []
    return render_template("results.html", devices=devices, license=_read_license())


@app.route("/license")
@_require_role("admin")
def license_page():
    lic = _read_license()
    dl  = _days_left(lic.get("expires", "")) if lic.get("activated") else None
    return render_template("license.html",
        license=lic, serial=_get_serial(),
        hostname=platform.node(), days_left=dl,
        now_date=_date.today().isoformat(),
    )


@app.route("/settings", methods=["GET", "POST"])
@_require_auth
def settings():
    msg = error = None
    if request.method == "POST":
        if not _csrf_check():
            abort(400, "CSRF token invalido")
        old_pw  = request.form.get("old_password", "")
        new_pw  = request.form.get("new_password", "")
        confirm = request.form.get("confirm_password", "")
        username = session.get("username", "admin")
        if not validate_login(username, old_pw):
            error = "Password attuale errata"
            audit(AuditEvent.LOGIN_FAILURE, ip=_client_ip(),
                  detail={"context": "settings_change"})
        elif len(new_pw) < MIN_PASSWORD_LEN:
            error = f"La nuova password deve avere almeno {MIN_PASSWORD_LEN} caratteri"
        elif new_pw != confirm:
            error = "Le password non coincidono"
        else:
            try:
                save_password(new_pw)
                if _roles.user_exists(username):
                    _roles.update_password(username, new_pw)
                # Rotate session so the old cookie can't be replayed.
                role = session.get("role", "admin")
                session.clear()
                session["auth_id"]  = generate_session_token()
                session["auth_ip"]  = _client_ip()
                session["username"] = username
                session["role"]     = role
                session.permanent = True
                audit(AuditEvent.PASSWORD_CHANGE, ip=_client_ip())
                msg = "Password aggiornata con successo"
            except ValueError as exc:
                error = str(exc)
    return render_template("settings.html", msg=msg, error=error,
                           license=_read_license(), min_len=MIN_PASSWORD_LEN)


@app.route("/support", methods=["GET", "POST"])
@_require_role("admin")
def support():
    tickets_f = BASE_DIR / "logs" / "tickets.json"
    ticket_number = None
    if request.method == "POST":
        if not _csrf_check():
            abort(400, "CSRF token invalido")
        import random
        import string
        ticket_number = "TK-" + "".join(random.choices(string.digits, k=6))
        ticket = {
            "ticket": ticket_number,
            "data": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "nome": request.form.get("nome", "")[:200],
            "clinica": request.form.get("clinica", "")[:200],
            "telefono": request.form.get("telefono", "")[:40],
            "email": request.form.get("email", "")[:200],
            "problema": request.form.get("problema", "")[:4000],
        }
        tickets = []
        if tickets_f.exists():
            try:
                tickets = json.loads(tickets_f.read_text())
            except Exception:
                tickets = []
        tickets.insert(0, ticket)
        tickets_f.write_text(json.dumps(tickets, indent=2, ensure_ascii=False))
    tickets = []
    if tickets_f.exists():
        try:
            tickets = json.loads(tickets_f.read_text())
        except Exception:
            tickets = []
    return render_template("support.html",
        ticket_number=ticket_number, tickets=tickets, license=_read_license())


# ── REST API ──────────────────────────────────────────────────────────────────

# ── Patient rights (nDSG / GDPR) ─────────────────────────────────────────────

@app.route("/api/patient/<patient_id>/export", methods=["GET"])
@_require_role("admin")
def api_patient_export(patient_id: str):
    """
    Right to access (nDSG art. 25 / GDPR art. 15).
    Returns every trace of the patient. Audited.
    """
    from src.common.patient_rights import export
    data = export(patient_id)
    audit(AuditEvent.CONFIG_READ, actor=session.get("username","?"),
          ip=_client_ip(),
          detail={"patient_export": patient_id, "records": sum([
              len(data.get("dispatches") or []),
              len(data.get("dead_letter") or []),
              len(data.get("orders") or []),
              len(data.get("seen_samples") or []),
          ])})
    return jsonify(data)


@app.route("/api/patient/<patient_id>/purge", methods=["POST"])
@_require_role("admin")
def api_patient_purge(patient_id: str):
    """
    Right to be forgotten (nDSG art. 25 / GDPR art. 17).
    Requires ?confirm=<patient_id> in body/query as safety.
    """
    if not _csrf_check():
        return jsonify({"ok": False, "error": "CSRF token invalido"}), 400
    body = request.get_json(silent=True) or {}
    confirm = body.get("confirm") or request.args.get("confirm", "")
    if confirm != patient_id:
        return jsonify({"ok": False,
                        "error": "confirm token must equal the patient_id"}), 400
    from src.common.patient_rights import purge
    report = purge(patient_id)
    audit(AuditEvent.PASSWORD_CHANGE,  # closest existing event (destructive)
          actor=session.get("username","?"), ip=_client_ip(),
          detail={"patient_purge": patient_id, "report": report})
    return jsonify({"ok": True, "report": report})


# ── Public status page (unauthenticated) ─────────────────────────────────────

@app.route("/api/status/public")
def api_status_public():
    """
    Statuspage.io-compatible summary suitable for embedding on a status page.
    Available WITHOUT authentication -- exposes only aggregate up/degraded/down.
    """
    from datetime import datetime as _dt
    st = _read_status()
    svc = _service_status()
    now_ts = _dt.now().isoformat()

    def _comp(name: str, ok: bool) -> dict:
        return {"name": name,
                "status": "operational" if ok else "major_outage",
                "updated_at": now_ts}

    running = svc == "active" and st.get("running")
    components = [
        _comp("Gateway process",  running),
        _comp("Web UI",           True),  # if we're serving this, UI is up
        _comp("HL7 dispatch",     running and st.get("errors_today", 0) < 100),
        _comp("Device readers",   running and bool(st.get("active_readers"))),
    ]
    incidents = []
    if not running:
        incidents.append({
            "name": "Gateway not running",
            "impact": "critical",
            "status": "investigating",
            "created_at": now_ts,
        })

    overall = "operational" if all(c["status"] == "operational" for c in components) else \
              "partial_outage"

    return jsonify({
        "page": {
            "id": "jerumednexus-gateway",
            "name": "JerumedNexus Gateway",
            "url": request.host_url,
            "updated_at": now_ts,
        },
        "status": {"indicator": overall, "description": overall.replace("_", " ").title()},
        "components": components,
        "incidents": incidents,
        "scheduled_maintenances": [],
    })


@app.route("/api/history")
@_require_auth
def api_history():
    from src.common.history import search
    entries = search(
        q=request.args.get("q", ""),
        device=request.args.get("device", ""),
        status=request.args.get("status", ""),
        since=request.args.get("since", ""),
        limit=int(request.args.get("limit", 200)),
        offset=int(request.args.get("offset", 0)),
    )
    return jsonify({"entries": entries})


@app.route("/api/history/trend")
@_require_auth
def api_history_trend():
    from src.common.history import hourly_counts
    hours = int(request.args.get("hours", 24))
    return jsonify({"hours": hourly_counts(hours=max(1, min(hours, 168)))})


@app.route("/api/status")
@_require_auth
def api_status():
    svc = _service_status()
    st  = _read_status()
    st["service_systemd"] = svc
    st["timestamp"] = datetime.now().isoformat()
    return jsonify(st)


@app.route("/api/config", methods=["GET"])
@_require_auth
def api_config_get():
    return jsonify({"yaml": _read_yaml_raw()})


@app.route("/api/config", methods=["POST"])
@_require_role("admin")
def api_config_save():
    if not _csrf_check():
        return jsonify({"ok": False, "error": "CSRF token invalido"}), 400
    data = request.get_json(force=True)
    yaml_text = data.get("yaml", "")
    if not yaml_text.strip():
        return jsonify({"ok": False, "error": "Empty configuration"}), 400
    try:
        import yaml as _yaml
        _yaml.safe_load(yaml_text)
    except Exception as e:
        return jsonify({"ok": False, "error": f"YAML syntax error: {e}"}), 400
    _write_yaml(yaml_text)
    audit(AuditEvent.CONFIG_SAVE, ip=_client_ip(),
          detail={"bytes": len(yaml_text)})
    return jsonify({"ok": True, "message": "Configuration saved."})


# ── Structured (form-based) config save ─────────────────────────────────────
# The legacy ``POST /api/config`` accepts raw YAML because the "advanced
# editor" needs it. The Configurazione page's toggle-based form used to also
# hand-craft a YAML string via JavaScript regex substitutions — extremely
# fragile, one wrong replace and the server rejected everything with a 400.
#
# This endpoint takes STRUCTURED JSON, merges it on top of the current
# gateway.yaml (preserving unknown top-level keys like ``praxis:`` / ``backup:``),
# validates the result via Pydantic (the same loader the gateway uses at
# boot — no divergence possible), then writes and returns the effective YAML.
#
# Multi-target, multi-device, works for every clinic template.

_TARGET_FIELD_WHITELIST = {
    "name", "type", "enabled",
    "host", "port", "mllp_timeout",
    "watch_folder", "file_encoding", "file_extension",
    "sftp_host", "sftp_port", "sftp_user", "sftp_pass", "sftp_remote_path",
    "fhir_endpoint", "fhir_verify_tls", "fhir_token",
}

# Unica definizione dei gestionali mostrati nella pagina Configurazione.
# Prima esisteva due volte -- una tabella Jinja nel template e una tabella JS
# accanto -- e le due sono andate alla deriva: porte di default diverse, e
# WinMed disegnato come file-drop ma raccolto come MLLP, quindi inconfigurabile
# dalla WebUI. Da qui la usano sia il template sia il JavaScript.
#   mode: come si consegna  ->  'mllp' host+porta | 'sftp' Tomedo | 'file' cartella
UI_TARGETS = [
    {"id": "vitomed",  "label": "Vitomed / Vitodata",        "mode": "mllp", "port": 6661},
    {"id": "curamed",  "label": "curaMED (Swisscom Health)", "mode": "mllp", "port": 6662},
    {"id": "aeskulap", "label": "Aeskulap (CGM)",            "mode": "mllp", "port": 2575},
    {"id": "axenita",  "label": "Axenita (Axon Lab)",        "mode": "mllp", "port": 6663},
    {"id": "dnamed",   "label": "DnaMed",                    "mode": "mllp", "port": 6664},
    {"id": "winmed",   "label": "WinMed (TMR AG)",           "mode": "file", "port": None},
    {"id": "tomedo",   "label": "Tomedo (zollsoft)",         "mode": "sftp", "port": 22},
]

def _pulisci_campi_trasporto(voce: dict, trasporto: str) -> dict:
    """
    Toglie i campi del collegamento che NON e' stato scelto.

    Serve perche' cambiare un apparecchio da USB a TCP lasciava dentro il
    vecchio `serial_port`, e i lettori guardano prima quello:

        if self._serial_port: apri_seriale() else: apri_tcp()

    Il Sysmex riconfigurato in rete continuava quindi ad aprire /dev/ttyUSB1,
    rubando il cavo a un altro apparecchio, mentre la porta 5006 restava
    muta. Dal di fuori sembrava semplicemente che non arrivasse niente.

    Si toglie anche `transport`, che e' un concetto del modulo web e non
    esiste nello schema, e `overwrite`, che e' un comando di salvataggio e
    non una proprieta' dell'apparecchio.
    """
    voce.pop("transport", None)
    voce.pop("overwrite", None)
    if trasporto == "tcp":
        for campo in ("serial_port", "baudrate"):
            voce.pop(campo, None)
    else:
        for campo in ("listen_host", "listen_port"):
            voce.pop(campo, None)
    return voce


# UI kind → schema type (config.settings.PISTarget.type is a closed Literal set)
_UI_KIND_TO_TYPE = {
    "vitomed": "vitomed", "curamed": "curamed", "aeskulap": "aeskulap",
    "axenita": "axenita", "winmed": "winmed", "dnamed": "dnamed",
    "tomedo": "tomedo",
    "mllp_hl7": "generic_hl7_mllp", "generic_hl7_mllp": "generic_hl7_mllp",
    "file_drop": "file_drop", "fhir_r4": "fhir_r4", "fhir": "fhir_r4",
}


def _validate_target_form(target: dict) -> list[str]:
    """
    Human-readable pre-check before Pydantic. Returns a list of missing
    fields for the given target, so the UI can highlight ROOT CAUSES
    instead of Pydantic's cryptic ValidationError chains.
    """
    problems: list[str] = []
    if not target.get("enabled"):
        return problems
    ttype = str(target.get("type", "")).strip()
    name  = str(target.get("name", "")).strip()

    if ttype == "tomedo":
        if not str(target.get("sftp_host", "")).strip():
            problems.append(f"[{name}] IP server SFTP mancante")
        if not str(target.get("sftp_user", "")).strip():
            problems.append(f"[{name}] Utente SFTP mancante")
        if not target.get("sftp_pass") and target.get("sftp_pass") != "********":
            problems.append(f"[{name}] Password SFTP mancante")
        if not str(target.get("sftp_remote_path", "")).strip():
            problems.append(f"[{name}] Cartella remota SFTP mancante")
    elif ttype in ("vitomed", "curamed", "aeskulap", "axenita",
                    "dnamed", "generic_hl7_mllp"):
        if not str(target.get("host", "")).strip():
            problems.append(f"[{name}] Host del gestionale mancante")
        if not target.get("port"):
            problems.append(f"[{name}] Porta del gestionale mancante")
    elif ttype in ("winmed", "file_drop"):
        if not str(target.get("watch_folder", "")).strip():
            problems.append(f"[{name}] Cartella di destinazione mancante")
    elif ttype == "fhir_r4":
        if not str(target.get("fhir_endpoint", "")).strip():
            problems.append(f"[{name}] Endpoint FHIR mancante")
    return problems


def _merge_form_into_yaml(existing: dict, form: dict) -> dict:
    """Overlay UI form fields onto the current gateway.yaml dict."""
    cfg = dict(existing or {})

    # ── hl7 block ──
    if isinstance(form.get("hl7"), dict):
        hl7 = dict(cfg.get("hl7") or {})
        for k in ("sending_facility", "receiving_facility",
                  "sending_application", "receiving_application",
                  "version", "charset", "include_timezone"):
            if k in form["hl7"] and form["hl7"][k] != "":
                hl7[k] = form["hl7"][k]
        cfg["hl7"] = hl7

    # ── loc200 block ──
    if isinstance(form.get("loc200"), dict):
        loc = dict(cfg.get("loc200") or {})
        f = form["loc200"]
        if f.get("connection_type") in ("http", "serial", "network", "wifi"):
            loc["connection_type"] = f["connection_type"]
        if f.get("http_port"):
            try: loc["http_port"] = int(f["http_port"])
            except (TypeError, ValueError): pass
        if f.get("serial_port") or f.get("baudrate") or f.get("parity"):
            serial = dict(loc.get("serial") or {})
            if f.get("serial_port"):
                serial["port"] = str(f["serial_port"])
            if f.get("baudrate"):
                try: serial["baudrate"] = int(f["baudrate"])
                except (TypeError, ValueError): pass
            if f.get("parity") in ("N", "E", "O"):
                serial["parity"] = f["parity"]
            loc["serial"] = serial
        cfg["loc200"] = loc

    # ── targets ──
    # La lista viene ricostruita: un target che l'operatore ha deselezionato
    # deve sparire, altrimenti disattivarlo sarebbe impossibile. Ma "assente
    # dal modulo" e "deselezionato dall'operatore" sono due cose diverse: il
    # modulo dichiara in `targets_managed` quali sa gestire, e tutto il resto
    # resta intatto. Senza questa distinzione un salvataggio qualsiasi
    # cancellava i target che la pagina non sapeva ancora mostrare -- il
    # gateway smetteva di consegnare e nessuno capiva perche'.
    gestiti = form.get("targets_managed")
    if isinstance(gestiti, list):
        nomi_gestiti = {str(x).strip() for x in gestiti if str(x).strip()}
    else:
        # Modulo vecchio che non dichiara niente: si assume che gestisca solo
        # quello che ha effettivamente inviato, mai piu' di quello.
        nomi_gestiti = {str(t.get("name", "")).strip()
                        for t in (form.get("targets") or []) if isinstance(t, dict)}
    conservati = [t for t in (cfg.get("targets") or [])
                  if isinstance(t, dict)
                  and str(t.get("name", "")).strip() not in nomi_gestiti]

    incoming_targets: list[dict] = []
    for t in (form.get("targets") or []):
        if not isinstance(t, dict):
            continue
        # Passwords may arrive as the sentinel "********" when the operator
        # didn't change the field. Preserve the existing secret in that case.
        raw_name = str(t.get("name", "")).strip()
        raw_type = str(t.get("type", "")).strip() or raw_name
        mapped_type = _UI_KIND_TO_TYPE.get(raw_type, raw_type)
        target: dict = {}
        for k, v in t.items():
            if k in _TARGET_FIELD_WHITELIST:
                target[k] = v
        if not target.get("name"):
            continue
        target["type"] = mapped_type
        target.setdefault("enabled", True)
        if "port" in target and target["port"] not in (None, ""):
            try: target["port"] = int(target["port"])
            except (TypeError, ValueError): target.pop("port")
        if "sftp_port" in target and target["sftp_port"] not in (None, ""):
            try: target["sftp_port"] = int(target["sftp_port"])
            except (TypeError, ValueError): target.pop("sftp_port")
        # Preserve secrets marked with the placeholder
        prev = next((x for x in (cfg.get("targets") or [])
                     if isinstance(x, dict) and x.get("name") == target["name"]), {})
        for secret_key in ("sftp_pass", "fhir_token"):
            if target.get(secret_key) in ("", "********"):
                if prev.get(secret_key):
                    target[secret_key] = prev[secret_key]
                else:
                    target.pop(secret_key, None)
        incoming_targets.append(target)
    cfg["targets"] = conservati + incoming_targets

    # ── per-analyzer enabled toggles (legacy per-device blocks) ──
    dev_flags = form.get("devices_enabled") or {}
    for name, on in dev_flags.items():
        if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,32}", name):
            continue
        block = dict(cfg.get(name) or {})
        block["enabled"] = bool(on)
        cfg[name] = block

    return cfg


@app.route("/api/config/save-form", methods=["POST"])
@_require_role("admin")
def api_config_save_form():
    """Structured save — no client-side YAML editing. See _merge_form_into_yaml."""
    if not _csrf_check():
        return jsonify({"ok": False, "error": "CSRF token invalido"}), 400
    form = request.get_json(force=True, silent=True) or {}

    import yaml as _yaml
    try:
        existing = _yaml.safe_load(_read_yaml_raw()) or {}
    except Exception as e:
        return jsonify({"ok": False,
                        "error": f"Config attuale illeggibile: {e}"}), 400
    if not isinstance(existing, dict):
        existing = {}

    merged = _merge_form_into_yaml(existing, form)

    # Human-first validation: highlight *root causes* (missing SFTP host,
    # missing MLLP port, ...) with the target name attached, before
    # letting Pydantic emit a cryptic ValidationError chain.
    field_problems: list[str] = []
    for t in (merged.get("targets") or []):
        if isinstance(t, dict):
            field_problems.extend(_validate_target_form(t))
    if field_problems:
        return jsonify({
            "ok": False,
            "error": " • ".join(field_problems),
            "problems": field_problems,
        }), 400

    # Validate against the SAME loader the gateway uses at boot. If Pydantic
    # rejects it, the gateway would too — better to tell the operator now.
    try:
        from config.settings import GatewayConfig
        GatewayConfig.model_validate(merged)
    except Exception as e:
        return jsonify({"ok": False,
                        "error": f"Configurazione non valida: {e}"}), 400

    try:
        yaml_text = _yaml.safe_dump(merged, allow_unicode=True, sort_keys=False)
        _write_yaml(yaml_text)
    except Exception as e:
        return jsonify({"ok": False, "error": f"Errore scrittura: {e}"}), 500

    audit(AuditEvent.CONFIG_SAVE, ip=_client_ip(),
          detail={"structured": True,
                  "targets": [t.get("name") for t in merged.get("targets") or []]})

    # Best-effort restart so the operator sees the change take effect
    # immediately. Failure to restart is a warning, not an error — the
    # config is safely on disk either way.
    restart_ok, restart_err = _service_action("restart")
    return jsonify({
        "ok": True,
        "message": "Configurazione salvata",
        "restarted": restart_ok,
        "restart_error": restart_err if not restart_ok else None,
        "yaml": yaml_text,
    })


@app.route("/api/service/<action>", methods=["POST"])
@_require_role("operator")
def api_service(action: str):
    if not _csrf_check():
        return jsonify({"ok": False, "error": "CSRF token invalido"}), 400
    if action not in ("start", "stop", "restart"):
        return jsonify({"ok": False, "error": "Azione non valida"}), 400
    ok, err = _service_action(action)
    audit(AuditEvent.SERVICE_ACTION, ip=_client_ip(),
          detail={"action": action, "ok": ok,
                  "error": err[:200] if err else None})
    time.sleep(1.5)
    return jsonify({
        "ok": ok,
        "error": err if not ok else None,
        "status": _service_status(),
        "action": action,
    })


@app.route("/api/logs")
@_require_auth
def api_logs():
    lines = _read_recent_logs(int(request.args.get("n", 80)))
    return jsonify({"lines": lines})


@app.route("/api/license/activate", methods=["POST"])
@_require_auth
def api_license_activate():
    if not _csrf_check():
        return jsonify({"ok": False, "error": "CSRF token invalido"}), 400
    data = request.get_json(force=True)
    key  = data.get("key", "").strip()
    if not key:
        return jsonify({"ok": False, "error": "Chiave mancante"}), 400
    if not re.match(r"^LOC200-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$", key):
        return jsonify({"ok": False, "error": "Formato chiave non valido"}), 400
    serial = _get_serial()
    secret = os.environ.get("LOC200_LICENSE_SECRET")
    if not secret:
        return jsonify({
            "ok": False,
            "error": "LOC200_LICENSE_SECRET non configurato — contatta il supporto."
        }), 500
    payload = f"{serial}:{key[:19]}"
    # Full 32-hex HMAC comparison — chunk is last 16 hex chars of key
    expected = hmac.new(secret.encode(), payload.encode(),
                        hashlib.sha256).hexdigest()[:16].upper()
    provided = key.split("-", 1)[1].replace("-", "")[-16:]  # last 16 chars
    if not hmac.compare_digest(provided, expected):
        return jsonify({"ok": False, "error": "Chiave non valida per questo dispositivo"}), 400
    lic = {
        "activated": True, "key": key,
        "customer": data.get("customer", "")[:200],
        "device_serial": serial,
        "activated_at": datetime.now().isoformat(),
        "expires": (datetime.now() + timedelta(days=365)).strftime("%Y-%m-%d"),
    }
    LICENSE_F.parent.mkdir(parents=True, exist_ok=True)
    LICENSE_F.write_text(json.dumps(lic, indent=2))
    return jsonify({"ok": True, "license": lic})


# Update endpoint: gated to localhost + CSRF. Prefer apt-based upgrades.
@app.route("/api/update/check", methods=["POST"])
@_require_auth
@_require_local
def api_update_check():
    try:
        r = subprocess.run(["git", "-C", str(BASE_DIR), "fetch", "--dry-run"],
                           capture_output=True, text=True, timeout=15)
        return jsonify({"ok": True, "update_available": bool(r.stderr.strip())})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/update/apply", methods=["POST"])
@_require_auth
@_require_local
def api_update_apply():
    """
    Available only from localhost (SSH session on the Pi).
    For remote/enterprise upgrades use: sudo apt install --only-upgrade jerumednexus-gateway
    """
    if not _csrf_check():
        return jsonify({"ok": False, "error": "CSRF token invalido"}), 400
    try:
        subprocess.run(["git", "-C", str(BASE_DIR), "pull", "--ff-only"],
                       check=True, capture_output=True, timeout=60)
        subprocess.run([str(BASE_DIR / ".venv/bin/pip"), "install", "-r",
                        str(BASE_DIR / "requirements.txt"), "-q"],
                       check=True, capture_output=True, timeout=120)
        _service_action("restart")  # tuple return — we ignore for update flow
        return jsonify({"ok": True, "message": "Aggiornamento completato. Gateway riavviato."})
    except subprocess.CalledProcessError as e:
        return jsonify({"ok": False, "error": e.stderr.decode(errors="replace")})


# Discovery endpoints moved to webui/blueprints/discovery.py

def _run_async(coro):
    """Run an async coroutine from a sync Flask handler. Used by /api/targets/test."""
    from webui.blueprints._helpers import run_async as _rh
    return _rh(coro)


# NOTE: users, DLQ, discovery, metrics endpoints live in webui/blueprints/*


# ── Live protocol trace ───────────────────────────────────────────────────────

@app.route("/api/trace")
@_require_role("operator")
def api_trace_list():
    from src.common import trace as _trace
    return jsonify({"devices": _trace.devices()})


@app.route("/api/trace/<path:device>")
@_require_role("operator")
def api_trace_device(device: str):
    from src.common import trace as _trace
    limit = int(request.args.get("limit", 100))
    return jsonify({"entries": _trace.snapshot(device=device, limit=limit)})


@app.route("/trace")
@_require_role("admin")
def trace_page():
    """
    Il trace e' diventato una scheda della pagina Log: chi indaga un guasto
    passa di continuo dall'una all'altra. L'indirizzo vecchio resta valido
    perche' e' finito in appunti e segnalazioni di assistenza.
    """
    return redirect("/logs#trace")


# ── HL7 preview + validator ───────────────────────────────────────────────────

@app.route("/api/targets/<name>/preview", methods=["POST"])
@_require_role("operator")
def api_targets_preview(name: str):
    """
    Build the HL7 message that WOULD be sent to `name`, applying rewrites,
    and run the compliance validator. NO network call.
    """
    if not _csrf_check():
        return jsonify({"ok": False, "error": "CSRF token invalido"}), 400
    try:
        import yaml as _y
        cfg = _y.safe_load(_read_yaml_raw()) or {}
    except Exception as exc:
        return jsonify({"ok": False, "error": f"config: {exc}"}), 500

    target = next((t for t in cfg.get("targets", []) if t.get("name") == name), None)
    if not target:
        return jsonify({"ok": False, "error": f"target {name!r} not found"}), 404

    from datetime import datetime as _dt
    from config.settings import HL7Config
    from src.hl7.builder import HL7Builder
    from src.hl7.rewrites import apply_rewrites
    from src.hl7.validator import validate_hl7_message

    fake = {
        "timestamp":    _dt.now(),
        "sample_id":    f"PREVIEW_{_dt.now():%H%M%S}",
        "patient_id":   "PREVIEW",
        "patient_name": "Muster Patient",
        "gender":       "M",
        "disc_name":    "PREVIEW",
        "lot_id":       "PREVIEW",
        "observations": [{
            "analyte": "AST", "value": "10", "value_num": 10.0, "flag": "",
            "ref_low": 15, "ref_high": 40, "unit": "U/L",
        }],
    }
    builder = HL7Builder(HL7Config.model_validate(cfg.get("hl7", {})))
    msg = builder.build_oru_r01(fake)
    raw = msg.to_string()
    rewritten = apply_rewrites(raw, name)
    report = validate_hl7_message(rewritten)
    return jsonify({
        "raw":      raw,
        "final":    rewritten,
        "diff":     rewritten != raw,
        "validation": report.to_dict(),
    })


@app.route("/api/rewrites/<name>", methods=["GET", "POST"])
@_require_role("admin")
def api_rewrites(name: str):
    from pathlib import Path as _P
    import yaml as _y
    p = _P("config/rewrites") / f"{name}.yaml"
    if request.method == "GET":
        text = p.read_text(encoding="utf-8") if p.exists() else ""
        return jsonify({"target": name, "yaml": text})
    if not _csrf_check():
        return jsonify({"ok": False, "error": "CSRF token invalido"}), 400
    body = request.get_json(force=True)
    text = body.get("yaml", "")
    try:
        loaded = _y.safe_load(text)
        if loaded is not None and not isinstance(loaded, list):
            raise ValueError("rewrites file must be a YAML list of rule objects")
    except Exception as exc:
        return jsonify({"ok": False, "error": f"YAML: {exc}"}), 400
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    audit(AuditEvent.CONFIG_SAVE, ip=_client_ip(),
          actor=session.get("username", "?"),
          detail={"rewrites": name, "bytes": len(text)})
    return jsonify({"ok": True})


# ── Device wizard save ────────────────────────────────────────────────────────

def _try_reload_gateway() -> None:
    """Send SIGHUP so config changes are picked up without a restart."""
    try:
        subprocess.run(
            ["sudo", "systemctl", "kill", "--signal=SIGHUP", "jerumednexus-gateway"],
            capture_output=True, timeout=5,
        )
    except Exception:
        pass


@app.route("/api/devices/<dev_id>/enable", methods=["POST"])
@_require_role("admin")
def api_devices_enable(dev_id: str):
    if not _csrf_check():
        return jsonify({"ok": False, "error": "CSRF token invalido"}), 400
    body = request.get_json(force=True) or {}
    enabled = bool(body.get("enabled", True))
    import yaml as _y
    from pathlib import Path as _P
    path = _P("config/devices") / f"{dev_id}.yaml"
    if not path.exists():
        return jsonify({"ok": False, "error": "device not found"}), 404
    d = _y.safe_load(path.read_text(encoding="utf-8")) or {}
    d["enabled"] = enabled
    path.write_text(_y.safe_dump(d, sort_keys=False), encoding="utf-8")
    audit(AuditEvent.DEVICE_CONNECTED, ip=_client_ip(),
          actor=session.get("username", "?"),
          detail={"toggle": dev_id, "enabled": enabled})
    _try_reload_gateway()
    return jsonify({"ok": True, "enabled": enabled})


@app.route("/api/devices/<dev_id>/archive", methods=["POST"])
@_require_role("admin")
def api_devices_archive(dev_id: str):
    """Soft-delete: move the device YAML to config/devices/_archive/ so it can be restored."""
    if not _csrf_check():
        return jsonify({"ok": False, "error": "CSRF token invalido"}), 400
    from pathlib import Path as _P
    src = _P("config/devices") / f"{dev_id}.yaml"
    if not src.exists():
        return jsonify({"ok": False, "error": "device not found"}), 404
    arch_dir = _P("config/devices/_archive")
    arch_dir.mkdir(parents=True, exist_ok=True)
    from datetime import datetime as _dt
    stamp = _dt.now().strftime("%Y%m%d-%H%M%S")
    dst = arch_dir / f"{dev_id}.{stamp}.yaml"
    src.rename(dst)
    audit(AuditEvent.DEVICE_CONNECTED, ip=_client_ip(),
          actor=session.get("username", "?"),
          detail={"archived": dev_id, "path": str(dst)})
    _try_reload_gateway()
    return jsonify({"ok": True, "archived_to": str(dst)})


@app.route("/api/devices/archived", methods=["GET"])
@_require_role("admin")
def api_devices_archived():
    from pathlib import Path as _P
    import yaml as _y
    arch_dir = _P("config/devices/_archive")
    if not arch_dir.exists():
        return jsonify({"entries": []})
    out = []
    for f in sorted(arch_dir.glob("*.yaml"), reverse=True):
        try:
            d = _y.safe_load(f.read_text(encoding="utf-8")) or {}
            d["_file"] = f.name
            out.append(d)
        except Exception:
            continue
    return jsonify({"entries": out})


@app.route("/api/devices/archived/<path:filename>/restore", methods=["POST"])
@_require_role("admin")
def api_devices_restore(filename: str):
    if not _csrf_check():
        return jsonify({"ok": False, "error": "CSRF token invalido"}), 400
    from pathlib import Path as _P
    # Prevent path traversal
    safe = _P(filename).name
    src = _P("config/devices/_archive") / safe
    if not src.exists():
        return jsonify({"ok": False, "error": "archived file not found"}), 404
    import yaml as _y
    d = _y.safe_load(src.read_text(encoding="utf-8")) or {}
    dev_id = d.get("id") or safe.split(".")[0]
    dst = _P("config/devices") / f"{dev_id}.yaml"
    if dst.exists():
        return jsonify({"ok": False, "error": f"a device with id {dev_id!r} already exists"}), 409
    src.rename(dst)
    _try_reload_gateway()
    return jsonify({"ok": True, "restored_as": str(dst)})


@app.route("/api/devices/<dev_id>", methods=["GET"])
@_require_role("admin")
def api_devices_get(dev_id: str):
    from pathlib import Path as _P
    import yaml as _y
    path = _P("config/devices") / f"{dev_id}.yaml"
    if not path.exists():
        return jsonify({"ok": False, "error": "device not found"}), 404
    return jsonify({"ok": True, "device": _y.safe_load(path.read_text(encoding="utf-8")) or {}})


@app.route("/api/devices/<dev_id>", methods=["PUT"])
@_require_role("admin")
def api_devices_update(dev_id: str):
    if not _csrf_check():
        return jsonify({"ok": False, "error": "CSRF token invalido"}), 400
    from pathlib import Path as _P
    import yaml as _y
    path = _P("config/devices") / f"{dev_id}.yaml"
    if not path.exists():
        return jsonify({"ok": False, "error": "device not found"}), 404
    body = request.get_json(force=True) or {}
    # Merge: keep id + type, allow updating everything else
    existing = _y.safe_load(path.read_text(encoding="utf-8")) or {}
    body["id"] = dev_id
    body["type"] = body.get("type") or existing.get("type")
    # Il collegamento scelto decide quali campi sopravvivono: lasciarci dentro
    # quelli del collegamento precedente faceva aprire la porta sbagliata.
    trasporto = str(body.get("transport")
                    or ("tcp" if body.get("listen_port") else "usb")).lower()
    body = _pulisci_campi_trasporto(body, trasporto)
    path.write_text(_y.safe_dump(body, sort_keys=False), encoding="utf-8")
    audit(AuditEvent.DEVICE_CONNECTED, ip=_client_ip(),
          actor=session.get("username", "?"),
          detail={"updated": dev_id})
    _try_reload_gateway()
    return jsonify({"ok": True})


@app.route("/api/devices", methods=["GET"])
@_require_role("viewer")
def api_devices_list():
    """List every device in the catalog."""
    from pathlib import Path as _P
    import yaml as _y
    out = []
    dev_dir = _P("config/devices")
    if dev_dir.is_dir():
        for f in sorted(dev_dir.glob("*.yaml")):
            try:
                d = _y.safe_load(f.read_text(encoding="utf-8")) or {}
                d.setdefault("id", f.stem)
                out.append(d)
            except Exception:
                continue
    return jsonify({"devices": out})


_ALLOWED_TYPES = ("mllp_hl7", "sysmex_astm", "uc1000_serial", "cobas_poct",
                  "loc200_http", "loc200_serial", "reflotron_serial",
                  "generic_hl7", "generic_astm")


@app.route("/api/devices/create", methods=["POST"])
@_require_role("admin")
def api_devices_create():
    """
    Create a device from the web wizard.

    Body: {
      id: "<kebab-case>",             REQUIRED
      transport: "usb" | "tcp",       REQUIRED
      type: "<protocol>",             REQUIRED (see _ALLOWED_TYPES, or 'custom')
      display_name, vendor, model,
      enabled: bool,
      # USB only:
      serial_port, baudrate,
      # TCP only:
      listen_host, listen_port,
    }
    """
    if not _csrf_check():
        return jsonify({"ok": False, "error": "CSRF token invalido"}), 400
    body = request.get_json(force=True) or {}
    dev_id = (body.get("id") or "").strip()
    if not re.fullmatch(r"[a-z0-9_-]{2,40}", dev_id):
        return jsonify({"ok": False, "error": "id: 2-40 caratteri, solo [a-z0-9_-]"}), 400

    transport = body.get("transport", "")
    if transport not in ("usb", "tcp"):
        return jsonify({"ok": False, "error": "transport must be 'usb' or 'tcp'"}), 400

    dtype = body.get("type") or ""
    if dtype not in _ALLOWED_TYPES:
        # Allow custom types with a warning flag, so tecnici avanzati possono
        # aggiungere protocolli nuovi che poi verranno gestiti da adapter custom.
        if not re.fullmatch(r"[a-z0-9_]{2,40}", dtype):
            return jsonify({"ok": False, "error": "type invalido"}), 400

    import yaml as _y
    from pathlib import Path as _P
    entry = {
        "id":           dev_id,
        "type":         dtype,
        "enabled":      bool(body.get("enabled", False)),
        "display_name": (body.get("display_name") or dev_id)[:80],
        "vendor":       (body.get("vendor") or "")[:60],
        "model":        (body.get("model") or "")[:60],
    }
    if transport == "usb":
        _sp = body.get("serial_port") or "/dev/ttyUSB1"
        try:
            from src.discovery.probes import stable_serial_path as _stable
            _sp = _stable(_sp)   # pin to a reboot/hub-stable path when possible
        except Exception:
            pass
        entry["serial_port"] = _sp
        entry["baudrate"]    = int(body.get("baudrate") or 9600)
    else:  # tcp
        entry["listen_host"] = body.get("listen_host") or "0.0.0.0"
        entry["listen_port"] = int(body.get("listen_port") or 5100)

    path = _P("config/devices") / f"{dev_id}.yaml"
    if path.exists() and not body.get("overwrite"):
        return jsonify({"ok": False, "error": "device already exists (pass overwrite:true)"}), 409
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_y.safe_dump(entry, sort_keys=False), encoding="utf-8")
    audit(AuditEvent.DEVICE_CONNECTED, ip=_client_ip(),
          actor=session.get("username", "?"),
          detail={"created": dev_id, "type": dtype, "transport": transport})
    _try_reload_gateway()
    return jsonify({"ok": True, "path": str(path), "custom_type": dtype not in _ALLOWED_TYPES})


# ── SLA report ────────────────────────────────────────────────────────────────

@app.route("/api/sla/<period>")
@_require_role("operator")
def api_sla(period: str):
    """period = YYYY-MM"""
    m = re.match(r"^(\d{4})-(\d{2})$", period)
    if not m:
        return jsonify({"ok": False, "error": "period must be YYYY-MM"}), 400
    y, mo = int(m.group(1)), int(m.group(2))
    from src.common.sla_report import compute_month, render_html
    report = compute_month(y, mo)
    if request.args.get("format") == "html":
        cfg_raw = _read_yaml_raw()
        try:
            import yaml as _y
            facility = ((_y.safe_load(cfg_raw) or {}).get("hl7") or {}).get("sending_facility", "PRAXIS")
        except Exception:
            facility = "PRAXIS"
        html = render_html(report, facility=facility, version=GATEWAY_VERSION)
        return html, 200, {"Content-Type": "text/html; charset=utf-8"}
    return jsonify(report)


# ── Test dispatch ─────────────────────────────────────────────────────────────

@app.route("/api/targets/<name>/test", methods=["POST"])
@_require_role("operator")
def api_targets_test(name: str):
    """
    Send a synthetic HL7 message to a target to verify the wiring.
    The message uses a fake sample id "TEST_<timestamp>" so a real LIS can
    easily identify and discard it.
    """
    if not _csrf_check():
        return jsonify({"ok": False, "error": "CSRF token invalido"}), 400
    try:
        import yaml as _yaml
        raw = _read_yaml_raw()
        cfg = _yaml.safe_load(raw) or {}
    except Exception as exc:
        return jsonify({"ok": False, "error": f"config parse: {exc}"}), 500

    target = next((t for t in cfg.get("targets", []) if t.get("name") == name), None)
    if not target:
        return jsonify({"ok": False, "error": f"target {name!r} not found"}), 404
    if not target.get("enabled"):
        return jsonify({"ok": False, "error": f"target {name!r} is disabled"}), 400

    # Build a fake result + message
    from config.settings import GatewayConfig, HL7Config
    from src.hl7.builder import HL7Builder
    from src.transport.dispatcher import Dispatcher
    from datetime import datetime as _dt

    fake_result = {
        "timestamp":    _dt.now(),
        "sample_id":    f"TEST_{_dt.now().strftime('%H%M%S%f')}",
        "patient_id":   "TEST0000",
        "patient_name": "TEST Patient",
        "gender":       "M",
        "disc_name":    "TEST",
        "lot_id":       "TEST",
        "observations": [{
            "analyte": "AST", "value": "10", "value_num": 10.0, "flag": "",
            "ref_low": 15, "ref_high": 40, "unit": "U/L",
        }],
    }
    hl7_cfg = HL7Config.model_validate(cfg.get("hl7", {}))
    builder = HL7Builder(hl7_cfg)
    msg = builder.build_oru_r01(fake_result)

    # Build a single-target dispatcher to send just to `name`
    single_target_cfg = GatewayConfig.model_validate({**cfg, "targets": [target]})
    dispatcher = Dispatcher(single_target_cfg)
    summary = _run_async(dispatcher.dispatch(msg, fake_result))
    audit(AuditEvent.SERVICE_ACTION, ip=_client_ip(),
          actor=session.get("username","?"),
          detail={"test_target": name, "summary": summary.to_dict()})
    return jsonify({"ok": bool(summary.succeeded), "summary": summary.to_dict(),
                    "hl7_preview": msg.to_string()[:400]})


# ── Health probes (Kubernetes-style / systemd / LB) ──────────────────────────
#
# Public — no auth. `/livez` proves the process turns; `/readyz` aggregates
# subsystem state. Wired to src.common.health so probes match what the docs
# and the runbook promise.

@app.route("/livez")
def livez_endpoint():
    from src.common.health import livez as _livez
    code, body = _livez()
    return jsonify(body), code


@app.route("/readyz")
def readyz_endpoint():
    from src.common.health import readyz as _readyz
    code, body = _readyz()
    return jsonify(body), code


@app.route("/healthz")
def healthz_endpoint():
    # Kubernetes historically used /healthz for both. Alias to /livez so
    # older probe configs keep working.
    from src.common.health import livez as _livez
    code, body = _livez()
    return jsonify(body), code


# ── Hot config reload ─────────────────────────────────────────────────────────

@app.route("/api/config/reload", methods=["POST"])
@_require_role("admin")
def api_config_reload():
    """
    Send SIGHUP to the gateway pid so it re-reads gateway.yaml without a full
    systemctl restart. Only structural changes (queue size, log_file) still
    need a restart -- the gateway logs a WARNING when it detects those.
    """
    if not _csrf_check():
        return jsonify({"ok": False, "error": "CSRF token invalido"}), 400
    try:
        # Prefer systemctl kill so we don't need to read the PID file.
        subprocess.run(["sudo", "systemctl", "kill", "--signal=SIGHUP", "jerumednexus-gateway"],
                       check=True, capture_output=True, timeout=5)
        audit(AuditEvent.SERVICE_ACTION, ip=_client_ip(),
              actor=session.get("username","?"),
              detail={"action": "SIGHUP"})
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


# Register blueprints
app.register_blueprint(users_bp)
app.register_blueprint(dlq_bp)
app.register_blueprint(discovery_bp)
app.register_blueprint(metrics_bp)
app.register_blueprint(inspect_bp)
app.register_blueprint(wizard_bp)
app.register_blueprint(topology_bp)
app.register_blueprint(verifica_bp)
app.register_blueprint(wire_replay_bp)
app.register_blueprint(bulk_dlq_bp)
app.register_blueprint(qr_bp)
app.register_blueprint(golden_bp)
app.register_blueprint(build_info_bp)
app.register_blueprint(fleet_bp)


# Doctor overview (live area of the dashboard)
from webui import overview as _overview  # noqa: E402


def _overview_inputs() -> dict:
    return {"status_file": STATUS_F, "config_file": CONFIG_F,
            "service": _service_status()}


app.register_blueprint(_overview.make_blueprint(_require_auth, _overview_inputs))
_overview.register_filters(app)
from webui import results_view as _results_view  # noqa: E402
app.register_blueprint(_results_view.make_blueprint(_require_auth))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=False)
