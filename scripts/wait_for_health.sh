#!/usr/bin/env bash
# Wait until the API reports "ok" on /health. Usage: bash scripts/wait_for_health.sh [url] [seconds]
set -uo pipefail
URL="${1:-http://localhost:8000/health}"
LIMIT="${2:-120}"
for ((i = 0; i < LIMIT; i++)); do
  if curl -fsS "$URL" 2>/dev/null | grep -q '"status":"ok"'; then
    echo "healthy after ${i}s: $URL"
    exit 0
  fi
  sleep 1
done
echo "FAIL: $URL not healthy after ${LIMIT}s"
exit 1
