"""`make demo-bad`: send faulty readings and show that the pipeline refuses them.

What it does (needs the compose stack running):
  1. Builds one batch with deliberate faults: a negative volume, a gap of 20 missing intervals
     and, because it sends the same batch twice, duplicates across requests.
  2. Posts the batch twice to the API and prints what the API rejected and why.
  3. Waits until the bucket holds every accepted reading, then runs the pipeline on it.
  4. Exits non-zero and prints which check failed, on which asset, and why.

Rejected readings also show in Grafana (mcb_api_readings_rejected_total).
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable, Sequence
from datetime import timedelta
from pathlib import Path

import httpx

from ingest.synthetic import DEFAULT_START
from orchestration.run import main as run_pipeline_cli
from scripts.smoke_assert import raw_reading_count, wait_for_readings
from services.common.aws import s3_client
from services.common.config import Settings

SITE = "9001"


def faulty_readings() -> list[dict]:
    """One detector, one day (96 intervals), then three deliberate faults."""
    from ingest import replay

    readings = list(replay.synthetic_readings(1, 1, 1, faults=False, seed=99))
    for r in readings:
        r["site_id"] = SITE
    gap = readings[:30] + readings[50:]  # 20 intervals missing
    negative = {**readings[0], "detector_id": "2", "volume": -5}  # a value that cannot be real
    return [*gap, negative]


def post_twice(client: httpx.Client, api_url: str, batch: list[dict]) -> list[dict]:
    """Send the same batch twice. The second copy is a duplicate across requests."""
    out = []
    for attempt in (1, 2):
        resp = client.post(f"{api_url}/v1/readings", json={"readings": batch}, timeout=30)
        body = resp.json()
        reasons = sorted(
            {r.split(":")[0] for item in body.get("rejections", []) for r in item["reasons"]}
        )
        print(
            f"  request {attempt}: HTTP {resp.status_code}, accepted {body.get('accepted')}, "
            f"rejected {body.get('rejected')} {reasons or ''}"
        )
        out.append(body)
    return out


def raw_readings_now() -> int:
    """Readings already in the raw bucket, for example from an earlier `make demo`."""
    settings = Settings.from_env()
    return raw_reading_count(s3_client(settings), settings.raw_bucket)


def wait_for_readings_in_bucket(expected: int, wait: float) -> bool:
    """Wait until the worker has written every accepted reading (decisions D36)."""
    return wait_for_readings(Settings.from_env(), expected, wait) >= expected


def main(
    argv: Sequence[str] | None = None,
    client: httpx.Client | None = None,
    wait: int = 40,
    after_post: Callable[[], None] | None = None,
) -> int:
    api_url = os.environ.get("API_URL", "http://127.0.0.1:8000")
    db = os.environ.get("DEMO_BAD_DB", "data/warehouse/demo_bad.duckdb")
    Path(db).unlink(missing_ok=True)
    print("demo-bad: sending a batch with a gap, a negative value and a duplicate send")
    batch = faulty_readings()
    before = raw_readings_now()
    own = client is None
    client = client or httpx.Client()
    try:
        responses = post_twice(client, api_url, batch)
    finally:
        if own:
            client.close()
    accepted = sum(int(body.get("accepted") or 0) for body in responses)
    if after_post is not None:
        after_post()  # tests use this to run the worker in-process
    if wait and not wait_for_readings_in_bucket(before + accepted, wait):
        print("demo-bad: the worker did not write the objects in time", file=sys.stderr)
        return 2
    print("demo-bad: running the pipeline on what reached the bucket")
    end = DEFAULT_START + timedelta(days=1)
    clock = f"{end.isoformat()}T00:00:00+00:00"
    code = run_pipeline_cli(["--source", "bucket", "--db", db, "--replay-clock", clock])
    if code == 0:
        print("demo-bad: the pipeline passed. That is a bug: the data was faulty.", file=sys.stderr)
        return 3
    print(json.dumps({"demo_bad": "pipeline refused the faulty data", "exit": code}))
    return code


if __name__ == "__main__":
    sys.exit(main())
