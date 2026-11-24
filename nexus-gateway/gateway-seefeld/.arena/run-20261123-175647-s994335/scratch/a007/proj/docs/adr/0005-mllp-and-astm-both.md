# ADR-0005 — Support both HL7 MLLP and ASTM E1381/1394 first-class

- **Status:** Accepted
- **Date:** 2026-08-27
- **Deciders:** protocol engineer, integration engineer

## Context

The device-catalog research (see [docs/devices/RESEARCH.md](../devices/RESEARCH.md))
confirmed that even devices from the same vendor (Roche c111 vs. b101,
Sysmex XQ-320 vs. XN-1000) speak **different transport protocols**.
POCT devices increasingly speak POCT1-A but many chemistry / hematology
analyzers still ship with ASTM only.

Options:
1. Support HL7 only — force clinics to buy a middleware.
2. Support ASTM only — same problem the other way.
3. Support both, first-class.

## Decision

Both protocols are first-class adapters:

- `sysmex_astm` — LIS2-A2 / E1381 low-level + E1394 record structure,
  ENQ/ACK/EOT handshake, per-device `read_timeout_seconds`.
- `mllp_hl7` — HL7 v2.5/2.7 with MLLP framing (VT..FS-CR), MSA
  acknowledgement.
- `cobas_poct` — POCT1-A2 XML variant for the Roche POCT family.
- `uc1000_serial`, `reflotron_serial`, `loc200_native` — vendor-specific
  serial formats we translate to canonical HL7 in-house.

All adapters converge on the same canonical message object, then the
HL7 builder emits ORU^R01 to whatever the clinic's LIS wants.

## Consequences

- Positive: **no middleware required** for 28 supported analyzers.
- Positive: adding a new protocol is a new adapter + registry branch;
  the canonical model is stable.
- Negative: more code paths to test. Golden-file tests + property
  fuzzing (Hypothesis) + mutation testing (mutmut) mitigate.
- Positive: the ASTM adapter can be reused for any LIS-2 device with
  small mapping tweaks (this is how we added Horiba Microsemi and
  Bio-Rad D-10 without new code).
