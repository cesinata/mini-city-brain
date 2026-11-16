from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from services.api.ports import SqsPublisher
from services.common.models import Reading
from services.worker.main import Worker, object_key, parse_message


def make_readings(n: int, day: str = "2026-03-02", site: str = "100") -> list[Reading]:
    start = datetime.fromisoformat(f"{day}T00:15:00+00:00")
    return [
        Reading(
            site_id=site,
            detector_id="1",
            interval_end=start + timedelta(minutes=15 * i),
            volume=i,
            source="synthetic",
        )
        for i in range(n)
    ]


def raw_keys(aws) -> list[str]:
    resp = aws.s3.list_objects_v2(Bucket=aws.settings.raw_bucket)
    return sorted(o["Key"] for o in resp.get("Contents", []))


def queue_count(aws, url: str) -> int:
    attrs = aws.sqs.get_queue_attributes(QueueUrl=url, AttributeNames=["All"])["Attributes"]
    return int(attrs["ApproximateNumberOfMessages"]) + int(
        attrs["ApproximateNumberOfMessagesNotVisible"]
    )


def make_worker(aws, **kw) -> Worker:
    return Worker(aws.settings, aws.sqs, aws.s3, wait_seconds=0, **kw)


def test_publish_consume_write(aws):
    SqsPublisher(aws.settings, aws.sqs).publish(make_readings(5))
    worker = make_worker(aws)
    assert worker.receive() == 1
    assert worker.flush() == 1

    keys = raw_keys(aws)
    assert len(keys) == 1
    assert keys[0].startswith("raw/scats/date=2026-03-02/")
    assert keys[0].endswith(".ndjson")
    body = aws.s3.get_object(Bucket=aws.settings.raw_bucket, Key=keys[0])["Body"].read().decode()
    lines = [json.loads(line) for line in body.strip().split("\n")]
    assert len(lines) == 5
    assert lines[0] == {
        "site_id": "100",
        "detector_id": "1",
        "interval_end": "2026-03-02T00:15:00Z",
        "volume": 0,
        "source": "synthetic",
    }
    assert queue_count(aws, aws.ingest_url) == 0


def test_readings_are_split_by_utc_date(aws):
    pub = SqsPublisher(aws.settings, aws.sqs)
    pub.publish(make_readings(2, "2026-03-02"))
    pub.publish(make_readings(2, "2026-03-03"))
    worker = make_worker(aws)
    worker.receive()
    assert worker.flush() == 2
    keys = raw_keys(aws)
    assert [k.split("/")[2] for k in keys] == ["date=2026-03-02", "date=2026-03-03"]


def test_batching_by_count_waits_until_limit(aws):
    settings = aws.settings
    object.__setattr__(settings, "batch_max_readings", 6)
    pub = SqsPublisher(settings, aws.sqs)
    pub.publish(make_readings(3, site="1"))
    worker = make_worker(aws)
    worker.receive()
    assert worker.flush_due() is False
    pub.publish(make_readings(3, site="2"))
    worker.receive()
    assert worker.flush_due() is True
    worker.flush()
    assert len(raw_keys(aws)) == 1  # two messages, one object


def test_batching_by_time(aws):
    now = [1000.0]
    SqsPublisher(aws.settings, aws.sqs).publish(make_readings(1))
    worker = Worker(aws.settings, aws.sqs, aws.s3, clock=lambda: now[0], wait_seconds=0)
    worker.receive()
    assert worker.flush_due() is False
    now[0] += aws.settings.batch_max_seconds
    assert worker.flush_due() is True


def test_invalid_message_is_not_deleted_and_reaches_dead_letter_queue(aws):
    aws.sqs.send_message(QueueUrl=aws.ingest_url, MessageBody='[{"site_id": "x"}]')
    worker = make_worker(aws)
    # Visibility timeout is 0, so each receive sees the message again. After maxReceiveCount (3)
    # receives the queue moves it to the dead-letter queue. The worker does nothing by hand.
    for _ in range(6):
        worker.receive()
    assert worker._buffer == []
    assert queue_count(aws, aws.dlq_url) == 1
    assert queue_count(aws, aws.ingest_url) == 0
    assert raw_keys(aws) == []


def test_not_json_message_goes_to_dead_letter_queue(aws):
    aws.sqs.send_message(QueueUrl=aws.ingest_url, MessageBody="not json at all")
    worker = make_worker(aws)
    for _ in range(6):
        worker.receive()
    assert queue_count(aws, aws.dlq_url) == 1


def test_good_message_next_to_bad_one_is_still_written(aws):
    aws.sqs.send_message(QueueUrl=aws.ingest_url, MessageBody="{}")
    SqsPublisher(aws.settings, aws.sqs).publish(make_readings(2))
    worker = make_worker(aws)
    worker.receive()
    worker.flush()
    assert len(raw_keys(aws)) == 1


def test_no_message_deleted_when_write_fails(aws):
    SqsPublisher(aws.settings, aws.sqs).publish(make_readings(3))

    class BrokenS3:
        def put_object(self, **_: object) -> None:
            raise OSError("disk full")

    worker = Worker(aws.settings, aws.sqs, BrokenS3(), wait_seconds=0)
    worker.receive()
    assert worker.flush() == 0
    assert raw_keys(aws) == []
    # The message is still on the queue and can be received again.
    assert queue_count(aws, aws.ingest_url) == 1
    retry = make_worker(aws)
    assert retry.receive() == 1
    assert retry.flush() == 1
    assert len(raw_keys(aws)) == 1
    assert queue_count(aws, aws.ingest_url) == 0


def test_parse_message_rejects_empty_and_non_list():
    for bad in ("[]", "{}", '"x"', "null"):
        try:
            parse_message(bad)
        except ValueError:
            continue
        raise AssertionError(f"accepted {bad}")


def test_object_key_layout():
    assert object_key("2026-03-02", "abc") == "raw/scats/date=2026-03-02/abc.ndjson"


def test_interval_end_equal_to_midnight_utc_belongs_to_its_own_date(aws):
    r = Reading(
        site_id="1",
        detector_id="1",
        interval_end=datetime(2026, 3, 3, 0, 0, tzinfo=UTC),
        volume=1,
        source="synthetic",
    )
    SqsPublisher(aws.settings, aws.sqs).publish([r])
    worker = make_worker(aws)
    worker.receive()
    worker.flush()
    assert "date=2026-03-03" in raw_keys(aws)[0]
