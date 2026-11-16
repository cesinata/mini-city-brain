"""Baseline forecast for one site, read from the DuckDB marts."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Protocol

import duckdb

from forecast import baselines, store


class WarehouseUnavailable(RuntimeError):  # noqa: N818
    """The warehouse file is missing, locked or has no marts yet."""


class ForecastProvider(Protocol):
    def forecast(self, site_id: str, horizon: int) -> dict | None:
        """Return a forecast dict, or None when the site has no data."""


class DuckDbForecastProvider:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    def forecast(self, site_id: str, horizon: int) -> dict | None:
        if not Path(self._db_path).exists():
            raise WarehouseUnavailable("warehouse file not found")
        try:
            con = duckdb.connect(self._db_path, read_only=True)
        except duckdb.Error as exc:
            raise WarehouseUnavailable("cannot open warehouse") from exc
        try:
            series, latest = store.load_recent_series(con, site_id)
            sources = con.execute(
                "select distinct source from main.fct_volume_15min where site_id = ?", [site_id]
            ).fetchall()
        except duckdb.Error as exc:
            raise WarehouseUnavailable("marts not built") from exc
        finally:
            con.close()
        if latest is None:
            return None
        names = sorted(s[0] for s in sources)
        return {
            "site_id": site_id,
            "horizon": horizon,
            "last_observed": _utc(latest),
            "data_source": names[0] if len(names) == 1 else "mixed",
            "points": [
                {**p, "interval_end": _utc(p["interval_end"])}
                for p in baselines.forecast_steps(series, latest, horizon)
            ],
        }


def _utc(value: datetime) -> datetime:
    from datetime import UTC

    return value.replace(tzinfo=UTC)
