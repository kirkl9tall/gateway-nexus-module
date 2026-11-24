#!/bin/bash
# ============================================================
#  build-deb.sh -- build a .deb package of JerumedNexus Gateway
#
#  Prereqs (Debian/Ubuntu build host):
#     sudo apt install devscripts debhelper dh-python
#
#  Output:  ../jerumednexus-gateway_<version>_all.deb
# ============================================================
set -euo pipefail

cd "$(dirname "$0")/.."
PROJECT_ROOT="$(pwd)"

if ! command -v dpkg-buildpackage >/dev/null 2>&1; then
    echo "ERROR: dpkg-buildpackage not found."
    echo "Install with:  sudo apt install devscripts debhelper dh-python"
    exit 1
fi

VERSION=$(dpkg-parsechangelog --show-field Version)
echo "[build-deb] Building jerumednexus-gateway v${VERSION} ..."

# Build in a clean copy to avoid dirtying the source tree
BUILD_DIR="/tmp/jerumednexus-gateway-build-$$"
mkdir -p "$BUILD_DIR"
rsync -a --exclude='.git' --exclude='.venv' --exclude='__pycache__' \
      --exclude='logs/*.log' --exclude='logs/*.json' \
      --exclude='config/secrets.env' --exclude='config/webui_*' \
      --exclude='config/license.json' \
      "$PROJECT_ROOT/" "$BUILD_DIR/"

cd "$BUILD_DIR"
dpkg-buildpackage -us -uc -b

# Move artifacts back
mv /tmp/jerumednexus-gateway_*.deb   "$PROJECT_ROOT/../" 2>/dev/null || true
mv /tmp/jerumednexus-gateway_*.buildinfo "$PROJECT_ROOT/../" 2>/dev/null || true
mv /tmp/jerumednexus-gateway_*.changes   "$PROJECT_ROOT/../" 2>/dev/null || true

rm -rf "$BUILD_DIR"

echo "[build-deb] Done. Package is in $(realpath "$PROJECT_ROOT/..")"
ls -lh "$PROJECT_ROOT"/../jerumednexus-gateway_"${VERSION}"_*.deb 2>/dev/null || true
