# Decisions

Each entry has an ID, date, choice, reason and how to revert. New entries go at the bottom. "Owner to confirm" means the choice is a default until the owner signs it off.

## D1. Rebuild in place, keep the name (2026-11-10, confirmed by the owner 2026-11-17)

- **Choice:** Keep `mini-city-brain`. Replace the single-file prototype (`main.py`, `main.tf`) with the layout in `CLAUDE.md`.
- **Reason:** The old prototype writes each POSTed record to a bucket and nothing reads it back. There are no tests, no CI and no data source.
- **History:** The remote `main` holds only a fresh "Initial commit". The rebuild branches from it. The old prototype commits live only in the owner's local clone, on a renamed branch, and are never pushed (D14).
- **Revert:** The old files remain in the owner's local clone.

## D2. Local AWS emulator: Moto server by default (2026-11-10)

- **Choice:** Use Moto in server mode (Docker image, port 5000) for `docker compose`. Use Moto's in-process `ThreadedMotoServer` in pytest. LocalStack is an optional compose profile only.
- **Reason:** Since March 2026 the LocalStack image needs an account and an auth token, even for the free non-commercial tier. Moto needs neither, and its server mode works with any AWS SDK and with Terraform through custom endpoints.
- **Rule:** All code reads `AWS_ENDPOINT_URL`, so switching emulators is one setting. A LocalStack token, if ever used, lives only in a local `.env` or a GitHub Actions secret, never in git.
- **Revert:** Point `AWS_ENDPOINT_URL` at another emulator.

## D3. Event-driven ingestion with a dead-letter queue (2026-11-10)

- **Choice:** The API validates readings and publishes them to a queue. A worker consumes, batches and writes newline-delimited JSON to object storage. Messages that fail validation go to a dead-letter queue through a redrive policy.
- **Reason:** It shows a real event flow rather than one write per request, and failures stay visible.
- **Revert:** The worker can be bypassed by writing from the API directly (not recommended).

## D4. Orchestrator: Dagster (2026-11-10)

- **Choice:** Dagster, run locally. One job: load to DuckDB, then dbt build, then asset checks. It has one schedule.
- **Reason:** It is small to run locally. dbt tests can surface as asset checks, and checks can fail a run loudly.
- **Trade-off:** Airflow is the more common name in job ads.
- **Revert:** The pipeline steps are plain Python functions, so they can be wrapped in Airflow later.

## D5. Data: Victorian traffic-signal volume (SCATS) (2026-11-10, licence confirmed by the owner 2026-11-17: CC BY 4.0)

- **Choice:** Primary source is the Department of Transport and Planning "Traffic Signal Volume Data" (15-minute volumes per detector).
- **Data rules:**
  - CI and tests use synthetic data that follows the published column layout.
  - Real data is downloaded by the owner into `data/raw/` (gitignored) and never committed.
  - See `docs/data.md`.
- **Revert:** Not applicable.

## D6. Warehouse: DuckDB file plus dbt-duckdb (2026-11-10)

- **Choice:** One DuckDB file under `data/warehouse/` (gitignored), with dbt-duckdb for staging, marts and tests.
- **Reason:** Free, local, no server.
- **Rule:** This is not described as experience with any hosted warehouse.

## D7. Dashboards: Grafana and Prometheus for operations, one static page for the public demo (2026-11-10)

- **Choice:** The API and worker expose Prometheus metrics, and Grafana is provisioned with one dashboard defined in JSON for operators. The public demo is a single static page in plain HTML and JavaScript (D11). No React or other front-end framework lives in this repo.
- **Reason:** It keeps this repo focused on the data and ingestion side. A full web app belongs in a separate project.

## D8. Out of scope for the first build (2026-11-10)

- **Out:** Kubernetes, any real cloud deployment, Spark, LLM features.
- **Planned instead:**
  - A real Terraform deploy is a separate, optional step with a billing alert and `terraform destroy`.
  - Kubernetes could later be added locally with kind.

## D9. Licence: MIT (2026-11-10, confirmed by the owner 2026-11-17)

- **Choice:** Replace `LICENSE.txt` (which held the Terraform BSL text, not a licence for this code) with an MIT `LICENSE` naming the owner.
- **Revert:** Swap in another licence file.

## D10. Python 3.12 (2026-11-10)

- **Choice:** Python 3.12 for all services. If a pinned dependency does not support it, record the fallback here.

## D11. Public demo: static page on GitHub Pages (2026-11-10)

