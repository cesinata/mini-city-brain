"""Evaluate the two baselines on a time-based holdout and write results/forecast_eval.json.

Holdout: the last `holdout_days` days of each site's data. The forecasts for the holdout use
only data before it. MAE and MAPE are computed per method over all sites. MAPE skips intervals
whose actual volume is zero (and says how many).

The result file carries a `data_source` and a `label`: results from synthetic data are labelled
`simulated` and are not headline numbers (CLAUDE.md rule 5).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from pathlib import Path

import duckdb

from forecast import baselines, store


def split_series(series: Mapping[datetime, float], holdout_days: int):
    end = max(series)
    cut = end - timedelta(days=holdout_days)
    train = {t: v for t, v in series.items() if t <= cut}
    test = {t: v for t, v in series.items() if t > cut}
    return train, test, cut


def evaluate_series(
    all_series: Mapping[str, Mapping[datetime, float]], holdout_days: int = 7
) -> dict:
    stats = {
        name: {"abs_error": 0.0, "pct_error": 0.0, "n": 0, "n_pct": 0, "skipped_zero_actual": 0}
        for name in baselines.METHODS
    }
    no_forecast = dict.fromkeys(baselines.METHODS, 0)
    sites_used = 0
    for series in all_series.values():
        if len(series) < 2:
            continue
        train, test, _ = split_series(series, holdout_days)
        if not train or not test:
            continue
        sites_used += 1
        for target, actual in test.items():
            for name, fn in baselines.METHODS.items():
                pred = fn(train, target)
                if pred is None:
                    no_forecast[name] += 1
                    continue
                s = stats[name]
                s["abs_error"] += abs(pred - actual)
                s["n"] += 1
                if actual == 0:
                    s["skipped_zero_actual"] += 1
                else:
                    s["pct_error"] += abs(pred - actual) / actual
                    s["n_pct"] += 1
    methods = {}
    for name, s in stats.items():
        methods[name] = {
            "points_evaluated": s["n"],
            "points_without_forecast": no_forecast[name],
            "mae": round(s["abs_error"] / s["n"], 4) if s["n"] else None,
            "mape_percent": round(100 * s["pct_error"] / s["n_pct"], 4) if s["n_pct"] else None,
            "mape_skipped_zero_actuals": s["skipped_zero_actual"],
        }
    return {"holdout_days": holdout_days, "sites_evaluated": sites_used, "methods": methods}


def run(
    db_path: str, out_path: Path, holdout_days: int = 7, data_source: str | None = None
) -> dict:
    con = duckdb.connect(db_path)
    try:
        series = store.load_series(con)
        if data_source is None:
            row = con.execute(
                "select min(source), max(source) from main.fct_volume_15min"
            ).fetchone()
            data_source = "synthetic" if row[0] == row[1] == "synthetic" else "real"
    finally:
        con.close()
    result = evaluate_series(series, holdout_days)
    result["data_source"] = data_source
    result["label"] = "simulated" if data_source == "synthetic" else "measured (host CPU)"
    result["units"] = "vehicles per 15-minute interval per site (sum over detectors)"
    result["note"] = (
        "Synthetic data: not a headline result."
        if data_source == "synthetic"
        else "Real data, one run on the host machine."
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2) + "\n")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Evaluate the baseline forecasts.")
    p.add_argument("--db", default="data/warehouse/mcb.duckdb")
    p.add_argument("--out", type=Path, default=Path("results/forecast_eval.json"))
    p.add_argument("--holdout-days", type=int, default=7)
    a = p.parse_args(argv)
    print(json.dumps(run(a.db, a.out, a.holdout_days), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
