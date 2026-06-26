#!/usr/bin/env bash
set -euo pipefail

echo "screen sessions:"
screen -ls || true

echo
echo "Local check:"
curl -I --max-time 5 http://127.0.0.1:8501 || true

echo
echo "Public check:"
curl -I --max-time 10 https://casemix.ahmadluthfi.online || true

