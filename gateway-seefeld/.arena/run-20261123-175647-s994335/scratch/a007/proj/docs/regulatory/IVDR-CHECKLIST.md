# IVDR (Regulation (EU) 2017/746) checklist -- Class A

**This gateway probably falls under IVDR Class A.** Confirm with a notified
body / IVDR consultant.

## Classification (Article 47 + Annex VIII, Rule 5)

- [x] Intended purpose declared in `README.md` and user manual
- [x] No direct impact on diagnosis / therapy (pure IT integration)
- [x] Not a companion diagnostic (Rule 3a)
- [x] Not near-patient testing (Rule 4)
- [x] Rule 5 default -> Class A

Class A means:
- Self-certification (no notified body required)
- General safety and performance requirements (Annex I) must be met
- Technical documentation (Annexes II + III) required
- EUDAMED registration required from 2027 onwards

## General safety and performance requirements (Annex I)

- [x] Reduce risks as far as possible (Ch. I § 2) -- see RISK-ANALYSIS.md
- [x] Software lifecycle documented (Ch. II § 17.1) -- see IEC-62304.md
- [x] IT security (Ch. II § 17.2) -- see SECURITY.md
- [x] Verification and validation (Ch. II § 17.3) -- tests/ + integration/
- [x] Instructions for use in language(s) of member state -- README currently DE/IT
- [ ] Traceability (Ch. III § 20) -- UDI-DI assigned: ______

## Technical documentation (Annex II)

- [ ] Device description + intended purpose (draft in README.md, expand)
- [x] Information supplied by the manufacturer (README, docs/, in-app help)
- [x] Design and manufacturing information (ARCHITECTURE.md)
- [x] General safety and performance requirements checklist (this file)
- [x] Benefit-risk analysis (RISK-ANALYSIS.md)
- [x] Product verification and validation (tests/, CI)
- [ ] Post-market surveillance plan (create `docs/PMS-PLAN.md`)

## Declaration of conformity

Draft under `docs/regulatory/DoC-TEMPLATE.md` -- fill in with your QM.

## Post-market surveillance (Article 78)

- [x] Vulnerability disclosure (SECURITY.md)
- [x] Version tracking (CHANGELOG.md)
- [ ] Complaint log procedure
- [ ] PMS report every 2 years (Class A)

## EUDAMED (Article 26)

- [ ] Manufacturer registered
- [ ] Device registered with UDI-DI
- [ ] Basic UDI-DI assigned to product family
