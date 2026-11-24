#!/bin/bash
# shot.sh PORT LANG W "query" out.png [H]
P=$(mktemp -d); H=${6:-1400}
timeout 40 google-chrome --headless=new --no-sandbox --disable-gpu --user-data-dir=$P --accept-lang=$2 --lang=$2 --hide-scrollbars --window-size=$(( $3 + 20 )),$H --virtual-time-budget=4000 --screenshot=$5 "http://127.0.0.1:$1/__frame?w=$3&$4" >/dev/null 2>&1; rm -rf $P
