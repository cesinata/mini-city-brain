from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb
import pytest

from ingest.synthetic import DEFAULT_START
from orchestration import checks
from orchestration.definitions import PipelineSettings, parse_manifest
from orchestration.run import format_failure, main, run_pipeline
from warehouse import load as wh


@pytest.fixture(scope="module")
def manifest(tmp_path_factory) -> Path:
    return parse_manifest(tmp_path_factory.mktemp("manifest"))


def settings_for(tmp_path: Path, **kw) -> PipelineSettings:
    clock = datetime.combine(DEFAULT_START, datetime.min.time(), UTC) + timedelta(days=1)
    base = {
        "db_path": str(tmp_path / "wh.duckdb"),
        "source": "synthetic",
        "replay_clock": clock.isoformat(),
        "dbt_target_path": str(tmp_path / "dbt_target"),
    }
    base.update(kw)
    return PipelineSettings(**base)


def query(db: str, sql: str):
    con = duckdb.connect(db)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def test_clean_data_passes_every_check_and_records_success(tmp_path, manifest, monkeypatch):
    monkeypatch.setenv("DUCKDB_PATH", str(tmp_path / "wh.duckdb"))
    s = settings_for(tmp_path)
    res = run_pipeline(s, manifest)
    assert res.success, res.failures
    assert res.failures == []
    names = {n.split(":")[-1] for n in res.passed_checks}
    assert {"freshness", "no_negative_volumes", "duplicate_rate", "completeness"} <= names
    assert query(s.db_path, "select count(*) from main.fct_volume_15min")[0][0] == 2 * 2 * 96
    assert query(s.db_path, "select status from ops.pipeline_runs") == [("success",)]


def test_bad_data_fails_the_run_and_stops_downstream(tmp_path, manifest, monkeypatch):
    monkeypatch.setenv("DUCKDB_PATH", str(tmp_path / "wh.duckdb"))
    clock = datetime.combine(DEFAULT_START, datetime.min.time(), UTC) + timedelta(days=3)
    s = settings_for(
        tmp_path,
        synthetic_faults=True,
        synthetic_sites=3,
        synthetic_days=3,
        replay_clock=clock.isoformat(),
    )
    res = run_pipeline(s, manifest)
    assert not res.success
    failed = {f.check for f in res.failures}
    assert "no_negative_volumes" in failed
    assert "duplicate_rate" in failed or "freshness" in failed or failed  # at least the negative
    # Blocking: dbt models and the success marker were not built.
    tables = {t[0] for t in query(s.db_path, "select table_name from information_schema.tables")}
    assert "fct_volume_hourly" not in tables
    assert "pipeline_runs" not in tables
    text = format_failure(res)
    assert "PIPELINE FAILED" in text
    assert "raw_objects_loaded" in text
    assert "negative volume" in text


def test_stale_data_fails_the_freshness_check(tmp_path, manifest, monkeypatch):
    monkeypatch.setenv("DUCKDB_PATH", str(tmp_path / "wh.duckdb"))
    late = datetime.combine(DEFAULT_START, datetime.min.time(), UTC) + timedelta(days=10)
    s = settings_for(tmp_path, replay_clock=late.isoformat())
    res = run_pipeline(s, manifest)
    assert not res.success
    assert any(f.check == "freshness" for f in res.failures)


def test_cli_exit_codes_and_message(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DUCKDB_PATH", str(tmp_path / "wh.duckdb"))
    monkeypatch.setenv("DBT_TARGET_PATH", str(tmp_path / "t"))
    assert main(["--source", "synthetic", "--db", str(tmp_path / "ok.duckdb")]) == 0
    assert "PIPELINE OK" in capsys.readouterr().out
    monkeypatch.setenv("DUCKDB_PATH", str(tmp_path / "bad.duckdb"))
    code = main(
        ["--source", "synthetic", "--faults", "--sites", "3", "--days", "3",
         "--db", str(tmp_path / "bad.duckdb")]
    )  # fmt: skip
    out = capsys.readouterr().out
    assert code == 1
    assert "check:" in out and "asset:" in out and "why:" in out


def test_cli_with_relative_paths_keeps_dbt_and_the_loader_on_one_database(
    tmp_path, monkeypatch, capsys
):
    """make demo passes relative paths; dbt runs from transform/ and must still use them (D35)."""
    transform_data = Path(__file__).resolve().parent.parent / "transform" / "data"
    before = sorted(transform_data.rglob("*")) if transform_data.exists() else []
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DUCKDB_PATH", raising=False)
    monkeypatch.setenv("DBT_TARGET_PATH", "data/dbt_target")
    (tmp_path / "data" / "warehouse").mkdir(parents=True)
    assert main(["--source", "synthetic", "--db", "data/warehouse/mcb.duckdb"]) == 0
    assert "PIPELINE OK" in capsys.readouterr().out
    assert (tmp_path / "data" / "dbt_target" / "manifest.json").exists()
    db = str(tmp_path / "data" / "warehouse" / "mcb.duckdb")
    assert query(db, "select count(*) from main.fct_volume_15min")[0][0] == 2 * 2 * 96
    after = sorted(transform_data.rglob("*")) if transform_data.exists() else []
    assert after == before, "dbt wrote files under transform/data"


# ---- the check functions on their own ------------------------------------------------------


def make_db(tmp_path) -> duckdb.DuckDBPyConnection:
    con = wh.connect(tmp_path / "c.duckdb")
    wh.ensure_schema(con)
    return con


def reading(minute_offset: int, volume: int = 5, det: str = "1") -> dict:
    end = datetime(2026, 3, 2, 0, 15, tzinfo=UTC) + timedelta(minutes=15 * minute_offset)
    return {
        "site_id": "1",
        "detector_id": det,
        "interval_end": end.isoformat(),
        "volume": volume,
        "source": "synthetic",
    }


def test_freshness_boundaries(tmp_path):
    con = make_db(tmp_path)
    assert not checks.freshness(con, datetime(2026, 3, 3, tzinfo=UTC), 48).passed  # empty
    wh.insert_readings(con, [reading(0)], "k")
    latest = datetime(2026, 3, 2, 0, 15, tzinfo=UTC)
    assert checks.freshness(con, latest + timedelta(hours=48), 48).passed
    assert not checks.freshness(con, latest + timedelta(hours=48, minutes=1), 48).passed


def test_negative_and_duplicate_checks(tmp_path):
    con = make_db(tmp_path)
    wh.insert_readings(con, [reading(0), reading(1)], "k1")
    assert checks.no_negative_volumes(con).passed
    assert checks.duplicate_rate(con, 0.0).passed
    wh.insert_readings(con, [reading(1, volume=-3)], "k2")
    assert not checks.no_negative_volumes(con).passed
    out = checks.duplicate_rate(con, 0.1)
    assert not out.passed and "1 of 3" in out.message


def test_completeness_check_reports_the_worst_rows(tmp_path):
    con = make_db(tmp_path)
    wh.insert_readings(con, [reading(i) for i in range(10)], "k")
    con.execute("create schema if not exists main")
    con.execute(
        "create table main.fct_detector_health as select '1' site_id, '1' detector_id, "
        "date '2026-03-02' local_date, 10 intervals_observed, 10/96.0 completeness"
    )
    out = checks.completeness(con, 0.9)
    assert not out.passed
    assert "site 1 detector 1 on 2026-03-02 (10/96)" in out.message
    assert checks.completeness(con, 0.05).passed