- **Choice:** `site/` holds a static page that reads one exported `summary.json` (busiest sites, hour-by-weekday heat map, forecast against actual, data completeness). A workflow builds and deploys it to GitHub Pages on demand and weekly.
- **Real data:** only when the repository variable `REAL_DATA_ENABLED` is `true`. Otherwise the page uses synthetic data and says so in a banner.
- **Reason:** A pipeline has no camera moment. A page anyone can open, plus a demo that breaks on purpose (`make demo-bad`), shows what the system produces and how it protects data quality. It needs no server and costs nothing.
- **Revert:** Disable Pages; the rest of the repo is unaffected.

## D12. Site locations and the map (2026-11-10, not in use: no map is built; the locations dataset's licence has not been read)

- **Choice:** Join SCATS site IDs to a Department of Transport and Planning traffic-signal locations dataset (see `docs/data.md`). Show the map only if at least 80% of the shown sites match.
- **Reason:** It has not been checked that the location dataset's site number is the same ID as the volume data's SCATS site.
- **Revert:** Hide the map; charts and tables still work.

## D13. README origin note (2026-11-10)

- **Choice:** The README keeps a short "Why this exists" paragraph written by the owner. It names no organisation.

## D14. Old local history stays local (2026-11-10)

- **Choice:** Branch the rebuild from the remote's initial commit. Rename the old local `main` to `old-local-main` and never push, pull or merge it.
- **Reason:** The old commits contain a large installer binary and a university author address. They were once pushed and later replaced on the remote by a forced update. GitHub may still serve them by direct commit link until its cached views expire; this was not verified. The owner decided not to rewrite history or delete the repository.
- **Revert:** Not applicable.

## D15. AI use is logged and disclosed (2026-11-10)

- **Choice:** `docs/ai-log.md` holds entries the owner writes or confirms. The README has a "How AI was used and verified" section linking to it. Claude Code may only draft entries marked `DRAFT: to be confirmed`.
- **Reason:** The log is evidence of reviewed AI use; an invented log would be worse than none.

## D16. Volume upper bound: 2000 per 15 minutes (2026-11-10)

- **Choice:** The API and worker reject a reading with `volume` above 2000 or below 0.
- **Reason:** One detector sits on one lane. A saturated signalised lane passes roughly 1,800 to 2,000 vehicles an hour, so about 450 in 15 minutes. 2000 leaves a wide margin while still catching sentinel or corrupt values. This is an engineering estimate, not a figure from the publisher.
- **Revert:** Change `MAX_VOLUME_15MIN` in `services/common/models.py` and the dbt accepted-range test.

## D17. Idempotency scope (2026-11-10)

- **Choice:** The key is `site_id`, `detector_id`, `interval_end`. The API rejects a repeat of a key inside one request (reason `duplicate`). It keeps no state between requests, so a repeat across requests is published again and removed in dbt `stg_readings`.
- **Reason:** A stateless API can scale and restart freely. The standard SQS queue has no deduplication, so the warehouse is the one place that can enforce it.
- **Revert:** Add a key store (for example in DuckDB or a cache) in the API.

## D18. Python 3.13 locally instead of 3.12 (2026-11-10)

- **Choice:** Use Python 3.13.5 for the local virtual environment and `python:3.13.5-slim` in Docker images. `pyproject.toml` keeps `requires-python >= 3.12`.
- **Reason:** D10 asks for 3.12. This machine has 3.13 and 3.14 only, no 3.12 and no `uv`. 3.13 is the closest and all pinned packages installed on it. CI uses the same 3.13 so that results match.
- **Revert:** Install 3.12, change `PYTHON` in the `Makefile`, the image tags and the CI setup step, and re-resolve `requirements/constraints.txt`.

## D19. Old prototype files were not removed (2026-11-10)

- **Choice:** `main.py`, `main.tf`, `requirements.txt`, `Dockerfile` and `LICENSE.txt` are still in the working tree. The new layout does not use them. `main.py` is excluded from ruff in `pyproject.toml`.
- **Reason:** The tool blocked the `rm` for these tracked files, and the build does not work around a block. The files are still in git history of the owner's branch.
- **Revert / owner action:** Run `rm main.py main.tf requirements.txt Dockerfile LICENSE.txt`, stage the removals by name, and delete the `main.py` entry in `pyproject.toml` `extend-exclude`.

## D20. Dependency pins (2026-11-10)

- **Choice:** `requirements/direct.txt` pins direct dependencies and `requirements/constraints.txt` pins every installed package. Both resolve releases uploaded on or before 2026-10-27, which is 14 days before this build. Service images install `requirements/api.txt`, `worker.txt` or `tools.txt` with `-c requirements/constraints.txt`.
- **Reason:** One constraints file keeps the venv, CI and images on the same versions.
- **Revert:** Delete the files and re-resolve.

## D21. Worker batching and queue settings (2026-11-10)

