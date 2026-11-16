"""boto3 clients for the local AWS emulator.

Every client takes its endpoint from `AWS_ENDPOINT_URL` and uses the dummy credentials
`test` / `test`. There is no path that reads real credentials or a real AWS endpoint.
"""

from __future__ import annotations

from typing import Any

import boto3
from botocore.config import Config

from services.common.config import Settings

DUMMY_KEY = "test"


def _client(service: str, settings: Settings) -> Any:
    return boto3.client(
        service,
        endpoint_url=settings.endpoint_url,
        region_name=settings.region,
        aws_access_key_id=DUMMY_KEY,
        aws_secret_access_key=DUMMY_KEY,
        config=Config(retries={"max_attempts": 2}, connect_timeout=3, read_timeout=25),
    )


def sqs_client(settings: Settings) -> Any:
    return _client("sqs", settings)


def s3_client(settings: Settings) -> Any:
    return _client("s3", settings)


def queue_url(sqs: Any, name: str) -> str:
    return str(sqs.get_queue_url(QueueName=name)["QueueUrl"])
