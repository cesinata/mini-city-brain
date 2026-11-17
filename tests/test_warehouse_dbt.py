from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import duckdb
import pytest

from ingest import scats, synthetic
from tests.helpers import run_dbt, synthetic_readings
from warehouse import load as wh


def seeded_db(tmp_path: Path, readings, key: str = "obj-1") -> Path:
    db = tmp_path / "wh.duckdb"
    con = wh.connect(db)
    wh.insert_readings(con, readings, key)
    con.close()
    return db


def failed(statuses: dict[str, str]) -> set[str]:
    return {name for name, st in statuses.items() if st in ("fail", "error")}


def query(db: Path, sql: str):
    con = duckdb.connect(str(db))
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


# ---- loader --------------------------------------------------------------------------------


def put_ndjson(aws, key: str, readings) -> None:
    body = "\n".join(
        json.dumps(
            {**r, "interval_end": r["interval_end"].replace("+00:00", "Z")}, separators=(",", ":")
        )
        for r in readings
    )
    aws.s3.put_object(Bucket=aws.settings.raw_bucket, Key=key, Body=(body + "\n").encode())


def test_loader_loads_objects_and_is_idempotent(aws, tmp_path):
    readings = synthetic_readings(tmp_path, sites=1, detectors=1, days=1)
    put_ndjson(aws, "raw/scats/date=2026-03-01/a.ndjson", readings[:50])
    put_ndjson(aws, "raw/scats/date=2026-03-02/b.ndjson", readings[50:])
    db = tmp_path / "wh.duckdb"

    first = wh.load(aws.settings, db, s3=aws.s3)
    assert (first.objects_loaded, first.objects_skipped, first.rows_loaded) == (2, 0, 96)

    second = wh.load(aws.settings, db, s3=aws.s3)
    assert (second.objects_loaded, second.objects_skipped, second.rows_loaded) == (0, 2, 0)
    assert query(db, "select count(*) from raw.readings") == [(96,)]

    put_ndjson(aws, "raw/scats/date=2026-03-02/c.ndjson", readings[:2])
    third = wh.load(aws.settings, db, s3=aws.s3)
    assert (third.objects_loaded, third.objects_skipped) == (1, 2)
    assert query(db, "select count(*) from raw.loaded_objects") == [(3,)]


def test_loader_stores_interval_end_as_utc(aws, tmp_path):
    readings = synthetic_readings(tmp_path, sites=1, detectors=1, days=1)
    put_ndjson(aws, "raw/scats/date=2026-03-01/a.ndjson", readings)
    db = tmp_path / "wh.duckdb"
    wh.load(aws.settings, db, s3=aws.s3)
    first = query(db, "select min(interval_end)::varchar from raw.readings")[0][0]
    assert first == "2026-03-01 13:15:00"  # V00 of 2026-03-02 ends 00:15 AEDT (UTC+11)


def test_failed_object_load_rolls_back_and_is_retried(aws, tmp_path):
    aws.s3.put_object(
        Bucket=aws.settings.raw_bucket, Key="raw/scats/date=2026-03-01/bad.ndjson", Body=b"{oops\n"
    )
    db = tmp_path / "wh.duckdb"
    with pytest.raises(duckdb.Error):
        wh.load(aws.settings, db, s3=aws.s3)
    assert query(db, "select count(*) from raw.loaded_objects") == [(0,)]
    assert query(db, "select count(*) from raw.readings") == [(0,)]


# ---- dbt -----------------------------------------------------------------------------------


def test_dbt_build_passes_on_clean_synthetic_data(tmp_path):
    readings = synthetic_readings(tmp_path, sites=2, detectors=2, days=2)
    db = seeded_db(tmp_path, readings)
    ok, statuses = run_dbt(db, tmp_path, "build")
    assert ok, statuses
    assert not failed(statuses)
    assert query(db, "select count(*) from main.stg_readings") == [(len(readings),)]
    assert query(db, "select count(*) from main.fct_volume_15min") == [(len(readings),)]
    # completeness is 1.0 for every detector-day on clean data
    assert query(
        db, "select min(completeness), max(completeness) from main.fct_detector_health"
    ) == [(1.0, 1.0)]
    # 4 detector-days per site -> 2 sites x 2 detectors x 2 days = 8 rows
    assert query(db, "select count(*) from main.fct_detector_health") == [(8,)]


def test_hourly_model_uses_local_time_and_sums_detectors(tmp_path):
    readings = synthetic_readings(tmp_path, sites=1, detectors=2, days=1)
    db = seeded_db(tmp_path, readings)
    ok, _ = run_dbt(db, tmp_path, "build")
    assert ok
    rows = query(
        db,
        "select hour_of_day, intervals_observed, detectors_reporting "
        "from main.fct_volume_hourly order by 1",
    )
    assert [r[0] for r in rows] == list(range(24))
    assert all(r[1] == 8 and r[2] == 2 for r in rows)  # 4 intervals x 2 detectors


