from __future__ import annotations

import json

from fastapi.testclient import TestClient

from scripts.init_resources import create_resources
from services.api.main import create_app
from services.api.ports import AwsProbe, SqsPublisher
from services.common.config import Settings
from services.worker.main import Worker


def test_boto3_init_creates_buckets_queues_and_redrive(moto_endpoint):
    settings = Settings(
        endpoint_url=moto_endpoint,
        region="ap-southeast-2",
        raw_bucket="init-raw",
        curated_bucket="init-curated",
        ingest_queue_name="init-ingest",
        dead_letter_queue_name="init-dlq",
        batch_max_readings=1000,
        batch_max_seconds=5,
        visibility_timeout=30,
    )
    urls = create_resources(settings)
    from services.common.aws import s3_client, sqs_client

    names = {b["Name"] for b in s3_client(settings).list_buckets()["Buckets"]}
    assert {"init-raw", "init-curated"} <= names
    attrs = sqs_client(settings).get_queue_attributes(
        QueueUrl=urls["ingest_queue_url"], AttributeNames=["RedrivePolicy", "VisibilityTimeout"]
    )["Attributes"]
    assert json.loads(attrs["RedrivePolicy"])["maxReceiveCount"] == 3
    assert attrs["VisibilityTimeout"] == "30"


def test_api_to_queue_to_worker_to_bucket(aws):
    client = TestClient(create_app(SqsPublisher(aws.settings, aws.sqs), AwsProbe(aws.settings)))
    assert client.get("/health").json()["status"] == "ok"

    items = [
        {
            "site_id": "10",
            "detector_id": "1",
            "interval_end": f"2026-03-02T0{h}:00:00+00:00",
            "volume": 5,
            "source": "synthetic",
        }
        for h in range(1, 4)
    ]
    resp = client.post("/v1/readings", json={"readings": items})
    assert resp.status_code == 202
    assert resp.json()["accepted"] == 3

    worker = Worker(aws.settings, aws.sqs, aws.s3, wait_seconds=0)
    worker.receive()
    assert worker.flush() == 1
    keys = [o["Key"] for o in aws.s3.list_objects_v2(Bucket=aws.settings.raw_bucket)["Contents"]]
    assert len(keys) == 1


def test_health_reports_degraded_when_resources_are_missing(moto_endpoint):
    settings = Settings(
        endpoint_url=moto_endpoint,
        region="ap-southeast-2",
        raw_bucket="does-not-exist-bucket",
        curated_bucket="x",
        ingest_queue_name="does-not-exist-queue",
        dead_letter_queue_name="x",
        batch_max_readings=1,
        batch_max_seconds=1,
        visibility_timeout=1,
    )
    from services.api.ports import InMemoryPublisher

    client = TestClient(create_app(InMemoryPublisher(), AwsProbe(settings)))
    assert client.get("/health").json() == {"status": "degraded", "queue": False, "bucket": False}


def test_health_reports_degraded_when_emulator_is_down():
    settings = Settings(
        endpoint_url="http://127.0.0.1:9",
        region="ap-southeast-2",
        raw_bucket="b",
        curated_bucket="c",
        ingest_queue_name="q",
        dead_letter_queue_name="d",
        batch_max_readings=1,
        batch_max_seconds=1,
        visibility_timeout=1,
    )
    from services.api.ports import InMemoryPublisher

    client = TestClient(create_app(InMemoryPublisher(), AwsProbe(settings)))
    body = client.get("/health").json()
    assert body["status"] == "degraded"
