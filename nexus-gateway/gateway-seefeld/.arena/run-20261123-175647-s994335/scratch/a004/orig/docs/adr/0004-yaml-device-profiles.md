# ADR-0004 — YAML device profiles under `config/devices/`

- **Status:** Accepted
- **Date:** 2026-08-25
- **Deciders:** core engineering, integration engineer

## Context

Originally each analyzer had its own top-level block in
`gateway.yaml`. Adding a device meant editing the schema, the loader,
and the UI. This did not scale past ~5 devices; we now ship 28.

## Decision

Every device is a **single YAML file** under `config/devices/`. The
registry ([src/devices/registry.py](../../src/devices/registry.py))
walks the directory at boot, parses each file into a
`DeviceDefinition` (`pydantic`), and instantiates the matching
adapter based on `type`.

Adding a device is: one YAML file + optional new `DeviceType` value.
No changes to core loader, wizard, or Web UI.

## Consequences

- Positive: profile files are diffable, reviewable, shareable between
  clinics. `python -m tools.device_matrix` reads the catalog.
- Positive: legacy `gateway.yaml` blocks still work through
  `src/devices/legacy.py` — no forced migration.
- Negative: 28 tiny files instead of 1 medium file. Editors love the
  new layout, ops sometimes complain about `find` — mitigated by the
  matrix generator and the wizard.
