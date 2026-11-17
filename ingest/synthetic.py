"""Deterministic synthetic traffic-signal volumes in the SCATS layout (docs/data.md).

The layout mirrors a real monthly file (checked on October 2026, decisions D43): the published
columns, `-1` for an interval with no data, and, for `write_zip`, one `VSDATA_YYYYMMDD.csv` per
day. On the day Melbourne clocks go forward, V07 to V11 are `-1`, as in the real file.

Everything computed from this data is labelled `simulated`. The generator can inject faults so
that the data-quality checks have something to catch.
"""

from __future__ import annotations

import csv
import io
import math
import random
import zipfile
from collections.abc import Iterable
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

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
MISSING = "-1"  # how the real files mark an interval with no data
MELBOURNE = ZoneInfo("Australia/Melbourne")
CLOCK_GAP_INTERVALS = range(7, 12)  # V07 to V11 are -1 in the real file when clocks go forward
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
      * detector 1 of the first site has missing intervals (`-1`) on day 1,
      * one negative value other than -1 (`-5`) on the second site (if there is one, else the
        first); the real October file has none, but the API must still reject one,
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
                if clocks_go_forward(d):
                    for k in CLOCK_GAP_INTERVALS:
                        vols[k] = None
                rows.append(_row(site_id, d, str(det), vols, region, alarms=0))

    if faults and rows:
        _inject_faults(rows, site_ids, detectors, days)
    return rows


def clocks_go_forward(d: date) -> bool:
    """True on the day Melbourne moves from standard to daylight time."""
    start = datetime(d.year, d.month, d.day, tzinfo=MELBOURNE).utcoffset()
    end = (datetime(d.year, d.month, d.day, tzinfo=MELBOURNE) + timedelta(days=1)).utcoffset()
    return end > start


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
        row[name] = MISSING if v is None else str(v)
    return row


def _refresh(row: dict[str, str]) -> None:
    vals = [row[c] for c in VOLUME_COLUMNS if row[c] not in ("", MISSING)]
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
        gap[VOLUME_COLUMNS[k]] = MISSING
    _refresh(gap)
    # 2. a negative value
    neg_site = site_ids[1] if len(site_ids) > 1 else first
    neg = _find(rows, neg_site, "1", min(1, days - 1), start)
    neg[VOLUME_COLUMNS[34]] = "-5"
    _refresh(neg)
    # 3. alarm-heavy detector with gaps on day 1
    bad = _find(rows, last, str(detectors), 0, start)
    bad["CT_ALARM_24HOUR"] = "37"
    for k in range(40, 52):
        bad[VOLUME_COLUMNS[k]] = MISSING
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


def write_zip(rows: Iterable[dict[str, str]], path: Path) -> int:
    """Write rows as a monthly-style ZIP: one `VSDATA_YYYYMMDD.csv` per day, in row order."""
    by_day: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        by_day.setdefault(row["QT_INTERVAL_COUNT"], []).append(row)
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for day, day_rows in by_day.items():
            buffer = io.StringIO()
            writer = csv.DictWriter(buffer, fieldnames=COLUMNS, lineterminator="\r\n")
            writer.writeheader()
            writer.writerows(day_rows)
            zf.writestr(f"VSDATA_{day.replace('-', '')}.csv", buffer.getvalue())
    return sum(len(r) for r in by_day.values())


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
