"""Settings read from environment variables. All AWS access goes through the endpoint override."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    endpoint_url: str
    region: str
    raw_bucket: str
    curated_bucket: str
    ingest_queue_name: str
    dead_letter_queue_name: str
    batch_max_readings: int
    batch_max_seconds: float
    visibility_timeout: int

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            endpoint_url=os.environ.get("AWS_ENDPOINT_URL", "http://127.0.0.1:5050"),
            region=os.environ.get("AWS_DEFAULT_REGION", "ap-southeast-2"),
            raw_bucket=os.environ.get("RAW_BUCKET", "mcb-raw-readings"),
            curated_bucket=os.environ.get("CURATED_BUCKET", "mcb-curated-exports"),
            ingest_queue_name=os.environ.get("INGEST_QUEUE_NAME", "mcb-ingest"),
            dead_letter_queue_name=os.environ.get("DEAD_LETTER_QUEUE_NAME", "mcb-ingest-dlq"),
            batch_max_readings=int(os.environ.get("WORKER_BATCH_MAX_READINGS", "1000")),
            batch_max_seconds=float(os.environ.get("WORKER_BATCH_MAX_SECONDS", "5")),
            visibility_timeout=int(os.environ.get("WORKER_VISIBILITY_TIMEOUT", "30")),
        )
