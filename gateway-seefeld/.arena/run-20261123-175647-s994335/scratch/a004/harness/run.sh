#!/bin/bash
# usage: run.sh <project_dir> <outdir> <port> [extra hash, e.g. theme=dark] [page glob]
set -u
H=$(cd "$(dirname "$0")" && pwd)
PROJ=$1; OUT=$2; PORT=$3; HASH=${4:-}; GLOB=${5:-*-??-*}
PY=/home/the-worst/Desktop/nexus-gateway/gateway-seefeld/.venv/bin/python
mkdir -p "$OUT"
if [ -z "${NORENDER:-}" ]; then (cd "$PROJ" && PYTHONDONTWRITEBYTECODE=1 $PY -I "$H/render.py" "$PROJ" "$OUT/site") || exit 1; fi
$PY -I "$H/serve.py" "$OUT/site" "$PORT" &
SRV=$!
sleep 1
rm -rf "$OUT/res"; mkdir -p "$OUT/res" "$OUT/prof"
for f in "$OUT"/site/p/$GLOB.html; do
  b=$(basename "$f" .html)
  for w in 320 360 390 768 853 1024 1280 1440 1920; do echo "$b $w"; done
done | xargs -P 8 -n 2 sh -c '
  b=$0; w=$1
  d='"$OUT"'/prof/$b-$w
  timeout 40 google-chrome --headless=new --disable-gpu --no-first-run --no-default-browser-check \
    --user-data-dir=$d --hide-scrollbars --window-size=1940,1000 --virtual-time-budget=5000 \
    --dump-dom "http://127.0.0.1:'"$PORT"'/wrap.html?w=$w&u=/p/$b.html#'"$HASH"'" 2>/dev/null \
    | grep -o "<pre id=\"__chk\">.*</pre>" | sed -e "s/<pre id=\"__chk\">//" -e "s/<\/pre>//" > '"$OUT"'/res/$b-$w.json
  rm -rf $d'
kill $SRV
echo done
