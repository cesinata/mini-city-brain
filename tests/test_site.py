from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
import sys
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import duckdb
import httpx
import jsonschema
import pytest

from orchestration.definitions import PipelineSettings, parse_manifest
from orchestration.run import run_pipeline
from tests.helpers import run_dbt, synthetic_readings
from warehouse import load as wh

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"

spec = importlib.util.spec_from_file_location("site_export", SITE / "export.py")
export = importlib.util.module_from_spec(spec)
sys.modules["site_export"] = export
spec.loader.exec_module(export)


@pytest.fixture(scope="module")
def warehouse(tmp_path_factory) -> str:
    """Six weeks of clean synthetic data, built by the real pipeline."""
    tmp = tmp_path_factory.mktemp("site")
    db = str(tmp / "wh.duckdb")
    settings = PipelineSettings(
        db_path=db,
        source="synthetic",
        synthetic_sites=12,
        synthetic_detectors=1,
        synthetic_days=42,
        replay_clock="2026-04-13T00:00:00+00:00",
        dbt_target_path=str(tmp / "dbt"),
    )
    result = run_pipeline(settings, parse_manifest(tmp / "manifest"))
    assert result.success, result.failures
    return db


@pytest.fixture(scope="module")
def summary(warehouse, tmp_path_factory) -> dict:
    out = tmp_path_factory.mktemp("out")
    path = export.export(warehouse, out)
    return json.loads(path.read_text())


def test_summary_validates_against_the_schema(summary):
    schema = json.loads((SITE / "schema.json").read_text())
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(summary, schema)


def test_synthetic_label_is_set_and_attribution_matches(summary):
    assert summary["data_label"] == "synthetic"
    assert "Synthetic data" in summary["source"]
    assert any("Synthetic data" in a for a in summary["attribution"])
    assert not any("CC BY" in a for a in summary["attribution"])
    for site in summary["forecast"]["sites"]:
        assert site["mae_label"] == "simulated"


def test_top_sites_are_at_most_20_and_sorted(summary):
    top = summary["top_sites"]
    assert len(top) == 12  # the fixture has 12 sites; the cap is 20
    volumes = [t["total_volume"] for t in top]
    assert volumes == sorted(volumes, reverse=True)
    assert [t["rank"] for t in top] == list(range(1, 13))


def test_heatmap_is_7_by_24_with_weekday_peaks(summary):
    values = summary["heatmap"]["values"]
    assert len(values) == 7 and all(len(row) == 24 for row in values)
    monday = values[0]
    assert monday[8] > 2 * monday[3]  # morning peak against the small hours
    assert summary["heatmap"]["weekdays"][0] == "Mon"


def test_forecast_has_up_to_10_sites_with_week_of_points(summary):
    fc = summary["forecast"]
    assert fc["available"] is True
    assert 1 <= len(fc["sites"]) <= 10
    site = fc["sites"][0]
    assert 160 <= len(site["points"]) <= 170  # 7 days of hours, plus an edge hour
    assert site["mae_15min"]["seasonal_naive"] is not None


def test_completeness_is_one_on_clean_data(summary):
    assert all(c["completeness"] == 1.0 for c in summary["completeness"])


def test_summary_is_small(warehouse, tmp_path):
    path = export.export(warehouse, tmp_path)
    assert path.stat().st_size < 2 * 1024 * 1024


def test_architecture_diagram_is_copied_next_to_the_summary(warehouse, tmp_path):
    export.export(warehouse, tmp_path)
    assert (tmp_path / "architecture.svg").exists()


def test_short_history_means_forecast_unavailable_not_invented(tmp_path):
    db = tmp_path / "short.duckdb"
    con = wh.connect(db)
    wh.insert_readings(con, synthetic_readings(tmp_path, sites=2, detectors=1, days=2), "k")
    con.close()
    ok, _ = run_dbt(db, tmp_path, "build")
    assert ok
    summary = export.build_summary(str(db))
    export.validate(summary)
    assert summary["forecast"]["available"] is False
    assert summary["forecast"]["sites"] == []
    assert summary["forecast"]["reason"]


def test_real_label_when_source_is_scats(tmp_path):
    db = tmp_path / "real.duckdb"
    con = wh.connect(db)
    readings = [
        {**r, "source": "scats"}
        for r in synthetic_readings(tmp_path, sites=2, detectors=1, days=42)
    ]
    wh.insert_readings(con, readings, "k")
    con.close()
    ok, _ = run_dbt(db, tmp_path, "build")
    assert ok
    summary = export.build_summary(str(db))
    export.validate(summary)
    assert summary["data_label"] == "real"
    assert any("CC BY 4.0" in a for a in summary["attribution"])
    assert {s["mae_label"] for s in summary["forecast"]["sites"]} == {"measured (host CPU)"}


@pytest.mark.parametrize(
    "mutate",
    [
        lambda s: s.pop("data_label"),
        lambda s: s.update(data_label="maybe"),
        lambda s: s.update(top_sites=s["top_sites"] * 3),
        lambda s: s["heatmap"].update(values=s["heatmap"]["values"][:6]),
        lambda s: s.update(extra="x"),
        lambda s: s["completeness"][0].update(completeness=1.5),
    ],
)
def test_schema_rejects_bad_documents(summary, mutate):
    bad = json.loads(json.dumps(summary))
    mutate(bad)
    with pytest.raises(jsonschema.ValidationError):
        export.validate(bad)


# ---- the page ------------------------------------------------------------------------------


