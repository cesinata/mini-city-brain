# Testing

Each level below lists the exact command and whether it was run on the build machine (macOS, Python 3.13.5, no Docker) on 2026-11-10.

The commands assume `make setup` has made `.venv`. The build machine ran them from a virtual environment outside the repo folder because importing packages from a OneDrive folder hung (decision D23): `make VENV=<path> test`.

## 1. Lint

```
make lint        # ruff check . and ruff format --check .
```

Run: passed.

## 2. Unit and in-process tests (no Docker)

```
make test        # pytest, all of tests/
```

Run: passed. These use Moto's `ThreadedMotoServer` as an in-process AWS emulator, DuckDB files in temporary folders, and FastAPI's test client. Together they took 106.59 s on the build machine (measured (host CPU), one run: 158 tests, `results/test_run.txt`).

| File | What it covers |
| --- | --- |
| `tests/test_api_ingest.py` | validation edge cases, batch limits, duplicates in a batch, health in both states, no exception text in responses |
| `tests/test_worker.py` | publish, consume, write; batching by count and time; dead-letter after 3 receives; no delete when a write fails |
| `tests/test_init_and_flow.py` | boto3 init fallback; API to queue to worker to bucket; health when resources are missing |
| `tests/test_ingest.py` | synthetic generator and faults; SCATS unpivot (96 intervals, boundaries, time zones); replay batching, speed, retry; `--top-sites` ranking, plan output and the warning for `0` |
| `tests/test_compose.py` | the api's bind mount is the folder `scripts/demo.sh` writes the DuckDB file to; no named warehouse volume |
| `tests/test_warehouse_dbt.py` | loader idempotency; `dbt build` passes on clean data and fails on injected duplicates, negatives and gaps |
| `tests/test_orchestration.py` | Dagster job passes on clean data, fails and stops on bad data; each check function |
| `tests/test_metrics.py`, `tests/test_observability.py` | `/metrics` content; dashboard JSON; every dashboard metric is exposed |
| `tests/test_forecast.py` | baselines, evaluation, endpoint |
| `tests/test_demo.py` | `demo-bad` exits non-zero in-process; scripts refuse cleanly without Docker |
| `tests/test_site.py` | export schema, labels, limits; page served over HTTP; `app.js` rendered against a fake DOM (needs Node) |
| `tests/test_pages_build.py` | real-data gate, fallbacks and warnings (fake HTTP client); workflow permissions and pins |

## 3. Terraform

```
cd infra/terraform
terraform init -backend=false
terraform fmt -check -recursive
terraform validate
```

Run: all passed. `terraform apply` against a local Moto server also ran and created four resources (`results/terraform_apply_moto.txt`).

## 4. Preflight

```
make preflight   # bash scripts/preflight.sh --tree
```

Run: 0 failures. It warns that `docs/ai-log.md` has draft entries until the owner confirms them.

## 5. Pipeline from the command line

```
python -m orchestration.run --source synthetic
python -m orchestration.run --source synthetic --faults --sites 3 --days 3
```

Run: the first exits 0, the second exits 1 with a readable block (`results/pipeline_synthetic_ok.txt`, `results/pipeline_synthetic_bad.txt`).

## 6. Docker and compose

```
make up
make replay
python -m scripts.smoke_assert
make down
make demo
make demo-bad
```

Not run: no Docker on the build machine. The CI `compose-smoke` job runs the first four with 1 synthetic day for 2 sites. The Docker images, the Terraform `init` container and every image tag are unverified.

## 7. CI and Pages workflows

Not run. The YAML parses (Python `yaml.safe_load`) and `tests/test_pages_build.py` checks permissions and action pins. `actionlint` was not available: not checked.

## 8. Not tested at all

- Anything with a real SCATS file. The reader follows the data dictionary only.
- The page in a browser (visual check not done).
- Grafana loading the dashboard.
