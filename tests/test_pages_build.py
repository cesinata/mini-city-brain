from __future__ import annotations

import zipfile
from datetime import UTC, date, datetime
from pathlib import Path

import duckdb
import pytest

from ingest import synthetic
from scripts import pages_build


class FakeHttp:
    """Stands in for the CKAN API and the file download. No network is used."""

    def __init__(self, csv_path: Path | None, fail: bool = False) -> None:
        self.csv_path = csv_path
        self.fail = fail
        self.downloads: list[str] = []

    def get_json(self, url: str) -> dict:
        if self.fail:
            raise OSError("network down")
        return {
            "result": {
                "resources": [
                    {
                        "name": "2026-01",
                        "url": "https://x/2026-01.zip",
                        "last_modified": "2026-02-01",
                    },
                    {
                        "name": "2026-02",
                        "url": "https://x/2026-02.zip",
                        "last_modified": "2026-03-01",
                    },
                    {"name": "readme", "url": "https://x/readme.pdf"},
                ]
            }
        }

    def download(self, url: str, dest: Path) -> Path:
        self.downloads.append(url)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(dest, "w") as zf:
            zf.write(self.csv_path, arcname="volumes.csv")
        return dest


def make_csv(tmp_path: Path, faults: bool, sites: int = 3, days: int = 42) -> Path:
    path = tmp_path / "source.csv"
    synthetic.write_csv(synthetic.generate(sites, 1, days, faults=faults), path)
    return path


def labels(db: str) -> set[str]:
    con = duckdb.connect(db)
    try:
        return {
            r[0]
            for r in con.execute("select distinct source from main.fct_volume_15min").fetchall()
        }
    finally:
        con.close()


def test_latest_zip_resource_picks_the_newest_zip():
    res = pages_build.latest_zip_resource(FakeHttp(None).get_json(""))
    assert res["name"] == "2026-02"


def _zip(name: str, modified: str) -> dict:
    return {"name": name, "url": f"https://x/{name}.zip", "last_modified": modified}


def test_latest_zip_resource_prefers_the_newest_month_that_has_ended():
    package = {"result": {"resources": [
        _zip("traffic_signal_volume_data_september_2026", "2026-10-01"),
        _zip("traffic_signal_volume_data_october_2026", "2026-11-01"),
        _zip("traffic_signal_volume_data_november_2026", "2026-11-17"),
    ]}}  # fmt: skip
    pick = pages_build.latest_zip_resource(package, today=date(2026, 11, 17))
    assert pick["name"] == "traffic_signal_volume_data_october_2026"
    first_of_december = pages_build.latest_zip_resource(package, today=date(2026, 12, 1))
    assert first_of_december["name"] == "traffic_signal_volume_data_november_2026"


def test_resource_month_reads_names_and_urls():
    name = "Traffic Signal Volume Data October 2026"
    assert pages_build.resource_month({"name": name}) == (2026, 10)
    assert pages_build.resource_month({"url": "https://x/VSDATA_2026-09.zip"}) == (2026, 9)
    assert pages_build.resource_month({"name": "Sept-2025"}) == (2025, 9)
    assert pages_build.resource_month({"name": "readme", "url": "https://x/data.zip"}) is None


def test_latest_zip_resource_falls_back_to_last_modified_without_a_month():
    package = {"result": {"resources": [_zip("a", "2026-01-01"), _zip("b", "2026-03-01")]}}
    assert pages_build.latest_zip_resource(package, today=date(2026, 11, 17))["name"] == "b"
    only_current = {"result": {"resources": [_zip("november_2026", "2026-11-17")]}}
    pick = pages_build.latest_zip_resource(only_current, today=date(2026, 11, 17))
    assert pick["name"] == "november_2026"


def test_latest_zip_resource_errors_when_there_is_no_zip():
    with pytest.raises(LookupError):
        pages_build.latest_zip_resource({"result": {"resources": [{"url": "https://x/a.pdf"}]}})


