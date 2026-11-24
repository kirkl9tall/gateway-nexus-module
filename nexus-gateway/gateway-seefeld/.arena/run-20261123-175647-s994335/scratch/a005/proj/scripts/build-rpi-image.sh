#!/bin/bash
# ============================================================
#  build-rpi-image.sh -- build a pre-flashed Raspberry Pi OS image
#                        with JerumedNexus Gateway pre-installed.
#
#  Uses pi-gen (https://github.com/RPi-Distro/pi-gen) to produce
#  a .img.xz you can flash with Raspberry Pi Imager.
#
#  Run on a Debian 12 (bookworm) build host with 16 GB free disk:
#     sudo apt install git quilt parted debootstrap zerofree zip \
#                      dosfstools libarchive-tools libcap2-bin grep \
#                      rsync xz-utils file kmod bc qemu-user-static
#
#  Output: deploy/jerumednexus-gateway-YYYYMMDD.img.xz
# ============================================================
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK_DIR="${WORK_DIR:-/tmp/loc200-pi-gen}"
PI_GEN_URL="https://github.com/RPi-Distro/pi-gen.git"
PI_GEN_BRANCH="arm64"

if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: must run as root"; exit 1
fi

# 1. Clone pi-gen
if [ ! -d "$WORK_DIR/pi-gen" ]; then
    git clone --depth 1 --branch "$PI_GEN_BRANCH" "$PI_GEN_URL" "$WORK_DIR/pi-gen"
fi

# 2. Create our custom stage that installs the .deb we just built
STAGE_DIR="$WORK_DIR/pi-gen/stage-loc200"
mkdir -p "$STAGE_DIR/00-install"
touch "$STAGE_DIR/EXPORT_IMAGE"

# Stage prerun -- copy the .deb into rootfs
DEB_FILE=$(ls "$PROJECT_ROOT"/../jerumednexus-gateway_*_all.deb 2>/dev/null | head -1 || true)
if [ -z "$DEB_FILE" ]; then
    echo "ERROR: no .deb found -- run scripts/build-deb.sh first"
    exit 1
fi
cp "$DEB_FILE" "$STAGE_DIR/00-install/jerumednexus-gateway.deb"

cat > "$STAGE_DIR/00-install/00-run.sh" <<'STAGE'
#!/bin/bash -e
install -v -m 644 files/jerumednexus-gateway.deb "${ROOTFS_DIR}/tmp/"
on_chroot << CHROOT
DEBIAN_FRONTEND=noninteractive apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y /tmp/jerumednexus-gateway.deb
rm -f /tmp/jerumednexus-gateway.deb
systemctl enable jerumednexus-webui.service
CHROOT
STAGE
chmod +x "$STAGE_DIR/00-install/00-run.sh"

mkdir -p "$STAGE_DIR/00-install/files"
mv "$STAGE_DIR/00-install/jerumednexus-gateway.deb" "$STAGE_DIR/00-install/files/"

cat > "$STAGE_DIR/prerun.sh" <<'PRE'
#!/bin/bash -e
if [ ! -d "${ROOTFS_DIR}" ]; then
    copy_previous
fi
PRE
chmod +x "$STAGE_DIR/prerun.sh"

# 3. pi-gen config
cat > "$WORK_DIR/pi-gen/config" <<EOF
IMG_NAME='jerumednexus-gateway'
RELEASE=bookworm
LOCALE_DEFAULT="en_GB.UTF-8"
TARGET_HOSTNAME=loc200-gw
KEYBOARD_KEYMAP=ch
TIMEZONE_DEFAULT=Europe/Zurich
FIRST_USER_NAME=admin
FIRST_USER_PASS=$(openssl rand -base64 12)
ENABLE_SSH=1
STAGE_LIST="stage0 stage1 stage2 stage-loc200"
EOF

# 4. Run pi-gen
cd "$WORK_DIR/pi-gen"
./build.sh

# 5. Copy result
mkdir -p "$PROJECT_ROOT/deploy"
find "$WORK_DIR/pi-gen/deploy" -name "*.img.xz" -exec cp -v {} "$PROJECT_ROOT/deploy/" \;

echo ""
echo "Done -- image is in $PROJECT_ROOT/deploy/"
echo "Flash with:  xzcat *.img.xz | sudo dd of=/dev/sdX bs=8M status=progress"
echo "Or use Raspberry Pi Imager."
