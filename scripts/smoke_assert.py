"""Assert the compose stack wrote objects to the raw bucket and the dead-letter queue is empty.

Usage: python -m scripts.smoke_assert [--wait SECONDS] [--expect-readings N]
Reads AWS_ENDPOINT_URL and resource names from the environment. Exit code 0 = pass.

With --expect-readings, it also waits until the raw objects hold at least N readings in total.
The worker flushes by count or after a few seconds, so "an object exists" can be true while
part of the replay is still in the queue (decisions D36).
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import Any

from services.common.aws import queue_url, s3_client, sqs_client
from services.common.config import Settings

RAW_PREFIX = "raw/scats/"


def raw_reading_count(s3: Any, bucket: str) -> int:
    """Readings (non-empty ndjson lines) in every object under raw/scats/."""
    total = 0
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=RAW_PREFIX):
        for obj in page.get("Contents", []):
            body = s3.get_object(Bucket=bucket, Key=obj["Key"])["Body"].read()
            total += sum(1 for line in body.splitlines() if line.strip())
    return total


def wait_for_readings(
    settings: Settings, expected: int, wait: float, s3: Any | None = None, interval: float = 2
) -> int:
    """Poll until the raw bucket holds at least `expected` readings. Returns the last count."""
    s3 = s3 or s3_client(settings)
    deadline = time.monotonic() + wait
    while True:
        count = raw_reading_count(s3, settings.raw_bucket)
        if count >= expected or time.monotonic() >= deadline:
            return count
        time.sleep(interval)


def check(
    settings: Settings,
    s3: Any | None = None,
    sqs: Any | None = None,
    expect_readings: int = 0,
) -> list[str]:
    """Return a list of problems. Empty means pass."""
    s3 = s3 or s3_client(settings)
    sqs = sqs or sqs_client(settings)
    problems = []
    listing = s3.list_objects_v2(Bucket=settings.raw_bucket, Prefix=RAW_PREFIX)
    if listing.get("KeyCount", 0) == 0:
        problems.append("no objects under raw/scats/ in the raw bucket")
    elif expect_readings:
        count = raw_reading_count(s3, settings.raw_bucket)
        if count < expect_readings:
            problems.append(
                f"raw bucket holds {count} readings, expected at least {expect_readings}"
            )
    url = queue_url(sqs, settings.dead_letter_queue_name)
    attrs = sqs.get_queue_attributes(QueueUrl=url, AttributeNames=["All"])["Attributes"]
    depth = int(attrs["ApproximateNumberOfMessages"]) + int(
        attrs["ApproximateNumberOfMessagesNotVisible"]
    )
    if depth:
        problems.append(f"dead-letter queue has {depth} message(s)")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wait", type=int, default=30, help="seconds to keep retrying")
    parser.add_argument(
        "--expect-readings",
        type=int,
        default=0,
        help="also wait until the raw objects hold at least this many readings",
    )
    args = parser.parse_args(argv)
    settings = Settings.from_env()
    deadline = time.monotonic() + args.wait
    while True:
        problems = check(settings, expect_readings=args.expect_readings)
        if not problems:
            held = f", at least {args.expect_readings} readings" if args.expect_readings else ""
            print(f"smoke check passed: objects in raw bucket{held}, dead-letter queue empty")
            return 0
        if time.monotonic() >= deadline:
            for p in problems:
                print(f"FAIL: {p}")
            return 1
        time.sleep(2)


if __name__ == "__main__":
    sys.exit(main())
