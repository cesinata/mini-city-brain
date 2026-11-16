from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import duckdb
import pytest
from fastapi.testclient import TestClient

from forecast import baselines, evaluate, store
from services.api.forecast_provider import DuckDbForecastProvider
from services.api.main import create_app
from services.api.ports import InMemoryPublisher, StaticProbe

T0 = datetime(2026, 1, 5, 0, 15, tzinfo=UTC)
WEEK = timedelta(days=7)


def weekly_series(weeks: int, value=lambda w, k: 100.0, steps: int = 96) -> dict:
    """`weeks` weeks of data, `steps` 15-minute intervals per day."""
    out = {}
    for w in range(weeks):
        for d in range(7):
            for k in range(steps):
                out[T0 + w * WEEK + timedelta(days=d, minutes=15 * k)] = value(w, k)
    return out


# ---- baselines -----------------------------------------------------------------------------


def test_seasonal_naive_is_the_same_interval_one_week_earlier():
    series = {T0: 10.0, T0 + WEEK: 20.0}
    assert baselines.seasonal_naive(series, T0 + WEEK) == 10.0
    assert baselines.seasonal_naive(series, T0 + 2 * WEEK) == 20.0
    assert baselines.seasonal_naive(series, T0 + timedelta(days=3)) is None


def test_trailing_mean_averages_previous_four_weeks_only():
    series = {T0 + i * WEEK: float(v) for i, v in enumerate([10, 20, 30, 40, 1000])}
    # Target is week 5: uses weeks 1 to 4 (20, 30, 40, 1000), not week 0.
    assert baselines.trailing_mean(series, T0 + 5 * WEEK) == (20 + 30 + 40 + 1000) / 4
    # Target is week 4: uses weeks 0 to 3.
    assert baselines.trailing_mean(series, T0 + 4 * WEEK) == 25.0


def test_trailing_mean_uses_the_weeks_that_exist():
    series = {T0: 10.0, T0 + 2 * WEEK: 30.0}
    assert baselines.trailing_mean(series, T0 + 3 * WEEK) == 20.0  # weeks 0 and 2; 1 is missing
    assert baselines.trailing_mean({}, T0) is None


def test_forecast_never_uses_the_future():
    series = {T0: 1.0, T0 + WEEK: 2.0, T0 + 2 * WEEK: 999.0}
    assert baselines.seasonal_naive(series, T0 + WEEK) == 1.0
    assert baselines.trailing_mean(series, T0 + WEEK) == 1.0


def test_forecast_steps_walks_forward_in_15_minute_steps():
    series = weekly_series(2, steps=96)
    last = max(series)
    pts = baselines.forecast_steps(series, last, 4)
    assert [p["interval_end"] - last for p in pts] == [
        timedelta(minutes=15 * i) for i in range(1, 5)
    ]
    assert all(p["seasonal_naive"] == 100.0 for p in pts)


# ---- evaluation ----------------------------------------------------------------------------


def test_perfect_weekly_pattern_has_zero_error():
    result = evaluate.evaluate_series({"1": weekly_series(5)}, holdout_days=7)
    for m in result["methods"].values():
        assert m["mae"] == 0.0 and m["mape_percent"] == 0.0
        assert m["points_evaluated"] == 7 * 96


def test_known_errors_give_known_mae_and_mape():
    # 5 weeks. Weeks 0 to 3 are 100. The holdout week (week 4) is 120.
    series = weekly_series(5, value=lambda w, k: 120.0 if w == 4 else 100.0)
    result = evaluate.evaluate_series({"1": series}, holdout_days=7)
    sn = result["methods"]["seasonal_naive"]
    tm = result["methods"]["trailing_mean_4w"]
    # Seasonal naive predicts week 3 (100) for week 4 (120): error 20, 20/120 = 16.67 %.
    assert sn["mae"] == 20.0
    assert sn["mape_percent"] == pytest.approx(100 * 20 / 120, abs=1e-3)
    assert tm["mae"] == 20.0


def test_time_split_is_by_time_and_has_no_overlap():
    series = weekly_series(5)
    train, test, cut = evaluate.split_series(series, 7)
    assert max(train) <= cut < min(test)
    assert len(train) + len(test) == len(series)
    assert len(test) == 7 * 96


def test_zero_actuals_are_skipped_for_mape_and_counted():
    series = weekly_series(5, value=lambda w, k: 0.0 if (w == 4 and k < 10) else 50.0)
    m = evaluate.evaluate_series({"1": series}, 7)["methods"]["seasonal_naive"]
    assert m["mape_skipped_zero_actuals"] == 10 * 7  # 10 zero intervals on each of 7 days
    assert m["points_evaluated"] == 7 * 96
    assert m["mape_percent"] is not None


