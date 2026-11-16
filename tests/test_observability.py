from __future__ import annotations

import json
import re
from pathlib import Path

import yaml
from fastapi.testclient import TestClient
from prometheus_client import generate_latest

from services.api.main import create_app
from services.api.ports import InMemoryPublisher, StaticProbe
from services.worker import main as _worker  # noqa: F401  (registers the worker metrics)

ROOT = Path(__file__).resolve().parent.parent
DASHBOARD = ROOT / "observability/grafana/dashboards/mcb-overview.json"
EXPECTED_PANELS = {
    "Ingest rate",
    "Rejection rate",
    "Ingest queue depth",
    "Dead-letter queue",
    "API p95 latency",
    "Time since last pipeline success",
}


def test_dashboard_json_has_the_six_panels():
    dash = json.loads(DASHBOARD.read_text())
    titles = {p["title"].split(" (")[0] for p in dash["panels"]}
    assert titles == EXPECTED_PANELS
    assert len({p["id"] for p in dash["panels"]}) == 6


def test_every_metric_in_the_dashboard_is_exposed_by_the_apps():
    dash = json.loads(DASHBOARD.read_text())
    exprs = " ".join(t["expr"] for p in dash["panels"] for t in p["targets"])
    names = set(re.findall(r"mcb_[a-z_]+", exprs))
    client = TestClient(create_app(InMemoryPublisher(), StaticProbe(), pipeline_reader=lambda: 1.0))
    client.get("/health")  # a histogram shows no buckets until it has seen one request
    api = client.get("/metrics").text
    exposed = api + generate_latest().decode()
    for name in names:
        assert name in exposed, f"{name} is in the dashboard but no service exposes it"


def test_prometheus_scrapes_both_services():
    cfg = yaml.safe_load((ROOT / "observability/prometheus.yml").read_text())
    jobs = {j["job_name"]: j["static_configs"][0]["targets"][0] for j in cfg["scrape_configs"]}
    assert jobs == {"api": "api:8000", "worker": "worker:9101"}


def test_compose_obs_profile_and_read_only_anonymous_grafana():
    cfg = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    svc = cfg["services"]
    assert svc["prometheus"]["profiles"] == ["obs"]
    assert svc["grafana"]["profiles"] == ["obs"]
    env = svc["grafana"]["environment"]
    assert env["GF_AUTH_ANONYMOUS_ORG_ROLE"] == "Viewer"
    assert all(p.startswith("127.0.0.1:") for p in svc["grafana"]["ports"])
    assert "profiles" not in svc["api"] and "profiles" not in svc["worker"]
    assert svc["localstack"]["profiles"] == ["localstack"]
