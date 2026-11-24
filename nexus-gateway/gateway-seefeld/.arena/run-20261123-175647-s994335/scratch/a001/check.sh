#!/bin/bash
# check.sh PORT "query" widths... ; langs via LANGS env
PORT=$1; Q=$2; shift 2
for L in ${LANGS:-it de fr en}; do for W in "$@"; do
  P=$(mktemp -d)
  out=$(timeout 40 google-chrome --headless=new --no-sandbox --disable-gpu --user-data-dir=$P --accept-lang=$L --lang=$L --hide-scrollbars --window-size=2000,1500 --virtual-time-budget=4000 --dump-dom "http://127.0.0.1:$PORT/__frame?w=$W&check=1&$Q" 2>/dev/null | grep -o 'id="__r">RESULT[^<]*' | head -1 | head -c 900)
  echo "$L $W: $out"; rm -rf $P
done; done
