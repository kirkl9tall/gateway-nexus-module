#!/bin/bash
# shot.sh file.html outprefix height widths...
f=$1; o=$2; h=$3; shift 3
for w in "$@"; do
  wr=${f%.html}.swrap$w.html
  cat > $wr <<H
<!doctype html><html><body style="margin:0"><iframe src="file://$f" style="border:0;width:${w}px;height:${h}px"></iframe></body></html>
H
  ww=$w; [ $ww -lt 500 ] && ww=500
  google-chrome --headless=new --disable-gpu --no-sandbox --hide-scrollbars --allow-file-access-from-files --virtual-time-budget=3000 --window-size=$ww,$h --screenshot=$o-$w.png "file://$wr" >/dev/null 2>&1
done
