from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from scripts import demo_bad, smoke_assert
from services.api.main import create_app
from services.api.ports import AwsProbe, SqsPublisher
from services.worker.main import Worker

ROOT = Path(__file__).resolve().parent.parent


def in_process_client(api: TestClient) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        r = api.post("/v1/readings", content=request.content, headers=dict(request.headers))
        return httpx.Response(r.status_code, json=r.json())

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_faulty_batch_has_the_three_faults():
    batch = demo_bad.faulty_readings()
    assert sum(1 for r in batch if r["volume"] < 0) == 1
    normal = [r for r in batch if r["detector_id"] == "1"]
    assert len(normal) == 96 - 20  # a gap of 20 intervals
    assert {r["site_id"] for r in batch} == {demo_bad.SITE}


def test_demo_bad_exits_non_zero_and_names_the_failed_check(aws, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("AWS_ENDPOINT_URL", aws.settings.endpoint_url)
    monkeypatch.setenv("RAW_BUCKET", aws.settings.raw_bucket)
    monkeypatch.setenv("INGEST_QUEUE_NAME", aws.settings.ingest_queue_name)
    monkeypatch.setenv("DEAD_LETTER_QUEUE_NAME", aws.settings.dead_letter_queue_name)
    monkeypatch.setenv("DEMO_BAD_DB", str(tmp_path / "bad.duckdb"))
    monkeypatch.setenv("DBT_TARGET_PATH", str(tmp_path / "dbt"))
    api = TestClient(create_app(SqsPublisher(aws.settings, aws.sqs), AwsProbe(aws.settings)))

    def run_worker() -> None:
        worker = Worker(aws.settings, aws.sqs, aws.s3, wait_seconds=0)
        worker.receive()
        worker.flush()

    code = demo_bad.main(client=in_process_client(api), wait=5, after_post=run_worker)
    out = capsys.readouterr().out
    assert code != 0
    # The API rejected the negative value and said why.
    assert "rejected 1" in out and "volume" in out
    # The duplicate send reached the bucket, so the duplicate-rate check fails, readably.
    assert "PIPELINE FAILED" in out
    assert "check: duplicate_rate" in out
    assert "asset: raw_objects_loaded" in out
    assert "repeat a key" in out
    assert json.loads(out.strip().splitlines()[-1])["exit"] == code


@pytest.mark.skipif(shutil.which("docker") is not None, reason="only meaningful without Docker")
@pytest.mark.parametrize("script", ["scripts/demo.sh", "scripts/demo_bad.sh"])
def test_scripts_refuse_cleanly_without_docker(script):
    done = subprocess.run(["bash", script], cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert done.returncode == 2
    assert "Docker is not available" in done.stderr


# ---- waiting for the worker (decisions D36) -------------------------------------------------


def _put_ndjson(aws, key: str, lines: int) -> None:
    body = "".join(json.dumps({"n": i}) + "\n" for i in range(lines))
    aws.s3.put_object(Bucket=aws.settings.raw_bucket, Key=key, Body=body.encode())


def test_raw_reading_count_sums_lines_over_all_objects(aws):
    assert smoke_assert.raw_reading_count(aws.s3, aws.settings.raw_bucket) == 0
    _put_ndjson(aws, "raw/scats/date=2026-03-01/a.ndjson", 3)
    _put_ndjson(aws, "raw/scats/date=2026-03-02/b.ndjson", 4)
    _put_ndjson(aws, "other/c.ndjson", 10)  # outside raw/scats/: not counted
    assert smoke_assert.raw_reading_count(aws.s3, aws.settings.raw_bucket) == 7


def test_check_fails_until_every_expected_reading_is_in_the_bucket(aws):
    _put_ndjson(aws, "raw/scats/date=2026-03-01/a.ndjson", 1000)
    problems = smoke_assert.check(aws.settings, aws.s3, aws.sqs, expect_readings=1920)
    assert problems == ["raw bucket holds 1000 readings, expected at least 1920"]
    _put_ndjson(aws, "raw/scats/date=2026-03-02/b.ndjson", 920)
    assert smoke_assert.check(aws.settings, aws.s3, aws.sqs, expect_readings=1920) == []
    # Without an expected count, one object is enough (the CI smoke test's behaviour).
    assert smoke_assert.check(aws.settings, aws.s3, aws.sqs) == []


def test_wait_for_readings_returns_the_count_after_the_deadline(aws):
    _put_ndjson(aws, "raw/scats/date=2026-03-01/a.ndjson", 5)
    got = smoke_assert.wait_for_readings(aws.settings, 10, wait=0, s3=aws.s3)
    assert got == 5
    assert smoke_assert.wait_for_readings(aws.settings, 5, wait=0, s3=aws.s3) == 5
