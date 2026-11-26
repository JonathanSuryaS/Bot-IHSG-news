import pytest

from brief.chart import Bar, analyze, candle_pattern, describe, rsi, sma


def test_sma():
    assert sma([1, 2, 3, 4], 2) == [None, 1.5, 2.5, 3.5]


def test_rsi_extremes():
    assert rsi([float(i) for i in range(1, 30)]) == 100.0
    down = rsi([float(i) for i in range(30, 1, -1)])
    assert down == pytest.approx(0.0)
    assert rsi([1.0] * 5) is None


def test_patterns():
    red = Bar(110, 111, 99, 100, 1)
    assert candle_pattern([red, Bar(99, 112, 98, 111, 1)]).startswith("Bullish engulfing")
    green = Bar(100, 111, 99, 110, 1)
    assert candle_pattern([green, Bar(111, 112, 98, 99, 1)]).startswith("Bearish engulfing")
    assert candle_pattern([green, Bar(105, 110, 100, 105.2, 1)]).startswith("Doji")
    assert candle_pattern([green, Bar(108, 109, 100, 109, 1)]).startswith("Hammer")
    assert candle_pattern([green, Bar(101, 109, 100, 100.5, 1)]) is not None


def test_analyze_uptrend_text():
    bars = [Bar(100 + i, 102 + i, 99 + i, 101 + i, 1000) for i in range(80)]
    a = analyze(bars, (20, 50))
    assert a["close"] == 180 and a["ma_fast"] > a["ma_slow"]
    assert a["support"] == min(b.l for b in bars[-20:])
    text = "\n".join(describe(a, (20, 50), "hari", 0))
    assert "uptrend" in text and "jenuh beli" in text
    for bad in ("beli sekarang", "jual sekarang", "target"):
        assert bad not in text.lower()
