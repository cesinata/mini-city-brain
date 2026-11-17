# Data

Raw and downloaded data is never committed: `data/` is gitignored. Tests and CI use synthetic data only.

## 1. Traffic Signal Volume Data (primary source)

- **Publisher:** Department of Transport and Planning, Victoria.
- **What it is:** Vehicle counts from SCATS loop detectors at traffic signals. Counts are aggregated into 15-minute periods per detector (per lane) at each signal site. Monthly ZIP files, updated daily.
- **Where:**
  - data.vic.gov.au dataset "Traffic Signal Volume Data"
  - publisher page: opendata.transport.vic.gov.au/dataset/traffic-signal-volume-data
- **Licence:** Creative Commons Attribution 4.0 International (http://creativecommons.org/licenses/by/4.0/). Listed on the data.vic.gov.au dataset and resource pages (seen 2026-11-10) and confirmed by me on the publisher's own page on 2026-11-17.
- **Attribution text:** "Contains Traffic Signal Volume Data from the Department of Transport and Planning (Victoria), licensed under CC BY 4.0."

### Columns

These come from the published data dictionary. The October 2026 file has exactly these 103 columns in this order (`results/real_data_inspection.txt`).

| Column | Meaning (from the data dictionary) |
| --- | --- |
| `NB_SCATS_SITE` | SCATS site ID (intersection number) |
| `QT_INTERVAL_COUNT` | Date reading, Australian Eastern Standard Time |
| `NB_DETECTOR` | SCATS detector ID |
| `V00` to `V95` | Volume per 15-minute increment; `V00` is 12:00 to 12:15 am |
| `NM_REGION` | SCATS region |
| `CT_RECORDS` | Number of 15-minute periods with data for the detector that day |
| `QT_VOLUME_24HOUR` | Sum of volume for the day |
| `CT_ALARM_24HOUR` | Number of detector alarms that day |

### What a real file shows (October 2026, checked 2026-11-17)

From a read-only scan of `traffic_signal_volume_data_october_2026.zip` (`results/real_data_inspection.txt`; measured (host CPU), one run; data real):

- **Layout:** one CSV per day, `VSDATA_20261001.csv` to `VSDATA_20261031.csv`, 31 files, 932,713,050 bytes unpacked. CRLF line endings, no byte-order mark, the header above in every file.
- **Date:** `QT_INTERVAL_COUNT` is a plain date, `2026-10-01`.
- **Missing intervals:** marked `-1`. There are no blanks. On 1 October, 398,633 of 11,465,760 values were `-1`, no other value was negative, and the largest value was 759. All 3,786 rows that were `-1` all day had `CT_ALARM_24HOUR = 96`.
- **Time zone:** Melbourne wall-clock time, daylight saving included, not fixed UTC+10. Daylight saving started on Sunday 4 October 2026 at 02:00. The morning peak stays at 08:00 local before (1 October) and after (5, 8 and 15 October); a fixed UTC+10 reading would move it to 07:00. On 4 October, V07 to V11 are `-1` for every row: the hour that did not exist on the clock, plus V07.
- **Not explained:** on Saturday 3 October, V08 to V11 (02:00 to 03:00) are also `-1` for every row. That is not a clock-change day.
- **`CT_RECORDS`** equals the number of intervals that are not `-1` in 113,187 of 119,435 rows on 1 October. **`QT_VOLUME_24HOUR`** equals their sum in 118,265 of 119,435 rows. Neither column feeds the checks; completeness is computed from the readings.
- **Not checked:** the day clocks go back (first Sunday of April), when 02:00 to 03:00 happens twice but a day still has 96 columns.

### How this repo uses it

- **Locally:** the owner downloads files into `data/raw/`.
- **Public demo page:** the GitHub Pages workflow downloads the latest month inside the runner, only when `REAL_DATA_ENABLED` is `true`. Only small aggregates are published, with the attribution line. Raw files are never published or committed.

Steps for the local path:

1. The owner downloads one monthly ZIP into `data/raw/`.
2. `python -m ingest.replay --file data/raw/<file>.zip` reads it, keeps the 20 sites with the highest summed `QT_VOLUME_24HOUR` (`--top-sites N`; `0` sends every site and prints a warning with the count), unpivots `V00` to `V95` into one row per site, detector and 15-minute interval, prints how many sites and readings it will send, and replays the rows into the API. The Pages build ranks sites with the same function (`ingest/scats.py`, `top_sites`).
3. Completeness and detector health are computed from the readings that arrive (intervals per detector and local day). `CT_RECORDS` and `CT_ALARM_24HOUR` are not used (decision D26).

## 2. Traffic-signal locations (for the map)

Two Department of Transport and Planning datasets on data.vic.gov.au look usable. Both are listed as CC BY 4.0 (seen 2026-11-10). **Owner to confirm on the publisher's page.**

- **"Traffic Lights":** columns include `SITE_NO`, `SITE_NAME` and `SITE_TYPE`. The resource page says the data was last updated in November 2020, so it may be stale.
- **"Victorian Traffic Signals":** created in 2025. Described as identifiers, type data and locations for all operational signal assets. Columns not yet checked.

Not yet known: whether `SITE_NO` equals `NB_SCATS_SITE`. The build measures the match rate, and the map is shown only above 80% (decision D12).

## 3. Map tiles (if a map is shown)

OpenStreetMap tiles need visible attribution and must follow the OSM tile usage policy. Owner to read that policy before the map goes live.

## 4. Synthetic data (tests and CI)

- Generated by a script in `ingest/` with a fixed seed. It uses the same columns as above.
- It mirrors the real layout: `-1` for a missing interval, CRLF line endings, and (with `write_zip`) one `VSDATA_YYYYMMDD.csv` per day. On the day Melbourne clocks go forward it writes `-1` for V07 to V11, as the real file does.
- It includes deliberate faults (missing intervals, one `-5` value, alarms, a duplicate row) so the checks have something to catch. The real October file has no negative value other than `-1`; the `-5` is there so the API's rejection path is exercised.
- Every number computed from it is labelled `simulated`.

## 5. Candidates not used yet

- **City of Melbourne "On-street Parking Bay Sensors":** near real-time bay occupancy with a `Lastupdated` field. Listed as CC BY on data.vic.gov.au. Owner to confirm the licence on the City of Melbourne page before use.
- **City of Melbourne "Pedestrian Counting System":** hourly counts. Mirrors list the licence as "Not specified" or "Other (Open)", so it stays out until the licence is confirmed on the publisher's page.

## 6. How the reader handles the real layout (decision D43)

- **Dates:** `QT_INTERVAL_COUNT` is parsed as `YYYY-MM-DD` (what the real file uses), `DD/MM/YYYY`, or either with a time. A row whose date does not parse is skipped and counted.
- **Missing intervals:** `-1` and blank produce no reading and are counted (`missing_intervals`, `blank_intervals`). A zero is a real zero. Any other negative value is passed to the API, which rejects it and says why.
- **Time zone:** `Australia/Melbourne` by default. `V00` starts at local midnight and each interval lasts 15 minutes of real time. Intervals that start in the clock gap when daylight saving begins are skipped and counted (`nonexistent_local_times`). `--tz AEST` reads a file as fixed UTC+10. The dbt models use the same zone for local hour, weekday and day (`local_time_zone` in `transform/dbt_project.yml`).
- **ZIP layout:** every `.csv` inside a ZIP is read in name order, so the real one-file-per-day layout works.
- **Alarms:** `CT_ALARM_24HOUR` is not carried into readings (the reading schema has no alarm field), so detector health uses missing intervals only (decision D26).