@pytest.fixture
def served(warehouse, tmp_path):
    """Copy the page to a temp folder, add data/, and serve it over HTTP."""
    root = tmp_path / "public"
    shutil.copytree(SITE, root, ignore=shutil.ignore_patterns("data", "__pycache__", "*.py"))
    export.export(warehouse, root / "data")
    handler = partial(SimpleHTTPRequestHandler, directory=str(root))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", root
    finally:
        server.shutdown()


def test_page_and_summary_are_served_and_the_page_names_its_parts(served):
    base, _ = served
    page = httpx.get(base + "/index.html")
    assert page.status_code == 200
    html = page.text
    assert "When are Melbourne's signalised intersections busiest" in html
    for needle in (
        "Busiest intersections",
        "Hour by weekday",
        "Forecast against actual",
        "How it works",
    ):
        assert needle in html
    assert 'src="app.js"' in html and 'href="style.css"' in html
    assert '<script src="http' not in html  # no third-party scripts
    data = httpx.get(base + "/data/summary.json").json()
    assert data["data_label"] == "synthetic"
    assert httpx.get(base + "/data/architecture.svg").status_code == 200
    hero = httpx.get(base + "/data/hero-isometric.svg")
    assert hero.status_code == 200
    assert hero.headers["content-type"].startswith("image/svg+xml")
    assert httpx.get(base + "/app.js").status_code == 200


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_app_js_renders_without_errors_against_a_fake_dom(served):
    _, root = served
    smoke = str(ROOT / "tests/site_dom_smoke.js")
    args = ["node", smoke, str(root / "data/summary.json"), str(root / "app.js")]
    done = subprocess.run(args, capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    out = json.loads(done.stdout.strip().splitlines()[-1])
    assert "SYNTHETIC DATA" in out["banner"]
    assert out["busiest"] == 1 and out["heat"] == 1 and out["forecast"] >= 1
    assert "Synthetic data" in out["attribution"]


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_app_js_has_valid_syntax():
    done = subprocess.run(
        ["node", "--check", str(SITE / "app.js")], capture_output=True, text=True, timeout=30
    )
    assert done.returncode == 0, done.stderr


def test_duckdb_connection_is_closed_after_export(warehouse):
    # export() must not leave the warehouse locked for the next writer
    con = duckdb.connect(warehouse)
    con.close()


# ---- images in the README and on the page ---------------------------------------------------

HERO_ALT = (
    "Isometric city feeding a pipeline of eight stages (replay, API, queue, worker, raw bucket, "
    "DuckDB and dbt, checks, forecast) that ends at a dashboard."
)
MD_IMAGE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)\)")
IMG_TAG = re.compile(r"<img\b[^>]*>")


def _attr(tag: str, name: str) -> str:
    match = re.search(rf'\b{name}="([^"]*)"', tag)
    assert match, f"{name} missing in {tag}"
    return match.group(1)


def _readme_images() -> list[tuple[str, str]]:
    text = (ROOT / "README.md").read_text()
    found = MD_IMAGE.findall(text)
    found += [(_attr(t, "alt"), _attr(t, "src")) for t in IMG_TAG.findall(text)]
    return [(alt, src) for alt, src in found if not src.startswith(("http://", "https://"))]


def _page_images() -> list[tuple[str, str]]:
    tags = IMG_TAG.findall((SITE / "index.html").read_text())
    return [(_attr(t, "alt"), _attr(t, "src")) for t in tags]


def test_readme_image_paths_resolve_to_files():
    images = _readme_images()
    assert images
    for _, src in images:
        assert (ROOT / src).is_file(), f"README image {src} does not exist"


def test_page_image_paths_resolve_to_files():
    """data/ is written by site/export.py, which copies these images from docs/media/."""
    images = _page_images()
    assert images
    for _, src in images:
        if src.startswith("data/"):
            name = src.removeprefix("data/")
            assert name in export.MEDIA_FILES, f"{src} is not copied by site/export.py"
            assert (ROOT / "docs" / "media" / name).is_file(), f"docs/media/{name} is missing"
        else:
            assert (SITE / src).is_file(), f"page image {src} does not exist"


def test_hero_uses_one_file_and_one_alt_text_in_readme_and_page():
    readme = {src: alt for alt, src in _readme_images()}
    page = {src: alt for alt, src in _page_images()}
    assert readme["docs/media/hero-isometric.svg"] == HERO_ALT
    assert page["data/hero-isometric.svg"] == HERO_ALT
    assert (ROOT / "docs/media/hero-isometric.svg").stat().st_size < 2 * 1024 * 1024


def test_every_media_file_is_copied_next_to_the_summary(warehouse, tmp_path):
    export.export(warehouse, tmp_path)
    for name in export.MEDIA_FILES:
        copied = tmp_path / name
        assert copied.read_bytes() == (ROOT / "docs" / "media" / name).read_bytes()


def test_desktop_layout_places_every_section_and_keeps_one_column_below_it():
    css = (SITE / "style.css").read_text()
    html = (SITE / "index.html").read_text()
    match = re.search(r"@media \(min-width: (\d+)px\) \{(.*?)\n\}", css, re.S)
    assert match, "no desktop media query in site/style.css"
    assert int(match.group(1)) >= 900  # phones and small tablets keep the single column
    desktop = match.group(2)
    areas = set(re.findall(r"main > \.(s-[a-z]+) \{ grid-area: [a-z]+; \}", desktop))
    sections = set(re.findall(r'<section class="(s-[a-z]+)"', html))
    assert sections and areas == sections
