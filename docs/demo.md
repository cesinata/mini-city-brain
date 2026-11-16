# Demo guide

Three things to try, in order of effort: the static page, the one-command local demo, and the run that breaks on purpose. Status of each on the build machine is at the end.

## 1. Look at the static page locally (no Docker)

```
make setup
make pipeline            # synthetic data into data/warehouse/mcb.duckdb
make site                # writes site/data/summary.json (gitignored)
python -m http.server --directory site 8000
```

Open `http://localhost:8000`. With synthetic data the page shows a large "SYNTHETIC DATA" banner. Nothing is downloaded.

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
- The command exits non-zero and prints a block naming the check, the asset and the reason, like this (from an in-process run on synthetic data):

```
PIPELINE FAILED
------------------------------------------------------------
  check: duplicate_rate
  asset: raw_objects_loaded
  why:   96 of 1800 raw rows repeat a key (rate 0.0533, limit 0.01)
```

Rejected readings also show in Grafana as the "Rejection rate" panel.

## 4. Publish the page with GitHub Pages

1. In the repository, open **Settings > Pages** and set **Source** to **GitHub Actions**.
2. Run the **Pages demo** workflow from the Actions tab (it also runs weekly).
3. The first run builds from synthetic data and the page says so.

### Switching on real data

Do this only after you have confirmed the licence on the publisher's own page (see [data.md](data.md)).

1. Open **Settings > Secrets and variables > Actions > Variables**.
2. Add a repository variable named `REAL_DATA_ENABLED` with the value `true`.
3. Re-run the workflow. It asks the publisher's API for the latest monthly file, downloads it inside the runner, keeps the busiest sites, runs the pipeline and publishes only small aggregates with the attribution line.

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
| `make demo`, `make demo-bad`, Grafana, `make up` | Not run: no Docker |
| Pages workflow | Not run (needs GitHub). The real-data download is tested with a fake HTTP client only |
