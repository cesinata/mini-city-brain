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


# Files that reach the emulator from the host, and the text before the URL in each.
HOST_ENDPOINTS = {
    "scripts/demo.sh": r"AWS_ENDPOINT_URL=(\S+)",
    "scripts/demo_bad.sh": r"AWS_ENDPOINT_URL=(\S+)",
    "env.example": r"AWS_ENDPOINT_URL=(\S+)",
    ".github/workflows/ci.yml": r"AWS_ENDPOINT_URL:\s*(\S+)",
    "services/common/config.py": r'"AWS_ENDPOINT_URL",\s*"([^"]+)"',
    "infra/terraform/variables.tf": r'default\s*=\s*"(http[^"]+)"',
}


def test_host_side_endpoints_use_the_published_emulator_port():
    ports = _compose()["services"]["emulator"]["ports"]
    assert len(ports) == 1
    host_ip, host_port, container_port = ports[0].split(":")
    assert host_ip == "127.0.0.1"
    # macOS AirPlay Receiver listens on 5000 on every address (decisions D34).
    assert host_port != "5000"
    expected = f"http://127.0.0.1:{host_port}"
    for path, pattern in HOST_ENDPOINTS.items():
        found = re.findall(pattern, (ROOT / path).read_text())
        assert found, f"no emulator URL found in {path}"
        assert set(found) == {expected}, f"{path}: {found} != {expected}"
    assert container_port == "5000"
