"""Data-quality checks as plain functions over the DuckDB warehouse.

Each returns a `Outcome`. Dagster wraps them as blocking asset checks (see definitions.py), so a
failing check stops the run. Keeping them as plain functions makes them easy to test.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import duckdb


@dataclass(frozen=True)
class Outcome:
    check: str
    asset: str
    passed: bool
    message: str
    warning: bool = False  # passed, but with something worth printing (decisions D45)


def freshness(
    con: duckdb.DuckDBPyConnection, replay_clock: datetime, max_lag_hours: float
) -> Outcome:
    """The latest interval end must be within `max_lag_hours` of the replay clock."""
    latest = con.execute("select max(interval_end) from raw.readings").fetchone()[0]
    if latest is None:
        return Outcome("freshness", "raw_objects_loaded", False, "raw.readings is empty")
    latest = latest.replace(tzinfo=UTC)
    lag = replay_clock - latest
    ok = lag <= timedelta(hours=max_lag_hours)
    hours = lag.total_seconds() / 3600
    return Outcome(
        "freshness",
        "raw_objects_loaded",
        ok,
        f"latest interval_end is {latest:%Y-%m-%d %H:%M} UTC, {hours:.1f} h behind the replay "
        f"clock (limit {max_lag_hours:g} h)",
    )


def no_negative_volumes(con: duckdb.DuckDBPyConnection) -> Outcome:
    n = con.execute("select count(*) from raw.readings where volume < 0").fetchone()[0]
    return Outcome(
        "no_negative_volumes",
        "raw_objects_loaded",
        n == 0,
        f"{n} reading(s) with a negative volume in raw.readings" if n else "no negative volumes",
    )


def duplicate_rate(con: duckdb.DuckDBPyConnection, max_rate: float) -> Outcome:
    total, distinct = con.execute(
        "select count(*), count(distinct site_id || '|' || detector_id || '|' || interval_end) "
        "from raw.readings"
    ).fetchone()
    rate = 0.0 if total == 0 else (total - distinct) / total
    return Outcome(
        "duplicate_rate",
        "raw_objects_loaded",
        rate <= max_rate,
        f"{total - distinct} of {total} raw rows repeat a key "
        f"(rate {rate:.4f}, limit {max_rate:g})",
    )


def completeness(
    con: duckdb.DuckDBPyConnection, min_completeness: float, max_incomplete_share: float = 0.0
) -> Outcome:
    """Fail when more than `max_incomplete_share` of detector-days are below `min_completeness`.

    Below that share the check passes and lists the incomplete detector-days as a warning. With
    the default share of 0, any incomplete detector-day fails, as before (decisions D45).
    """
    total = con.execute("select count(*) from main.fct_detector_health").fetchone()[0]
    rows = con.execute(
        "select site_id, detector_id, local_date, intervals_observed "
        "from main.fct_detector_health where completeness < ? order by 1, 2, 3",
        [min_completeness],
    ).fetchall()
    if not rows:
        return Outcome(
            "completeness",
            "fct_detector_health",
            True,
            f"every detector-day has >= {min_completeness:g}",
        )
    share = len(rows) / total
    sample = ", ".join(f"site {s} detector {d} on {day} ({n}/96)" for s, d, day, n in rows[:3])
    more = f" and {len(rows) - 3} more" if len(rows) > 3 else ""
    counts = (
        f"{len(rows)} of {total} detector-day(s) ({share:.2%}) below {min_completeness:g} of 96 "
        f"intervals, limit {max_incomplete_share:.0%}: {sample}{more}"
    )
    if share <= max_incomplete_share:
        return Outcome("completeness", "fct_detector_health", True, f"WARNING {counts}", True)
    return Outcome("completeness", "fct_detector_health", False, counts)
