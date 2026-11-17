# Demo guide

Three things to try, in order of effort: the static page, the one-command local demo, and the run that breaks on purpose. Status of each on the build machine is at the end.

## 1. Look at the static page locally (no Docker)

```
make setup
make pipeline            # synthetic data into data/warehouse/mcb.duckdb
make site                # writes site/data/summary.json (gitignored)
python -m http.server --directory site 8000
```

Open `http://localhost:8000`. With synthetic data the page shows a large "SYNTHETIC DATA" banner. Nothing is downloaded. `make site` also copies the hero illustration and the diagram from `docs/media/` into `site/data/`, which is where the page loads them from.

## 2. One-command demo (needs Docker)

```
make demo
```

It starts the stack with the `obs` profile, replays 2 synthetic days for 5 sites at full speed, runs the pipeline once and prints a short summary and the URLs:

| What | URL |
| --- | --- |
| API docs | `http://localhost:8000/docs` |
| Grafana (anonymous, read-only) | `http://localhost:3000` |
| Dagster UI | `make dagster-ui`, then `http://localhost:3001` |

Stop everything and remove the volumes with `make demo-down`.

Open the Dagster UI on its own with `make dagster-ui`. It uses a local `dagster_home/` folder (gitignored).

## 3. See it break on purpose (needs Docker)

```
make demo-down     # start from an empty queue and bucket
make demo-bad
```

It sends one batch with a negative volume, a 20-interval gap, and sends that batch twice. Then it runs the pipeline. Expected result:

- The API response for each request lists the rejected reading and the reason (`volume`).
- The duplicate send reaches the bucket, so the `duplicate_rate` check fails and the run stops before any model is built.
- The command exits non-zero and prints a block naming the check, the asset and the reason. From a run against the Docker stack on 2026-11-17, started after `make demo-down` (`results/demo_bad_run.txt`; synthetic data, so `simulated`):

```
  request 1: HTTP 202, accepted 76, rejected 1 ['volume']
  request 2: HTTP 202, accepted 76, rejected 1 ['volume']
demo-bad: running the pipeline on what reached the bucket
PIPELINE FAILED
------------------------------------------------------------
  check: duplicate_rate
  asset: raw_objects_loaded
  why:   76 of 152 raw rows repeat a key (rate 0.5000, limit 0.01)
Nothing downstream of a failed check was built.
```

Without `make demo-down` first, the bucket still holds the clean readings from `make demo`, so the rate is lower but still over the limit: 76 of 2072 rows, rate 0.0367 (`results/demo_bad_after_demo.txt`, `simulated`). The script waits until the bucket holds every accepted reading before it runs the pipeline (decisions D36).

Rejected readings also show in Grafana as the "Rejection rate" panel.

In `make demo` the "Ingest rate" panel stays flat: the replay at full speed finishes in about a second, so Prometheus (scraping every 5 seconds) only sees the counter jump, not a rate. A slower replay against a running stack, for example `make replay SPEED=60` (one synthetic day in about 24 minutes), should show a rate; that has not been tried.

## 4. Publish the page with GitHub Pages

1. In the repository, open **Settings > Pages** and set **Source** to **GitHub Actions**.
2. Run the **Pages demo** workflow from the Actions tab (it also runs weekly).
3. The first run builds from synthetic data and the page says so.

### Switching on real data

Do this only after you have confirmed the licence on the publisher's own page (see [data.md](data.md)).

1. Open **Settings > Secrets and variables > Actions > Variables**.
2. Add a repository variable named `REAL_DATA_ENABLED` with the value `true`.
3. Run the workflow again (**Run workflow**, not **Re-run**, so it builds the current `main`). It asks the publisher's API for the monthly files, picks the newest month that has already ended (decisions D48), downloads it inside the runner, keeps the 50 busiest sites, runs the pipeline and publishes only small aggregates with the attribution line. The job summary names the file it used.

If the download, the load or the pipeline checks fail, the workflow builds the synthetic page instead and writes a warning in the job summary. Raw files are never committed or published. To go back, delete the variable or set it to anything other than `true`.

## 5. Record the GIF

There is no GIF in the repo yet, and the README does not show one. After recording, link it from the README.

1. Run `make demo` and open the Grafana dashboard and the page.
2. Record 15 to 20 seconds with a screen recorder (on macOS, Shift-Command-5), then convert to a GIF with a tool you trust.
3. Keep it under 2 MB and save it as `docs/media/demo.gif`.

## Status on the build machine

| Item | Status |
| --- | --- |
| Static page: file serving, JSON schema, rendering against a fake DOM | Run, passed (`tests/test_site.py`, `results/site_serve_check.txt`) |
| Static page in a real browser | Visual check not done |
| `make pipeline` on synthetic data | Run, passed (`results/pipeline_synthetic_ok.txt`) |
| `make demo-bad` logic in-process (API, queue, worker, bucket, pipeline) | Run, exits non-zero (`tests/test_demo.py`) |
| `make demo` against Docker | Run 2026-11-17, exit 0, 189 s wall time (measured (host CPU), one run; `results/demo_run.txt`) |
| `make demo-bad` against Docker | Run 2026-11-17, exits non-zero with the block above (`results/demo_bad_run.txt`) |
| `make up`, `make replay`, smoke check, `make down` | Run 2026-11-17, each exit 0 (`results/compose_targets.txt`) |
| API health, forecast endpoint, Prometheus targets, Grafana health and dashboard, Dagster UI on port 3001 | Checked with `curl` on 2026-11-17 (`results/stack_checks.txt`) |
| Grafana dashboard, Dagster UI and API docs by eye | Looked at 2026-11-17. Two Grafana panels were wrong and are fixed (decisions D39) |
| README screenshots (demo page, Grafana, Dagster asset graph) | Taken 2026-11-17 with headless Chrome after a real October 2026 replay and pipeline run (`docs/media/*.png`) |
| Failed `make demo-bad` run in the Dagster UI | Screenshot taken 2026-11-17 after `DAGSTER_HOME=$PWD/dagster_home make demo-bad` (`docs/media/dagster-demo-bad-run.png`). No GIF recorded |
| Pages workflow | Run on GitHub on 2026-11-17 from `main` with `REAL_DATA_ENABLED` unset: build and deploy passed, and https://cesinata.github.io/mini-city-brain/ serves the synthetic page. The real-data download is still tested with a fake HTTP client only |
