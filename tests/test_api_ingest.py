from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from services.api.main import create_app
from services.api.ports import InMemoryPublisher, StaticProbe
from services.common.models import MAX_BATCH_SIZE, MAX_VOLUME_15MIN


def reading(**overrides):
    base = {
        "site_id": "1234",
        "detector_id": "5",
        "interval_end": "2026-03-02T08:15:00+11:00",
        "volume": 42,
        "source": "synthetic",
    }
    base.update(overrides)
    return base


@pytest.fixture
def publisher() -> InMemoryPublisher:
    return InMemoryPublisher()


@pytest.fixture
def client(publisher: InMemoryPublisher) -> TestClient:
    return TestClient(create_app(publisher, StaticProbe()), raise_server_exceptions=False)


def post(client: TestClient, *items):
    return client.post("/v1/readings", json={"readings": list(items)})


def test_valid_batch_is_accepted_and_published(client, publisher):
    resp = post(client, reading(), reading(detector_id="6"))
    assert resp.status_code == 202
    assert resp.json() == {"accepted": 2, "rejected": 0, "rejections": []}
    assert len(publisher.batches) == 1
    assert len(publisher.batches[0]) == 2


def test_interval_end_is_stored_in_utc(client, publisher):
    post(client, reading())
    assert publisher.batches[0][0].interval_end.isoformat() == "2026-03-01T21:15:00+00:00"


@pytest.mark.parametrize(
    ("overrides", "needle"),
    [
        ({"volume": -1}, "volume"),
        ({"volume": MAX_VOLUME_15MIN + 1}, "volume"),
        ({"volume": 1.5}, "volume"),
        ({"site_id": "12 34"}, "site_id"),
        ({"site_id": ""}, "site_id"),
        ({"site_id": "1234567"}, "site_id"),
        ({"detector_id": "abc"}, "detector_id"),
        ({"detector_id": "1000"}, "detector_id"),
        ({"interval_end": "2026-03-02T08:10:00+11:00"}, "interval_end"),
        ({"interval_end": "2026-03-02T08:15:30+11:00"}, "interval_end"),
        ({"interval_end": "2026-03-02T08:15:00"}, "interval_end"),
        ({"interval_end": "not a date"}, "interval_end"),
        ({"source": "other"}, "source"),
    ],
)
def test_invalid_reading_is_rejected_with_reason(client, publisher, overrides, needle):
    resp = post(client, reading(**overrides))
    assert resp.status_code == 202
    body = resp.json()
    assert body["accepted"] == 0
    assert body["rejected"] == 1
    assert needle in " ".join(body["rejections"][0]["reasons"])
    assert publisher.batches == []


def test_volume_bounds_are_inclusive(client):
    resp = post(client, reading(volume=0), reading(detector_id="6", volume=MAX_VOLUME_15MIN))
    assert resp.json()["accepted"] == 2


def test_unknown_field_is_rejected(client):
    resp = post(client, reading(extra="x"))
    assert resp.json()["rejected"] == 1


def test_rejection_does_not_echo_the_submitted_value(client):
    resp = post(client, reading(site_id="SECRET-VALUE"))
    assert "SECRET-VALUE" not in resp.text


def test_mixed_batch_accepts_good_and_rejects_bad(client, publisher):
    resp = post(client, reading(), reading(volume=-5, detector_id="7"))
    body = resp.json()
    assert (body["accepted"], body["rejected"]) == (1, 1)
    assert body["rejections"][0]["index"] == 1
    assert len(publisher.batches[0]) == 1


def test_batch_of_max_size_is_accepted(client):
    items = [reading(site_id=str(i)) for i in range(MAX_BATCH_SIZE)]
    assert post(client, *items).json()["accepted"] == MAX_BATCH_SIZE


def test_oversized_batch_is_refused(client, publisher):
    items = [reading(site_id=str(i)) for i in range(MAX_BATCH_SIZE + 1)]
    resp = post(client, *items)
    assert resp.status_code == 422
    assert resp.json()["error"] == "invalid_request"
    assert publisher.batches == []


def test_empty_batch_is_refused(client):
    assert client.post("/v1/readings", json={"readings": []}).status_code == 422


def test_malformed_body_is_refused_without_echo(client):
    resp = client.post("/v1/readings", json={"readings": "SECRET-VALUE"})
    assert resp.status_code == 422
    assert "SECRET-VALUE" not in resp.text


def test_duplicate_key_in_one_batch_is_rejected_once(client, publisher):
    same_instant = reading(interval_end="2026-03-01T21:15:00Z")
    resp = post(client, reading(), same_instant)
    body = resp.json()
    assert (body["accepted"], body["rejected"]) == (1, 1)
    assert "duplicate" in body["rejections"][0]["reasons"][0]


def test_same_reading_in_two_requests_is_published_twice_and_left_to_staging(client, publisher):
    # The API is stateless. Cross-request duplicates are removed in dbt (stg_readings). D17.
    post(client, reading())
    post(client, reading())
    assert len(publisher.batches) == 2


def test_health_ok(publisher):
    c = TestClient(create_app(publisher, StaticProbe(True, True)))
    assert c.get("/health").json() == {"status": "ok", "queue": True, "bucket": True}


@pytest.mark.parametrize(("queue", "bucket"), [(False, True), (True, False), (False, False)])
def test_health_degraded(publisher, queue, bucket):
    c = TestClient(create_app(publisher, StaticProbe(queue, bucket)))
    resp = c.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "degraded", "queue": queue, "bucket": bucket}


def test_publish_failure_returns_503_without_exception_text(caplog):
    failing = InMemoryPublisher(fail=True)
    c = TestClient(create_app(failing, StaticProbe()), raise_server_exceptions=False)
    with caplog.at_level(logging.ERROR, logger="mcb.api"):
        resp = post(c, reading())
    assert resp.status_code == 503
    assert "secret detail" not in resp.text
    assert "RuntimeError" not in resp.text
    assert "secret detail" in caplog.text or any(
        "publish failed" in r.message for r in caplog.records
    )


def test_unhandled_error_returns_generic_500_and_logs(caplog):
    class Boom:
        def queue_reachable(self) -> bool:
            raise ValueError("internal detail 12345")

        def bucket_reachable(self) -> bool:
            return True

    c = TestClient(create_app(InMemoryPublisher(), Boom()), raise_server_exceptions=False)
    with caplog.at_level(logging.ERROR, logger="mcb.api"):
        resp = c.get("/health")
    assert resp.status_code == 500
    assert resp.json() == {"error": "internal_error", "detail": []}
    assert "12345" not in resp.text
    assert any("unhandled error" in r.message for r in caplog.records)
