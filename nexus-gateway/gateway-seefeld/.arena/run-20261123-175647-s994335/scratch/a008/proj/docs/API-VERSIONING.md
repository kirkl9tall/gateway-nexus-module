# API versioning & deprecation

The REST API under `/api/v1/**` is a **stable contract**. This document
tells you what "stable" means and how we evolve it without breaking
clients.

## URL scheme

Every endpoint is prefixed by the API major version:

```
/api/v1/devices
/api/v1/devices/<id>
/api/v1/history?...
/api/v1/patient/<id>/export
/api/v1/patient/<id>/purge
```

Web UI endpoints (`/ui/*`) and probe endpoints (`/livez`, `/readyz`,
`/metrics`) are **not** part of this contract and may change at any
minor bump.

## Compatibility rules within a MAJOR

Within a MAJOR (say `v1`), we guarantee:

- No field is **removed** from a response.
- No field **changes type**.
- No response's HTTP status code changes for the same input.
- New fields **may** be added — clients MUST tolerate unknown fields.
- New optional query parameters **may** be added.
- New endpoints **may** be added.

Any change that would violate the above requires bumping to `v2`.

## Error format (stable across MAJORs)

Every 4xx/5xx response conforms to:

```json
{
  "error":   "E3001",
  "message": "cannot reach LIS 'tomedo-prod': connection refused",
  "detail":  {"target": "tomedo-prod", "cause": "connection refused"}
}
```

The `error` field uses the [error taxonomy](../src/common/errors.py).
Codes are stable across MAJORs (a code never gets a new meaning). New
codes appear at any minor; retired codes stay reserved and never come
back.

## Deprecation

An endpoint or field marked **DEPRECATED** in `vN.Y.Z`:

1. Returns a `Deprecation: <date>` and `Sunset: <date>` HTTP header.
2. Logs at `WARNING` in `gateway.log`.
3. Is documented in the CHANGELOG under _Deprecated_.
4. Is removed no earlier than `v(N+1).0.0`.

Example:
```
GET /api/v1/legacy/status HTTP/1.1

HTTP/1.1 200 OK
Deprecation: 2026-09-01
Sunset: 2027-09-01
Link: </api/v1/status>; rel="successor-version"
```

## Version rollover checklist

When the vendor cuts `v2`:

- [ ] `v2` endpoints ship in parallel to `v1` for at least 12 months.
- [ ] Migration guide at `docs/migrations/v1-to-v2.md`.
- [ ] Auto-detection in the JS SDK — falls back to `v1` if `v2` 404s.
- [ ] Sunset date announced 60 days ahead in the changelog and via the
      trust page.

## Client libraries

- Python: `pip install jerumednexus-client` — pinned to a MAJOR.
- JavaScript: `npm i @jerumednexus/client` — pinned to a MAJOR.
- Postman collection: [docs/postman/](postman/) — updated per minor.
