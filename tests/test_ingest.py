from __future__ import annotations

import csv
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from ingest import replay, scats, synthetic

FIXTURE = Path(__file__).parent / "fixtures" / "scats_synthetic.csv"


# ---- synthetic generator -------------------------------------------------------------------


def test_fixture_is_small_and_matches_generator():
    assert FIXTURE.stat().st_size < 200_000
    regenerated = synthetic.generate(sites=3, detectors=2, days=3)
    with FIXTURE.open(newline="") as fh:
        stored = list(csv.DictReader(fh))
    assert stored == regenerated


def test_generator_is_deterministic():
    a = synthetic.generate(2, 2, 2, seed=1)
    b = synthetic.generate(2, 2, 2, seed=1)
    c = synthetic.generate(2, 2, 2, seed=2)
    assert a == b
    assert a != c


def test_clean_data_has_no_faults():
    rows = synthetic.generate(3, 2, 3, faults=False)
    assert len(rows) == 3 * 2 * 3
    for row in rows:
        assert row["CT_RECORDS"] == "96"
        assert row["CT_ALARM_24HOUR"] == "0"
        assert all(row[c] != "" and int(row[c]) >= 0 for c in synthetic.VOLUME_COLUMNS)


def test_faults_are_injected():
    rows = synthetic.generate(3, 2, 3, faults=True)
    keys = [(r["NB_SCATS_SITE"], r["NB_DETECTOR"], r["QT_INTERVAL_COUNT"]) for r in rows]
    assert len(keys) == len(set(keys)) + 1, "exactly one duplicate row"
    assert any(r["CT_RECORDS"] != "96" for r in rows), "missing intervals"
    assert any(int(r["CT_ALARM_24HOUR"]) > 10 for r in rows), "alarm-heavy detector"
    negatives = [c for r in rows for c in synthetic.VOLUME_COLUMNS if r[c].startswith("-")]
    assert len(negatives) == 1


def test_ct_records_matches_non_blank_intervals():
    for row in synthetic.generate(3, 2, 3):
        present = sum(1 for c in synthetic.VOLUME_COLUMNS if row[c] != "")
        assert int(row["CT_RECORDS"]) == present


def test_weekday_has_morning_and_evening_peaks():
    rows = synthetic.generate(1, 1, 1, faults=False)  # 2026-03-02 is a Monday
    vols = [int(rows[0][c]) for c in synthetic.VOLUME_COLUMNS]
    night = sum(vols[8:16]) / 8  # 02:00 to 04:00
    am = sum(vols[30:34]) / 4  # about 07:30 to 08:30
    pm = sum(vols[66:70]) / 4  # about 16:30 to 17:30
    assert am > 3 * night
    assert pm > 3 * night


def test_columns_follow_the_published_layout():
    assert synthetic.COLUMNS[:3] == ["NB_SCATS_SITE", "QT_INTERVAL_COUNT", "NB_DETECTOR"]
    assert synthetic.COLUMNS[3] == "V00" and synthetic.COLUMNS[98] == "V95"
    assert synthetic.COLUMNS[-4:] == [
        "NM_REGION",
        "CT_RECORDS",
        "QT_VOLUME_24HOUR",
        "CT_ALARM_24HOUR",
    ]


# ---- unpivot -------------------------------------------------------------------------------


def clean_file(tmp_path: Path, sites=1, detectors=1, days=1) -> Path:
    path = tmp_path / "clean.csv"
    synthetic.write_csv(synthetic.generate(sites, detectors, days, faults=False), path)
    return path


def test_one_row_gives_96_readings(tmp_path):
    readings, stats = scats.read_readings(clean_file(tmp_path), source="synthetic")
    assert len(readings) == 96
    assert stats.readings == 96
    assert stats.volume_columns == 96
    assert len({r["interval_end"] for r in readings}) == 96


