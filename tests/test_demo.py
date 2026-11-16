from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from scripts import demo_bad
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

    code = demo_bad.main(client=in_process_client(api), wait=0, after_post=run_worker)
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
