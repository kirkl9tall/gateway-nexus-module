"""
HL7 v2.9 and FHIR R5 additions.

v2.9 (2019) is the newest published HL7 v2. Backwards compatible with 2.5:
the MSH-12 changes to "2.9" and we honor the new required MSH-21
(Message Profile Identifier) and MSH-24 semantics we already added in
provenance.py.

FHIR R5 (2023) — Observation resource dropped `basedOn.request` in
favor of `basedOn.ServiceRequest` and added `Observation.instantiatesCanonical`.
For our transmission use case, the only user-visible change is bumping
the fhirVersion in Bundle.meta.
"""
from __future__ import annotations

SUPPORTED_HL7_VERSIONS = ("2.5", "2.5.1", "2.7", "2.7.1", "2.8", "2.9")
SUPPORTED_FHIR_VERSIONS = ("4.0", "4.0.1", "4.3", "5.0")


def normalize_hl7_version(v: str) -> str:
    """Coerce a user-supplied version string to a canonical one."""
    v = str(v).strip()
    if v in SUPPORTED_HL7_VERSIONS:
        return v
    if v.startswith("2."):
        return "2.5"
    return "2.5"


def normalize_fhir_version(v: str) -> str:
    v = str(v).strip()
    if v in SUPPORTED_FHIR_VERSIONS:
        return v
    if v.startswith("5"):
        return "5.0"
    if v.startswith("4."):
        return "4.0.1"
    return "4.0.1"


def is_v29_or_newer(v: str) -> bool:
    """True if the HL7 version supports MSH-25 message profile identifier."""
    return v in ("2.7", "2.7.1", "2.8", "2.9")
