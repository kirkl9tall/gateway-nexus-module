#!/bin/bash
# shot.sh PORT WIDTH OUTNAME [HEIGHT] [SCALE]
D=/home/the-worst/Desktop/nexus-gateway/gateway-seefeld/.arena/run-20261123-175647-s994335/scratch/a002
mkdir -p $D/shots
H=${4:-1800}; S=${5:-1}
timeout 40 google-chrome --headless=new --disable-gpu --no-sandbox --hide-scrollbars --user-data-dir=/tmp/claude-1000/a002chrome-$1-$2 \
  --force-device-scale-factor=$S --window-size=$2,$H --virtual-time-budget=4000 --screenshot=$D/shots/$3.png http://localhost:$1/ >/dev/null 2>&1
echo $D/shots/$3.png
