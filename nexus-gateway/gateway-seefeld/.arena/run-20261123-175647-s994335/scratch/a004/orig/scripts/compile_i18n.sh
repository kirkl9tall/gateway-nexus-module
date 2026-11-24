#!/bin/bash
# ============================================================
#  compile_i18n.sh — build .mo files from .po in webui/locale/
#
#  Requires: pybabel or msgfmt (gettext)
#  Called by:
#    - manually before commit
#    - CI on every push (see .github/workflows/quality.yml)
# ============================================================
set -euo pipefail

LOCALE_DIR="webui/locale"
[ -d "$LOCALE_DIR" ] || { echo "no locale dir"; exit 1; }

if command -v pybabel >/dev/null 2>&1; then
    pybabel compile -d "$LOCALE_DIR" || true
elif command -v msgfmt >/dev/null 2>&1; then
    for po in $(find "$LOCALE_DIR" -name '*.po'); do
        mo="${po%.po}.mo"
        msgfmt "$po" -o "$mo"
        echo "compiled $mo"
    done
else
    echo "install pybabel or gettext (msgfmt)" >&2
    exit 1
fi
echo "i18n compile complete."
