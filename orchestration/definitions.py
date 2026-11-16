"""Dagster definitions: load -> dbt build -> checks -> record success.

Assets
  raw_objects_loaded      loads new objects from the bucket (or, for demos and tests, seeds
                          synthetic readings straight into DuckDB)
  stg_readings ... fct_*  the dbt models, built by `dbt build` (dbt tests also run)
  pipeline_last_success   writes the time of the last fully successful run to ops.pipeline_runs

Blocking asset checks
  on raw_objects_loaded:  freshness, no_negative_volumes, duplicate_rate
  on fct_detector_health: completeness
A failing blocking check fails the run and stops downstream assets.
"""

import os
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import dagster as dg
import duckdb
from dagster import AssetExecutionContext
from dagster_dbt import DagsterDbtTranslator, DbtCliResource, dbt_assets

from ingest import scats, synthetic
from orchestration import checks
from services.common.config import Settings
from warehouse import load as wh

TRANSFORM_DIR = Path(__file__).resolve().parent.parent / "transform"
RAW_ASSET = dg.AssetKey("raw_objects_loaded")
HEALTH_ASSET = dg.AssetKey("fct_detector_health")


class PipelineSettings(dg.ConfigurableResource):
    """Everything a run needs. Thresholds live here and default to the project values."""

    db_path: str = os.environ.get("DUCKDB_PATH", "data/warehouse/mcb.duckdb")
    source: str = (
        "bucket"  # "bucket", "existing" (data already loaded) or "synthetic" (demos, tests)
    )
    synthetic_sites: int = 2
    synthetic_detectors: int = 2
    synthetic_days: int = 1
    synthetic_faults: bool = False
    replay_clock: str = ""  # ISO time; empty means "now"
    max_lag_hours: float = float(os.environ.get("PIPELINE_MAX_LAG_HOURS", "48"))
    max_duplicate_rate: float = 0.01
    min_completeness: float = 0.9
    dbt_target_path: str = ""  # where dbt writes its manifest and logs; empty = project default

    def clock(self) -> datetime:
        if self.replay_clock:
            return datetime.fromisoformat(self.replay_clock).astimezone(UTC)
        return datetime.now(UTC)

    def connect(self) -> duckdb.DuckDBPyConnection:
        con = wh.connect(self.db_path)
        wh.ensure_schema(con)
        return con


class _Translator(DagsterDbtTranslator):
    def get_asset_key(self, dbt_resource_props: dict[str, Any]) -> dg.AssetKey:
        if dbt_resource_props["resource_type"] == "source":
            return RAW_ASSET  # the dbt source raw.readings is produced by raw_objects_loaded
        return super().get_asset_key(dbt_resource_props)


@dg.asset(group_name="ingest", compute_kind="python")
def raw_objects_loaded(
    context: AssetExecutionContext, settings: PipelineSettings
) -> dg.MaterializeResult:
    con = settings.connect()
    try:
        if settings.source == "synthetic":
            rows = synthetic.generate(
                settings.synthetic_sites,
                settings.synthetic_detectors,
                settings.synthetic_days,
                faults=settings.synthetic_faults,
            )
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "synthetic.csv"
                synthetic.write_csv(rows, path)
                readings, _ = scats.read_readings(path, source="synthetic")
            key = f"synthetic/{datetime.now(UTC):%Y%m%dT%H%M%S%f}"
            loaded = wh.insert_readings(con, readings, key)
            meta: dict[str, Any] = {"source": "synthetic", "rows_loaded": loaded}
        elif settings.source == "existing":
            # Data is already in raw.readings (the Pages build loads a file straight in).
            rows = con.execute("select count(*) from raw.readings").fetchone()[0]
            meta = {"source": "existing", "rows_present": rows}
        else:
            result = wh.load(Settings.from_env(), settings.db_path, con=con)
            meta = {
                "source": "bucket",
                "objects_loaded": result.objects_loaded,
                "objects_skipped": result.objects_skipped,
                "rows_loaded": result.rows_loaded,
            }
    finally:
        con.close()
    context.log.info(f"load finished: {meta}")
    return dg.MaterializeResult(metadata=meta)


def _result(o: checks.Outcome) -> dg.AssetCheckResult:
    return dg.AssetCheckResult(
        passed=o.passed,
        severity=dg.AssetCheckSeverity.ERROR,
        description=o.message,
    )


def _run_check(settings: PipelineSettings, fn: Any, *args: Any) -> dg.AssetCheckResult:
    con = settings.connect()
    try:
        return _result(fn(con, *args))
    finally:
        con.close()


