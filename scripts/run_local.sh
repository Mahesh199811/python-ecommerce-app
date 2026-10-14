#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install -q -r requirements.txt

mkdir -p data logs .run

start_service() {
  local name="$1"
  local port="$2"
  local script="$3"
  local pidfile=".run/${name}.pid"

  if [[ -f "$pidfile" ]] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
    echo "${name} already running (pid $(cat "$pidfile")) on port ${port}"
    return
  fi

  nohup env PORT="$port" python "$script" >"logs/${name}.log" 2>&1 &
  echo $! >"$pidfile"
  echo "started ${name} (pid $!) on http://127.0.0.1:${port}"
}

start_service user 5001 services/user_service/app.py
start_service product 5002 services/product_service/app.py
start_service order 5003 services/order_service/app.py
start_service frontend 5004 frontend/app.py

for _ in 1 2 3 4 5 6 7 8 9 10; do
  if curl -sf http://127.0.0.1:5001/health >/dev/null \
    && curl -sf http://127.0.0.1:5002/health >/dev/null \
    && curl -sf http://127.0.0.1:5003/health >/dev/null \
    && curl -sf http://127.0.0.1:5004/health >/dev/null; then
    echo "all services are healthy"
    echo "open http://127.0.0.1:5004"
    exit 0
  fi
  sleep 0.3
done

echo "services did not become healthy; see logs/ for details" >&2
exit 1