- **Choice:** The worker flushes after 1000 readings or 5 seconds since the first buffered message, whichever comes first (`WORKER_BATCH_MAX_READINGS`, `WORKER_BATCH_MAX_SECONDS`). One SQS message holds one accepted API request (at most 500 readings). One flush writes one object per UTC date. Queue visibility timeout is 30 seconds and `maxReceiveCount` is 3.
- **Reason:** Small objects are cheap on an emulator and give quick feedback. A date-partitioned key matches the `raw/scats/date=YYYY-MM-DD/` layout the warehouse loader reads. The date is the UTC date of `interval_end`.
- **Side effect:** A failed write also counts as a receive, so a batch that fails three times lands in the dead-letter queue.
- **Revert:** Change the environment variables or the `maxReceiveCount` in `infra/terraform/main.tf` and `scripts/init_resources.py`.

## D22. Terraform provider version and local verification (2026-11-10)

- **Choice:** `hashicorp/aws` pinned to `6.22.1`, Terraform `>= 1.15.0, < 2.0.0`. `infra/terraform/.terraform.lock.hcl` is tracked.
- **Reason:** 6.22.1 is far older than 14 days (newer 6.x releases exist). The registry API does not return publish dates, so this is judged from the version sequence, not a date.
- **Verified:** `terraform fmt -check`, `validate`, and `apply` against a local Moto server created all four resources (`results/terraform_apply_moto.txt`).
- **Not verified:** the `init` compose service (Terraform in a `hashicorp/terraform:1.15.6` container). There is no Docker on this machine. The boto3 fallback `scripts/init_resources.py` is tested in pytest. Which one the compose stack uses stays Terraform until CI shows it failing.
- **Revert:** Change the `init` service command to run the boto3 script in a Python image.

## D23. Build environment note (2026-11-10)

- **Choice:** Tests and lint in this build ran from a virtual environment in the scratchpad, not `.venv` in the repo folder. `make` accepts `VENV=<path>`.
- **Reason:** The repo is inside a OneDrive folder. Importing packages from `.venv` there blocked on file reads (no progress after 100 seconds). The same pinned requirements installed cleanly outside OneDrive and the tests ran in seconds.
- **Owner action:** Keep the repo outside OneDrive, or mark the folder "Always keep on this device".

## D24. SCATS time zone: fixed UTC+10 by default (2026-11-10, replaced by D43 after the first real file)

- **Choice:** `QT_INTERVAL_COUNT` and the `V00` to `V95` intervals are read as "Australian Eastern Standard Time" literally, a fixed UTC+10 offset with no daylight saving. `interval_end` is stored in UTC. `V00` ends at 00:15 local, `V95` ends at the next local midnight. `--tz Australia/Melbourne` reads them as local clock time instead.
- **Reason:** That is what the data dictionary says. No real file has been seen on this machine. If the publisher actually uses Melbourne local time, summer data is one hour off until the setting is changed.
- **Check on the first real file:** compare the busiest hours with expectations (peaks near 08:00 and 17:00 local) in both modes.
- **Revert:** Pass `--tz Australia/Melbourne`, or change the default in `ingest/scats.py`.

## D25. Replay and faults (2026-11-10)

- **Choice:** Replay sends readings ordered by `interval_end`. Speed 0 sends without waiting. Retries use exponential backoff (0.5 s, 1 s, 2 s, 4 s) for connection errors, 429 and 5xx, five attempts in all. A 422 is not retried. Synthetic data includes faults by default; `--clean` removes them (CI smoke test uses `--clean`).
- **Reason:** A negative value is rejected by the API, so it never reaches the queue and the dead-letter queue stays empty. The remaining faults (gaps, alarms, duplicate rows) pass the API on purpose, so the warehouse checks can catch them.
- **Revert:** Edit `ingest/replay.py`.

## D26. Warehouse and dbt details (2026-11-10)

- **Choice:**
  - `raw.readings` stores `interval_end` as a UTC `TIMESTAMP`. `raw.loaded_objects` is the manifest of loaded object keys. Each object loads in one transaction.
  - Four dbt models: `stg_readings` (deduplicated on the key, earliest load wins), `fct_volume_15min`, `fct_volume_hourly` (sum over detectors per site and local hour), `fct_detector_health` (observed intervals / 96 per detector and local day).
  - Local time for hour-of-day and weekday is UTC plus `local_offset_hours` (10, from D24).
  - Raw-layer tests: `raw_no_negative_volume` and `raw_duplicate_rate_within_limit` (limit `max_duplicate_rate`, default 0.01). The completeness singular test uses `min_completeness` (default 0.9). All three thresholds live in `transform/dbt_project.yml` vars.
  - No `dbt_utils`: the range test is a small custom generic test. That avoids a package download.
