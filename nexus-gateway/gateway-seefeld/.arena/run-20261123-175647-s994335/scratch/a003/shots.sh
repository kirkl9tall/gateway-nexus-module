#!/bin/bash
# shots.sh <proj> <port> <outdir> [widths] [langs] [scens] [roles] [png:0/1]
P=$1; PORT=$2; OUT=$3; mkdir -p $OUT
WIDTHS=${4:-"360 390 768 853 1024 1280 1440 1920"}
LANGS=${5:-"it de fr en"}
SCENS=${6:-"good problems off"}
ROLES=${7:-"viewer admin"}
PNG=${8:-0}
D=$(dirname $0)
PY=/home/the-worst/Desktop/nexus-gateway/gateway-seefeld/.venv/bin/python
$PY $D/serve.py $P $PORT > $OUT/server.log 2>&1 &
SP=$!
sleep 2.5
for s in $SCENS; do for r in $ROLES; do for l in $LANGS; do for w in $WIDTHS; do
  INNER="%2F%3Fscen%3D$s%26role%3D$r%26check%3D1"; URL="http://127.0.0.1:$PORT/lang/$l?next=%2F__frame%3Fw%3D$w%26h%3D${H:-2400}%26u%3D$(python3 -c "import urllib.parse,sys;print(urllib.parse.quote(urllib.parse.unquote(sys.argv[1]),safe=''))" $INNER)"; WW=$(( w < 520 ? 520 : w ))
  UD=$(mktemp -d)
  res=$(timeout 40 google-chrome --headless=new --disable-gpu --no-first-run --user-data-dir=$UD --window-size=$WW,3000 --virtual-time-budget=4000 --dump-dom "$URL" 2>/dev/null | grep -o 'CHK\[[^<]*' | head -1)
  echo "$s $r $l $w :: $res"
  if [ "$PNG" = "1" ]; then
    timeout 40 google-chrome --headless=new --disable-gpu --no-first-run --hide-scrollbars --user-data-dir=$UD --window-size=$WW,${H:-2400} --virtual-time-budget=4000 --screenshot=$OUT/${s}_${r}_${l}_${w}.png "$URL" >/dev/null 2>&1
  fi
  rm -rf $UD
done; done; done; done
kill $SP
