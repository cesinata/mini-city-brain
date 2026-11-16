"""The two things the API needs from the outside world, and their implementations."""

from __future__ import annotations

import json
from typing import Any, Protocol

from services.common.aws import queue_url, s3_client, sqs_client
from services.common.config import Settings
from services.common.models import Reading


class ReadingPublisher(Protocol):
    def publish(self, readings: list[Reading]) -> None: ...


class HealthProbe(Protocol):
    def queue_reachable(self) -> bool: ...

    def bucket_reachable(self) -> bool: ...


class InMemoryPublisher:
    """Test double. Keeps every published batch."""

    def __init__(self, fail: bool = False) -> None:
        self.batches: list[list[Reading]] = []
        self.fail = fail

    def publish(self, readings: list[Reading]) -> None:
        if self.fail:
            raise RuntimeError("simulated publish failure with a secret detail")
        self.batches.append(list(readings))


class StaticProbe:
    """Test double for health checks."""

    def __init__(self, queue: bool = True, bucket: bool = True) -> None:
        self._queue = queue
        self._bucket = bucket

    def queue_reachable(self) -> bool:
        return self._queue

    def bucket_reachable(self) -> bool:
        return self._bucket


class SqsPublisher:
    """Sends one SQS message per accepted request. The body is a JSON list of readings."""

    def __init__(self, settings: Settings, sqs: Any | None = None) -> None:
        self._sqs = sqs or sqs_client(settings)
        self._url = queue_url(self._sqs, settings.ingest_queue_name)

    def publish(self, readings: list[Reading]) -> None:
        body = json.dumps([r.to_json_dict() for r in readings], separators=(",", ":"))
        self._sqs.send_message(QueueUrl=self._url, MessageBody=body)


class AwsProbe:
    """Checks that the queue and the raw bucket answer on the emulator."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._sqs = sqs_client(settings)
        self._s3 = s3_client(settings)

    def queue_reachable(self) -> bool:
        try:
            url = queue_url(self._sqs, self._settings.ingest_queue_name)
            self._sqs.get_queue_attributes(QueueUrl=url, AttributeNames=["QueueArn"])
        except Exception:
            return False
        return True

    def bucket_reachable(self) -> bool:
        try:
            self._s3.head_bucket(Bucket=self._settings.raw_bucket)
        except Exception:
            return False
        return True