def test_interval_boundaries_aest(tmp_path):
    readings, _ = scats.read_readings(clean_file(tmp_path), tz="AEST")
    ends = sorted(datetime.fromisoformat(r["interval_end"]) for r in readings)
    # Day is 2026-03-02. V00 ends 00:15 AEST = 2026-03-01 14:15 UTC.
    # V95 ends 24:00 AEST = 2026-03-02 14:00 UTC.
    assert ends[0] == datetime(2026, 3, 1, 14, 15, tzinfo=UTC)
    assert ends[-1] == datetime(2026, 3, 2, 14, 0, tzinfo=UTC)
    assert all(e.minute % 15 == 0 and e.second == 0 for e in ends)


def test_v00_maps_to_the_first_interval_and_v95_to_the_last(tmp_path):
    row = dict.fromkeys(synthetic.COLUMNS, "")
    row.update(NB_SCATS_SITE="5", NB_DETECTOR="2", QT_INTERVAL_COUNT="2026-03-02", V00="7", V95="9")
    stats = scats.ReadStats()
    out = list(scats.unpivot(iter([row]), stats))
    by_volume = {r["volume"]: r["interval_end"] for r in out}
    assert by_volume[7] == "2026-03-01T14:15:00+00:00"
    assert by_volume[9] == "2026-03-02T14:00:00+00:00"
    assert stats.blank_intervals == 94


def test_melbourne_zone_applies_daylight_saving(tmp_path):
    row = dict.fromkeys(synthetic.COLUMNS, "")
    row.update(NB_SCATS_SITE="5", NB_DETECTOR="2", QT_INTERVAL_COUNT="2026-01-15", V00="1")
    stats = scats.ReadStats()
    fixed = next(scats.unpivot(iter([row]), stats, tz="AEST"))["interval_end"]
    local = next(scats.unpivot(iter([row]), stats, tz="Australia/Melbourne"))["interval_end"]
    assert fixed == "2026-01-14T14:15:00+00:00"  # +10
    assert local == "2026-01-14T13:15:00+00:00"  # +11 in summer


def test_blank_intervals_produce_no_reading_and_negatives_pass_through():
    rows = synthetic.generate(3, 2, 3, faults=True)
    stats = scats.ReadStats()
    out = list(scats.unpivot(iter(rows), stats))
    assert stats.blank_intervals > 0
    assert any(r["volume"] < 0 for r in out)  # left for the API to reject
    assert len(out) + stats.blank_intervals == len(rows) * 96


def test_csv_and_zip_give_the_same_readings(tmp_path):
    csv_path = clean_file(tmp_path, sites=2, days=2)
    zip_path = tmp_path / "month.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.write(csv_path, arcname="2026-03/volumes.csv")
    a, _ = scats.read_readings(csv_path)
    b, stats = scats.read_readings(zip_path)
    assert a == b
    assert stats.files == ["2026-03/volumes.csv"]


def test_reader_survives_unknown_layout(tmp_path, caplog):
    path = tmp_path / "odd.csv"
    path.write_text(
        "﻿nb_scats_site, qt_interval_count ,nb_detector,v00,V01,EXTRA\n"
        "10,02/03/2026,1,5,6,x\n"  # day/month/year date, lower-case header, BOM
        "11,not-a-date,1,5,6,x\n"  # unreadable date: skipped
        ",2026-03-02,1,5,6,x\n"  # no site: skipped
        "12,2026-03-02,1,abc,7,x\n"  # unreadable value: counted
    )
    readings, stats = scats.read_readings(path)
    assert stats.rows_read == 4
    assert stats.rows_skipped == 2
    assert stats.skip_reasons == {"unreadable date": 1, "missing site or detector": 1}
    assert stats.unreadable_values == 1
    assert stats.volume_columns == 2
    assert {r["site_id"] for r in readings} == {"10", "12"}
    assert [r["interval_end"] for r in readings if r["site_id"] == "10"][0].startswith("2026-03-01")


def test_missing_required_column_is_logged(tmp_path, caplog):
    path = tmp_path / "bad.csv"
    path.write_text("A,B\n1,2\n")
    with caplog.at_level("WARNING", logger="mcb.ingest.scats"):
        readings, stats = scats.read_readings(path)
    assert readings == []
    assert stats.rows_skipped == 1
    assert "column missing" in caplog.text


# ---- replay --------------------------------------------------------------------------------


