#!/usr/bin/env bash
# Local "machines connected" simulation: simulated Tomedo + real gateway + 2 fake analyzers.
#
#   demo/demo.sh start        start everything (logs in demo/logs/)
#   demo/demo.sh stop         stop everything (also processes started by hand)
#   demo/demo.sh status       show what is running
#   demo/demo.sh tomedo-down  stop only the simulated Tomedo (see the red state)
#   demo/demo.sh tomedo-up    start it again
#
# The gateway is started/stopped with the same code as the on/off switch on
# the Overview (webui/gateway_process.py), so the two never start it twice.
# Uses config/gateway.yaml (the test config). Open http://127.0.0.1:8088
set -u
cd "$(dirname "$0")/.."
PY=.venv/bin/python
mkdir -p demo/logs demo/pids

run() {   # run <name> <script> [args…]   (skips if the same command already runs)
  if pgrep -f -- "${*:2}" >/dev/null; then echo "already running: $1"; return; fi
  nohup "$PY" "${@:2}" > "demo/logs/$1.log" 2>&1 & echo $! > "demo/pids/$1.pid"
  echo "started $1"
}
stop_script() {   # stop_script <name> <script>
  if pkill -f "$2"; then echo "stopped $1"; fi
  rm -f "demo/pids/$1.pid"
}
gateway() {   # gateway start|stop
  "$PY" -c "import sys; from webui import gateway_process as gp; ok, err = gp.action('$1'); print('gateway $1:', 'ok' if ok else err); sys.exit(0 if ok else 1)"
}

case "${1:-}" in
  start)
    run tomedo demo/mock_tomedo.py; sleep 1
    gateway start; sleep 2
    run smt120 demo/fake_analyzer.py --port 6000 --name SMT120 --every 20
    run horiba demo/fake_analyzer.py --port 5004 --name HORIBA --every 35
    echo "Open http://127.0.0.1:8088 (start the web UI first if it is not running)." ;;
  stop)
    stop_script smt120 "demo/fake_analyzer.py --port 6000"
    stop_script horiba "demo/fake_analyzer.py --port 5004"
    gateway stop
    stop_script tomedo demo/mock_tomedo.py ;;
  status)
    for s in demo/mock_tomedo.py "demo/fake_analyzer.py --port 6000" "demo/fake_analyzer.py --port 5004"; do
      if pgrep -f "$s" >/dev/null; then echo "running   $s"; else echo "stopped   $s"; fi
    done
    "$PY" -c "from webui import gateway_process as gp; print(('running ' if gp.gateway_pids() else 'stopped ') + '  gateway (main.py)')"
    if pgrep -f "flask --app webui.app" >/dev/null || pgrep -f "webui.serve" >/dev/null; then echo "running   web UI"; else echo "stopped   web UI"; fi ;;
  tomedo-down) stop_script tomedo demo/mock_tomedo.py ;;
  tomedo-up)   run tomedo demo/mock_tomedo.py ;;
  *) sed -n 2,8p "$0" ;;
esac