@dg.asset_check(asset=raw_objects_loaded, blocking=True, name="freshness")
def freshness_check(settings: PipelineSettings) -> dg.AssetCheckResult:
    return _run_check(settings, checks.freshness, settings.clock(), settings.max_lag_hours)


@dg.asset_check(asset=raw_objects_loaded, blocking=True, name="no_negative_volumes")
def negative_check(settings: PipelineSettings) -> dg.AssetCheckResult:
    return _run_check(settings, checks.no_negative_volumes)


@dg.asset_check(asset=raw_objects_loaded, blocking=True, name="duplicate_rate")
def duplicate_check(settings: PipelineSettings) -> dg.AssetCheckResult:
    return _run_check(settings, checks.duplicate_rate, settings.max_duplicate_rate)


@dg.asset_check(asset=HEALTH_ASSET, blocking=True, name="completeness")
def completeness_check(settings: PipelineSettings) -> dg.AssetCheckResult:
    return _run_check(settings, checks.completeness, settings.min_completeness)


def make_dbt_assets(manifest_path: Path) -> dg.AssetsDefinition:
    @dbt_assets(manifest=manifest_path, dagster_dbt_translator=_Translator(), name="mcb_dbt")
    def mcb_dbt(
        context: AssetExecutionContext, dbt: DbtCliResource, settings: PipelineSettings
    ) -> Any:
        target = Path(settings.dbt_target_path) if settings.dbt_target_path else None
        args = [
            "build",
            "--vars",
            f"{{max_duplicate_rate: {settings.max_duplicate_rate}, "
            f"min_completeness: {settings.min_completeness}}}",
        ]
        yield from dbt.cli(args, context=context, target_path=target).stream()

    return mcb_dbt


@dg.asset(
    deps=[dg.AssetKey("fct_volume_hourly"), dg.AssetKey("fct_volume_15min"), HEALTH_ASSET],
    group_name="ops",
    compute_kind="python",
)
def pipeline_last_success(settings: PipelineSettings) -> dg.MaterializeResult:
    """Records the time of the last run in which every earlier step and check passed."""
    now = datetime.now(UTC).replace(tzinfo=None)
    con = settings.connect()
    try:
        con.execute("create schema if not exists ops")
        con.execute(
            "create table if not exists ops.pipeline_runs (finished_at timestamp, status varchar)"
        )
        con.execute("insert into ops.pipeline_runs values (?, 'success')", [now])
    finally:
        con.close()
    return dg.MaterializeResult(metadata={"finished_at_utc": now.isoformat()})


def parse_manifest(target_path: Path) -> Path:
    """Run `dbt parse` (no database access needed for the manifest) and return its path."""
    from dbt.cli.main import dbtRunner

    target_path.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("DUCKDB_PATH", str(Path(tempfile.gettempdir()) / "mcb_parse.duckdb"))
    res = dbtRunner().invoke(
        [
            "parse",
            "--project-dir",
            str(TRANSFORM_DIR),
            "--profiles-dir",
            str(TRANSFORM_DIR),
            "--target-path",
            str(target_path),
            "--log-path",
            str(target_path / "logs"),
        ]
    )
    if not res.success:
        raise RuntimeError("dbt parse failed")
    return target_path / "manifest.json"


def _dbt_executable() -> str:
    """The dbt that lives next to this Python (works without activating the venv)."""
    candidate = Path(sys.executable).parent / "dbt"
    return str(candidate) if candidate.exists() else "dbt"


def build_definitions(
    settings: PipelineSettings, manifest_path: Path | None = None
) -> dg.Definitions:
    manifest_path = manifest_path or parse_manifest(
        Path(os.environ.get("DBT_TARGET_PATH", Path(tempfile.gettempdir()) / "mcb_dbt_target"))
    )
    mcb_dbt = make_dbt_assets(manifest_path)
    job = dg.define_asset_job("mcb_pipeline", selection=dg.AssetSelection.all())
    schedule = dg.ScheduleDefinition(
        job=job, cron_schedule="0 * * * *", default_status=dg.DefaultScheduleStatus.STOPPED
    )
    return dg.Definitions(
        assets=[raw_objects_loaded, mcb_dbt, pipeline_last_success],
        asset_checks=[freshness_check, negative_check, duplicate_check, completeness_check],
        jobs=[job],
        schedules=[schedule],
        resources={
            "settings": settings,
            "dbt": DbtCliResource(
                project_dir=str(TRANSFORM_DIR),
                profiles_dir=str(TRANSFORM_DIR),
                dbt_executable=_dbt_executable(),
            ),
        },
    )


@dg.definitions
def defs() -> dg.Definitions:
    """Entry point for `dagster dev -m orchestration.definitions` (see docs/demo.md)."""
    return build_definitions(PipelineSettings())
