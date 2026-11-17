#!/usr/bin/env bash
# make demo-bad: send faulty readings; the pipeline must fail with a readable message.
set -uo pipefail
cd "$(dirname "$0")/.."
PY="${PY:-.venv/bin/python}"
if ! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
  echo "demo-bad: Docker is not available. This command needs Docker (see docs/demo.md)." >&2
  exit 2
fi
export AWS_ENDPOINT_URL=http://127.0.0.1:5050 AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test
export AWS_DEFAULT_REGION=ap-southeast-2
export DBT_TARGET_PATH="${DBT_TARGET_PATH:-data/dbt_target}"
mkdir -p data/warehouse
docker compose --profile obs up -d --build
bash scripts/wait_for_health.sh http://127.0.0.1:8000/health 180
"$PY" -m scripts.demo_bad
