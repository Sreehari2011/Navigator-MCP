"""Metering: counting, persistence, daily aggregates, privacy."""

import json

from navigator_mcp.metering import UsageMeter


def test_record_and_report(tmp_path):
    meter = UsageMeter(tmp_path / "usage.json")
    meter.record("browser_navigate", navigation=True)
    meter.record("browser_snapshot", snapshot_chars=1200)
    meter.record("browser_snapshot", snapshot_chars=800)
    meter.record("browser_captcha_solve", captcha=True, ok=False)

    report = meter.report()
    assert report["tools"]["browser_navigate"] == 1
    assert report["tools"]["browser_snapshot"] == 2
    assert report["totals"]["tool_calls"] == 4
    assert report["totals"]["snapshots"] == 2
    assert report["totals"]["snapshot_chars"] == 2000
    assert report["totals"]["navigations"] == 1
    assert report["totals"]["captcha_solves"] == 1
    assert report["totals"]["errors"] == 1


def test_persistence_across_instances(tmp_path):
    path = tmp_path / "usage.json"
    meter = UsageMeter(path)
    meter.record("browser_click")
    meter.record("browser_click")

    meter2 = UsageMeter(path)
    assert meter2.report()["tools"]["browser_click"] == 2


def test_daily_aggregate_shape(tmp_path):
    meter = UsageMeter(tmp_path / "usage.json")
    meter.record("browser_fill")
    agg = meter.daily_aggregate()
    assert "day" in agg and "tools" in agg
    assert agg["tools"]["browser_fill"] == 1
    assert "install_id" in agg
    # privacy: no page data anywhere
    blob = json.dumps(agg)
    assert "http" not in blob


def test_disabled_meter_records_nothing(tmp_path):
    meter = UsageMeter(tmp_path / "usage.json", enabled=False)
    meter.record("browser_click")
    assert meter.report()["totals"]["tool_calls"] == 0


def test_corrupt_file_recovers(tmp_path):
    path = tmp_path / "usage.json"
    path.write_text("{not valid json")
    meter = UsageMeter(path)
    meter.record("x")
    assert meter.report()["tools"]["x"] == 1
