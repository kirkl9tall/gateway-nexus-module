#!/bin/bash
# start.sh PORT ROLE LANG SCEN [PROJDIR]
D=/home/the-worst/Desktop/nexus-gateway/gateway-seefeld/.arena/run-20261123-175647-s994335/scratch/a002
P=${5:-$D/proj}
[ -f $D/pid.$1 ] && kill $(cat $D/pid.$1) 2>/dev/null
/home/the-worst/Desktop/nexus-gateway/gateway-seefeld/.venv/bin/python $D/tools/serve.py $P $1 $2 $3 $4 > $D/srv.$1.log 2>&1 &
echo $! > $D/pid.$1
for i in 1 2 3 4 5 6 7 8 9 10; do curl -s -o /dev/null localhost:$1/static/ui.css && break; sleep 0.5; done
