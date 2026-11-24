# Risk analysis (ISO 14971 template)

**This is a starting skeleton -- work through it with a certified ISO 14971
consultant. Do not ship without an approved Risk Management File.**

## Scope

Software: JerumedNexus Gateway v1.1
Intended use: convert laboratory analyzer results into HL7 v2.5 messages
and forward them to a Practice Information System. No clinical decision.
Intended users: laboratory technicians and IT administrators in Swiss and
DACH private practices.

## Method

Method: FMEA + hazard analysis per ISO 14971:2019.
Severity, probability and detectability graded 1-5.
Risk Priority Number (RPN) = S x P x D.
Acceptance: RPN <= 12 for uncontrolled risks; risk reduction required above.

## Hazard categories

### H1. Data integrity

| ID | Hazard | Cause | Effect | S | P | D | RPN | Mitigation | Residual |
|----|--------|-------|--------|---|---|---|-----|-----------|----------|
| H1.1 | HL7 message mis-assembled | Parser bug | LIS rejects or, worse, misinterprets result | 5 | 2 | 3 | 30 | Unit + property tests; ACK correlation; complete HL7 escape | 8 |
| H1.2 | Wrong LOINC code | Placeholder in map | LIS misclassifies analyte | 4 | 2 | 3 | 24 | Warning logged on placeholder; catalog reviewed each release | 8 |
| H1.3 | Wrong unit | Adapter bug | Clinician misreads result | 5 | 1 | 3 | 15 | Unit fixture per adapter; property test on unit round-trip | 5 |
| H1.4 | Message dropped silently | Queue overflow | Result never reaches LIS | 5 | 2 | 4 | 40 | Backpressure + DLQ + alerts + queue_full metric | 10 |
| H1.5 | Duplicate message | Retry after ACK lost | LIS may re-file result | 3 | 2 | 3 | 18 | ACK correlation + LIS-side dedup | 6 |

### H2. Availability

| ID | Hazard | Cause | Effect | S | P | D | RPN | Mitigation | Residual |
|----|--------|-------|--------|---|---|---|-----|-----------|----------|
| H2.1 | Gateway crashes | Unhandled exception | Results stop flowing | 4 | 2 | 5 | 40 | systemd Restart=on-failure + health check + Prometheus alerts | 8 |
| H2.2 | PIS unreachable | Network fault | Backlog accumulates | 4 | 3 | 4 | 48 | Retry + circuit breaker + DLQ; alert to on-call | 12 |
| H2.3 | SD card corruption | Power loss | Data loss + failed boot | 5 | 2 | 3 | 30 | Periodic seen_samples save; recommend battery UPS in datasheet | 10 |

### H3. Security / confidentiality

| ID | Hazard | Cause | Effect | S | P | D | RPN | Mitigation | Residual |
|----|--------|-------|--------|---|---|---|-----|-----------|----------|
| H3.1 | Unauthorised admin access | Weak or default password | Full config change, license bypass | 5 | 2 | 3 | 30 | bcrypt, 12-char min, no default, rate limit | 8 |
| H3.2 | Injected results via HTTP | Missing token | Fake results reach LIS | 5 | 1 | 4 | 20 | Bearer token, IP allowlist, disabled if no token set | 5 |
| H3.3 | Log leakage | Patient IDs in plain logs | nDSG breach | 4 | 2 | 3 | 24 | Audit log hashes IDs; app logs restricted to loc200 user | 6 |
| H3.4 | CSRF against admin | Malicious link | Config changed | 3 | 2 | 3 | 18 | CSRF token + SameSite cookie | 6 |

### H4. Clinical (out of scope but declared)

| ID | Hazard | Cause | Effect | S | P | D | RPN | Mitigation | Residual |
|----|--------|-------|--------|---|---|---|-----|-----------|----------|
| H4.1 | Clinician misuses "abnormal" flag | Reads H/L as decision | Wrong treatment | 5 | 1 | 5 | 25 | User manual states gateway does no clinical judgement | 15 |

## Overall benefit-risk

The residual risks are acceptable when the software is deployed as
documented (isolated LAN, admin training, monitoring). No single failure
mode causes patient harm without an intervening clinical decision.

## Post-market surveillance

- CHANGELOG.md tracks every issue.
- SECURITY.md defines vulnerability disclosure.
- Customer support tickets triaged monthly for new hazards.
- New version = new risk analysis review (see IEC 62304 lifecycle).

---
Approved by: _____________________  Date: __________
Quality Manager: _________________  Date: __________
