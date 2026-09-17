from datetime import date, datetime, timezone

from app.modules.notifications.router import _operational_today


def test_operational_day_remains_previous_day_until_midnight_in_brasilia():
    # 00:01 UTC de 11/09 ainda é 21:01 de 10/09 em Brasília.
    assert _operational_today(datetime(2026, 9, 11, 0, 1, tzinfo=timezone.utc)) == date(2026, 9, 10)


def test_operational_day_changes_at_midnight_in_brasilia():
    assert _operational_today(datetime(2026, 9, 11, 3, 0, tzinfo=timezone.utc)) == date(2026, 9, 11)
