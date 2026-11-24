#!/bin/bash
# ============================================================
#  sign-deb.sh -- sign a built .deb with your apt repo GPG key
#
#  Prereqs:
#     * A GPG key: gpg --gen-key   (choose "sign only", 4096-bit RSA)
#     * Export the key id (long form):  gpg --list-secret-keys --keyid-format=long
#     * Set GPG_KEY_ID env var to that id.
#
#  Usage:
#     GPG_KEY_ID=1234ABCD5678EFAB ./scripts/sign-deb.sh path/to/jerumednexus-gateway_x.y.z_all.deb
# ============================================================
set -euo pipefail

if [ -z "${GPG_KEY_ID:-}" ]; then
    echo "ERROR: set GPG_KEY_ID first (gpg --list-secret-keys --keyid-format=long)"
    exit 1
fi

DEB="${1:-}"
if [ -z "$DEB" ] || [ ! -f "$DEB" ]; then
    echo "Usage: GPG_KEY_ID=<id> $0 <path-to.deb>"
    exit 1
fi

if ! command -v debsigs >/dev/null 2>&1; then
    echo "Installing debsigs..."
    sudo apt-get install -y debsigs
fi

debsigs --sign=origin -k "$GPG_KEY_ID" "$DEB"
echo "[sign-deb] Signed $DEB with $GPG_KEY_ID"
echo ""
echo "Verify with:"
echo "  debsigs --verify $DEB"
echo ""
echo "Publish the public key so customers can trust it:"
echo "  gpg --armor --export $GPG_KEY_ID > jerumednexus-gateway-apt.asc"
