"""Helpers shared by warehouse, dbt and pipeline tests."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dbt.cli.main import dbtRunner

from ingest import scats, synthetic

TRANSFORM_DIR = Path(__file__).resolve().parent.parent / "transform"


def synthetic_readings(
    tmp_path: Path, sites: int = 2, detectors: int = 2, days: int = 2, faults: bool = False
) -> list[dict[str, Any]]:
    path = tmp_path / "synthetic.csv"
    synthetic.write_csv(synthetic.generate(sites, detectors, days, faults=faults), path)
    readings, _ = scats.read_readings(path, source="synthetic")
    return readings


def run_dbt(
    db_path: Path, workdir: Path, *args: str, extra_vars: str | None = None
) -> tuple[bool, dict[str, str]]:
    """Run a dbt command against `db_path`. Returns (success, {node name: status})."""
    os.environ["DUCKDB_PATH"] = str(db_path)
    cmd = [
        *args,
        "--project-dir",
        str(TRANSFORM_DIR),
        "--profiles-dir",
        str(TRANSFORM_DIR),
        "--target-path",
        str(workdir / "target"),
        "--log-path",
        str(workdir / "logs"),
    ]
    if extra_vars:
        cmd += ["--vars", extra_vars]
    res = dbtRunner().invoke(cmd)
    statuses: dict[str, str] = {}
    if res.result is not None and hasattr(res.result, "results"):
        for r in res.result.results:
            statuses[r.node.name] = str(r.status)
    return res.success, statuses