def test_load_top_sites_keeps_only_the_busiest_and_drops_impossible_values(tmp_path):
    csv = make_csv(tmp_path, faults=True, sites=4, days=3)
    db = str(tmp_path / "w.duckdb")
    counts = pages_build.load_top_sites(csv, db, top_n=2)
    assert counts["sites_kept"] == 2
    assert counts["dropped_out_of_range"] >= 0
    con = duckdb.connect(db)
    sites = {r[0] for r in con.execute("select distinct site_id from raw.readings").fetchall()}
    sources = {r[0] for r in con.execute("select distinct source from raw.readings").fetchall()}
    negatives = con.execute("select count(*) from raw.readings where volume < 0").fetchone()[0]
    con.close()
    assert len(sites) == 2
    assert sources == {"scats"}
    assert negatives == 0


def test_real_disabled_builds_synthetic_and_says_why(tmp_path):
    db = str(tmp_path / "pages.duckdb")
    result = pages_build.build(db, tmp_path / "work", real_enabled=False)
    assert result.label == "synthetic"
    assert any("REAL_DATA_ENABLED" in w for w in result.warnings)
    assert labels(db) == {"synthetic"}


def test_real_enabled_with_a_good_file_builds_real(tmp_path):
    http = FakeHttp(make_csv(tmp_path, faults=False))
    db = str(tmp_path / "pages.duckdb")
    result = pages_build.build(db, tmp_path / "work", real_enabled=True, http=http)
    assert result.label == "real", result.warnings
    assert result.warnings == []
    assert http.downloads == ["https://x/2026-02.zip"]
    assert labels(db) == {"scats"}
    assert result.detail["load"]["readings"] > 0


def test_download_failure_falls_back_to_synthetic_with_a_warning(tmp_path):
    db = str(tmp_path / "pages.duckdb")
    result = pages_build.build(
        db, tmp_path / "work", real_enabled=True, http=FakeHttp(None, fail=True)
    )
    assert result.label == "synthetic"
    assert len(result.warnings) == 1
    assert "could not be used" in result.warnings[0] and "network down" in result.warnings[0]
    assert labels(db) == {"synthetic"}


def test_failed_checks_on_real_data_fall_back_to_synthetic_with_the_reason(tmp_path):
    http = FakeHttp(make_csv(tmp_path, faults=True))
    db = str(tmp_path / "pages.duckdb")
    result = pages_build.build(db, tmp_path / "work", real_enabled=True, http=http)
    assert result.label == "synthetic"
    assert "pipeline checks failed" in result.warnings[0]
    assert "PIPELINE FAILED" in result.warnings[0]
    assert labels(db) == {"synthetic"}


def test_job_summary_and_warning_annotations(tmp_path, capsys):
    result = pages_build.BuildResult("synthetic", ["Real data could not be used (X: y).\nmore"])
    summary = tmp_path / "summary.md"
    pages_build.write_job_summary(result, str(summary), lambda: datetime(2026, 3, 1, tzinfo=UTC))
    text = summary.read_text()
    assert "Data label: **synthetic**" in text and "WARNING: Real data could not be used" in text
    assert "::warning::Real data could not be used (X: y)." in capsys.readouterr().out


def test_workflow_files_use_least_privilege_and_pinned_actions():
    import re

    import yaml

    root = Path(__file__).resolve().parent.parent / ".github/workflows"
    for name in ("ci.yml", "pages.yml"):
        text = (root / name).read_text()
        assert yaml.safe_load(text)["permissions"] == {"contents": "read"}
        for use in re.findall(r"uses:\s*(\S+)", text):
            assert re.search(r"@v\d+\.\d+\.\d+$", use), f"{name}: {use} is not pinned to a full tag"
    pages = yaml.safe_load((root / "pages.yml").read_text())
    deploy = pages["jobs"]["deploy"]["permissions"]
    assert deploy == {"pages": "write", "id-token": "write", "contents": "read"}
    on = pages.get(True) or pages["on"]
    assert "workflow_dispatch" in on and "schedule" in on
    assert "vars.REAL_DATA_ENABLED" in (root / "pages.yml").read_text()
