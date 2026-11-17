"""Run the pipeline job once from the command line: `make pipeline`.

Exit code 0 when every step and check passed, 1 otherwise. On failure it prints one block that
names the check, the asset and the reason.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path

import dagster as dg

from orchestration.definitions import PipelineSettings, build_definitions


@dataclass
class Failure:
    check: str
    asset: str
    why: str


@dataclass
class PipelineResult:
    success: bool
    failures: list[Failure] = field(default_factory=list)
    passed_checks: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def run_pipeline(
    settings: PipelineSettings,
    manifest_path: Path | None = None,
    instance: dg.DagsterInstance | None = None,
) -> PipelineResult:
    # dbt reads the database path from the environment, so keep it in step with the loader.
    # Absolute, because dbt runs from transform/ and would resolve a relative path there (D35).
    os.environ["DUCKDB_PATH"] = str(Path(settings.db_path).resolve())
    defs = build_definitions(settings, manifest_path)
    job = defs.resolve_job_def("mcb_pipeline")
    result = job.execute_in_process(raise_on_error=False, instance=instance)
    failures: list[Failure] = []
    passed: list[str] = []
    warnings: list[str] = []
    for ev in result.get_asset_check_evaluations():
        name = f"{ev.asset_key.to_user_string()}:{ev.check_name}"
        if ev.passed:
            passed.append(name)
            if (ev.description or "").startswith("WARNING"):
                warnings.append(
                    f"{ev.check_name} on {ev.asset_key.to_user_string()}: "
                    f"{ev.description.removeprefix('WARNING ')}"
                )
        else:
            failures.append(
                Failure(ev.check_name, ev.asset_key.to_user_string(), ev.description or "failed")
            )
    if not result.success and not failures:
        for event in result.get_step_failure_events():
            data = event.step_failure_data
            first = (data.error.message if data.error else "step failed").strip().splitlines()[0]
            failures.append(Failure("step failure", event.step_key or "unknown", first))
    return PipelineResult(result.success, failures, passed, warnings)


def format_failure(result: PipelineResult) -> str:
    lines = ["PIPELINE FAILED", "-" * 60]
    for f in result.failures:
        lines += [f"  check: {f.check}", f"  asset: {f.asset}", f"  why:   {f.why}", ""]
    lines.append("Nothing downstream of a failed check was built.")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Run the load -> dbt -> checks job once.")
    p.add_argument("--source", choices=["bucket", "synthetic"], default="synthetic")
    p.add_argument("--db", default=os.environ.get("DUCKDB_PATH", "data/warehouse/mcb.duckdb"))
    p.add_argument("--sites", type=int, default=2)
    p.add_argument("--detectors", type=int, default=2)
    p.add_argument("--days", type=int, default=1)
    p.add_argument("--faults", action="store_true", help="synthetic data with injected faults")
    p.add_argument("--replay-clock", default="", help="ISO time; default is now (or data end)")
    a = p.parse_args(argv)

    clock = a.replay_clock
    if a.source == "synthetic" and not clock:
        # Synthetic data is generated for March 2026, so "now" would always look stale. Use the
        # end of the generated period as the replay clock. See docs/decisions.md D27.
        from ingest.synthetic import DEFAULT_START

        end = DEFAULT_START + timedelta(days=a.days)
        clock = f"{end.isoformat()}T00:00:00+00:00"

    settings = PipelineSettings(
        db_path=a.db,
        source=a.source,
        synthetic_sites=a.sites,
        synthetic_detectors=a.detectors,
        synthetic_days=a.days,
        synthetic_faults=a.faults,
        replay_clock=clock,
        dbt_target_path=os.environ.get("DBT_TARGET_PATH", "transform/target"),
    )
    instance = dg.DagsterInstance.get() if os.environ.get("DAGSTER_HOME") else None
    result = run_pipeline(settings, instance=instance)
    if result.success:
        print(f"PIPELINE OK: {len(result.passed_checks)} checks passed")
        for warning in result.warnings:
            print(f"  warning: {warning}")
        return 0
    print(format_failure(result))
    return 1


if __name__ == "__main__":
    sys.exit(main())
