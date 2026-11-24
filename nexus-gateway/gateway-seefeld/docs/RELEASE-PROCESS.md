# Release Process

Cutting a new release is a **single shell command** that runs the full
pipeline end-to-end and produces signed artifacts.

## Prerequisites

- **Signing GPG key** in the vendor's keyring, exported via
  `SIGNING_KEY_ID=<hex>`
- **cosign** installed for Docker signing
- **debsigs** installed for .deb signing
- **reprepro** available on the APT repo server
- **SSH access** to the APT publisher account
- **Docker registry** authenticated (via `docker login`)

## Cutting a release

```bash
export SIGNING_KEY_ID=4A5B6C7D8E9F0A1B
sudo ./scripts/release.sh 1.4.0
```

The script does:

1. Bumps `pyproject.toml` version
2. Verifies `CHANGELOG.md` has `Unreleased` content (fails if empty)
3. Runs full test suite (must be green)
4. Runs `bandit` + `pip-audit` (must be clean)
5. Generates `sbom-<version>.cdx.json` (CycloneDX SPDX)
6. Builds the `.deb` via `dh_virtualenv`
7. Signs the `.deb` with `debsigs --sign=origin`
8. Builds the Docker image
9. Signs the Docker image with `cosign sign` + `cosign attest --predicate sbom.json`
10. Publishes the `.deb` to the APT repo
11. Pushes the Docker image to the registry
12. Creates a signed git tag and pushes to origin

## Verification (by the customer)

```bash
# Verify .deb signature
debsigs --verify /var/cache/apt/archives/jerumednexus-gateway_1.4.0*.deb

# Verify Docker image signature
cosign verify ghcr.io/jerumed-nexus/gateway:1.4.0 \
    --certificate-identity-regexp='.*'

# Fetch attached SBOM
cosign download attestation ghcr.io/jerumed-nexus/gateway:1.4.0 | jq .
```

## Rollback

```bash
# APT — pin the previous version
apt install jerumednexus-gateway=1.3.9*
apt-mark hold jerumednexus-gateway

# Docker — rollback via tag
docker pull ghcr.io/jerumed-nexus/gateway:1.3.9
```

## Semver policy

See [docs/VERSIONING.md](VERSIONING.md).