- **Alarms:** the reading schema has no alarm field, so `fct_detector_health` has no alarm column. `CT_ALARM_24HOUR` from the source file is not carried through. Add an alarm field to the schema, API, worker and loader if it is wanted.
- **Partial days:** the first and last day of a replay can be partial and will fail the completeness test. That is intended: the check reports incomplete detector-days.
- **No `dim_site`:** the optional map model is not built (see P9 notes in `PROGRESS.md`).
- **Revert:** edit the models and the vars.

## D27. Pipeline design and the replay clock (2026-11-10)

- **Choice:**
  - One job, `mcb_pipeline`: `raw_objects_loaded` (load), the dbt models (`dbt build`, dbt tests included), `pipeline_last_success` (writes `ops.pipeline_runs`). One schedule, hourly, `STOPPED` by default.
  - Four blocking asset checks (Python, in `orchestration/checks.py`): `freshness`, `no_negative_volumes` and `duplicate_rate` on `raw_objects_loaded`, then `completeness` on `fct_detector_health`. The first three run before dbt, so bad raw data stops the run before any model is built and the message names the check.
  - The dbt source `raw.readings` is mapped to the `raw_objects_loaded` asset.
  - `raw_objects_loaded` can seed synthetic readings straight into DuckDB (`source=synthetic`). That is for demos and tests only. The default source is the bucket.
  - **Replay clock:** freshness compares the newest `interval_end` with a "replay clock", not with the wall clock, because replayed data is old by design. Default is now; `--replay-clock` overrides it. Synthetic CLI runs use the end of the generated period. With real data replayed at speed, set it to the replay's current data time. This is a convention, not a measurement of lag.
- **Why Python checks as well as dbt tests:** dbt tests fail the run but report through dbt's log. The Python checks produce one readable message per failure and make the "which check, which asset, why" block possible.
- **Note:** `from __future__ import annotations` cannot be used in `orchestration/definitions.py`; Dagster reads context type hints as real types.
- **Revert:** Edit `orchestration/`.

## D28. Observability choices (2026-11-10)

- **Choice:**
  - Metrics names are prefixed `mcb_`. The API serves `/metrics` from a per-app registry. The worker serves its own on port 9101. Route labels use the route template and one shared `unmatched` label for unknown paths, so a scanner cannot create unlimited label values.
  - The pipeline gauge `mcb_pipeline_last_success_timestamp_seconds` is read from `ops.pipeline_runs` in DuckDB at scrape time by the API, which mounts the warehouse volume read-only. 0 means no run recorded.
  - Queue depth and dead-letter count are read by the worker from the queue attributes and exposed as gauges.
  - Grafana runs in the `obs` compose profile with anonymous access as Viewer only, bound to 127.0.0.1. The admin login is `admin` / `admin`, for local use only.
- **Not verified:** the dashboard loading in Grafana (no Docker). A test checks that every metric the dashboard uses is exposed by the apps.
- **Revert:** Remove the `obs` profile services and `/metrics`.

## D29. Forecast design (2026-11-10)

- **Choice:**
  - Series are per site, summed over detectors, in 15-minute steps. Two baselines: seasonal naive (same interval one week earlier) and the mean of the same interval over the previous four weeks, using the weeks that exist.
  - The API horizon is in 15-minute steps, 1 to 672 (one week), default 96 (one day). The cap keeps the seasonal lag inside observed history.
  - `forecast/evaluate.py` uses a holdout of the last 7 days per site, with forecasts built from earlier data only. MAPE skips zero actuals and reports how many. A result file records `data_source` and a `label`: `simulated` for synthetic data, `measured (host CPU)` for real data.
  - `results/forecast_eval.json` in the repo comes from 6 weeks of synthetic data, 3 sites, 2 detectors. It is labelled `simulated` and does not appear in the README summary.
- **Not done:** real-data forecast results. They stay "not measured" until the owner loads a real file.
- **Revert:** Edit `forecast/`.

## D30. Demo, static page and Pages workflow (2026-11-10)

- **Choice:**
  - The page has no JavaScript library and no CDN script. Charts are SVG drawn by `site/app.js`, each with a table alternative. This avoids pinned CDN versions, SRI hashes and a third-party licence.
  - `site/export.py` is run as a script. Output is `site/data/summary.json` (schema in `site/schema.json`, limit 2 MB, gitignored) plus a copy of `docs/media/architecture.svg`. The diagram is a hand-written SVG, not rendered from the README's Mermaid block.
  - No map. The optional `dim_site` join needs a locations file that was not downloaded on this machine, so no match rate was measured. The page says so (D12 stays open for the owner).
  - `make demo-bad` sends one faulty batch twice. The negative value is rejected by the API. The duplicate send passes the stateless API (D17) and fails the `duplicate_rate` check. The gap is reported by the completeness check only if the earlier checks pass.
  - The Pages workflow builds in the runner. With `REAL_DATA_ENABLED` unset, or on any failure of the download, the load or the pipeline, it builds from synthetic data and writes a warning to the job summary. The real path keeps the 50 busiest sites by daily volume, drops readings outside 0 to 2000 (counted in the job summary) and uses the end of the data as the replay clock.
  - The Pages workflow finds the latest ZIP through the publisher's CKAN API (`package_show` for `traffic-signal-volume-data`). The dataset id and resource fields are assumptions and were never called from this machine.
  - Dagster UI uses port 3001 so it does not clash with Grafana on 3000.
