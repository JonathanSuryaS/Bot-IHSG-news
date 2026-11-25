from brief.verify import unverified_numbers

DATA = '{"index": {"display": {"close": "7.123,45", "change_pct": "+0,84%"}}, "market_date": "2026-11-24"}'


def test_copied_numbers_pass():
    brief = "IHSG pagi — 2026-11-24\nIHSG ditutup 7.123,45 (+0,84%)"
    assert unverified_numbers(brief, DATA) == []


def test_invented_number_fails():
    assert unverified_numbers("IHSG ditutup 7.200,00", DATA) == ["7.200,00"]


def test_reformatted_number_fails():
    # LLM "helpfully" switched to English separators
    assert unverified_numbers("IHSG closed at 7,123.45", DATA) == ["7,123.45"]


def test_small_ints_allowed():
    assert unverified_numbers("1. Top 5 news, 20-day avg, 14 hari", DATA) == []


def test_flipped_sign_fails():
    assert unverified_numbers("IHSG ditutup 7.123,45 (-0,84%)", DATA) == ["-0,84"]
