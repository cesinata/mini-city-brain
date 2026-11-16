"""FastAPI ingestion app.

`create_app` takes its publisher and health probe as arguments so tests can use fakes.
`app` at the bottom builds the real ones lazily from environment variables.
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable
from typing import Annotated, Any

from fastapi import FastAPI, Path, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from pydantic import TypeAdapter, ValidationError

from forecast.baselines import MAX_HORIZON_STEPS
from services.api.forecast_provider import ForecastProvider, WarehouseUnavailable
from services.api.metrics import ApiMetrics
from services.api.ports import HealthProbe, ReadingPublisher
from services.api.schemas import (
    ErrorResponse,
    ForecastResponse,
    HealthResponse,
    IngestResponse,
    ReadingBatch,
    Rejection,
)
from services.common.models import Reading

log = logging.getLogger("mcb.api")
_reading_adapter = TypeAdapter(Reading)


def _reasons(exc: ValidationError) -> list[str]:
    """Readable reasons that never echo the submitted value."""
    out = []
    for err in exc.errors(include_input=False, include_url=False, include_context=False):
        field = ".".join(str(p) for p in err["loc"]) or "reading"
        out.append(f"{field}: {err['msg']}")
    return out


def validate_batch(items: list[dict[str, Any]]) -> tuple[list[Reading], list[Rejection]]:
    """Validate each item. A repeat of an earlier key in the same batch is rejected."""
    accepted: list[Reading] = []
    rejections: list[Rejection] = []
    seen: set[tuple[str, str, str]] = set()
    for index, item in enumerate(items):
        try:
            reading = _reading_adapter.validate_python(item)
        except ValidationError as exc:
            rejections.append(Rejection(index=index, reasons=_reasons(exc)))
            continue
        if reading.key in seen:
            rejections.append(
                Rejection(index=index, reasons=["duplicate: key already seen in this batch"])
            )
            continue
        seen.add(reading.key)
        accepted.append(reading)
    return accepted, rejections


def create_app(
    publisher: ReadingPublisher,
    probe: HealthProbe,
    pipeline_reader: Callable[[], float | None] | None = None,
    forecast_provider: ForecastProvider | None = None,
) -> FastAPI:
    app = FastAPI(title="mini-city-brain ingestion API", version="0.2.0")
    metrics = ApiMetrics(pipeline_reader)

    @app.middleware("http")
    async def _measure(request: Request, call_next: Callable) -> Response:
        started = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            route = request.scope.get("route")
            # Unknown paths share one label so a scanner cannot create endless label values.
            path = getattr(route, "path", None) or "unmatched"
            metrics.observe(request.method, path, status, started)

    @app.exception_handler(RequestValidationError)
    async def _bad_request(_: Request, exc: RequestValidationError) -> JSONResponse:
        detail = [
            f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}"  # loc and msg only, never input
            for e in exc.errors()
        ]
        body = ErrorResponse(error="invalid_request", detail=detail)
        return JSONResponse(status_code=422, content=body.model_dump())

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception) -> JSONResponse:
        log.error(
            "unhandled error",
            exc_info=exc,
            extra={"path": request.url.path, "method": request.method},
        )
        body = ErrorResponse(error="internal_error")
        return JSONResponse(status_code=500, content=body.model_dump())

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        queue = bool(probe.queue_reachable())
        bucket = bool(probe.bucket_reachable())
        return HealthResponse(
            status="ok" if queue and bucket else "degraded", queue=queue, bucket=bucket
        )

    @app.get("/v1/sites/{site_id}/forecast", response_model=ForecastResponse)
    def site_forecast(
        site_id: Annotated[str, Path(pattern=r"^[0-9]{1,6}$")],
        horizon: Annotated[
            int, Query(ge=1, le=MAX_HORIZON_STEPS, description="15-minute steps ahead")
        ] = 96,
    ) -> ForecastResponse | JSONResponse:
        """Two baseline forecasts (seasonal naive and 4-week trailing mean). Not a trained model."""
        if forecast_provider is None:
            return JSONResponse(
                status_code=503, content=ErrorResponse(error="warehouse_unavailable").model_dump()
            )
        try:
            result = forecast_provider.forecast(site_id, horizon)
        except WarehouseUnavailable as exc:
            log.warning("forecast unavailable", extra={"reason": str(exc)})
            return JSONResponse(
                status_code=503, content=ErrorResponse(error="warehouse_unavailable").model_dump()
            )
        if result is None:
            return JSONResponse(
                status_code=404, content=ErrorResponse(error="site_not_found").model_dump()
            )
        return ForecastResponse(**result)

    @app.get("/metrics", include_in_schema=False)
    def prometheus_metrics() -> Response:
        return Response(metrics.render(), media_type="text/plain; version=0.0.4")

    @app.post("/v1/readings", status_code=202, response_model=IngestResponse)
    def ingest(batch: ReadingBatch) -> IngestResponse | JSONResponse:
        accepted, rejections = validate_batch(batch.readings)
        if accepted:
            try:
                publisher.publish(accepted)
            except Exception as exc:
                log.error("publish failed", exc_info=exc, extra={"readings": len(accepted)})
                body = ErrorResponse(error="queue_unavailable")
                return JSONResponse(status_code=503, content=body.model_dump())
        metrics.accepted.inc(len(accepted))
        metrics.rejected.inc(len(rejections))
        log.info(
            "batch handled",
            extra={"accepted": len(accepted), "rejected": len(rejections)},
        )
        return IngestResponse(
            accepted=len(accepted), rejected=len(rejections), rejections=rejections
        )

    return app


def build_default_app() -> FastAPI:
    from services.api.forecast_provider import DuckDbForecastProvider
    from services.api.pipeline_status import read_last_success
    from services.api.ports import AwsProbe, SqsPublisher
    from services.common.config import Settings
    from services.common.logging import configure_logging

    configure_logging()
    settings = Settings.from_env()
    db_path = os.environ.get("DUCKDB_PATH", "data/warehouse/mcb.duckdb")
    return create_app(
        _LazyPublisher(settings, SqsPublisher),
        AwsProbe(settings),
        pipeline_reader=lambda: read_last_success(db_path),
        forecast_provider=DuckDbForecastProvider(db_path),
    )


class _LazyPublisher:
    """Builds the SQS publisher on first use so the API can start before the queue exists."""

    def __init__(self, settings: Any, factory: Any) -> None:
        self._settings = settings
        self._factory = factory
        self._inner: ReadingPublisher | None = None

    def publish(self, readings: list[Reading]) -> None:
        if self._inner is None:
            self._inner = self._factory(self._settings)
        self._inner.publish(readings)