- **README live-demo URL:** `https://cesinata.github.io/mini-city-brain/` is the address GitHub Pages normally uses for this repository name. It was not checked.
- **Revert:** Delete `site/`, `scripts/pages_build.py` and `.github/workflows/pages.yml`.

## D31. The api reads the warehouse through a bind mount (2026-11-16)

- **Choice:** The api service mounts `./data/warehouse:/data/warehouse:ro`. The named volume `warehouse` is removed. `make up`, `scripts/demo.sh`, `scripts/demo_bad.sh` and the CI compose-smoke job create `data/warehouse` before `docker compose up`.
- **Reason:** The pipeline runs on the host and writes `data/warehouse/mcb.duckdb`. A named volume is a separate, empty folder inside Docker, so the api would never see that file and the forecast endpoint and pipeline gauge would report no warehouse. Creating the folder first stops Docker from creating it as root.
- **Check:** `tests/test_compose.py` parses `docker-compose.yml` and asserts that the mount's host folder is the folder of the `--db` path in `scripts/demo.sh`.
- **Revert:** Put the named volume back and run the pipeline inside a container that mounts it.

## D32. Replay of a real file sends the 20 busiest sites by default (2026-11-16)

- **Choice:** `python -m ingest.replay --file` takes `--top-sites N` (default 20, 0 means every site). Sites are ranked by `QT_VOLUME_24HOUR` summed over all rows of the file; a blank total counts as 0, a non-number is ignored, ties go to the lower site ID as text. Only rows for kept sites are unpivoted. The command prints one JSON line `{"plan": {"top_sites", "sites", "readings"}}` before sending, and with `0` a warning with the counts on stderr. `--top-sites` has no effect with `--synthetic`.
- **Reason:** A monthly file covers thousands of sites. Sending all of them to a laptop stack is slow and is rarely what a demo needs. The ranking lives in `ingest/scats.py` (`site_totals`, `top_sites`, `rows_for_sites`) so the Pages build (which keeps 50, D30) and the replay use one function.
- **Revert:** Pass `--top-sites 0`, or change `DEFAULT_TOP_SITES` in `ingest/replay.py`.

## D33. Old prototype files removed; ruff covers every main.py (2026-11-16, resolves D19)

- **Choice:** `main.py`, `main.tf`, `requirements.txt`, `Dockerfile` and `LICENSE.txt` were removed from the working tree by the owner. `"main.py"` is dropped from ruff's `extend-exclude`, because that pattern also excluded `services/api/main.py` and `services/worker/main.py`. Ruff then found one unsorted import block and one line over 100 characters in those two files; both were fixed in the code, with no new ignore.
- **Also:** The repo now lives outside OneDrive (D23), and `make setup` created `.venv` inside it. `make setup` stops with a message if `$(PYTHON)` (default `python3.13`, D18) is missing.
- **Revert:** Not applicable.

## D34. Emulator published on host port 5050, reached at 127.0.0.1 (2026-11-17)

- **Choice:** The Moto container still listens on 5000 inside the compose network (`http://emulator:5000`), but compose publishes it as `127.0.0.1:5050`. Every host-side default uses `http://127.0.0.1:5050`: `scripts/demo.sh`, `scripts/demo_bad.sh`, `env.example`, `.github/workflows/ci.yml`, `services/common/config.py` and the Terraform `endpoint_url` default.
- **Reason:** On macOS, AirPlay Receiver (Control Center) listens on port 5000 on every address, IPv6 included. Docker published the emulator on `127.0.0.1:5000` only, so `http://localhost:5000` reached AirPlay, which answered 403 Forbidden, and `make demo` failed at its smoke check. Seen on 2026-11-17 with `lsof` and `curl` (`Server: AirTunes`). Using the IPv4 literal avoids `localhost` resolving to `::1` first.
- **Check:** `tests/test_compose.py` asserts that the published port is not 5000 and that every host-side URL above uses it.
- **Revert:** Change the port in `docker-compose.yml` and in the files above together; the test lists them.

## D35. Paths handed to dbt are made absolute (2026-11-17)