def test_dbt_fails_when_duplicates_are_injected(tmp_path):
    readings = synthetic_readings(tmp_path, sites=1, detectors=1, days=1)
    db = tmp_path / "wh.duckdb"
    con = wh.connect(db)
    wh.insert_readings(con, readings, "obj-1")
    wh.insert_readings(con, readings, "obj-2")  # the same 96 readings again, a second object
    con.close()
    ok, statuses = run_dbt(db, tmp_path, "build")
    assert not ok
    assert any("raw_duplicate_rate_within_limit" in n for n in failed(statuses))


def test_staging_removes_duplicates_when_the_rate_is_allowed(tmp_path):
    readings = synthetic_readings(tmp_path, sites=1, detectors=1, days=1)
    db = tmp_path / "wh.duckdb"
    con = wh.connect(db)
    wh.insert_readings(con, readings, "obj-1")
    wh.insert_readings(con, readings, "obj-2")
    con.close()
    ok, statuses = run_dbt(db, tmp_path, "build", extra_vars="{max_duplicate_rate: 0.6}")
    assert ok, statuses
    assert query(db, "select count(*) from main.stg_readings") == [(96,)]


def test_dbt_fails_when_a_negative_volume_is_injected(tmp_path):
    readings = synthetic_readings(tmp_path, sites=1, detectors=1, days=1)
    readings[10] = {**readings[10], "volume": -1}
    db = seeded_db(tmp_path, readings)
    ok, statuses = run_dbt(db, tmp_path, "build")
    assert not ok
    assert any("raw_no_negative_volume" in n for n in failed(statuses))


def test_completeness_test_fails_on_data_with_gaps(tmp_path):
    clean = synthetic_readings(tmp_path, sites=1, detectors=1, days=1)
    gappy = clean[:40] + clean[60:]  # drop 20 of 96 intervals
    db = seeded_db(tmp_path, gappy)
    ok, statuses = run_dbt(db, tmp_path, "build")
    assert not ok
    assert "completeness_below_threshold" in failed(statuses)


def test_completeness_threshold_comes_from_the_project_vars(tmp_path):
    clean = synthetic_readings(tmp_path, sites=1, detectors=1, days=1)
    db = seeded_db(tmp_path, clean[:40] + clean[60:])
    ok, statuses = run_dbt(db, tmp_path, "build", extra_vars="{min_completeness: 0.5}")
    assert ok, statuses


def test_local_hour_and_day_follow_melbourne_time_across_the_clock_change(tmp_path):
    """8:00 to 9:00 local is hour 8 before and after daylight saving starts (4 Oct 2026)."""
    rows = synthetic.generate(1, 1, 3, start=date(2026, 10, 3), faults=False)
    synthetic.write_csv(rows, tmp_path / "dst.csv")
    readings, _ = scats.read_readings(tmp_path / "dst.csv", source="synthetic")
    db = seeded_db(tmp_path, readings)
    ok, _ = run_dbt(db, tmp_path, "build", extra_vars="{min_completeness: 0.5}")
    assert ok
    per_day = query(
        db,
        "select local_date::varchar, intervals_observed from main.fct_detector_health order by 1",
    )
    assert per_day == [("2026-10-03", 96), ("2026-10-04", 91), ("2026-10-05", 96)]
    hour8 = query(
        db,
        "select cast(local_interval_start as date)::varchar, min(local_interval_start)::varchar "
        "from main.fct_volume_15min where extract(hour from local_interval_start) = 8 "
        "group by 1 order by 1",
    )
    assert [r[1][11:16] for r in hour8] == ["08:00", "08:00", "08:00"]


def _drop_intervals(readings, site, detector, day_prefix, count):
    """Remove `count` readings of one detector on one UTC day prefix."""
    out, dropped = [], 0
    for r in readings:
        hit = r["site_id"] == site and r["detector_id"] == detector
        if hit and r["interval_end"].startswith(day_prefix) and dropped < count:
            dropped += 1
            continue
        out.append(r)
    assert dropped == count
    return out


def test_completeness_test_allows_a_small_share_of_incomplete_detector_days(tmp_path):
    """200 detector-days: 1 incomplete (0.5%) passes, 3 incomplete (1.5%) fail (limit 1%)."""
    readings = synthetic_readings(tmp_path, sites=10, detectors=2, days=10)
    one = _drop_intervals(readings, "1000", "1", "2026-03-03", 40)
    db = seeded_db(tmp_path, one)
    ok, statuses = run_dbt(db, tmp_path, "build")
    assert ok, statuses
    three = _drop_intervals(one, "1007", "1", "2026-03-04", 40)
    three = _drop_intervals(three, "1014", "2", "2026-03-05", 40)
    (tmp_path / "b").mkdir()
    db2 = seeded_db(tmp_path / "b", three)
    ok, statuses = run_dbt(db2, tmp_path / "b", "build")
    assert not ok
    assert "completeness_below_threshold" in failed(statuses)
