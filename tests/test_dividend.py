from datetime import date

import pytest

from brief.dividend import parse_price, render, rp, summarize

PAY = [
    (date(2023, 1, 10), 57.0), (date(2023, 3, 24), 231.22),
    (date(2024, 1, 2), 84.0), (date(2024, 3, 14), 235.0), (date(2024, 12, 27), 135.0),
    (date(2025, 4, 11), 208.4), (date(2025, 12, 30), 137.0),
    (date(2026, 4, 21), 209.0),
]
TODAY = date(2026, 11, 25)


def test_summarize_years_trend_ttm():
    s = summarize(PAY, 3070.0, TODAY, buy_price=3800)
    assert [r["year"] for r in s["rows"]] == [2023, 2024, 2025, 2026]
    assert s["rows"][1]["total"] == 454.0 and s["rows"][1]["count"] == 3
    assert s["rows"][-1]["partial"] and not s["rows"][0]["partial"]
    assert [t["year"] for t in s["trend"]] == [2024, 2025]  # current year excluded
    assert s["trend"][1]["pct"] < 0
    assert s["ttm"] == 346.0                      # 30 Dec 2025 + 21 Apr 2026
    assert s["yield_pct"] == pytest.approx(346 / 3070 * 100)
    assert s["buy"]["per_lot"] == 34600.0


def test_render_text():
    out = render("BBRI", "Bank Rakyat Indonesia", summarize(PAY, 3070.0, TODAY, 3800),
                 0.82, None)
    assert "2024: Rp454 (3x bayar)" in out
    assert "2023: Rp288,22 (2x bayar)" in out
    assert "2026: Rp209 (1x bayar, sejauh ini)" in out
    assert "belum diumumkan" in out
    assert "Per lot (100 lembar): Rp34.600" in out
    assert "Payout ratio: 82%" in out
    for bad in ("beli sekarang", "jual", "target"):
        assert bad not in out.lower().replace("jika beli di", "")


def test_no_dividends():
    out = render("GOTO", "GoTo", summarize([], 70.0, TODAY), None, None)
    assert "Belum ada riwayat dividen" in out


def test_rp_and_parse_price():
    assert rp(1234.0) == "Rp1.234" and rp(231.22) == "Rp231,22"
    assert parse_price("3.800") == 3800 and parse_price("Rp3800") == 3800
    assert parse_price("3800,5") == 3800.5
    with pytest.raises(ValueError):
        parse_price("abc")