- **Choice:** `run_pipeline` sets `DUCKDB_PATH` to the absolute form of `--db`. The dbt asset sets it again before each dbt call (this also covers runs started in the Dagster UI) and resolves its target path. `parse_manifest` resolves its target folder.
- **Reason:** Dagster runs dbt with `transform/` as its working directory. With the relative paths that `make demo` passes, dbt wrote its manifest to `transform/data/dbt_target/` while Dagster looked in `data/dbt_target/`, and dbt would have built its models in `transform/data/warehouse/mcb.duckdb` instead of the database the loader wrote. Tests used absolute temporary paths, so they never showed it.
- **Check:** `tests/test_orchestration.py::test_cli_with_relative_paths_keeps_dbt_and_the_loader_on_one_database` fails without the fix and passes with it.
- **Revert:** Pass absolute paths from every caller instead.

## D36. Wait for every accepted reading before running the pipeline (2026-11-17)

- **Choice:** `scripts.smoke_assert --expect-readings N` waits until the objects under `raw/scats/` hold at least N readings (non-empty ndjson lines). `make demo` passes the replay's accepted count. `make demo-bad` counts what is in the bucket before it posts and waits for that plus what the API accepted. CI's smoke test keeps the old check (at least one object, empty dead-letter queue).
- **Reason:** The worker flushes after 1000 readings or 5 seconds (D21). On 2026-11-17 the smoke check passed as soon as the first object existed, and the pipeline loaded 1000 of 1920 readings; the completeness check then failed 10 detector-days of clean data. `make demo-bad` waited for "at least 2 objects", which an earlier `make demo` already satisfies.
- **Revert:** Drop `--expect-readings` from `scripts/demo.sh` and restore the object check in `scripts/demo_bad.py`.

## D37. Terraform lock file holds provider hashes for four platforms (2026-11-17)

- **Choice:** `infra/terraform/.terraform.lock.hcl` lists `h1:` hashes for `darwin_arm64`, `darwin_amd64`, `linux_amd64` and `linux_arm64`, made with `terraform providers lock -platform=...`, one platform per run. The version stays 6.22.1 and the `zh:` hashes are unchanged.
- **Reason:** The compose `init` container (Linux on Apple silicon) added its own hash on the first `make demo`, so the tracked file changed after a normal run. With all four platforms listed, a run on macOS, on CI or in the container leaves it unchanged. One platform per run because this laptop's disk was nearly full and four unpacked providers in one temporary folder did not fit.
- **Revert:** Delete the added `h1:` lines.

## D38. make down also stops the obs profile (2026-11-17)

- **Choice:** `make down` runs `docker compose --profile obs down`. It keeps volumes; `make demo-down` still removes them.
- **Reason:** After `make demo` (which starts the `obs` profile), a plain `docker compose down` left Prometheus and Grafana running and could not remove the network ("Resource is still in use").
- **Revert:** Remove `--profile obs` from the `down` target.

## Stage 3 notes on earlier entries (2026-11-17)

- D22: the Terraform `init` container now runs in the compose stack. On a fresh stack it creates all four resources. A `terraform.tfstate` from an earlier run stays in `infra/terraform/` (gitignored); Terraform refreshes it, finds the resources missing in the new emulator and creates them again (`results/demo_run.txt`).
- D28: Grafana starts, its health endpoint is ok, and its API finds the provisioned dashboard `mcb-overview`. The panels have not been checked by eye.

## D39. Two Grafana panel fixes after the first look (2026-11-17)

- **Choice:** "Time since last pipeline success" uses `time() - (mcb_pipeline_last_success_timestamp_seconds > 0)`. "Rejection rate" keeps the `percentunit` unit and gets a fixed axis from 0 to 1 (0% to 100%).
- **Reason:** The first look at the dashboard showed ages in the hundreds of thousands of years. The old query multiplied the age by `(gauge > 0)`, and in PromQL a comparison without `bool` keeps the gauge's own value (about 1.8 billion), not 1. Against the live stack the old query gave 29805866327.8 s and the new one 16.5 s (`results/stack_checks.txt`, measured (host CPU), one run). With all-zero data Grafana picked an axis of 0 to 100 for a fraction, shown as 0% to 10000%.
- **Check:** `tests/test_observability.py` asserts both panel definitions.
- **Revert:** Edit `observability/grafana/dashboards/mcb-overview.json`.

## D40. Hero illustration: one source file, copied for the page (2026-11-17)

