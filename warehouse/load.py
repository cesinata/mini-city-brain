"""Load new raw objects from the raw bucket into DuckDB `raw.readings`.

Idempotent: `raw.loaded_objects` records every object key that has been loaded, and a key is
never loaded twice. Each object is loaded in one transaction together with its manifest row.
"""

from __future__ import annotations

import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb

from services.common.aws import s3_client
from services.common.config import Settings

log = logging.getLogger("mcb.warehouse")

RAW_PREFIX = "raw/scats/"


@dataclass
class LoadResult:
    objects_loaded: int = 0
    objects_skipped: int = 0
    rows_loaded: int = 0


def connect(db_path: str | os.PathLike[str]) -> duckdb.DuckDBPyConnection:
    path = Path(db_path)
    if str(db_path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(db_path))


def ensure_schema(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("CREATE SCHEMA IF NOT EXISTS raw")
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS raw.readings (
            site_id       VARCHAR   NOT NULL,
            detector_id   VARCHAR   NOT NULL,
            interval_end  TIMESTAMP NOT NULL,   -- UTC
            volume        INTEGER   NOT NULL,
            source        VARCHAR   NOT NULL,
            _object_key   VARCHAR   NOT NULL,
            _loaded_at    TIMESTAMP NOT NULL
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS raw.loaded_objects (
            object_key VARCHAR PRIMARY KEY,
            etag       VARCHAR,
            row_count  INTEGER   NOT NULL,
            loaded_at  TIMESTAMP NOT NULL
        )
        """
    )


def load_ndjson_file(
    con: duckdb.DuckDBPyConnection, path: Path, object_key: str, etag: str | None = None
) -> int:
    """Insert one ndjson file and its manifest row in one transaction. Returns rows loaded."""
    con.execute("BEGIN")
    try:
        con.execute(
            """
            INSERT INTO raw.readings
            SELECT site_id, detector_id,
                   strptime(interval_end, '%Y-%m-%dT%H:%M:%SZ'),
                   volume, source, ?, now()::TIMESTAMP
            FROM read_ndjson(?, columns = {
                site_id: 'VARCHAR', detector_id: 'VARCHAR', interval_end: 'VARCHAR',
                volume: 'INTEGER', source: 'VARCHAR'})
            """,
            [object_key, str(path)],
        )
        rows = con.execute(
            "SELECT count(*) FROM raw.readings WHERE _object_key = ?", [object_key]
        ).fetchone()[0]
        con.execute(
            "INSERT INTO raw.loaded_objects VALUES (?, ?, ?, now()::TIMESTAMP)",
            [object_key, etag, rows],
        )
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    return int(rows)


def insert_readings(con: duckdb.DuckDBPyConnection, readings: list[dict[str, Any]], key: str):
    """Load reading dictionaries (as the API accepts them) without going through a bucket.

    Used by tests and demos. Writes a temporary ndjson file and uses the same insert as the
    loader. `interval_end` must be a UTC ISO string ending in Z or +00:00.
    """
    import json
    from datetime import UTC, datetime

    ensure_schema(con)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "batch.ndjson"
        with path.open("w") as fh:
            for r in readings:
                end = datetime.fromisoformat(r["interval_end"]).astimezone(UTC)
                fh.write(
                    json.dumps({**r, "interval_end": end.strftime("%Y-%m-%dT%H:%M:%SZ")}) + "\n"
                )
        return load_ndjson_file(con, path, key)


def load(
    settings: Settings,
    db_path: str | os.PathLike[str],
    s3: Any | None = None,
    con: duckdb.DuckDBPyConnection | None = None,
) -> LoadResult:
    s3 = s3 or s3_client(settings)
    own = con is None
    con = con or connect(db_path)
    result = LoadResult()
    try:
        ensure_schema(con)
        loaded = {r[0] for r in con.execute("SELECT object_key FROM raw.loaded_objects").fetchall()}
        paginator = s3.get_paginator("list_objects_v2")
        keys: list[tuple[str, str]] = []
        for page in paginator.paginate(Bucket=settings.raw_bucket, Prefix=RAW_PREFIX):
            keys.extend((o["Key"], o.get("ETag", "")) for o in page.get("Contents", []))
        for key, etag in sorted(keys):
            if key in loaded:
                result.objects_skipped += 1
                continue
            body = s3.get_object(Bucket=settings.raw_bucket, Key=key)["Body"].read()
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "object.ndjson"
                path.write_bytes(body)
                result.rows_loaded += load_ndjson_file(con, path, key, etag)
            result.objects_loaded += 1
        log.info(
            "load finished",
            extra={
                "objects_loaded": result.objects_loaded,
                "objects_skipped": result.objects_skipped,
                "rows_loaded": result.rows_loaded,
            },
        )
    finally:
        if own:
            con.close()
    return result


def main() -> None:
    from services.common.logging import configure_logging

    configure_logging()
    res = load(Settings.from_env(), os.environ.get("DUCKDB_PATH", "data/warehouse/mcb.duckdb"))
    print(res)


if __name__ == "__main__":
    main()
