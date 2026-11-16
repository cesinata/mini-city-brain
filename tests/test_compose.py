"""The api container must read the same DuckDB file that the pipeline writes on the host."""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath

import yaml

ROOT = Path(__file__).resolve().parent.parent


def _compose() -> dict:
    return yaml.safe_load((ROOT / "docker-compose.yml").read_text())


def _demo_db_path() -> PurePosixPath:
    text = (ROOT / "scripts/demo.sh").read_text()
    paths = set(re.findall(r"orchestration\.run\b.*?--db\s+(\S+)", text))
    assert len(paths) == 1, f"expected one --db path in scripts/demo.sh, found {paths}"
    return PurePosixPath(paths.pop())


def test_api_bind_mounts_the_folder_demo_writes_to():
    api = _compose()["services"]["api"]
    mounts = [v for v in api["volumes"] if v.split(":")[1] == "/data/warehouse"]
    assert len(mounts) == 1
    host, container, mode = mounts[0].split(":")
    assert mode == "ro"
    assert host.startswith("./"), "must be a bind mount relative to the repo, not a named volume"

    db = _demo_db_path()
    assert PurePosixPath(host.removeprefix("./")) == db.parent

    duckdb_path = PurePosixPath(api["environment"]["DUCKDB_PATH"])
    assert duckdb_path.parent == PurePosixPath(container)
    assert duckdb_path.name == db.name


def test_no_named_warehouse_volume_remains():
    assert "warehouse" not in (_compose().get("volumes") or {})
