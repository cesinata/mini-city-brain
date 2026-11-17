"""Read SCATS traffic-signal volume files (CSV or monthly ZIP) and unpivot them into readings.

One input row is one detector on one day with 96 volume columns (V00 to V95). One output
reading is one detector in one 15-minute interval, with `interval_end` in UTC.

Checked against a real monthly file (October 2026, docs/data.md and decisions D43):

* A monthly ZIP holds one CSV per day, `VSDATA_YYYYMMDD.csv`, every one with the published header.
* `QT_INTERVAL_COUNT` is a plain date (`2026-10-01`).
* A missing interval is `-1`, not a blank. It produces no reading and is counted. Any other
  negative value is passed through, so the API rejects it and says why.
* The 96 intervals follow Melbourne wall-clock time, daylight saving included, so the default
  zone is `Australia/Melbourne`. On the day clocks go forward, intervals that start inside the
  clock gap (V08 to V11) are skipped and counted; the real file has `-1` for V07 to V11 there.
  `tz="AEST"` reads them as a fixed UTC+10 offset instead, as the data dictionary's wording
  suggests.

The reader stays defensive: it logs what it finds, skips rows it cannot read and counts them.
"""

from __future__ import annotations

import csv
import io
import logging
import re
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

log = logging.getLogger("mcb.ingest.scats")

AEST = timezone(timedelta(hours=10), "AEST")
DEFAULT_TZ = "Australia/Melbourne"
MISSING = -1  # how the real files mark an interval with no data
V_COLUMN = re.compile(r"^V(\d{2})$")
DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y %H:%M:%S")


def resolve_tz(tz: str) -> timezone | ZoneInfo:
    if tz.upper() == "AEST":
        return AEST
    return ZoneInfo(tz)


@dataclass
class ReadStats:
    """What the reader found. Logged at the end of a read and returned for tests."""

    files: list[str] = field(default_factory=list)
    columns_seen: list[str] = field(default_factory=list)
    volume_columns: int = 0
    rows_read: int = 0
    rows_skipped: int = 0
    skip_reasons: dict[str, int] = field(default_factory=dict)
    readings: int = 0
    blank_intervals: int = 0
    missing_intervals: int = 0  # value -1
    nonexistent_local_times: int = 0  # intervals that fall in the clock gap of a DST change
    unreadable_values: int = 0

    def skip(self, reason: str) -> None:
        self.rows_skipped += 1
        self.skip_reasons[reason] = self.skip_reasons.get(reason, 0) + 1


def _parse_date(text: str) -> date | None:
    text = text.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _csv_members(path: Path, stats: ReadStats) -> Iterator[tuple[str, io.TextIOBase]]:
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as zf:
            names = sorted(n for n in zf.namelist() if n.lower().endswith(".csv"))
            for name in names:
                stats.files.append(name)
                with zf.open(name) as raw:
                    yield name, io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")
    else:
        stats.files.append(path.name)
        with path.open(encoding="utf-8-sig", newline="") as fh:
            yield path.name, fh


def read_rows(path: Path, stats: ReadStats | None = None) -> Iterator[dict[str, str]]:
    """Yield input rows with upper-cased, stripped column names."""
    stats = stats if stats is not None else ReadStats()
    for name, handle in _csv_members(Path(path), stats):
        reader = csv.DictReader(handle)
        header = [(h or "").strip().upper() for h in (reader.fieldnames or [])]
        if not stats.columns_seen:
            stats.columns_seen = header
            stats.volume_columns = sum(1 for h in header if V_COLUMN.match(h))
        for needed in ("NB_SCATS_SITE", "QT_INTERVAL_COUNT", "NB_DETECTOR"):
            if needed not in header:
                log.warning("column missing", extra={"file": name, "column": needed})
        reader.fieldnames = header
        for row in reader:
            stats.rows_read += 1
            yield {(k or ""): (v or "") for k, v in row.items() if k is not None}
    log.info(
        "scats read",
        extra={
            "files": stats.files,
            "volume_columns": stats.volume_columns,
            "rows_read": stats.rows_read,
        },
    )


def _wall(day: date, minutes: int) -> datetime:
    return datetime(day.year, day.month, day.day) + timedelta(minutes=minutes)


def _exists(naive: datetime, tz: timezone | ZoneInfo) -> bool:
    """False for a wall-clock time inside the gap when clocks go forward."""
    aware = naive.replace(tzinfo=tz)
    return aware.astimezone(UTC).astimezone(tz).replace(tzinfo=None) == naive


