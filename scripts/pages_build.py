"""Build the data behind the GitHub Pages demo. Runs inside the Pages workflow runner.

Real data is used only when REAL_DATA_ENABLED is "true". The script then asks the publisher's
CKAN API for the latest monthly volume file, downloads it into a temporary folder, keeps the
top sites by volume, loads them into DuckDB, runs the pipeline and exports site/data/summary.json.

If the variable is unset, or the download, the load or the pipeline fails, the page is built
from synthetic data and a warning is printed and added to the job summary. Nothing downloaded is
ever committed. Real data is never downloaded on a developer machine by this repo's tools.

Usage: python -m scripts.pages_build [--out site/data]
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import re
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Protocol
from zoneinfo import ZoneInfo

import duckdb
import httpx

from ingest import scats
from orchestration.definitions import PipelineSettings, parse_manifest
from orchestration.run import format_failure, run_pipeline
from services.common.models import MAX_VOLUME_15MIN
from warehouse import load as wh

PACKAGE_URL = (
    "https://opendata.transport.vic.gov.au/api/3/action/package_show?id=traffic-signal-volume-data"
)
TOP_SITES = 50
CHUNK = 200_000
ROOT = Path(__file__).resolve().parent.parent


class Http(Protocol):
    def get_json(self, url: str) -> dict[str, Any]: ...

    def download(self, url: str, dest: Path) -> Path: ...


class RealHttp:
    def get_json(self, url: str) -> dict[str, Any]:
        resp = httpx.get(url, timeout=60, follow_redirects=True)
        resp.raise_for_status()
        return resp.json()

    def download(self, url: str, dest: Path) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        with httpx.stream("GET", url, timeout=600, follow_redirects=True) as resp:
            resp.raise_for_status()
            with dest.open("wb") as fh:
                for chunk in resp.iter_bytes():
                    fh.write(chunk)
        return dest


MONTHS = {
    name: number
    for number, names in enumerate(
        [("jan", "january"), ("feb", "february"), ("mar", "march"), ("apr", "april"),
         ("may",), ("jun", "june"), ("jul", "july"), ("aug", "august"),
         ("sep", "sept", "september"), ("oct", "october"), ("nov", "november"),
         ("dec", "december")],
        start=1,
    )
    for name in names
}  # fmt: skip
MONTH_NAME_YEAR = re.compile(r"(?<![a-z])([a-z]{3,9})[\s_-]*(20\d\d)(?!\d)")
YEAR_MONTH = re.compile(r"(?<!\d)(20\d\d)[-_]?(0[1-9]|1[0-2])(?!\d)")


def resource_month(resource: dict[str, Any]) -> tuple[int, int] | None:
    """(year, month) from a resource's name or URL, for example "october_2026" or "2026-10"."""
    text = f"{resource.get('name', '')} {resource.get('url', '')}".lower()
    for word, year in MONTH_NAME_YEAR.findall(text):
        if word in MONTHS:
            return int(year), MONTHS[word]
    match = YEAR_MONTH.search(text)
    return (int(match.group(1)), int(match.group(2))) if match else None


def latest_zip_resource(package: dict[str, Any], today: date | None = None) -> dict[str, Any]:
    """The newest monthly ZIP whose month has ended; otherwise the newest ZIP.

    The current month's file is still being filled in (the publisher updates it daily), so a
    complete earlier month is preferred when the month can be read from the name or URL
    (decisions D48). `today` is the Melbourne date; it defaults to now.
    """
    resources = package["result"]["resources"]
    zips = [r for r in resources if str(r.get("url", "")).lower().endswith(".zip")]
    if not zips:
        raise LookupError("the dataset lists no ZIP resources")
    today = today or datetime.now(ZoneInfo(scats.DEFAULT_TZ)).date()
    ended = [r for r in zips if (m := resource_month(r)) and m < (today.year, today.month)]
    if ended:
        return max(ended, key=lambda r: (resource_month(r), r.get("last_modified") or ""))
    return max(
        zips, key=lambda r: (r.get("last_modified") or r.get("created") or "", r.get("name", ""))
    )


def fetch_latest(dest_dir: Path, http: Http) -> tuple[Path, dict[str, Any]]:
    resource = latest_zip_resource(http.get_json(PACKAGE_URL))
    return http.download(resource["url"], dest_dir / "scats_latest.zip"), resource


