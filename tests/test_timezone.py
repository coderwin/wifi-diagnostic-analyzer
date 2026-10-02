from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from src.utils.timezone import local_day_bounds, to_local


def test_utc_instant_displays_in_seoul(monkeypatch):
    monkeypatch.setenv("WIFI_TIMEZONE", "Asia/Seoul")
    local = to_local(datetime(2026, 10, 2, 0, 10, tzinfo=timezone.utc))
    assert local.hour == 9
    assert local.minute == 10
    assert local.tzinfo == ZoneInfo("Asia/Seoul")


def test_local_calendar_day_maps_to_utc_range():
    start, end = local_day_bounds(date(2026, 10, 2), ZoneInfo("Asia/Seoul"))
    assert start == datetime(2026, 10, 1, 15, 0, 0)
    assert end == datetime(2026, 10, 2, 14, 59, 59, 999999)

