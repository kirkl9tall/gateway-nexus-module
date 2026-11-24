#!/usr/bin/env bash
# Local "machines connected" test: simulated Tomedo + real gateway + 2 fake analyzers.
#   demo/demo.sh start        start everything (logs in demo/logs/)
#   demo/demo.sh stop         stop everything
#   demo/demo.sh tomedo-down  stop only the simulated Tomedo (see the red state)
#   demo/demo.sh tomedo-up    start it again
# Uses config/gateway.yaml (the test config). Open http://127.0.0.1:8088
set -u
cd "$(dirname "$0")/.."
PY=.venv/bin/python
mkdir -p demo/logs demo/pids
run() { nohup "$PY" "${@:2}" > "demo/logs/$1.log" 2>&1 & echo $! > "demo/pids/$1.pid"; echo "started $1"; }
kill1() { [ -f "demo/pids/$1.pid" ] && kill "$(cat demo/pids/$1.pid)" 2>/dev/null && echo "stopped $1"; rm -f "demo/pids/$1.pid"; }
case "${1:-}" in
  start)
    run tomedo demo/mock_tomedo.py; sleep 1
    run gateway main.py; sleep 3
    run smt120 demo/fake_analyzer.py --port 6000 --name SMT120 --every 20
    run horiba demo/fake_analyzer.py --port 5004 --name HORIBA --every 35 ;;
  stop)        for p in horiba smt120 gateway tomedo; do kill1 $p; done ;;
  tomedo-down) kill1 tomedo ;;
  tomedo-up)   run tomedo demo/mock_tomedo.py ;;
  *) sed -n 2,7p "$0" ;;
esac
