"""Deterministic synthetic traffic-signal volumes in the SCATS column layout (docs/data.md).

Everything computed from this data is labelled `simulated`. The generator can inject faults so
that the data-quality checks have something to catch.
"""

from __future__ import annotations

import csv
import math
import random
from collections.abc import Iterable
from datetime import date, timedelta
from pathlib import Path

INTERVALS_PER_DAY = 96
VOLUME_COLUMNS = [f"V{i:02d}" for i in range(INTERVALS_PER_DAY)]
COLUMNS = [
    "NB_SCATS_SITE",
    "QT_INTERVAL_COUNT",
    "NB_DETECTOR",
    *VOLUME_COLUMNS,
    "NM_REGION",
    "CT_RECORDS",
    "QT_VOLUME_24HOUR",
    "CT_ALARM_24HOUR",
]
REGIONS = ["NORTH", "SOUTH", "EAST", "WEST"]
DEFAULT_START = date(2026, 3, 2)  # a Monday
DEFAULT_SEED = 20260310


def _shape(interval: int, weekend: bool) -> float:
    """Relative demand for one 15-minute interval: morning and evening peaks on weekdays."""
    hour = (interval + 0.5) / 4
    base = 0.08 + 0.12 * math.exp(-((hour - 13) ** 2) / 40)
    if weekend:
        return base + 0.55 * math.exp(-((hour - 13) ** 2) / 18)
    morning = 0.95 * math.exp(-((hour - 8.0) ** 2) / 2.2)
    evening = 1.0 * math.exp(-((hour - 17.0) ** 2) / 3.0)
    return base + morning + evening


def generate(
    sites: int = 3,
    detectors: int = 2,
    days: int = 3,
    start: date = DEFAULT_START,
    seed: int = DEFAULT_SEED,
    faults: bool = True,
) -> list[dict[str, str]]:
    """Return rows in the SCATS layout. Values are strings, as they would be read from a CSV.

    With `faults=True` the output contains, whenever there is enough data:
      * detector 1 of the first site has missing intervals (blank values) on day 1,
      * one negative value on the second site (if there is one, else the first),
      * the last detector of the last site reports many alarms (and gaps on day 1),
      * one row repeated exactly (a duplicate).
    """
    rng = random.Random(seed)
    rows: list[dict[str, str]] = []
    site_ids = [str(1000 + 7 * i) for i in range(sites)]
    for site_index, site_id in enumerate(site_ids):
        site_scale = 18 + 6 * rng.random() + 2 * site_index
        region = REGIONS[site_index % len(REGIONS)]
        for det in range(1, detectors + 1):
            det_scale = site_scale * (0.6 + 0.8 * rng.random())
            for day in range(days):
                d = start + timedelta(days=day)
                weekend = d.weekday() >= 5
                vols: list[int | None] = []
                for k in range(INTERVALS_PER_DAY):
                    mean = det_scale * _shape(k, weekend)
                    vols.append(max(0, round(rng.gauss(mean, math.sqrt(mean + 1)))))
                rows.append(_row(site_id, d, str(det), vols, region, alarms=0))

    if faults and rows:
        _inject_faults(rows, site_ids, detectors, days)
    return rows


def _row(
    site: str, d: date, det: str, vols: list[int | None], region: str, alarms: int
) -> dict[str, str]:
    present = [v for v in vols if v is not None]
    row = {
        "NB_SCATS_SITE": site,
        "QT_INTERVAL_COUNT": d.isoformat(),
        "NB_DETECTOR": det,
        "NM_REGION": region,
        "CT_RECORDS": str(len(present)),
        "QT_VOLUME_24HOUR": str(sum(v for v in present if v > 0)),
        "CT_ALARM_24HOUR": str(alarms),
    }
    for name, v in zip(VOLUME_COLUMNS, vols, strict=True):
        row[name] = "" if v is None else str(v)
    return row


def _refresh(row: dict[str, str]) -> None:
    vals = [row[c] for c in VOLUME_COLUMNS if row[c] != ""]
    row["CT_RECORDS"] = str(len(vals))
    row["QT_VOLUME_24HOUR"] = str(sum(int(v) for v in vals if int(v) > 0))


def _find(rows: list[dict[str, str]], site: str, det: str, day_index: int, start: date) -> dict:
    target = (start + timedelta(days=day_index)).isoformat()
    for r in rows:
        if (
            r["NB_SCATS_SITE"] == site
            and r["NB_DETECTOR"] == det
            and r["QT_INTERVAL_COUNT"] == target
        ):
            return r
    raise LookupError("row not found")


def _inject_faults(rows: list[dict[str, str]], site_ids: list[str], detectors: int, days: int):
    start = date.fromisoformat(rows[0]["QT_INTERVAL_COUNT"])
    first, last = site_ids[0], site_ids[-1]
    # 1. missing intervals: blank 12 consecutive intervals (03:00 to 06:00) for site 1 detector 1
    gap = _find(rows, first, "1", 0, start)
    for k in range(12, 24):
        gap[VOLUME_COLUMNS[k]] = ""
    _refresh(gap)
    # 2. a negative value
    neg_site = site_ids[1] if len(site_ids) > 1 else first
    neg = _find(rows, neg_site, "1", min(1, days - 1), start)
    neg[VOLUME_COLUMNS[34]] = "-1"
    _refresh(neg)
    # 3. alarm-heavy detector with gaps on day 1
    bad = _find(rows, last, str(detectors), 0, start)
    bad["CT_ALARM_24HOUR"] = "37"
    for k in range(40, 52):
        bad[VOLUME_COLUMNS[k]] = ""
    _refresh(bad)
    # 4. one exact duplicate row, placed right after the original
    index = rows.index(_find(rows, first, "1", min(1, days - 1), start))
    rows.insert(index + 1, dict(rows[index]))


def write_csv(rows: Iterable[dict[str, str]], path: Path) -> int:
    """Write rows with the SCATS header. Returns the number of rows written."""
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
            count += 1
    return count


def main() -> None:
    import argparse

    p = argparse.ArgumentParser(description="Write a synthetic SCATS-layout CSV.")
    p.add_argument("--out", type=Path, default=Path("data/synthetic/scats_synthetic.csv"))
    p.add_argument("--sites", type=int, default=5)
    p.add_argument("--detectors", type=int, default=4)
    p.add_argument("--days", type=int, default=14)
    p.add_argument("--seed", type=int, default=DEFAULT_SEED)
    p.add_argument("--clean", action="store_true", help="no injected faults")
    a = p.parse_args()
    n = write_csv(generate(a.sites, a.detectors, a.days, seed=a.seed, faults=not a.clean), a.out)
    print(f"wrote {n} rows to {a.out}")


if __name__ == "__main__":
    main()