def interval_end_utc(day: date, index: int, tz: timezone | ZoneInfo) -> datetime | None:
    """End of interval `index` (0 for V00) on local calendar day `day`, in UTC.

    The index follows the wall clock: V00 starts at 00:00 local, V95 ends at the next local
    midnight. Each interval lasts 15 minutes of real time from its start. Returns None when the
    start does not exist on the clock (02:00 to 02:45 on the day daylight saving starts). When
    clocks go back, the repeated hour is read as its first occurrence (fold 0); a real file
    around that change has not been checked yet.
    """
    start = _wall(day, 15 * index)
    if not _exists(start, tz):
        return None
    return start.replace(tzinfo=tz).astimezone(UTC) + timedelta(minutes=15)


def unpivot(
    rows: Iterator[dict[str, str]],
    stats: ReadStats,
    source: str = "scats",
    tz: str = DEFAULT_TZ,
) -> Iterator[dict[str, Any]]:
    """Turn input rows into reading dictionaries for the API.

    `-1` and blank volumes are missing intervals and produce no reading. Any other negative
    volume is passed through, so that the API's validation rejects it and says why.
    """
    zone = resolve_tz(tz)
    ends_by_day: dict[date, list[str | None]] = {}
    for row in rows:
        site = row.get("NB_SCATS_SITE", "").strip()
        detector = row.get("NB_DETECTOR", "").strip()
        day = _parse_date(row.get("QT_INTERVAL_COUNT", ""))
        if not site or not detector:
            stats.skip("missing site or detector")
            continue
        if day is None:
            stats.skip("unreadable date")
            continue
        for column, raw in row.items():
            match = V_COLUMN.match(column)
            if not match:
                continue
            index = int(match.group(1))
            if index >= 96:
                continue
            text = raw.strip()
            if text == "":
                stats.blank_intervals += 1
                continue
            try:
                volume = int(float(text))
            except ValueError:
                stats.unreadable_values += 1
                continue
            if volume == MISSING:
                stats.missing_intervals += 1
                continue
            if day not in ends_by_day:
                ends_by_day[day] = [
                    end.isoformat() if (end := interval_end_utc(day, i, zone)) else None
                    for i in range(96)
                ]
            interval_end = ends_by_day[day][index]
            if interval_end is None:
                stats.nonexistent_local_times += 1
                continue
            stats.readings += 1
            yield {
                "site_id": site,
                "detector_id": detector,
                "interval_end": interval_end,
                "volume": volume,
                "source": source,
            }


def site_totals(path: Path) -> dict[str, int]:
    """Sum `QT_VOLUME_24HOUR` per site over every row (all detectors, all days).

    A blank daily total counts as 0. A value that is not a number is ignored.
    """
    totals: dict[str, int] = {}
    for row in read_rows(path):
        site = row.get("NB_SCATS_SITE", "").strip()
        if not site:
            continue
        try:
            totals[site] = totals.get(site, 0) + int(float(row.get("QT_VOLUME_24HOUR") or 0))
        except ValueError:
            continue
    return totals


def top_sites(path: Path, n: int) -> set[str] | None:
    """The `n` sites with the highest summed daily volume. Ties go to the lower site ID text.

    `n` of 0 or less means no limit and returns None.
    """
    if n <= 0:
        return None
    ranked = sorted(site_totals(path).items(), key=lambda kv: (-kv[1], kv[0]))
    return {site for site, _ in ranked[:n]}


def rows_for_sites(
    path: Path, sites: set[str] | None, stats: ReadStats | None = None
) -> Iterator[dict[str, str]]:
    """Input rows, keeping only `sites` (all rows when `sites` is None)."""
    for row in read_rows(path, stats):
        if sites is None or row.get("NB_SCATS_SITE", "").strip() in sites:
            yield row


def read_readings(
    path: Path, source: str = "scats", tz: str = DEFAULT_TZ, sites: set[str] | None = None
) -> tuple[list[dict[str, Any]], ReadStats]:
    """Read a whole file. Returns readings sorted by interval end, and what was found.

    With `sites`, only rows for those sites are unpivoted.
    """
    stats = ReadStats()
    readings = list(unpivot(rows_for_sites(path, sites, stats), stats, source=source, tz=tz))
    readings.sort(key=lambda r: (r["interval_end"], r["site_id"], r["detector_id"]))
    return readings, stats
