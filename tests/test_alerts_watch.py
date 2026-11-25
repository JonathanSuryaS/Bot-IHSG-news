import pytest
import yaml

from brief.alerts import command, evaluate, targets
from brief.watchlist import WatchError, add, normalize_code, remove

WATCH = {
    "index": {"symbol": "^JKSE", "name": "IHSG"},
    "tickers": [
        {"symbol": "BBCA.JK", "name": "Bank Central Asia", "aliases": ["BBCA"]},
        {"symbol": "TLKM.JK", "name": "Telkom Indonesia", "aliases": ["TLKM"]},
    ],
}


def cfg():
    return {"defaults": {"move_pct": 3.0, "volume_x": 2.5, "fast_pct": 2.0},
            "index": {"enabled": True, "move_pct": 1.5, "fast_pct": 1.0}, "extra": [], "overrides": {}}


# ---------- evaluate ----------

STOCK = {"code": "TLKM", "move_pct": 3.0, "volume_x": 2.5, "decimals": 0}


def test_move_alert_fires_once_per_level():
    fired = {}
    assert evaluate(STOCK, -2.9, 2020, None, fired) == []
    first = evaluate(STOCK, -3.4, 2010, None, fired)
    assert first == ["🔻 TLKM -3,40% ke 2.010 (batas ±3,0%)"]
    assert evaluate(STOCK, -4.0, 2000, None, fired) == []       # same level: silent
    assert len(evaluate(STOCK, -6.1, 1950, None, fired)) == 1   # next level: fires
    assert len(evaluate(STOCK, +3.2, 2100, None, fired)) == 1   # other direction: own key


def test_volume_alert_once_a_day():
    fired = {}
    assert evaluate(STOCK, 0.5, 2050, 2.4, fired) == []
    assert evaluate(STOCK, 0.5, 2050, 2.6, fired) == ["📊 TLKM volume 2,60x rata-rata 20 hari (batas 2,5x)"]
    assert evaluate(STOCK, 0.5, 2050, 4.0, fired) == []


# ---------- targets / settings ----------

def test_targets_overrides_and_extra():
    c = cfg()
    c["overrides"] = {"TLKM": {"move_pct": 2.0}, "BBCA": {"enabled": False}}
    c["extra"] = ["BMRI"]
    t = {x["code"]: x for x in targets(c, WATCH)}
    assert set(t) == {"IHSG", "TLKM", "BMRI"}
    assert t["TLKM"]["move_pct"] == 2.0 and t["BMRI"]["move_pct"] == 3.0


def test_commands():
    c = cfg()
    assert command(["set", "tlkm", "move", "2,5"], c, WATCH)[1] is True
    assert c["overrides"]["TLKM"]["move_pct"] == 2.5
    command(["set", "default", "volume", "3"], c, WATCH)
    assert c["defaults"]["volume_x"] == 3.0
    command(["off", "BBCA"], c, WATCH)
    assert c["overrides"]["BBCA"] == {"enabled": False}
    command(["on", "BBCA"], c, WATCH)
    assert "BBCA" not in c["overrides"]
    command(["off", "ihsg"], c, WATCH)
    assert c["index"]["enabled"] is False
    command(["add", "bmri"], c, WATCH, lookup_fn=lambda code: None)
    assert c["extra"] == ["BMRI"]
    with pytest.raises(WatchError):
        command(["add", "BBCA"], c, WATCH)              # already watched
    with pytest.raises(WatchError):
        command(["set", "TLKM", "move", "abc"], c, WATCH)
    with pytest.raises(WatchError):
        command(["remove", "TLKM"], c, WATCH)           # not an extra
    assert command(["show"], c, WATCH)[1] is False


# ---------- watchlist file edits ----------

@pytest.fixture
def wl(tmp_path):
    p = tmp_path / "watchlist.yaml"
    p.write_text(yaml.safe_dump(WATCH, sort_keys=False))
    return p


def fake_lookup(code):
    return {"symbol": f"{code}.JK", "name": f"Name {code}", "aliases": [code]}


def test_add_and_remove(wl):
    msg = add("bmri", wl, lookup_fn=fake_lookup)
    assert "BMRI" in msg
    assert [t["symbol"] for t in yaml.safe_load(wl.read_text())["tickers"]][-1] == "BMRI.JK"
    with pytest.raises(WatchError):
        add("BMRI", wl, lookup_fn=fake_lookup)          # duplicate
    remove("TLKM", wl)
    assert "TLKM.JK" not in wl.read_text()
    with pytest.raises(WatchError):
        remove("TLKM", wl)                              # already gone


def test_normalize_code():
    assert normalize_code(" bbca.jk ") == "BBCA"
    for bad in ["BB", "Bank", "12AB"]:
        if bad == "Bank":
            assert normalize_code(bad) == "BANK"        # 4 letters is a valid code shape
            continue
        with pytest.raises(WatchError):
            normalize_code(bad)


def test_sudden_move_alert():
    t = {"code": "TLKM", "move_pct": 3.0, "fast_pct": 2.0, "volume_x": 2.5, "decimals": 0}
    fired = {}
    assert evaluate(t, -1.0, 2000, None, fired, prev_price=2030, minutes=15) == []      # -1,48%
    out = evaluate(t, -2.5, 1985, None, fired, prev_price=2030, minutes=15)              # -2,22%
    assert out == ["⚡ TLKM -2,22% dalam 15 menit ke 1.985 (batas ±2,0%)"]
    assert evaluate(t, -2.5, 1985, None, fired, prev_price=None) == []                   # no recent check


def test_set_fast():
    c = cfg()
    c["defaults"]["fast_pct"] = 2.0
    c["index"]["fast_pct"] = 1.0
    command(["set", "IHSG", "fast", "0,8"], c, WATCH)
    assert c["index"]["fast_pct"] == 0.8
    command(["set", "BBCA", "fast", "1.5"], c, WATCH)
    assert c["overrides"]["BBCA"]["fast_pct"] == 1.5
