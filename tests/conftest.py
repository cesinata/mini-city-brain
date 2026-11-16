"""Shared fixtures. The AWS emulator is Moto's in-process server: no Docker needed."""

from __future__ import annotations

import json
import socket
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import pytest
from moto.server import ThreadedMotoServer

from services.common.aws import s3_client, sqs_client
from services.common.config import Settings


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture(scope="session")
def moto_endpoint() -> Iterator[str]:
    port = _free_port()
    server = ThreadedMotoServer(ip_address="127.0.0.1", port=port, verbose=False)
    server.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.stop()


@dataclass
class Aws:
    settings: Settings
    sqs: Any
    s3: Any
    ingest_url: str
    dlq_url: str


@pytest.fixture
def aws(moto_endpoint: str, request: pytest.FixtureRequest) -> Aws:
    """Fresh bucket and queues per test, named after the test so tests do not share state."""
    suffix = "".join(c for c in request.node.name.lower() if c.isalnum())[:30]
    settings = Settings(
        endpoint_url=moto_endpoint,
        region="ap-southeast-2",
        raw_bucket=f"raw-{suffix}",
        curated_bucket=f"curated-{suffix}",
        ingest_queue_name=f"ingest-{suffix}",
        dead_letter_queue_name=f"dlq-{suffix}",
        batch_max_readings=1000,
        batch_max_seconds=5,
        visibility_timeout=0,
    )
    sqs = sqs_client(settings)
    s3 = s3_client(settings)
    s3.create_bucket(
        Bucket=settings.raw_bucket,
        CreateBucketConfiguration={"LocationConstraint": settings.region},
    )
    dlq_url = sqs.create_queue(QueueName=settings.dead_letter_queue_name)["QueueUrl"]
    dlq_arn = sqs.get_queue_attributes(QueueUrl=dlq_url, AttributeNames=["QueueArn"])["Attributes"][
        "QueueArn"
    ]
    ingest_url = sqs.create_queue(
        QueueName=settings.ingest_queue_name,
        Attributes={
            "VisibilityTimeout": "0",
            "RedrivePolicy": json.dumps({"deadLetterTargetArn": dlq_arn, "maxReceiveCount": 3}),
        },
    )["QueueUrl"]
    return Aws(settings, sqs, s3, ingest_url, dlq_url)
