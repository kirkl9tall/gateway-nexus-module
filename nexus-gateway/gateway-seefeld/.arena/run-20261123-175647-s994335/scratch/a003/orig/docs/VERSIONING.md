# Versioning policy

JerumedNexus Gateway follows **[Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html)**
strictly. This document is the contract between vendor and clinic.

## What each number means

- **MAJOR (`X`.y.z)** — breaking change to:
  - The `gateway.yaml` schema (a field removed or its semantics changed).
  - The HL7 v2 / FHIR R4 output format (a segment removed, a code changed).
  - The Web UI REST API (`/api/**`).
  - The Python public API (import surface of `src.*` used by plugins).
- **MINOR (`x`.`Y`.z)** — backwards-compatible addition:
  - A new device profile or protocol adapter.
  - A new optional config field.
  - A new endpoint in the Web UI API.
  - A new CLI subcommand.
- **PATCH (`x`.y.`Z`)** — backwards-compatible fix:
  - Bug fixes, security patches, doc improvements.
  - Performance improvements with no behavior change.

## Release cadence

- **Patch**: as needed, security-fix release SLA in [SECURITY.md](../SECURITY.md).
- **Minor**: every 6–8 weeks.
- **Major**: at most once per year, announced ≥ 60 days before release
  with a migration guide.

## Supported versions

At any time we support:

- The current **MAJOR.MINOR** line (all its patches).
- The previous **MAJOR.MINOR** line for 6 months after the next minor
  release ships.
- The last **MAJOR-1.x** line for 12 months after the next major
  ships (security-only patches).

See [SECURITY.md](../SECURITY.md) for the concrete table.

## Deprecation policy

A feature marked **DEPRECATED** in release `X.Y.Z`:

1. Stays functional in every subsequent minor release of `X`.
2. Emits a `DeprecationWarning` at import / boot time.
3. Is documented in the CHANGELOG **and** in a `docs/migrations/`
   guide with an equivalent replacement.
4. May be removed no earlier than **`X+1`.0.0** (the next major).

Removing a deprecated feature earlier than that is a bug we will
revert.

## Pre-release identifiers

- `1.4.0-rc.1` — release candidate, feature-frozen, only bugfixes
  allowed before promotion to `1.4.0`.
- `1.4.0-beta.1` — feature-complete but under active testing; API may
  still change without a major bump. Do not deploy to production
  clinics.
- `1.4.0-alpha.1` — internal / partner preview; no compatibility
  guarantees at all.

## Build metadata

`1.3.0+git.abcdef1` — the trailing `+…` is build metadata (ignored
by SemVer comparison). Our CI stamps it into the `.deb` version and
into `webui/__init__.py` for the About page.

## Data-file compatibility

- **SQLite `history.db`** schema migrations are applied automatically
  and are one-way (roll-forward only). Roll back the app to a previous
  minor only by restoring a backup.
- **`gateway.yaml`** — new optional fields are added at minor bumps
  with sensible defaults. Removed fields go through the deprecation
  policy above.
- **HL7/FHIR wire format** — segment ordering and required fields do
  not change within a MAJOR. LOINC code mapping changes are treated as
  breaking and bump MAJOR.

## Emergency exceptions

If a critical security fix requires a breaking change inside a MAJOR,
we release the fix as a MINOR bump, ship a migration script, and
document the exception in the CHANGELOG and in this file's log below.

## Exceptions log

_None yet._
