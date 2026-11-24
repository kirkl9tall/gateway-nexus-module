# Docker image signing with cosign

The Dockerfile builds `ghcr.io/jerumed-nexus/jerumednexus-gateway`.
For enterprise deployments sign the image so clients can verify provenance.

## One-time setup

```bash
# Install cosign
brew install cosign            # macOS
# or: apt install cosign        # Debian bookworm-backports

# Generate a keypair (or use keyless signing with OIDC)
cosign generate-key-pair
# writes cosign.key (KEEP PRIVATE, mode 600) and cosign.pub
```

## Sign at release time

Add to `.github/workflows/release.yml`:

```yaml
- name: Login to GHCR
  uses: docker/login-action@v3
  with:
    registry: ghcr.io
    username: ${{ github.actor }}
    password: ${{ secrets.GITHUB_TOKEN }}

- name: Build + push multi-arch image
  uses: docker/build-push-action@v5
  with:
    context: .
    platforms: linux/amd64,linux/arm64,linux/arm/v7
    push: true
    tags: |
      ghcr.io/jerumed-nexus/jerumednexus-gateway:${{ github.ref_name }}
      ghcr.io/jerumed-nexus/jerumednexus-gateway:latest

- name: Sign image with cosign (keyless, uses GitHub OIDC)
  env:
    COSIGN_EXPERIMENTAL: "1"
  run: |
    cosign sign --yes \
      ghcr.io/jerumed-nexus/jerumednexus-gateway:${{ github.ref_name }}
```

## Client verification (customer side)

```bash
COSIGN_EXPERIMENTAL=1 cosign verify \
  --certificate-identity-regexp "https://github.com/jerumed-nexus/.*" \
  --certificate-oidc-issuer "https://token.actions.githubusercontent.com" \
  ghcr.io/jerumed-nexus/jerumednexus-gateway:1.1.0
```

If the verify command exits 0, the image is authentic.
Add this to `docker-compose.yml` deployment scripts as a pre-pull step.

## Alternative: keyed signing (offline verification)

Publish `cosign.pub` alongside the release. Customers verify with:

```bash
cosign verify --key cosign.pub \
  ghcr.io/jerumed-nexus/jerumednexus-gateway:1.1.0
```
