"""Prometheus metrics for the API. Each app gets its own registry, so tests do not clash."""

from __future__ import annotations

import time
from collections.abc import Callable

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest
from prometheus_client.core import GaugeMetricFamily

LATENCY_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10)


class _PipelineCollector:
    """Reads the last successful pipeline run at scrape time. 0 means none recorded."""

    def __init__(self, reader: Callable[[], float | None]) -> None:
        self._reader = reader

    def collect(self):
        try:
            value = self._reader()
        except Exception:
            value = None
        gauge = GaugeMetricFamily(
            "mcb_pipeline_last_success_timestamp_seconds",
            "Unix time of the last fully successful pipeline run (0 = none recorded)",
        )
        gauge.add_metric([], value or 0.0)
        yield gauge


class ApiMetrics:
    def __init__(self, pipeline_reader: Callable[[], float | None] | None = None) -> None:
        self.registry = CollectorRegistry()
        self.requests = Counter(
            "mcb_api_requests_total",
            "HTTP requests by route and status",
            ["method", "route", "status"],
            registry=self.registry,
        )
        self.latency = Histogram(
            "mcb_api_request_duration_seconds",
            "HTTP request latency by route",
            ["method", "route"],
            buckets=LATENCY_BUCKETS,
            registry=self.registry,
        )
        self.accepted = Counter(
            "mcb_api_readings_accepted_total", "Readings accepted", registry=self.registry
        )
        self.rejected = Counter(
            "mcb_api_readings_rejected_total", "Readings rejected", registry=self.registry
        )
        self.up = Gauge("mcb_api_up", "1 while the API process is running", registry=self.registry)
        self.up.set(1)
        if pipeline_reader is not None:
            self.registry.register(_PipelineCollector(pipeline_reader))

    def observe(self, method: str, route: str, status: int, started: float) -> None:
        self.requests.labels(method, route, str(status)).inc()
        self.latency.labels(method, route).observe(time.perf_counter() - started)

    def render(self) -> bytes:
        return generate_latest(self.registry)