- **Choice:** The README shows `docs/media/hero-isometric.svg` directly under the summary sentence. The page shows the same file from `data/hero-isometric.svg`; `site/export.py` copies it there from `docs/media/`, as it already did for `architecture.svg` (`MEDIA_FILES`). Both use the same alt text. The embedded C2PA content-credentials manifest is kept as provided.
- **Reason:** `site/` is served on its own (locally and on Pages), so it cannot reach `docs/media/`. Copying at export time keeps one tracked file instead of two that could drift. The manifest holds no personal data (checked by decoding it: tool name, signer, timestamps) and records that the image was made with Claude, which matches how this repo discloses AI use.
- **Check:** `tests/test_site.py` checks that every image path in the README and the page resolves, that the copied files match their source byte for byte, that the hero alt text is the same in both, and that the served page returns the hero with HTTP 200.
- **Revert:** Remove the `<img id="hero">` tag, the README image line and the name from `MEDIA_FILES`.

## D41. Stage commits after the early merge (2026-11-17)

- **Choice:** `rebuild-v2` was merged into `main` twice before Stage 6 (CI green on both merge commits). Work from Stage 4 on goes on a new branch made from `origin/main`, merged through its own pull request.
- **Reason:** A new branch from the merged `main` carries no history that GitHub has already merged, whichever merge method was used. The plan's Stage 6 steps that merge `rebuild-v2` and recreate `main` no longer apply as written.
- **Revert:** Not applicable.

## D42. Demo page layout on wide screens (2026-11-17)

- **Choice:** From 1100 px wide, `site/style.css` switches to a grid up to 1200 px: the title and intro beside the illustration, then "Busiest intersections" and "Data completeness" side by side (3:2), and the heat map, forecast chart, map note and "How it works" at full width. Below 1100 px the single column stays as it was.
- **Reason:** On a desktop screen the page stayed a 960 px phone-style column. The charts are SVGs drawn 720 units wide, so the wide ones keep the full width and the bar chart gets the larger share of its row, to keep labels readable. The completeness table moves up beside the bar chart on desktop only; it has nothing focusable, so keyboard order does not change.
- **Check:** headless Chrome screenshots at 1600, 1280 and 600 px (not saved); `tests/test_site.py` checks that the desktop grid places every section.
- **Revert:** Delete the `@media (min-width: 1100px)` block and the `s-*` classes.

## D43. Reader and models follow the real file: -1 is missing, Melbourne wall-clock time (2026-11-17, supersedes the time-zone choice in D24)

- **Choice:**
  - `-1` in a `Vxx` column is a missing interval: no reading, counted. Other negative values still go to the API, which rejects them.
  - Intervals are read in `Australia/Melbourne` wall-clock time by default. `V00` starts at local midnight and lasts 15 minutes of real time. Intervals that start inside the clock gap when daylight saving begins (02:00 to 02:45) are skipped and counted. `--tz AEST` keeps the old fixed UTC+10 reading.
  - dbt converts to local time with the time zone (`local_time_zone: "Australia/Melbourne"`) instead of adding 10 hours (`local_offset_hours` is removed).
  - The synthetic generator writes `-1` for missing intervals, `-1` for V07 to V11 on the day clocks go forward, CRLF line endings, and (with `write_zip`) one `VSDATA_YYYYMMDD.csv` per day. Its negative-value fault is now `-5`.
- **Reason:** A read-only scan of the October 2026 file (`results/real_data_inspection.txt`) showed `-1` and no blanks, and showed the daylight-saving gap at 02:00 on 4 October with the morning peak staying at 08:00 local across the change. Read as before, every `-1` would reach the API as a negative volume and be rejected as bad data, local hours would be one hour off from 4 October, and on the change day the elapsed-time mapping would have pushed the evening's intervals into the next day.
- **Evidence limits:** The afternoon peak is broad (hours 15 to 17 within 0.1 percentage points), so it does not tell the two readings apart; the morning peak and the gap do. 1 October falls in the Victorian school holidays. The day clocks go back has not been checked. Saturday 3 October has an unexplained all-`-1` hour (V08 to V11).
- **Check:** `tests/test_ingest.py` (sentinel, clock gap with continuous 15-minute steps, default zone, monthly ZIP layout) and `tests/test_warehouse_dbt.py` (local hour 8 and local day across the change).
- **Revert:** Pass `--tz AEST`, set `local_time_zone` to a fixed-offset zone, and treat `-1` as a value in `ingest/scats.py`.

## D44. Host-side tools call the API at 127.0.0.1 (2026-11-17)