def load_top_sites(source: Path, db_path: str, top_n: int = TOP_SITES) -> dict[str, int]:
    """Keep the `top_n` sites by daily volume, unpivot, drop impossible values, load to DuckDB."""
    keep = scats.top_sites(source, top_n) or set()
    stats = scats.ReadStats()
    rows = scats.rows_for_sites(source, keep)
    con = wh.connect(db_path)
    counts = {"sites_kept": len(keep), "readings": 0, "dropped_out_of_range": 0, "chunks": 0}
    try:
        wh.ensure_schema(con)
        buffer: list[dict[str, Any]] = []

        def flush() -> None:
            if buffer:
                wh.insert_readings(con, buffer, f"pages/chunk-{counts['chunks']:05d}")
                counts["chunks"] += 1
                counts["readings"] += len(buffer)
                buffer.clear()

        for reading in scats.unpivot(rows, stats, source="scats"):
            if not 0 <= reading["volume"] <= MAX_VOLUME_15MIN:
                counts["dropped_out_of_range"] += 1
                continue
            buffer.append(reading)
            if len(buffer) >= CHUNK:
                flush()
        flush()
    finally:
        con.close()
    if counts["readings"] == 0:
        raise ValueError("no readings left after filtering")
    return counts


@dataclass
class BuildResult:
    label: str
    warnings: list[str] = field(default_factory=list)
    detail: dict[str, Any] = field(default_factory=dict)


def _run_pipeline(db: str, source: str, workdir: Path, clock: str, **kw: Any):
    settings = PipelineSettings(
        db_path=db,
        source=source,
        replay_clock=clock,
        dbt_target_path=str(workdir / "dbt_target"),
        **kw,
    )
    return run_pipeline(settings, parse_manifest(workdir / "manifest"))


def _data_end(db: str) -> str:
    con = duckdb.connect(db)
    try:
        end = con.execute("select max(interval_end) from raw.readings").fetchone()[0]
    finally:
        con.close()
    return end.replace(tzinfo=UTC).isoformat()


def build(
    db_path: str,
    workdir: Path,
    real_enabled: bool,
    http: Http | None = None,
) -> BuildResult:
    result = BuildResult("synthetic")
    if real_enabled:
        try:
            with tempfile.TemporaryDirectory() as tmp:
                source, resource = fetch_latest(Path(tmp), http or RealHttp())
                result.detail["file"] = resource.get("name") or resource.get("url")
                result.detail["load"] = load_top_sites(source, db_path)
            run = _run_pipeline(db_path, "existing", workdir, _data_end(db_path))
            if run.success:
                result.label = "real"
                return result
            result.warnings.append(
                "Real data loaded but the pipeline checks failed, so the page uses synthetic "
                "data instead:\n" + format_failure(run)
            )
        except Exception as exc:
            result.warnings.append(
                f"Real data could not be used ({type(exc).__name__}: {exc}). "
                "The page uses synthetic data instead."
            )
    else:
        result.warnings.append("REAL_DATA_ENABLED is not 'true'. The page uses synthetic data.")
    for suffix in ("", ".wal"):
        Path(db_path + suffix).unlink(missing_ok=True)
    clock = "2026-04-13T00:00:00+00:00"  # end of the 42 synthetic days (see orchestration/run.py)
    run = _run_pipeline(
        db_path,
        "synthetic",
        workdir,
        clock,
        synthetic_sites=12,
        synthetic_detectors=2,
        synthetic_days=42,
    )
    if not run.success:
        raise RuntimeError("the synthetic pipeline failed:\n" + format_failure(run))
    return result


def _load_export() -> Any:
    spec = importlib.util.spec_from_file_location("site_export", ROOT / "site" / "export.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["site_export"] = module
    spec.loader.exec_module(module)
    return module


def write_job_summary(result: BuildResult, path: str | None, now: Callable[[], datetime]) -> None:
    lines = [
        f"### Pages data build ({now():%Y-%m-%d %H:%M} UTC)",
        f"- Data label: **{result.label}**",
    ]
    for key, value in result.detail.items():
        lines.append(f"- {key}: {value}")
    for warning in result.warnings:
        lines.append(f"- WARNING: {warning}")
        print(f"::warning::{warning.splitlines()[0]}")
    text = "\n".join(lines) + "\n"
    print(text)
    if path:
        with open(path, "a") as fh:
            fh.write(text)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Build the data for the Pages demo.")
    p.add_argument("--out", type=Path, default=ROOT / "site" / "data")
    p.add_argument("--db", default="data/warehouse/pages.duckdb")
    a = p.parse_args(argv)
    real = os.environ.get("REAL_DATA_ENABLED", "").strip().lower() == "true"
    workdir = Path(tempfile.mkdtemp(prefix="pages_build_"))
    os.environ["DBT_TARGET_PATH"] = str(workdir / "dbt_target")
    result = build(a.db, workdir, real)
    _load_export().export(a.db, a.out)
    write_job_summary(result, os.environ.get("GITHUB_STEP_SUMMARY"), lambda: datetime.now(UTC))
    return 0


if __name__ == "__main__":
    sys.exit(main())
