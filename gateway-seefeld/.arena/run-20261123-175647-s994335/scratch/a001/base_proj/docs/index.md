# JerumedNexus Gateway

**HL7 v2.5 / FHIR R4 gateway per analizzatori di laboratorio.**
Girano su Raspberry Pi, escon dati in vari gestionali medici (Vitomed,
curaMED, Aeskulap, Axenita, WinMed, DnaMed, Tomedo) e verso qualsiasi
LIS che parli HL7 v2 MLLP o FHIR R4.

## Perché

Ogni analizzatore parla un protocollo diverso (ASTM, HL7, POCT1-A2, seriali
proprietari). Ogni PIS/LIS pretende un formato particolare. Senza un
intermediario, ogni combinazione richiede un'integrazione custom.

Il gateway **unifica**: legge da 24 modelli di analizzatore, produce HL7 v2.5
(o FHIR R4) conforme, lo consegna a chiunque, con retry + circuit breaker +
DLQ + audit + SLA report.

## Caratteristiche

- **28 analizzatori pre-configurati** (Sysmex, Roche, Abbott, Siemens,
  Bio-Rad, Beckman, HemoCue, Radiometer, Menarini, Dirui, Erba, Mindray,
  i-SENS, PixCell…) — vedi [matrice di compatibilità](devices/COMPATIBILITY.md)
  con badge VERIFIED-PROD / VERIFIED-DOC / SPECULATIVE.
- **Plug-and-play**: rileva device USB/TCP e propone attivazione
- **Bidirezionale**: riceve ordini dal LIS e li inoltra all'analizzatore
- **FHIR R4** oltre a HL7 v2.5
- **Enterprise auth**: 2FA/TOTP, OIDC/SAML, LDAP/AD, RBAC
- **Observability**: Prometheus + OpenTelemetry + audit log
- **Regolatorio**: template IVDR Classe A, ISO 14971, DPA nDSG/GDPR
- **CI/CD**: firma `.deb` con GPG, firma Docker image con cosign, SLSA
  provenance
- **Test**: 90+ unit, integration, property-based (Hypothesis), E2E
  (Playwright), load (Locust), chaos scripts

## Da dove iniziare

- [Installazione](install.md) — su Raspberry Pi in 5 minuti
- [Getting started](getting-started.md) — primo device + primo target
- [Device supportati](DEVICES.md) — catalogo completo
- [Ricerca sui protocolli](devices/RESEARCH.md) — fonti e note per ogni device
- [Matrice compatibilità](devices/COMPATIBILITY.md) — stato di verifica
- [API REST](API.md) — riferimento completo
- [Troubleshooting](TROUBLESHOOTING.md) — flowchart per sintomo

## Governance & operations

- [SECURITY.md](../SECURITY.md) — vulnerability disclosure
- [SUPPORT.md](../SUPPORT.md) — tier SLA, escalation matrix
- [CONTRIBUTING.md](../CONTRIBUTING.md) — dev handbook
- [CHANGELOG.md](../CHANGELOG.md) — version history (Keep a Changelog)
- [VERSIONING policy](VERSIONING.md) — SemVer + deprecation
- [Architecture Decision Records](adr/) — why the system looks like this
- [Threat model](regulatory/THREAT-MODEL.md) — STRIDE per trust boundary
- [Disaster recovery runbook](runbooks/disaster-recovery.md) — RTO 2h, RPO 24h

## Community

- [GitHub](https://github.com/jerumed-nexus/jerumednexus-gateway)
