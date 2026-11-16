"""Request and response models for the API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from services.common.models import MAX_BATCH_SIZE


class ReadingBatch(BaseModel):
    """Raw items are validated one by one, so one bad reading does not reject the batch."""

    readings: list[dict[str, Any]] = Field(min_length=1, max_length=MAX_BATCH_SIZE)


class Rejection(BaseModel):
    index: int
    reasons: list[str]


class IngestResponse(BaseModel):
    accepted: int
    rejected: int
    rejections: list[Rejection]


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    queue: bool
    bucket: bool


class ErrorResponse(BaseModel):
    error: str
    detail: list[str] = []


class ForecastPoint(BaseModel):
    interval_end: datetime
    seasonal_naive: float | None
    trailing_mean_4w: float | None


class ForecastResponse(BaseModel):
    site_id: str
    horizon: int
    last_observed: datetime
    data_source: str
    points: list[ForecastPoint]
