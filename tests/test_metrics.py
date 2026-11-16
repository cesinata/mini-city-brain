from __future__ import annotations

from datetime import UTC, datetime

import duckdb
from fastapi.testclient import TestClient
from prometheus_client import generate_latest

from services.api.main import create_app
from services.api.pipeline_status import read_last_success
from services.api.ports import InMemoryPublisher, StaticProbe
from services.worker import main as worker_main

API_METRICS = [
    "mcb_api_requests_total",
    "mcb_api_request_duration_seconds_bucket",
    "mcb_api_readings_accepted_total",
    "mcb_api_readings_rejected_total",
    "mcb_pipeline_last_success_timestamp_seconds",
]
WORKER_METRICS = [
    "mcb_worker_messages_processed_total",
    "mcb_worker_batches_written_total",
    "mcb_worker_write_failures_total",
    "mcb_worker_dead_letter_messages",
    "mcb_worker_ingest_queue_messages",
]


def reading(**kw):
    base = {
        "site_id": "1",
        "detector_id": "1",
        "interval_end": "2026-03-02T00:15:00Z",
        "volume": 3,
        "source": "synthetic",
    }
    return {**base, **kw}


def client(reader=lambda: 1_700_000_000.0) -> TestClient:
    return TestClient(create_app(InMemoryPublisher(), StaticProbe(), pipeline_reader=reader))


def value(text: str, name: str, labels: str = "") -> float:
    for line in text.splitlines():
        if line.startswith(name + labels):
            return float(line.rsplit(" ", 1)[1])
    raise AssertionError(f"{name}{labels} not found")


def test_metrics_endpoint_exposes_the_named_api_metrics():
    c = client()
    c.post("/v1/readings", json={"readings": [reading()]})
    text = c.get("/metrics").text
    for name in API_METRICS:
        assert name in text, name


def test_request_counts_use_route_templates_and_status():
    c = client()
    c.post("/v1/readings", json={"readings": [reading()]})
    c.post("/v1/readings", json={"readings": []})  # 422
    c.get("/health")
    text = c.get("/metrics").text
    assert 'mcb_api_requests_total{method="POST",route="/v1/readings",status="202"} 1.0' in text
    assert 'mcb_api_requests_total{method="POST",route="/v1/readings",status="422"} 1.0' in text
    assert 'mcb_api_requests_total{method="GET",route="/health",status="200"} 1.0' in text


def test_unknown_paths_share_one_label():
    c = client()
    for i in range(5):
        c.get(f"/nothing-{i}")
    text = c.get("/metrics").text
    assert 'route="unmatched",status="404"} 5.0' in text
    assert "nothing-" not in text


def test_accepted_and_rejected_counters():
    c = client()
    c.post("/v1/readings", json={"readings": [reading(), reading(volume=-1, detector_id="2")]})
    text = c.get("/metrics").text
    assert value(text, "mcb_api_readings_accepted_total") == 1.0
    assert value(text, "mcb_api_readings_rejected_total") == 1.0


def test_latency_histogram_counts_requests():
    c = client()
    c.get("/health")
    text = c.get("/metrics").text
    assert (
        value(text, "mcb_api_request_duration_seconds_count", '{method="GET",route="/health"}')
        == 1.0
    )


def test_pipeline_gauge_reports_reader_value_and_zero_when_missing():
    assert (
        value(client(lambda: 1_700_000_000.0).get("/metrics").text, API_METRICS[-1])
        == 1_700_000_000.0
    )
    assert value(client(lambda: None).get("/metrics").text, API_METRICS[-1]) == 0.0

    def broken():
        raise OSError("db locked")

    assert value(client(broken).get("/metrics").text, API_METRICS[-1]) == 0.0


def test_read_last_success_from_duckdb(tmp_path):
    db = tmp_path / "w.duckdb"
    assert read_last_success(str(db)) is None  # no file
    con = duckdb.connect(str(db))
    assert con is not None
    con.close()
    assert read_last_success(str(db)) is None  # no ops table
    con = duckdb.connect(str(db))
    con.execute("create schema ops")
    con.execute("create table ops.pipeline_runs (finished_at timestamp, status varchar)")
    con.execute("insert into ops.pipeline_runs values ('2026-03-02 10:00:00', 'success')")
    con.execute("insert into ops.pipeline_runs values ('2026-03-03 10:00:00', 'failed')")
    con.close()
    expected = datetime(2026, 3, 2, 10, 0, tzinfo=UTC).timestamp()
    assert read_last_success(str(db)) == expected


def test_worker_exposes_the_named_metrics():
    text = generate_latest().decode()
    for name in WORKER_METRICS:
        assert name in text, name
    assert worker_main.DEAD_LETTER_DEPTH is not None
