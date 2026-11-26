import json

import pytest

from brief.closing import alerts_today, day_block


def rows(closes, today="2026-11-26"):
    out = [{"date": f"2026-11-{i + 1:02d}", "close": c, "high": c + 5, "low": c - 5, "volume": 100}
           for i, c in enumerate(closes[:-1])]
    out.append({"date": today, "close": closes[-1], "high": closes[-1] + 10,
                "low": closes[-1] - 20, "volume": 300})
    return out


def test_day_block():
    b = day_block(rows([1000] * 21 + [1030]), "2026-11-26", 0)
    assert b["change_pct"] == 3.0 and b["display"]["change_pct"] == "+3,00%"
    assert b["display"]["day_high"] == "1.040" and b["display"]["day_low"] == "1.010"
    assert b["volume_vs_20d"] == 3.0


def test_day_block_needs_today():
    with pytest.raises(LookupError):
        day_block(rows([1000, 1010], today="2026-11-25"), "2026-11-26", 0)


def test_alerts_today(tmp_path):
    p = tmp_path / "alerts-state.json"
    p.write_text(json.dumps({"date": "2026-11-26",
                             "fired": {"TLKM:move:down": 1, "BBRI:volume": True}}))
    assert alerts_today(p, "2026-11-26") == [
        {"code": "TLKM", "type": "move", "direction": "down"},
        {"code": "BBRI", "type": "volume", "direction": None},
    ]
    assert alerts_today(p, "2026-11-27") == []          # yesterday's state is ignored
