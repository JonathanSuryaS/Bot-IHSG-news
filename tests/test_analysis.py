import json
from datetime import date

from brief.analysis import news_from_snapshots, perf


def bars(closes, vols=None):
    vols = vols or [100] * len(closes)
    return [
        {"date": f"2026-11-{i + 1:02d}", "close": c, "high": c + 1, "low": c - 1, "volume": v}
        for i, (c, v) in enumerate(zip(closes, vols))
    ]


def test_perf_basic():
    # base close 100, then a 5-session window
    rows = bars([100, 102, 101, 104, 103, 110])
    p = perf(rows, 5, price_decimals=0)
    assert p["start_close"] == 100 and p["end_close"] == 110
    assert p["change_pct"] == 10.0
    assert p["display"]["change_pct"] == "+10,00%"
    assert p["up_days"] == 3 and p["down_days"] == 2
    assert p["high"] == 111 and p["low"] == 100  # low of 101 bar = 100
    assert p["best_day"]["date"] == "2026-11-06"   # 103 -> 110
    assert p["worst_day"]["date"] == "2026-11-03"  # 102 -> 101


def test_perf_volume_vs_previous_period():
    closes = [100] * 11
    vols = [100] * 6 + [200] * 5          # prev 5 sessions avg 100, window avg 200
    p = perf(bars(closes, vols), 5, price_decimals=0)
    assert p["volume_vs_prev_period"] == 2.0
    assert p["display"]["volume_vs_prev_period"] == "2,00x"


def test_perf_needs_enough_rows():
    try:
        perf(bars([100, 101]), 5, price_decimals=0)
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_news_from_snapshots_merges_window_and_dedupes(tmp_path):
    def snap(day, titles, tagged=()):
        news = [{"title": t, "published": f"{day}T10:00+07:00",
                 "tickers": ["BBCA.JK"] if t in tagged else []} for t in titles]
        (tmp_path / f"{day}.json").write_text(json.dumps({"news": news}))

    snap("2026-11-10", ["Old story"])                      # outside 7-day window
    snap("2026-11-20", ["Rupiah melemah", "BCA laba naik"], tagged=["BCA laba naik"])
    snap("2026-11-21", ["Rupiah Melemah!"])                 # duplicate after normalising
    (tmp_path / "latest.json").write_text("{}")             # not a dated snapshot

    out = news_from_snapshots(tmp_path, date(2026, 11, 21), days=7, cap=10)
    titles = [n["title"] for n in out["items"]]
    assert out["coverage"]["snapshots_found"] == 2
    assert titles[0] == "BCA laba naik"                     # tagged first
    assert "Old story" not in titles
    assert len(titles) == 2


from brief.analysis import StockNotFound, resolve_stock  # noqa: E402

WATCH = {"tickers": [
    {"symbol": "BBCA.JK", "name": "Bank Central Asia", "aliases": ["BBCA", "BCA", "Bank Central Asia"]},
    {"symbol": "TLKM.JK", "name": "Telkom Indonesia", "aliases": ["TLKM", "Telkom"]},
]}


def test_resolve_watchlist_names():
    assert resolve_stock("BBCA", WATCH)["symbol"] == "BBCA.JK"
    assert resolve_stock("bbca.jk", WATCH)["symbol"] == "BBCA.JK"
    assert resolve_stock("telkom", WATCH)["symbol"] == "TLKM.JK"
    assert resolve_stock("Bank Central Asia", WATCH)["in_watchlist"] is True


def test_resolve_other_idx_code():
    t = resolve_stock("bmri", WATCH)
    assert t["symbol"] == "BMRI.JK" and t["in_watchlist"] is False


def test_resolve_rejects_free_text():
    for bad in ["Bank Mandiri", "BB", "12345", ""]:
        try:
            resolve_stock(bad, WATCH)
        except StockNotFound:
            continue
        raise AssertionError(f"expected StockNotFound for {bad!r}")
