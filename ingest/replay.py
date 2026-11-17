"""Post readings to the API in batches at a chosen speed.

Speed factor: 60 means one hour of data is sent in one minute. 0 means send as fast as
possible. Failed requests (connection errors, 429 and 5xx) are retried with exponential
backoff. A summary is printed at the end and the exit code is 1 if any batch failed.

With --file, only the busiest sites are sent by default (--top-sites 20, ranked by summed
QT_VOLUME_24HOUR); --top-sites 0 sends every site and prints a warning with the count.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from collections.abc import Callable, Iterator, Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from ingest import scats, synthetic
from services.common.models import MAX_BATCH_SIZE

RETRY_STATUS = {429, 500, 502, 503, 504}
DEFAULT_TOP_SITES = 20


@dataclass
class Summary:
    batches_sent: int = 0
    batches_failed: int = 0
    readings_sent: int = 0
    accepted: int = 0
    rejected: int = 0
    retries: int = 0
    reject_reasons: dict[str, int] = field(default_factory=dict)

    def note_reasons(self, rejections: list[dict[str, Any]]) -> None:
        for item in rejections:
            for reason in item.get("reasons", []):
                key = reason.split(":")[0]
                self.reject_reasons[key] = self.reject_reasons.get(key, 0) + 1


def plan_batches(readings: Sequence[dict[str, Any]], batch_size: int) -> list[list[dict[str, Any]]]:
    """Split time-ordered readings into batches of at most `batch_size` (never above 500)."""
    size = max(1, min(batch_size, MAX_BATCH_SIZE))
    return [list(readings[i : i + size]) for i in range(0, len(readings), size)]


def batch_delays(batches: Sequence[Sequence[dict[str, Any]]], speed: float) -> list[float]:
    """Seconds to wait before each batch so that data time passes `speed` times faster.

    The first batch is sent at once. The wait before batch n is the data time between the end
    of batch n-1 and the end of batch n, divided by `speed`. Speed 0 means no waiting.
    """
    if speed <= 0:
        return [0.0] * len(batches)

    def end(batch: Sequence[dict[str, Any]]) -> datetime:
        return max(datetime.fromisoformat(r["interval_end"]) for r in batch)

    delays = [0.0]
    for prev, cur in zip(batches, batches[1:], strict=False):
        gap = (end(cur) - end(prev)).total_seconds()
        delays.append(max(0.0, gap) / speed)
    return delays[: len(batches)]


def send_batch(
    client: httpx.Client,
    url: str,
    batch: list[dict[str, Any]],
    summary: Summary,
    sleep: Callable[[float], None] = time.sleep,
    max_attempts: int = 5,
    base_delay: float = 0.5,
) -> bool:
    for attempt in range(max_attempts):
        try:
            resp = client.post(f"{url}/v1/readings", json={"readings": batch}, timeout=30)
        except httpx.TransportError:
            resp = None
        if resp is not None and resp.status_code not in RETRY_STATUS:
            if resp.status_code == 202:
                body = resp.json()
                summary.accepted += body["accepted"]
                summary.rejected += body["rejected"]
                summary.note_reasons(body["rejections"])
                return True
            return False
        if attempt < max_attempts - 1:
            summary.retries += 1
            sleep(base_delay * 2**attempt)
    return False


def replay(
    readings: Sequence[dict[str, Any]],
    api_url: str,
    speed: float = 0,
    batch_size: int = 500,
    client: httpx.Client | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> Summary:
    summary = Summary()
    batches = plan_batches(readings, batch_size)
    delays = batch_delays(batches, speed)
    own_client = client is None
    client = client or httpx.Client()
    try:
        for batch, delay in zip(batches, delays, strict=True):
            if delay:
                sleep(delay)
            ok = send_batch(client, api_url.rstrip("/"), batch, summary, sleep=sleep)
            summary.batches_sent += 1
            summary.readings_sent += len(batch)
            if not ok:
                summary.batches_failed += 1
    finally:
        if own_client:
            client.close()
    return summary


def send_plan(readings: Sequence[dict[str, Any]], top_sites: int) -> dict[str, int]:
    """How many sites and readings a replay is about to send."""
    return {
        "top_sites": top_sites,
        "sites": len({r["site_id"] for r in readings}),
        "readings": len(readings),
    }


def synthetic_readings(
    sites: int, detectors: int, days: int, faults: bool, seed: int
) -> Iterator[dict[str, Any]]:
    rows = synthetic.generate(sites, detectors, days, seed=seed, faults=faults)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "synthetic.csv"
        synthetic.write_csv(rows, path)
        readings, _ = scats.read_readings(path, source="synthetic")
    yield from readings


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Replay readings into the ingestion API.")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--synthetic", action="store_true", help="generate synthetic data")
    src.add_argument("--file", type=Path, help="SCATS CSV or monthly ZIP on this machine")
    p.add_argument("--api-url", default="http://127.0.0.1:8000")
    p.add_argument(
        "--speed", type=float, default=60, help="60 = 1 hour of data per minute; 0 = max"
    )
    p.add_argument("--batch-size", type=int, default=500)
    p.add_argument("--sites", type=int, default=2)
    p.add_argument("--detectors", type=int, default=2)
    p.add_argument("--days", type=int, default=1)
    p.add_argument("--seed", type=int, default=synthetic.DEFAULT_SEED)
    p.add_argument("--clean", action="store_true", help="synthetic data without injected faults")
    p.add_argument(
        "--tz",
        default=scats.DEFAULT_TZ,
        help="time zone of the file's intervals; default Australia/Melbourne (wall clock, "
        "daylight saving included); AEST means fixed +10",
    )
    p.add_argument(
        "--top-sites",
        type=int,
        default=DEFAULT_TOP_SITES,
        help="with --file: send only the N sites with the highest summed QT_VOLUME_24HOUR; "
        "0 = all sites",
    )
    a = p.parse_args(argv)
    if a.top_sites < 0:
        p.error("--top-sites must be 0 or more")

    if a.synthetic:
        readings = list(
            synthetic_readings(a.sites, a.detectors, a.days, faults=not a.clean, seed=a.seed)
        )
    else:
        keep = scats.top_sites(a.file, a.top_sites)
        readings, stats = scats.read_readings(a.file, source="scats", tz=a.tz, sites=keep)
        print(json.dumps({"read": asdict(stats)}))
        plan = send_plan(readings, a.top_sites)
        print(json.dumps({"plan": plan}))
        if a.top_sites == 0:
            print(
                f"WARNING: --top-sites 0 sends every site in the file: {plan['sites']} sites, "
                f"{plan['readings']} readings.",
                file=sys.stderr,
            )
    summary = replay(readings, a.api_url, speed=a.speed, batch_size=a.batch_size)
    print(json.dumps({"summary": asdict(summary)}, indent=2))
    return 1 if summary.batches_failed else 0


if __name__ == "__main__":
    sys.exit(main())
