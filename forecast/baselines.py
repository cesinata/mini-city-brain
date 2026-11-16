"""Two baseline forecasts for 15-minute volume at one site.

seasonal naive : the volume in the same interval one week earlier.
trailing mean  : the mean volume in the same interval over the previous 4 weeks.

Both only look backwards from the interval being predicted. Missing history gives `None`.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta

WEEK = timedelta(days=7)
STEP = timedelta(minutes=15)
MAX_HORIZON_STEPS = 7 * 96  # one week ahead, so the seasonal lag is always in observed history

Series = Mapping[datetime, float]


def seasonal_naive(series: Series, target: datetime) -> float | None:
    return series.get(target - WEEK)


def trailing_mean(series: Series, target: datetime, weeks: int = 4) -> float | None:
    values = [series[t] for k in range(1, weeks + 1) if (t := target - k * WEEK) in series]
    if not values:
        return None
    return sum(values) / len(values)


METHODS = {"seasonal_naive": seasonal_naive, "trailing_mean_4w": trailing_mean}


def forecast_steps(series: Series, last_observed: datetime, horizon: int) -> list[dict]:
    """Forecast `horizon` 15-minute steps after `last_observed` with both methods."""
    points = []
    for step in range(1, horizon + 1):
        target = last_observed + step * STEP
        points.append(
            {
                "interval_end": target,
                "seasonal_naive": seasonal_naive(series, target),
                "trailing_mean_4w": trailing_mean(series, target),
            }
        )
    return points
