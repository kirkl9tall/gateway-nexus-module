# SLSA (Supply-chain Levels for Software Artifacts)

Come proteggiamo la supply chain del `.deb` e dell'immagine Docker.

## Livello attuale — target SLSA v1.0 Build L3

| Requisito | Stato |
|-----------|-------|
| Source: hosted repository | ✅ GitHub |
| Source: retained indefinitely | ✅ GitHub |
| Build: scripted | ✅ `scripts/build-deb.sh`, `Dockerfile` |
| Build: build service | ✅ GitHub Actions |
| Build: isolated | ✅ each job in fresh runner |
| Provenance: exists | ✅ `.buildinfo` (dpkg) + `sbom.cdx.json` |
| Provenance: authenticated | ⚠️ da attivare (in-toto attestation via slsa-github-generator) |
| Provenance: signed | ⚠️ cosign attestation nel release workflow |

## Attivazione provenance signing

Aggiungi al `.github/workflows/release.yml`:

```yaml
provenance:
  needs: [build-deb]
  permissions:
    actions:   read
    id-token:  write
    contents:  write
  uses: slsa-framework/slsa-github-generator/.github/workflows/generator_generic_slsa3.yml@v1.9.0
  with:
    base64-subjects: "${{ needs.build-deb.outputs.hashes }}"
    upload-assets:   true
```

## Reproducible builds

Il `.deb` è "riproducibile" nel senso:
- Stessa versione Python, stesse deps pinnate in `requirements.txt`
- Stesso `debian/changelog` → stesso version string
- No timestamp di build embedded nei file Python

Verifica reproducibility:
```bash
# Sul tuo host
./scripts/build-deb.sh
sha256sum ../jerumednexus-gateway_*.deb > /tmp/hash1.txt

# Su un altro host con stessa configurazione
./scripts/build-deb.sh
sha256sum ../jerumednexus-gateway_*.deb > /tmp/hash2.txt

diff /tmp/hash1.txt /tmp/hash2.txt   # dovrebbe essere vuoto
```

Se differiscono, cerca:
- Timestamp negli artifacts intermedi (`--reproducible` flag su dpkg-deb)
- Path assoluti hardcoded
- Random-seeded caches (pip wheel cache)

## SBOM

Auto-generato in ogni release (via workflow release.yml):
- `artifacts/sbom.cdx.json` (CycloneDX format)
- Attesta ogni pacchetto Python + versione + hash
- Cliente enterprise può verificare licenze e CVE con Grype o Trivy

## Verifica lato cliente

```bash
# Verify .deb signature
debsigs --verify jerumednexus-gateway_1.2.0_all.deb

# Verify Docker image signature (see DOCKER-SIGNING.md)
cosign verify --certificate-identity-regexp "https://github.com/jerumed-nexus/.*" \
              --certificate-oidc-issuer "https://token.actions.githubusercontent.com" \
              ghcr.io/jerumed-nexus/jerumednexus-gateway:1.2.0

# Verify SLSA provenance
slsa-verifier verify-artifact --provenance-path attestation.intoto.jsonl \
  --source-uri github.com/jerumed-nexus/jerumednexus-gateway \
  --source-tag v1.2.0 \
  jerumednexus-gateway_1.2.0_all.deb
```
