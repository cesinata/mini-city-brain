"""Read the time of the last successful pipeline run from the DuckDB warehouse."""

from __future__ import annotations

from datetime import UTC
from pathlib import Path


def read_last_success(db_path: str) -> float | None:
    """Unix time of the last successful run, or None if there is no database or no run yet."""
    if not Path(db_path).exists():
        return None
    import duckdb

    con = duckdb.connect(db_path, read_only=True)
    try:
        row = con.execute(
            "select max(finished_at) from ops.pipeline_runs where status = 'success'"
        ).fetchone()
    except duckdb.Error:
        return None
    finally:
        con.close()
    if row is None or row[0] is None:
        return None
    return float(row[0].replace(tzinfo=UTC).timestamp())
