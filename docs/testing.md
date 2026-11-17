# Testing

Each level below lists the exact command and whether it was run. Levels 1 to 5 were first run on 2026-11-10 without Docker. Since 2026-11-17 everything here runs on my laptop (macOS on Apple M3, Python 3.13.5, Docker Desktop 29.9.3), and CI runs levels 1 to 3 and a compose smoke test on Linux.

The commands assume `make setup` has made `.venv` in the repo folder. During the first build the repo sat in a OneDrive folder where imports hung, so tests ran from a virtual environment outside it (decision D23). `make VENV=<path> test` still works.

## 1. Lint

```
make lint        # ruff check . and ruff format --check .
```

Run: passed.

## 2. Unit and in-process tests (no Docker)

```
make test        # pytest, all of tests/
```

Run: passed. These use Moto's `ThreadedMotoServer` as an in-process AWS emulator, DuckDB files in temporary folders, and FastAPI's test client. On 2026-11-17: 171 passed and 2 skipped in 81.53 s (measured (host CPU), one run, `results/test_run.txt`). The 2 skipped tests only run on a machine without Docker.

| File | What it covers |
| --- | --- |
| `tests/test_api_ingest.py` | validation edge cases, batch limits, duplicates in a batch, health in both states, no exception text in responses |
| `tests/test_worker.py` | publish, consume, write; batching by count and time; dead-letter after 3 receives; no delete when a write fails |
| `tests/test_init_and_flow.py` | boto3 init fallback; API to queue to worker to bucket; health when resources are missing |
| `tests/test_ingest.py` | synthetic generator and faults; SCATS unpivot (96 intervals, boundaries, time zones); replay batching, speed, retry; `--top-sites` ranking, plan output and the warning for `0` |
| `tests/test_compose.py` | the api's bind mount is the folder `scripts/demo.sh` writes the DuckDB file to; no named warehouse volume; every host-side emulator URL uses the published port, which is not 5000 |
| `tests/test_warehouse_dbt.py` | loader idempotency; `dbt build` passes on clean data and fails on injected duplicates, negatives and gaps |
| `tests/test_orchestration.py` | Dagster job passes on clean data, fails and stops on bad data; relative `--db` and `DBT_TARGET_PATH` keep dbt and the loader on one database; each check function |
| `tests/test_metrics.py`, `tests/test_observability.py` | `/metrics` content; dashboard JSON; every dashboard metric is exposed; the two fixed panel definitions (D39) |
| `tests/test_forecast.py` | baselines, evaluation, endpoint |
| `tests/test_demo.py` | `demo-bad` exits non-zero in-process; scripts refuse cleanly without Docker; the smoke check counts readings in the bucket and waits for all of them |
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

Run on 2026-11-17 (measured (host CPU), one run each, synthetic data):

- `make up`, `make replay`, `python -m scripts.smoke_assert --wait 60`, `make down`: each exit 0 (`results/compose_targets.txt`).
- `make demo`: exit 0, 189 s wall time; 1920 readings sent and accepted, 4 objects written, `PIPELINE OK: 15 checks passed` (`results/demo_run.txt`).
- `make demo-bad` after `make demo-down`: exits non-zero; `duplicate_rate` fails on `raw_objects_loaded` (`results/demo_bad_run.txt`).
- With the stack up: `/health` ok, the forecast endpoint answers 200, Prometheus shows the api and worker targets up, Grafana's health is ok and its API finds the provisioned dashboard, and `make dagster-ui` serves port 3001 (`results/stack_checks.txt`).

The CI `compose-smoke` job runs `docker compose up`, a 1-day, 2-site synthetic replay and the smoke check on Linux. It passed on 2026-11-16.

## 7. CI and Pages workflows

CI: run on GitHub on 2026-11-16 for the push and the pull request of commit `4098a88`. All five jobs passed (lint, test, terraform, docker-build, compose-smoke; measured (CI runner), 3m40s and 3m20s per run). GitHub warns that `actions/checkout`, `actions/setup-python` and `hashicorp/setup-terraform` at the pinned versions target Node.js 20.

Pages workflow: not run. The YAML parses (Python `yaml.safe_load`) and `tests/test_pages_build.py` checks permissions and action pins. `actionlint` was not available: not checked.

## 8. Not tested at all

- Anything with a real SCATS file. The reader follows the data dictionary only.
- The page in a browser (visual check not done).
- Grafana panels against expected values. I looked at them on 2026-11-17 and two were fixed (decisions D39); `tests/test_observability.py` checks those two panel definitions, not what Grafana draws.
