#!/bin/bash
# ============================================================
#  release.sh — cut a new signed release end-to-end.
#
#  Steps:
#    1. Bump version in pyproject.toml
#    2. Update CHANGELOG (verify Unreleased section is not empty)
#    3. Run full test suite
#    4. Run bandit + pip-audit
#    5. Generate SBOM (CycloneDX)
#    6. Build .deb via dh_virtualenv
#    7. Sign .deb with debsigs (requires SIGNING_KEY_ID)
#    8. Build Docker image
#    9. Sign Docker image with cosign
#   10. Push .deb to internal APT repo
#   11. Push Docker to registry
#   12. Create git tag + push to origin
#
#  Usage:  sudo ./scripts/release.sh <new-version>
#     e.g. sudo ./scripts/release.sh 1.4.0
# ============================================================
set -euo pipefail

VERSION="${1:?Usage: $0 <new-version>}"
SIGNING_KEY_ID="${SIGNING_KEY_ID:?SIGNING_KEY_ID env var required}"
APT_REPO_HOST="${APT_REPO_HOST:-apt.jerumednexus.example}"
DOCKER_REG="${DOCKER_REG:-ghcr.io/jerumed-nexus}"

log() { echo -e "\033[1;34m[release]\033[0m $*"; }
die() { echo -e "\033[1;31m[FAIL]\033[0m $*" >&2; exit 1; }

# 1. Version bump
log "1/12 Bumping version to $VERSION"
sed -i "s/^version = \".*\"/version = \"$VERSION\"/" pyproject.toml
grep -q "^version = \"$VERSION\"$" pyproject.toml || die "version bump failed"

# 2. CHANGELOG check
log "2/12 Checking CHANGELOG has Unreleased content"
lines=$(awk '/^## \[Unreleased\]/{flag=1;next}/^## \[/{flag=0}flag' CHANGELOG.md | grep -c '^-' || true)
[ "$lines" -gt 0 ] || die "CHANGELOG has no Unreleased entries"

# 3. Tests
log "3/12 Running full test suite"
python -m pytest tests/ -q --tb=line || die "tests failed"

# 4. Security scans
log "4/12 bandit + pip-audit"
bandit -c pyproject.toml -r src -q || die "bandit found issues"
pip-audit -r requirements.txt --strict || die "pip-audit found vulnerabilities"

# 5. SBOM
log "5/12 Generating CycloneDX SBOM"
cyclonedx-py requirements -i requirements.txt -o dist/sbom-$VERSION.cdx.json

# 6. .deb build
log "6/12 Building .deb"
rm -rf build dist
mkdir -p dist
dh_virtualenv --python /usr/bin/python3.11 || die "dh_virtualenv failed"
mv ../jerumednexus-gateway_*.deb dist/

# 7. Sign .deb
log "7/12 Signing .deb with debsigs"
DEB=$(ls dist/jerumednexus-gateway_${VERSION}*.deb | head -1)
debsigs --sign=origin --default-key="$SIGNING_KEY_ID" "$DEB"
debsigs --verify "$DEB" || die "signature verification failed"

# 8. Docker build
log "8/12 Building Docker image"
docker build -t "$DOCKER_REG/gateway:$VERSION" -f deploy/Dockerfile . || die "docker build failed"
docker tag "$DOCKER_REG/gateway:$VERSION" "$DOCKER_REG/gateway:latest"

# 9. Cosign
log "9/12 Signing Docker image with cosign"
cosign sign --yes "$DOCKER_REG/gateway:$VERSION"
cosign attest --yes --predicate dist/sbom-$VERSION.cdx.json \
    --type cyclonedx "$DOCKER_REG/gateway:$VERSION"

# 10. Publish .deb to APT repo
log "10/12 Publishing .deb to APT repo"
scp "$DEB" "publisher@$APT_REPO_HOST:/srv/apt/incoming/"
ssh "publisher@$APT_REPO_HOST" "cd /srv/apt && reprepro includedeb stable incoming/*.deb"

# 11. Push Docker
log "11/12 Pushing Docker image"
docker push "$DOCKER_REG/gateway:$VERSION"
docker push "$DOCKER_REG/gateway:latest"

# 12. Git tag
log "12/12 Tagging git"
git tag -a "v$VERSION" -s -m "Release v$VERSION"
git push origin "v$VERSION"

log "Release $VERSION complete."
log "APT:    apt install jerumednexus-gateway=$VERSION*"
log "Docker: docker pull $DOCKER_REG/gateway:$VERSION"