def fake_readings(n: int, minutes_apart: int = 15) -> list[dict]:
    base = datetime(2026, 3, 2, tzinfo=UTC)
    return [
        {
            "site_id": "1",
            "detector_id": "1",
            "interval_end": datetime.fromtimestamp(
                base.timestamp() + i * minutes_apart * 60, UTC
            ).isoformat(),
            "volume": 1,
            "source": "synthetic",
        }
        for i in range(n)
    ]


def test_plan_batches_respects_size_and_hard_limit():
    batches = replay.plan_batches(fake_readings(1203), 500)
    assert [len(b) for b in batches] == [500, 500, 203]
    assert [len(b) for b in replay.plan_batches(fake_readings(10), 4)] == [4, 4, 2]
    assert max(len(b) for b in replay.plan_batches(fake_readings(1200), 9999)) == 500
    assert replay.plan_batches([], 500) == []


def test_batch_delays_scale_with_speed():
    batches = replay.plan_batches(fake_readings(8), 4)  # batch ends are 4 x 15 min apart
    assert replay.batch_delays(batches, 0) == [0.0, 0.0]
    assert replay.batch_delays(batches, 60) == [0.0, 3600 / 60]
    assert replay.batch_delays(batches, 3600) == [0.0, 1.0]


def mock_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def ok_handler(request: httpx.Request) -> httpx.Response:
    n = len(json.loads(request.content)["readings"])
    return httpx.Response(202, json={"accepted": n, "rejected": 0, "rejections": []})


def test_replay_sends_every_reading_once_in_batches():
    seen: list[int] = []

    def handler(request):
        seen.append(len(json.loads(request.content)["readings"]))
        return ok_handler(request)

    summary = replay.replay(fake_readings(1203), "http://api", client=mock_client(handler))
    assert seen == [500, 500, 203]
    assert (summary.batches_sent, summary.readings_sent, summary.accepted) == (3, 1203, 1203)
    assert summary.batches_failed == 0


def test_replay_waits_between_batches_at_the_given_speed():
    waits: list[float] = []
    replay.replay(
        fake_readings(8),
        "http://api",
        speed=60,
        batch_size=4,
        client=mock_client(ok_handler),
        sleep=waits.append,
    )
    assert waits == [60.0]


def test_replay_retries_with_backoff_then_succeeds():
    calls = {"n": 0}
    waits: list[float] = []

    def handler(request):
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503)
        return ok_handler(request)

    summary = replay.replay(
        fake_readings(3), "http://api", client=mock_client(handler), sleep=waits.append
    )
    assert calls["n"] == 3
    assert summary.retries == 2
    assert waits == [0.5, 1.0]
    assert summary.batches_failed == 0


def test_replay_retries_on_connection_error():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ConnectError("refused")
        return ok_handler(request)

    summary = replay.replay(
        fake_readings(2), "http://api", client=mock_client(handler), sleep=lambda _: None
    )
    assert summary.retries == 1 and summary.accepted == 2


def test_replay_gives_up_and_reports_failure():
    summary = replay.replay(
        fake_readings(2),
        "http://api",
        client=mock_client(lambda r: httpx.Response(503)),
        sleep=lambda _: None,
    )
    assert summary.batches_failed == 1
    assert summary.retries == 4


def test_replay_does_not_retry_a_422():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(422, json={"error": "invalid_request", "detail": []})

    summary = replay.replay(fake_readings(2), "http://api", client=mock_client(handler))
    assert calls["n"] == 1 and summary.batches_failed == 1


def test_summary_counts_rejection_reasons():
    def handler(request):
        return httpx.Response(
            202,
            json={
                "accepted": 1,
                "rejected": 2,
                "rejections": [
                    {"index": 0, "reasons": ["volume: Input should be >= 0"]},
                    {"index": 1, "reasons": ["duplicate: key already seen in this batch"]},
                ],
            },
        )

    summary = replay.replay(fake_readings(3), "http://api", client=mock_client(handler))
    assert summary.reject_reasons == {"volume": 1, "duplicate": 1}


