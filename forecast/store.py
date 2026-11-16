"""Read per-site 15-minute series from the DuckDB marts."""

from __future__ import annotations

from datetime import datetime, timedelta

import duckdb

SERIES_SQL = """
    select site_id, interval_end, sum(volume)::double as volume
    from main.fct_volume_15min
    {where}
    group by 1, 2
    order by 1, 2
"""


def load_series(con: duckdb.DuckDBPyConnection, site_id: str | None = None):
    """Return {site_id: {interval_end: volume}}. Volume is summed over the site's detectors."""
    where = "where site_id = ?" if site_id else ""
    rows = con.execute(SERIES_SQL.format(where=where), [site_id] if site_id else []).fetchall()
    out: dict[str, dict[datetime, float]] = {}
    for site, end, volume in rows:
        out.setdefault(site, {})[end] = volume
    return out


def load_recent_series(con: duckdb.DuckDBPyConnection, site_id: str, days: int = 29):
    """The last `days` days of one site's series, counted back from its newest interval."""
    latest = con.execute(
        "select max(interval_end) from main.fct_volume_15min where site_id = ?", [site_id]
    ).fetchone()[0]
    if latest is None:
        return {}, None
    since = latest - timedelta(days=days)
    rows = con.execute(
        "select interval_end, sum(volume)::double from main.fct_volume_15min "
        "where site_id = ? and interval_end > ? group by 1",
        [site_id, since],
    ).fetchall()
    return dict(rows), latest
