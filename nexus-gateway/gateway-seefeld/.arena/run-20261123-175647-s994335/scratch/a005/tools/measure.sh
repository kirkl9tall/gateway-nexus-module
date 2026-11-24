#!/bin/bash
# measure.sh PORT ROLE LANG SCN WIDTH...  -> one line per width
PORT=$1; ROLE=$2; LANG_=$3; SCN=$4; shift 4
for W in "$@"; do
  D=$(mktemp -d)
  OUT=$(timeout 60 google-chrome --headless=new --no-sandbox --disable-gpu --user-data-dir=$D --hide-scrollbars --window-size=$W,900 --virtual-time-budget=6000 --dump-dom "http://127.0.0.1:$PORT/__go?role=$ROLE&lang=$LANG_&scn=$SCN&next=/%3Fm%3D1" 2>/dev/null | grep -o 'MEASURE.*ENDMEASURE' | sed 's/^MEASURE//;s/ENDMEASURE$//')
  echo "$W $ROLE $LANG_ $SCN $OUT"
  rm -rf $D
done
