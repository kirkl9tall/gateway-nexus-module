import json, sys, os
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlsplit

site = sys.argv[1]
port = int(sys.argv[2])


class H(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=site, **kw)

    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        path = urlsplit(self.path).path
        ref = self.headers.get("Referer", "")
        if path == "/api/status":
            if "/p/off-" in ref:
                return self._json({"service_systemd": "inactive", "running": False})
            return self._json({"service_systemd": "active", "running": True, "errors_today": 3,
                               "results_total": 999, "uptime_seconds": 7200})
        if path == "/api/dlq":
            if "-viewer" in ref:
                return self._json({"ok": False}, 403)
            n = 12 if "/p/trouble-" in ref else 0
            return self._json({"entries": [{"targets": ["x"]}] * n})
        if path == "/api/devices/discovered":
            return self._json({"pending": [{"key": "a"}, {"key": "b"}] if "/p/trouble-" in ref else []})
        if path.startswith("/api/") or path.startswith("/overview/"):
            return self._json({}, 404)
        return super().do_GET()


ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