def test_points_without_history_are_counted_not_guessed():
    series = weekly_series(1)  # one week only: nothing a week earlier for the holdout
    m = evaluate.evaluate_series({"1": series}, 3)["methods"]["seasonal_naive"]
    assert m["points_evaluated"] == 0
    assert m["points_without_forecast"] == 3 * 96
    assert m["mae"] is None


def make_db(path, source: str = "synthetic", weeks: int = 5, sites=("1", "2")) -> str:
    con = duckdb.connect(str(path))
    con.execute(
        "create table main.fct_volume_15min (site_id varchar, detector_id varchar, "
        "interval_end timestamp, volume integer, source varchar)"
    )
    series = weekly_series(weeks, value=lambda w, k: 100 + k)
    rows = [
        (s, d, t.replace(tzinfo=None), int(v) // 2, source)
        for s in sites
        for t, v in series.items()
        for d in ("1", "2")
    ]
    con.executemany("insert into main.fct_volume_15min values (?, ?, ?, ?, ?)", rows)
    con.close()
    return str(path)


def test_run_writes_a_labelled_result_file_for_synthetic_data(tmp_path):
    db = make_db(tmp_path / "w.duckdb")
    out = tmp_path / "results" / "forecast_eval.json"
    result = evaluate.run(db, out, holdout_days=7)
    saved = json.loads(out.read_text())
    assert saved == result
    assert saved["data_source"] == "synthetic"
    assert saved["label"] == "simulated"
    assert saved["sites_evaluated"] == 2
    assert saved["methods"]["seasonal_naive"]["mae"] == 0.0


def test_real_data_label_is_measured(tmp_path):
    db = make_db(tmp_path / "w.duckdb", source="scats")
    result = evaluate.run(db, tmp_path / "r.json", holdout_days=7)
    assert result["data_source"] == "real"
    assert result["label"] == "measured (host CPU)"


def test_store_sums_detectors_per_site(tmp_path):
    db = make_db(tmp_path / "w.duckdb", weeks=1, sites=("1",))
    con = duckdb.connect(db)
    series = store.load_series(con)
    con.close()
    assert series["1"][T0.replace(tzinfo=None)] == 100.0  # two detectors of 50 each


# ---- endpoint ------------------------------------------------------------------------------


@pytest.fixture
def api(tmp_path):
    db = make_db(tmp_path / "w.duckdb", weeks=5)
    app = create_app(
        InMemoryPublisher(), StaticProbe(), forecast_provider=DuckDbForecastProvider(db)
    )
    return TestClient(app)


def test_forecast_endpoint_returns_both_baselines(api):
    resp = api.get("/v1/sites/1/forecast", params={"horizon": 8})
    assert resp.status_code == 200
    body = resp.json()
    assert body["site_id"] == "1" and body["horizon"] == 8
    assert body["data_source"] == "synthetic"
    assert len(body["points"]) == 8
    last = datetime.fromisoformat(body["last_observed"])
    first = datetime.fromisoformat(body["points"][0]["interval_end"])
    assert first - last == timedelta(minutes=15)
    assert body["points"][0]["seasonal_naive"] is not None
    assert body["points"][0]["trailing_mean_4w"] is not None


def test_forecast_default_horizon_is_one_day(api):
    assert len(api.get("/v1/sites/2/forecast").json()["points"]) == 96


@pytest.mark.parametrize("horizon", [0, -1, 673, "abc"])
def test_forecast_rejects_bad_horizon(api, horizon):
    assert api.get("/v1/sites/1/forecast", params={"horizon": horizon}).status_code == 422


def test_forecast_unknown_site_is_404(api):
    resp = api.get("/v1/sites/999/forecast")
    assert resp.status_code == 404
    assert resp.json()["error"] == "site_not_found"


def test_forecast_rejects_bad_site_id(api):
    assert api.get("/v1/sites/abc/forecast").status_code == 422


def test_forecast_without_warehouse_is_503_without_details(tmp_path):
    missing = DuckDbForecastProvider(str(tmp_path / "nope.duckdb"))
    client = TestClient(create_app(InMemoryPublisher(), StaticProbe(), forecast_provider=missing))
    resp = client.get("/v1/sites/1/forecast")
    assert resp.status_code == 503
    assert resp.json()["error"] == "warehouse_unavailable"
    assert "nope" not in resp.text
    assert (
        TestClient(create_app(InMemoryPublisher(), StaticProbe()))
        .get("/v1/sites/1/forecast")
        .status_code
        == 503
    )


def test_forecast_503_when_marts_are_not_built(tmp_path):
    db = tmp_path / "empty.duckdb"
    duckdb.connect(str(db)).close()
    client = TestClient(
        create_app(
            InMemoryPublisher(), StaticProbe(), forecast_provider=DuckDbForecastProvider(str(db))
        )
    )
    assert client.get("/v1/sites/1/forecast").status_code == 503
