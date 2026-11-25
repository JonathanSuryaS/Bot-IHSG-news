from datetime import date, datetime

from brief.fetcher import (
    build_alias_patterns,
    clean_text,
    expected_market_date,
    fmt_date_id,
    fmt_id,
    tag_tickers,
)
from brief.holidays import WIB

TICKERS = [
    {"symbol": "BBRI.JK", "name": "Bank Rakyat Indonesia", "aliases": ["BBRI", "BRI", "Bank Rakyat Indonesia"]},
    {"symbol": "TLKM.JK", "name": "Telkom Indonesia", "aliases": ["TLKM", "Telkom"]},
]


def test_fmt_id():
    assert fmt_id(7123.45) == "7.123,45"
    assert fmt_id(5800, 0) == "5.800"
    assert fmt_id(0.84, 2, sign=True) == "+0,84"
    assert fmt_id(-1.2, 2, sign=True) == "-1,20"


def test_fmt_date_id():
    assert fmt_date_id(date(2026, 12, 3)) == "03 Des 2026"


def test_expected_market_date_morning_uses_previous_session():
    wed_morning = datetime(2026, 11, 25, 7, 30, tzinfo=WIB)
    assert expected_market_date(wed_morning, {}) == date(2026, 11, 24)


def test_expected_market_date_monday_morning_is_friday():
    mon = datetime(2026, 11, 30, 7, 30, tzinfo=WIB)
    assert expected_market_date(mon, {}) == date(2026, 11, 27)


def test_expected_market_date_skips_holiday():
    mon = datetime(2026, 11, 30, 7, 30, tzinfo=WIB)
    assert expected_market_date(mon, {date(2026, 11, 27): "x"}) == date(2026, 11, 26)


def test_expected_market_date_after_close_is_today():
    wed_evening = datetime(2026, 11, 25, 17, 0, tzinfo=WIB)
    assert expected_market_date(wed_evening, {}) == date(2026, 11, 25)


def test_tagging():
    p = build_alias_patterns(TICKERS)
    assert tag_tickers("Kredit BRI tumbuh 9%", p) == ["BBRI.JK"]
    assert tag_tickers("Saham TELKOM naik", p) == ["TLKM.JK"]       # non-caps alias: case-insensitive
    assert tag_tickers("Riset BRIN soal pangan", p) == []            # no partial-word match
    assert tag_tickers("bri", p) == []                               # caps code: case-sensitive


def test_clean_text():
    assert clean_text("<p>Rupiah &amp; IHSG</p>\n  turun") == "Rupiah & IHSG turun"
