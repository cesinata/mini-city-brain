"""The reading model shared by the API, the worker and the ingest tools."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

# A 15-minute volume above this is rejected. See docs/decisions.md D16.
MAX_VOLUME_15MIN = 2000
MAX_BATCH_SIZE = 500

SiteId = Annotated[str, StringConstraints(pattern=r"^[0-9]{1,6}$")]
DetectorId = Annotated[str, StringConstraints(pattern=r"^[0-9]{1,3}$")]


def _check_aware_and_aligned(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("must include a timezone offset")
    as_utc = value.astimezone(UTC)
    if as_utc.minute % 15 != 0 or as_utc.second != 0 or as_utc.microsecond != 0:
        raise ValueError("must be on a 15-minute boundary")
    return as_utc


IntervalEnd = Annotated[datetime, AfterValidator(_check_aware_and_aligned)]


class Reading(BaseModel):
    """One 15-minute vehicle count for one detector. `interval_end` is stored in UTC."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    site_id: SiteId
    detector_id: DetectorId
    interval_end: IntervalEnd
    volume: Annotated[int, Field(ge=0, le=MAX_VOLUME_15MIN)]
    source: Literal["scats", "synthetic"]

    @property
    def key(self) -> tuple[str, str, str]:
        """Idempotency key: site, detector and interval end."""
        return (self.site_id, self.detector_id, self.interval_end.isoformat())

    def to_json_dict(self) -> dict[str, str | int]:
        return {
            "site_id": self.site_id,
            "detector_id": self.detector_id,
            "interval_end": self.interval_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "volume": self.volume,
            "source": self.source,
        }
