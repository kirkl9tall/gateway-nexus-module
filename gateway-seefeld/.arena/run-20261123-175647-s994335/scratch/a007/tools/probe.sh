#!/bin/bash
# probe.sh file.html widths...   (iframe of exact width => true viewport)
f=$1; shift
d=$(cd $(dirname $0); pwd)
g=${f%.html}.probe.html
python3 - "$f" "$g" "$d/probe.js" <<'P'
import sys; s=open(sys.argv[1]).read(); s=s.replace('</body>','<script>'+open(sys.argv[3]).read()+'</script></body>'); open(sys.argv[2],'w').write(s)
P
for w in "$@"; do
  wr=${f%.html}.wrap$w.html
  cat > $wr <<H
<!doctype html><html><body style="margin:0"><iframe id=f src="file://$g" style="border:0;width:${w}px;height:1000px"></iframe><pre id="__report">none</pre>
<script>addEventListener('message',function(e){document.getElementById('__report').textContent=e.data;});</script></body></html>
H
  r=$(google-chrome --headless=new --disable-gpu --no-sandbox --allow-file-access-from-files --virtual-time-budget=4000 --window-size=$((w+40)),1100 --dump-dom "file://$wr" 2>/dev/null | grep -o '<pre id="__report">[^<]*' | sed 's/<pre id="__report">//')
  echo "$w: $r" | sed 's/&quot;/"/g;s/&gt;/>/g'
done