- **Choice:** The replay client's default `--api-url`, `scripts/wait_for_health.sh`, `scripts/demo.sh`, `scripts/demo_bad.sh`, `scripts/demo_bad.py`, `env.example`, the CI health wait and the URLs `make demo` prints use `http://127.0.0.1:8000` (and `127.0.0.1` for Grafana and the Dagster UI) instead of `localhost`.
- **Reason:** Compose publishes the API on `127.0.0.1:8000` (IPv4) only. On 2026-11-17 another program on the laptop (a `python -m http.server` serving `docs/`) listened on IPv6 port 8000, `localhost` resolved to `::1`, and all 3,156 batches of the first real-data replay went to that server, which answered HTTP 501. Nothing reached the API. Same cause as D34.
- **Check:** `tests/test_compose.py` asserts the published port and every host-side API URL listed above.
- **Revert:** Change the URLs back to `localhost`; the test lists the files.

## D45. Completeness fails a run only above a share of incomplete detector-days (2026-11-17, chosen by the owner)

- **What happened:** On October 2026 (20 sites, 536 detectors, 16,532 detector-days) the blocking completeness check failed: 53 detector-days (0.32%) had fewer than 90% of their 96 intervals. 31 of them are one detector at site 849 that reports about half the day all month; the rest are spread over six sites. Mean completeness was 99.41% (`results/real_completeness_breakdown.txt`, measured (host CPU), one run). Under the old rule one broken detector among hundreds failed every real run, so the Pages build would always have fallen back to synthetic data.
- **Choice (owner, from two options proposed after the numbers were reported):** keep 0.9 per detector-day (`min_completeness`), and fail the run only when more than 1% of detector-days are below it (`max_incomplete_share: 0.01` in `transform/dbt_project.yml` and `PipelineSettings`). Below that share the Python check passes and lists the incomplete detector-days; `python -m orchestration.run` prints them as `warning:` lines. This matches how `duplicate_rate` works.
- **Result:** the same October data now passes with a warning for the 53 detector-days (`results/real_pipeline.txt`). It would fail if incomplete detector-days were about three times as common, or if one bad day hit many detectors at once.
- **Check:** `tests/test_orchestration.py` (strict default, warning below the limit, failure above it, the warning in the run summary) and `tests/test_warehouse_dbt.py` (1 of 200 incomplete detector-days passes, 3 of 200 fail).
- **Revert:** set `max_incomplete_share` to 0.

## D46. Pages and README screenshots (2026-11-17, owner's request)

- **Choice:** The GitHub Pages step and the README screenshots come earlier than planned, because the owner needs the repo in a portfolio now. The screenshots were taken with headless Chrome (a throwaway browser profile, no browser bar) after replaying the real October 2026 month: the demo page built from that month, the Grafana dashboard during the replay, and the Dagster asset graph after a run recorded in the local `dagster_home/`.
- **Consequences:** The demo GIF is not made.
- **Revert:** Not applicable.
- **Update (2026-11-17):** the owner enabled Pages and ran the workflow on `main`; it passed and the page is live at https://cesinata.github.io/mini-city-brain/ with synthetic data. The README links to it. The banner text is now 14 px, and `docs/media/architecture.svg` was redrawn so every label fits its box and no arrows cross.

## D47. GitHub Actions moved to versions that run on Node.js 24 (2026-11-17)

- **Choice:** `actions/checkout` v5.1.0, `actions/setup-python` v6.3.0, `hashicorp/setup-terraform` v4.0.1, `actions/configure-pages` v6.0.0, `actions/upload-pages-artifact` v5.0.0, `actions/deploy-pages` v5.0.1. Each is the oldest major version whose `action.yml` runs on Node.js 24, at its newest patch release; each was released more than 14 days ago (looked up on GitHub on 2026-11-17, `docs/third-party.md`).
- **Reason:** CI annotated every job with "Node.js 20 is deprecated" for the old pins, which GitHub forced onto Node.js 24 anyway. The inputs the workflows use (`python-version`, `terraform_version`, `path`) exist in the new versions.
- **Not verified:** the new versions in CI and in the Pages workflow; the first runs after this change show it.
- **Revert:** Put the old tags back in `.github/workflows/ci.yml` and `pages.yml`.

## D48. The Pages build uses the newest complete month (2026-11-17)

- **Choice:** With `REAL_DATA_ENABLED` set, `scripts/pages_build.py` reads the month from each ZIP resource's name or URL (month name and year, as in `traffic_signal_volume_data_october_2026.zip`, or `YYYY-MM`) and picks the newest month that has ended in Melbourne time. If no month can be read, it falls back to the newest file by `last_modified`, as before. The job summary lists the file used.
- **Reason:** The publisher updates the current month's file daily, so on 17 November it held about half a month (68 MB against 141 MB for October). A partial month gives a shorter forecast history and may end with a part day that the completeness check would flag; October also matches the README's numbers and screenshots.
- **Not verified:** the publisher's CKAN API has not been called from this repo yet, so the resource names it returns are an assumption (D30). The first real-data run's job summary shows which file was picked.
- **Revert:** Return the old `max(... last_modified ...)` in `latest_zip_resource`.
