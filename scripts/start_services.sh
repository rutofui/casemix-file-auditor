#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLOUDFLARED_CONFIG="${HOME}/.cloudflared/casemix-auditor.yml"

if ! command -v screen >/dev/null 2>&1; then
  echo "screen tidak tersedia. Install screen atau jalankan service secara manual."
  exit 1
fi

if [[ ! -x "${PROJECT_DIR}/.venv/bin/streamlit" ]]; then
  echo "Streamlit belum tersedia di .venv. Jalankan: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi

if [[ ! -f "${CLOUDFLARED_CONFIG}" ]]; then
  echo "Config cloudflared tidak ditemukan: ${CLOUDFLARED_CONFIG}"
  exit 1
fi

bash "${PROJECT_DIR}/scripts/stop_services.sh" >/dev/null 2>&1 || true

screen -dmS casemix_auditor bash -lc "cd '${PROJECT_DIR}' && .venv/bin/streamlit run app.py --server.headless true --server.address 127.0.0.1 --server.port 8501 > .streamlit.log 2>&1"
sleep 3

screen -dmS casemix_cloudflared bash -lc "cloudflared tunnel --config '${CLOUDFLARED_CONFIG}' run > '${HOME}/.cloudflared/casemix-auditor.log' 2>&1"
sleep 3

echo "Casemix Claim File Auditor started."
echo "Local:  http://127.0.0.1:8501"
echo "Public: https://casemix.ahmadluthfi.online"
