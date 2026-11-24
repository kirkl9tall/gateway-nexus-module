# JerumedNexus Gateway — REST API

Auth: session cookie (Web UI) or Bearer token on `/ingest/*`.
Content type: `application/json` unless noted.
CSRF: state-changing endpoints require `X-CSRF-Token` header
(supplied automatically by the Web UI's global fetch wrapper).

Roles:
- **viewer** — GET-only, dashboards, status
- **operator** — viewer + service actions + DLQ + discovery + test dispatch
- **admin** — operator + config save + users + license + update

---

## Auth

| Method | Path | Body | Response |
|--------|------|------|----------|
| POST | `/login` | form: `username`, `password` | 302 → `/` |
| GET  | `/logout` | | 302 → `/login` |
| POST | `/setup` | form: `password`, `confirm` (first-run only) | 302 → `/login` |

## Status & telemetry

| Method | Path | Role | Description |
|--------|------|------|-------------|
| GET | `/api/status` | viewer | Live status: results, errors, queue, targets, breakers, last_seen |
| GET | `/api/logs?n=80` | viewer | Last N log lines |
| GET | `/api/history?q=&device=&status=&since=&limit=200` | viewer | Search dispatch history (SQLite) |
| GET | `/api/history/trend?hours=24` | viewer | Hourly counts for the trend chart |
| GET | `/metrics` | localhost | Prometheus exposition (open with `WEBUI_METRICS_PUBLIC=1`) |

## Configuration

| Method | Path | Role | Description |
|--------|------|------|-------------|
| GET  | `/api/config` | admin | Get raw gateway.yaml |
| POST | `/api/config` | admin | Save gateway.yaml (validates YAML) |
| POST | `/api/config/reload` | admin | Send SIGHUP for hot-reload (no restart) |
| POST | `/api/service/start\|stop\|restart` | operator | Systemd action |

## Users

| Method | Path | Role | Description |
|--------|------|------|-------------|
| GET    | `/api/users` | admin | List users + current session role |
| POST   | `/api/users` | admin | `{name, password, role}` |
| DELETE | `/api/users/<name>` | admin | Remove user |
| POST   | `/api/users/<name>/role` | admin | `{role: "viewer\|operator\|admin"}` |

## Targets (PIS/LIS)

| Method | Path | Role | Description |
|--------|------|------|-------------|
| POST | `/api/targets/<name>/test` | operator | Send a synthetic HL7 to verify wiring |

## Dead-letter queue

| Method | Path | Role | Description |
|--------|------|------|-------------|
| GET  | `/api/dlq?limit=100` | operator | List DLQ entries (newest first) |
| GET  | `/api/dlq/<control_id>` | operator | Return raw HL7 body |
| POST | `/api/dlq/<control_id>/replay` | operator | Re-dispatch. Optional `{targets: [...]}` restricts. |

## Plug-and-play device discovery

| Method | Path | Role | Description |
|--------|------|------|-------------|
| GET  | `/api/devices/discovered` | viewer | Snapshot + pending list |
| POST | `/api/devices/discover` | operator | `{tcp_range: [...], tcp_ports: [...]}` (both optional; if omitted → USB only) |
| POST | `/api/devices/activate` | admin | `{key, device_type}` — writes gateway.yaml |
| POST | `/api/devices/notify_added` | localhost | udev callback (form: `dev`) |
| POST | `/api/devices/notify_removed` | localhost | udev callback (form/query: `dev`) |

## License

| Method | Path | Role | Description |
|--------|------|------|-------------|
| POST | `/api/license/activate` | admin | `{key, customer?}` — verifies HMAC + writes |

## Update

| Method | Path | Role | Description |
|--------|------|------|-------------|
| POST | `/api/update/check` | admin+localhost | `git fetch --dry-run` |
| POST | `/api/update/apply` | admin+localhost | `git pull && pip install && restart` |

## LOC-200 HTTP ingestion (separate service, port 5003)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/` `/hl7` `/result` `/upload` `/lis/*` `/detection` | Bearer `LOC200_HTTP_TOKEN` + optional IP allowlist | Accepts HL7 v2 text or JSON. Rate limit 60/min/IP. |
| GET  | `/health` | (public) | `{"status":"ok"}` |
