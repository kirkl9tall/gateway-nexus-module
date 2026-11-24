"""
Dual-server launcher — starts the Flask WebUI on:

  * HTTP  :8080  (legacy, plaintext, kept for backward compatibility)
  * HTTPS :8443  (self-signed cert, works in Chrome/Firefox/Edge without
                 special flags — user accepts the warning once)

Runs both on threads sharing the same Flask app. If the TLS cert files
are missing, only HTTP is started.

Called by the systemd unit:
    ExecStart=<venv>/bin/python -m webui.serve
"""
from __future__ import annotations

import logging
import sys
import threading
from pathlib import Path

# Make sure the project root is importable when run as `python -m webui.serve`
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from webui.app import app  # noqa: E402

log = logging.getLogger("webui.serve")
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

HTTP_PORT  = 8080
HTTPS_PORT = 8443
CERT_FILE = _ROOT / "config" / "webui_cert.pem"
KEY_FILE  = _ROOT / "config" / "webui_key.pem"


def _run_http() -> None:
    log.info("HTTP  listening on 0.0.0.0:%d", HTTP_PORT)
    app.run(host="0.0.0.0", port=HTTP_PORT,
            debug=False, use_reloader=False, threaded=True)


def _run_https() -> None:
    if not (CERT_FILE.exists() and KEY_FILE.exists()):
        log.warning("TLS cert (%s) or key (%s) missing — HTTPS disabled. "
                    "Run scripts/install.sh again, or generate manually with "
                    "openssl.", CERT_FILE, KEY_FILE)
        return
    log.info("HTTPS listening on 0.0.0.0:%d (self-signed cert %s)",
             HTTPS_PORT, CERT_FILE)
    try:
        app.run(host="0.0.0.0", port=HTTPS_PORT,
                debug=False, use_reloader=False, threaded=True,
                ssl_context=(str(CERT_FILE), str(KEY_FILE)))
    except Exception as exc:
        log.error("HTTPS server crashed: %s", exc, exc_info=True)


def main() -> None:
    # HTTPS on a background thread so the systemd unit's main process
    # stays the HTTP server (simpler process supervision).
    t = threading.Thread(target=_run_https, name="webui-https", daemon=True)
    t.start()
    _run_http()


if __name__ == "__main__":
    main()
