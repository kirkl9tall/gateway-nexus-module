# Contributing

Thanks for helping improve JerumedNexus Gateway. This document is the
short version — the full engineering handbook lives under `docs/`.

## Ground rules

1. **Patient safety over speed.** Every code path that touches a lab
   result must have a test. If it doesn't, it doesn't ship.
2. **Backward-compatible by default.** Breaking a running clinic's Pi
   is unacceptable. Breaking changes go in a major version and follow
   the deprecation policy ([docs/VERSIONING.md](docs/VERSIONING.md)).
3. **No PII in issues, PRs, logs, or commits.** Use the hashed IDs the
   gateway generates. If in doubt, redact.

## Dev environment

```bash
git clone <repo> && cd gateway-seefeld
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
pytest                             # unit + integration
python -m tools.device_matrix      # sanity check on device catalog
```

## Branch & commit conventions

- Branches: `feat/<slug>`, `fix/<slug>`, `docs/<slug>`, `chore/<slug>`.
- Commits: [Conventional Commits](https://www.conventionalcommits.org/).
  Example: `fix(sysmex): honor read_timeout_seconds from profile`.
- Sign your commits (`git commit -s`) — required for CLA.

## Pull requests

1. Fork → feature branch → open PR to `main`.
2. Fill the PR template — checklist covers tests, docs, changelog.
3. All GitHub Actions must be green (unit, integration, mypy, ruff,
   security-scan, .deb build).
4. Two reviewer approvals required for any change under
   `src/adapters/**` or `src/security/**`.
5. Squash-merge with a Conventional Commit title. Body goes into the
   changelog draft.

## Adding a new device profile

1. Copy an existing YAML in `config/devices/` and edit.
2. Add the ID to the appropriate set in `tools/device_matrix.py`
   (VERIFIED_PROD / VERIFIED_DOC / SPECULATIVE).
3. If it needs a new protocol, add an entry to `DeviceType` in
   [src/devices/base.py](src/devices/base.py) and a branch in
   [src/devices/registry.py](src/devices/registry.py).
4. Document sources in [docs/devices/RESEARCH.md](docs/devices/RESEARCH.md).
5. If you have a real capture, drop it under
   `tests/fixtures/golden/<device>/` — the golden-file test picks it
   up automatically.

## Reporting bugs

Use the bug report template. Include `jerumednexus support-bundle`
output. **Never paste real patient data.**

## Reporting security issues

**Do not open a public issue.** Follow [SECURITY.md](SECURITY.md).

## Code of Conduct

We follow the [Contributor Covenant v2.1](https://www.contributor-covenant.org/version/2/1/code_of_conduct/).
Enforcement: `conduct@jerumednexus.example`.
