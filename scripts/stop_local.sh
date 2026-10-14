#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

stop_service() {
  local name="$1"
  local pidfile=".run/${name}.pid"
  if [[ ! -f "$pidfile" ]]; then
    echo "${name} is not running"
    return
  fi
  local pid
  pid="$(cat "$pidfile")"
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid"
    echo "stopped ${name} (pid ${pid})"
  else
    echo "${name} was not running"
  fi
  rm -f "$pidfile"
}

stop_service frontend
stop_service order
stop_service product
stop_service user
