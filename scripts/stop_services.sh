#!/usr/bin/env bash
set -euo pipefail

screen -S casemix_cloudflared -X quit >/dev/null 2>&1 || true
screen -S casemix_auditor -X quit >/dev/null 2>&1 || true

TUNNEL_PIDS="$(pgrep -f "cloudflared tunnel --config ${HOME}/.cloudflared/casemix-auditor.yml run" || true)"
if [[ -n "${TUNNEL_PIDS}" ]]; then
  kill ${TUNNEL_PIDS} >/dev/null 2>&1 || true
fi

PORT_PIDS="$(lsof -ti tcp:8501 || true)"
if [[ -n "${PORT_PIDS}" ]]; then
  kill ${PORT_PIDS} >/dev/null 2>&1 || true
fi

echo "Casemix services stopped."
