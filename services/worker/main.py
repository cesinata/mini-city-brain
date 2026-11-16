"""Queue consumer.

Long-polls the ingest queue, re-validates every reading, batches by count or time and writes
newline-delimited JSON to `raw/scats/date=YYYY-MM-DD/<batch-id>.ndjson`. A message is deleted
only after every object for its batch is written. A message that fails validation, or whose
batch fails to write, is left on the queue. The queue's redrive policy moves it to the
dead-letter queue after `maxReceiveCount` receives. The worker never writes to the dead-letter
queue itself.
"""

from __future__ import annotations

import json
import logging
import signal
import time
import uuid
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from prometheus_client import Counter, Gauge, start_http_server
from pydantic import TypeAdapter, ValidationError

from services.common.aws import queue_url, s3_client, sqs_client
from services.common.config import Settings
from services.common.logging import configure_logging
from services.common.models import Reading

log = logging.getLogger("mcb.worker")

MESSAGES_PROCESSED = Counter("mcb_worker_messages_processed_total", "Messages written and deleted")
MESSAGES_REJECTED = Counter(
    "mcb_worker_messages_invalid_total", "Messages left on the queue because they failed validation"
)
BATCHES_WRITTEN = Counter("mcb_worker_batches_written_total", "Objects written to the raw bucket")
READINGS_WRITTEN = Counter(
    "mcb_worker_readings_written_total", "Readings written to the raw bucket"
)
WRITE_FAILURES = Counter("mcb_worker_write_failures_total", "Failed batch writes")
DEAD_LETTER_DEPTH = Gauge(
    "mcb_worker_dead_letter_messages", "Messages in the dead-letter queue (queue attribute)"
)
INGEST_DEPTH = Gauge("mcb_worker_ingest_queue_messages", "Messages waiting in the ingest queue")

_readings_adapter = TypeAdapter(list[Reading])


def parse_message(body: str) -> list[Reading]:
    """Raises ValueError or ValidationError when the body is not a list of valid readings."""
    data = json.loads(body)
    if not isinstance(data, list) or not data:
        raise ValueError("message body must be a non-empty JSON list")
    return _readings_adapter.validate_python(data)


def object_key(date: str, batch_id: str) -> str:
    return f"raw/scats/date={date}/{batch_id}.ndjson"


@dataclass
class _Buffered:
    message: dict[str, Any]
    readings: list[Reading]


@dataclass
class Worker:
    settings: Settings
    sqs: Any
    s3: Any
    clock: Callable[[], float] = time.monotonic
    wait_seconds: int = 1
    ingest_url: str = ""
    dlq_url: str = ""
    _buffer: list[_Buffered] = field(default_factory=list)
    _first_at: float | None = None

    def __post_init__(self) -> None:
        if not self.ingest_url:
            self.ingest_url = queue_url(self.sqs, self.settings.ingest_queue_name)
        if not self.dlq_url:
            self.dlq_url = queue_url(self.sqs, self.settings.dead_letter_queue_name)

    @property
    def buffered_readings(self) -> int:
        return sum(len(b.readings) for b in self._buffer)

    def receive(self) -> int:
        """One long-poll. Returns the number of valid messages added to the buffer."""
        resp = self.sqs.receive_message(
            QueueUrl=self.ingest_url,
            MaxNumberOfMessages=10,
            WaitTimeSeconds=self.wait_seconds,
        )
        added = 0
        for msg in resp.get("Messages", []):
            try:
                readings = parse_message(msg["Body"])
            except (ValueError, ValidationError) as exc:
                MESSAGES_REJECTED.inc()
                log.warning(
                    "invalid message left on queue",
                    extra={"message_id": msg.get("MessageId"), "error_type": type(exc).__name__},
                )
                continue
            if self._first_at is None:
                self._first_at = self.clock()
            self._buffer.append(_Buffered(msg, readings))
            added += 1
        return added

    def flush_due(self) -> bool:
        if not self._buffer:
            return False
        too_many = self.buffered_readings >= self.settings.batch_max_readings
        too_old = (
            self._first_at is not None
            and self.clock() - self._first_at >= self.settings.batch_max_seconds
        )
        return too_many or too_old

    def flush(self) -> int:
        """Write buffered readings, then delete their messages. Returns objects written."""
        if not self._buffer:
            return 0
        buffered, self._buffer, self._first_at = self._buffer, [], None
        by_date: dict[str, list[Reading]] = defaultdict(list)
        for item in buffered:
            for reading in item.readings:
                by_date[reading.interval_end.strftime("%Y-%m-%d")].append(reading)
        written = 0
        try:
            for date, readings in sorted(by_date.items()):
                body = "\n".join(
                    json.dumps(r.to_json_dict(), separators=(",", ":")) for r in readings
                )
                key = object_key(date, uuid.uuid4().hex)
                self.s3.put_object(
                    Bucket=self.settings.raw_bucket,
                    Key=key,
                    Body=(body + "\n").encode(),
                    ContentType="application/x-ndjson",
                )
                written += 1
                BATCHES_WRITTEN.inc()
                READINGS_WRITTEN.inc(len(readings))
        except Exception as exc:
            WRITE_FAILURES.inc()
            log.error(
                "batch write failed; messages stay on the queue",
                extra={"messages": len(buffered), "error_type": type(exc).__name__},
                exc_info=exc,
            )
            return written
        self._delete([b.message for b in buffered])
        MESSAGES_PROCESSED.inc(len(buffered))
        log.info(
            "batch written",
            extra={"objects": written, "messages": len(buffered)},
        )
        return written

    def _delete(self, messages: list[dict[str, Any]]) -> None:
        for start in range(0, len(messages), 10):
            chunk = messages[start : start + 10]
            self.sqs.delete_message_batch(
                QueueUrl=self.ingest_url,
                Entries=[
                    {"Id": str(i), "ReceiptHandle": m["ReceiptHandle"]} for i, m in enumerate(chunk)
                ],
            )

    def update_queue_gauges(self) -> None:
        try:
            for url, gauge in ((self.dlq_url, DEAD_LETTER_DEPTH), (self.ingest_url, INGEST_DEPTH)):
                attrs = self.sqs.get_queue_attributes(
                    QueueUrl=url, AttributeNames=["ApproximateNumberOfMessages"]
                )["Attributes"]
                gauge.set(int(attrs["ApproximateNumberOfMessages"]))
        except Exception as exc:
            log.warning("queue gauge update failed", extra={"error_type": type(exc).__name__})

    def step(self) -> None:
        """One loop iteration: receive, flush if due, refresh gauges."""
        self.receive()
        if self.flush_due():
            self.flush()
        self.update_queue_gauges()


def run() -> None:
    configure_logging()
    settings = Settings.from_env()
    start_http_server(9101)
    stop = False

    def _stop(*_: object) -> None:
        nonlocal stop
        stop = True

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    worker: Worker | None = None
    while not stop:
        try:
            if worker is None:
                worker = Worker(settings, sqs_client(settings), s3_client(settings), wait_seconds=5)
                log.info("worker started")
            worker.step()
        except Exception as exc:
            # Queue not created yet, emulator restarting, and so on: wait and try again.
            log.warning("worker loop error", extra={"error_type": type(exc).__name__})
            time.sleep(2)
    if worker is not None:
        worker.flush()
    log.info("worker stopped")


if __name__ == "__main__":
    run()
