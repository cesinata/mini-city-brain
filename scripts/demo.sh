#!/usr/bin/env bash
# make demo: stack up, replay 2 synthetic days for 5 sites, run the pipeline, print URLs.
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${PY:-.venv/bin/python}"
if ! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
  echo "demo: Docker is not available. This command needs Docker (see docs/demo.md)." >&2
  exit 2
fi
export AWS_ENDPOINT_URL=http://localhost:5000 AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test
export AWS_DEFAULT_REGION=ap-southeast-2
export DBT_TARGET_PATH="${DBT_TARGET_PATH:-data/dbt_target}"
mkdir -p data/warehouse data/demo
docker compose --profile obs up -d --build
bash scripts/wait_for_health.sh http://localhost:8000/health 180
"$PY" -m ingest.replay --synthetic --days 2 --sites 5 --detectors 2 --speed 0 --clean \
  | tee data/demo/replay.json
"$PY" -m scripts.smoke_assert --wait 60
CLOCK="$("$PY" -c "from datetime import timedelta; from ingest.synthetic import DEFAULT_START as s; print((s+timedelta(days=2)).isoformat()+'T00:00:00+00:00')")"
rm -f data/warehouse/mcb.duckdb
"$PY" -m orchestration.run --source bucket --db data/warehouse/mcb.duckdb --replay-clock "$CLOCK" \
  | tee data/demo/pipeline.txt
"$PY" -m scripts.demo_summary data/demo/replay.json data/demo/pipeline.txt
