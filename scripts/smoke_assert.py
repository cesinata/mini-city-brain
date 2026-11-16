"""Assert the compose stack wrote objects to the raw bucket and the dead-letter queue is empty.

Usage: python -m scripts.smoke_assert [--wait SECONDS]
Reads AWS_ENDPOINT_URL and resource names from the environment. Exit code 0 = pass.
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import Any

from services.common.aws import queue_url, s3_client, sqs_client
from services.common.config import Settings


def check(settings: Settings, s3: Any | None = None, sqs: Any | None = None) -> list[str]:
    """Return a list of problems. Empty means pass."""
    s3 = s3 or s3_client(settings)
    sqs = sqs or sqs_client(settings)
    problems = []
    listing = s3.list_objects_v2(Bucket=settings.raw_bucket, Prefix="raw/scats/")
    if listing.get("KeyCount", 0) == 0:
        problems.append("no objects under raw/scats/ in the raw bucket")
    url = queue_url(sqs, settings.dead_letter_queue_name)
    attrs = sqs.get_queue_attributes(QueueUrl=url, AttributeNames=["All"])["Attributes"]
    depth = int(attrs["ApproximateNumberOfMessages"]) + int(
        attrs["ApproximateNumberOfMessagesNotVisible"]
    )
    if depth:
        problems.append(f"dead-letter queue has {depth} message(s)")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wait", type=int, default=30, help="seconds to keep retrying")
    args = parser.parse_args()
    settings = Settings.from_env()
    deadline = time.monotonic() + args.wait
    while True:
        problems = check(settings)
        if not problems:
            print("smoke check passed: objects in raw bucket, dead-letter queue empty")
            return 0
        if time.monotonic() >= deadline:
            for p in problems:
                print(f"FAIL: {p}")
            return 1
        time.sleep(2)


if __name__ == "__main__":
    sys.exit(main())
