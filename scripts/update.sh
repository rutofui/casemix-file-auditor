#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${PROJECT_DIR}"

echo "Updating Casemix File Auditor..."

if ! command -v git >/dev/null 2>&1; then
  echo "Git belum terinstall."
  exit 1
fi

git pull origin master

if [[ ! -x "${PROJECT_DIR}/.venv/bin/pip" ]]; then
  echo "Virtual environment belum ada. Jalankan install terlebih dahulu."
  exit 1
fi

"${PROJECT_DIR}/.venv/bin/pip" install -r requirements.txt
echo "Update completed."
