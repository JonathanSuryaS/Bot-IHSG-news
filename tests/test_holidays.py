from datetime import date

from brief.holidays import is_trading_day

HOL = {date(2026, 12, 25): "Natal"}


def test_weekday_is_trading():
    assert is_trading_day(date(2026, 11, 25), HOL)[0] is True


def test_weekend_closed():
    assert is_trading_day(date(2026, 11, 28), HOL) == (False, "weekend")


def test_holiday_closed():
    ok, reason = is_trading_day(date(2026, 12, 25), HOL)
    assert ok is False and "Natal" in reason