def test_replay_synthetic_readings_against_the_real_api_validation():
    """Wire the generator and the real API validation together, without a network."""
    from fastapi.testclient import TestClient

    from services.api.main import create_app
    from services.api.ports import InMemoryPublisher, StaticProbe

    publisher = InMemoryPublisher()
    api = TestClient(create_app(publisher, StaticProbe()))

    def handler(request: httpx.Request) -> httpx.Response:
        r = api.post("/v1/readings", content=request.content, headers=dict(request.headers))
        return httpx.Response(r.status_code, json=r.json())

    readings = list(replay.synthetic_readings(2, 2, 1, faults=True, seed=7))
    summary = replay.replay(readings, "http://api", client=mock_client(handler))
    assert summary.batches_failed == 0
    assert summary.rejected >= 1  # the injected negative value
    assert "volume" in summary.reject_reasons
    assert summary.accepted + summary.rejected == len(readings)


def test_cli_refuses_two_sources():
    with pytest.raises(SystemExit):
        replay.main(["--synthetic", "--file", "x.csv"])


def test_cli_refuses_no_source():
    with pytest.raises(SystemExit):
        replay.main([])


# ---- top sites (shared by replay --file and the Pages build) -------------------------------


def _fixture_totals() -> dict[str, int]:
    totals: dict[str, int] = {}
    with FIXTURE.open(newline="") as fh:
        for row in csv.DictReader(fh):
            site = row["NB_SCATS_SITE"]
            totals[site] = totals.get(site, 0) + int(row["QT_VOLUME_24HOUR"] or 0)
    return totals


def test_site_totals_sum_the_daily_volume_per_site():
    expected = _fixture_totals()
    assert len(expected) == 3
    assert scats.site_totals(FIXTURE) == expected


def test_top_sites_keeps_the_busiest_and_zero_means_all():
    totals = _fixture_totals()
    busiest = sorted(totals, key=lambda s: (-totals[s], s))
    assert scats.top_sites(FIXTURE, 1) == {busiest[0]}
    assert scats.top_sites(FIXTURE, 2) == set(busiest[:2])
    assert scats.top_sites(FIXTURE, 99) == set(totals)
    assert scats.top_sites(FIXTURE, 0) is None


def _run_cli(monkeypatch, capsys, *args: str) -> tuple[list[dict], str, str]:
    sent: list[dict] = []

    def fake_replay(readings, api_url, **kwargs):
        sent.extend(readings)
        return replay.Summary(readings_sent=len(readings))

    monkeypatch.setattr(replay, "replay", fake_replay)
    assert replay.main(["--file", str(FIXTURE), "--speed", "0", *args]) == 0
    out, err = capsys.readouterr()
    return sent, out, err


def _plan(out: str) -> dict:
    line = next(x for x in out.splitlines() if x.startswith('{"plan"'))
    return json.loads(line)["plan"]


def test_cli_top_sites_sends_only_the_busiest_and_prints_the_plan(monkeypatch, capsys):
    keep = scats.top_sites(FIXTURE, 2)
    sent, out, err = _run_cli(monkeypatch, capsys, "--top-sites", "2")
    assert {r["site_id"] for r in sent} == keep
    assert _plan(out) == {"top_sites": 2, "sites": 2, "readings": len(sent)}
    assert "WARNING" not in err


def test_cli_top_sites_default_is_20(monkeypatch, capsys):
    sent, out, _ = _run_cli(monkeypatch, capsys)
    assert _plan(out)["top_sites"] == 20
    assert _plan(out)["sites"] == 3  # the fixture has only 3 sites


def test_cli_top_sites_zero_sends_all_and_warns_with_the_count(monkeypatch, capsys):
    all_readings, _ = scats.read_readings(FIXTURE)
    sent, out, err = _run_cli(monkeypatch, capsys, "--top-sites", "0")
    assert len(sent) == len(all_readings)
    assert _plan(out) == {"top_sites": 0, "sites": 3, "readings": len(all_readings)}
    assert f"3 sites, {len(all_readings)} readings" in err


def test_cli_refuses_negative_top_sites():
    with pytest.raises(SystemExit):
        replay.main(["--file", str(FIXTURE), "--top-sites", "-1"])
