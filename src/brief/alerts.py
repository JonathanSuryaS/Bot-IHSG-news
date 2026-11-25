"""Intraday price/volume alerts. No LLM: the check prints plain text or nothing.

Usage:
  brief-alerts check                     # run by the Hermes cron (--no-agent);
                                         # prints alert text, or nothing (= silent)
  brief-alerts show
  brief-alerts set <KODE|IHSG|default> move <pct>
  brief-alerts set <KODE|default> volume <x>
  brief-alerts set <KODE|IHSG|default> fast <pct>   # sudden move between two checks
  brief-alerts off <KODE|IHSG>           # mute a stock (or IHSG)
  brief-alerts on <KODE|IHSG>
  brief-alerts add <KODE>                # alert-only stock outside the watchlist
  brief-alerts remove <KODE>

Settings live in config/alerts.yaml. What already fired today is kept in
data/alerts-state.json so the same alert isn't sent every 15 minutes.
"""

from __future__ import annotations

import json
import math
import sys
from datetime import datetime, time
from pathlib import Path

from brief import CONFIG_DIR, DATA_DIR
from brief.fetcher import fmt_id
from brief.holidays import WIB, HolidayConfigError, is_trading_day, load_holidays
from brief.watchlist import WatchError, normalize_code

ALERTS_PATH = CONFIG_DIR / "alerts.yaml"
STATE_PATH = DATA_DIR / "alerts-state.json"
SESSION_START, SESSION_END = time(9, 0), time(16, 15)


# ---------- config ----------

def load_cfg(path: Path = ALERTS_PATH) -> dict:
    import yaml

    cfg = yaml.safe_load(path.read_text()) or {}
    cfg.setdefault("defaults", {})
    cfg["defaults"].setdefault("move_pct", 3.0)
    cfg["defaults"].setdefault("volume_x", 2.5)
    cfg["defaults"].setdefault("fast_pct", 2.0)
    cfg.setdefault("index", {})
    cfg["index"].setdefault("enabled", True)
    cfg["index"].setdefault("move_pct", 1.5)
    cfg["index"].setdefault("fast_pct", 1.0)
    cfg["extra"] = cfg.get("extra") or []
    cfg["overrides"] = cfg.get("overrides") or {}
    return cfg


def save_cfg(cfg: dict, path: Path = ALERTS_PATH) -> None:
    """Rewrite values, keeping the explanatory comment header of the file."""
    import yaml

    text = path.read_text() if path.exists() else ""
    header = "".join(l for l in text.splitlines(keepends=True) if l.startswith("#"))
    body = yaml.safe_dump(
        {k: cfg[k] for k in ("defaults", "index", "extra", "overrides")},
        sort_keys=False, default_flow_style=None,
    )
    path.write_text(header + "\n" + body)


def targets(cfg: dict, watchlist: dict) -> list[dict]:
    """Every stock to check, with its effective thresholds."""
    out = []
    if cfg["index"].get("enabled", True):
        out.append({"symbol": watchlist["index"]["symbol"], "code": "IHSG",
                    "move_pct": float(cfg["index"].get("move_pct", 1.5)),
                    "fast_pct": float(cfg["index"].get("fast_pct", 1.0)),
                    "volume_x": None, "decimals": 2})
    codes = [t["symbol"].split(".")[0] for t in watchlist.get("tickers", [])]
    codes += [c for c in cfg["extra"] if c not in codes]
    for code in codes:
        o = cfg["overrides"].get(code, {})
        if o.get("enabled", True) is False:
            continue
        out.append({"symbol": f"{code}.JK", "code": code,
                    "move_pct": float(o.get("move_pct", cfg["defaults"]["move_pct"])),
                    "volume_x": float(o.get("volume_x", cfg["defaults"]["volume_x"])),
                    "fast_pct": float(o.get("fast_pct", cfg["defaults"]["fast_pct"])),
                    "decimals": 0})
    return out


# ---------- evaluation (pure, tested) ----------

def evaluate(t: dict, change_pct: float, price: float, vol_ratio: float | None,
             fired: dict, prev_price: float | None = None, minutes: int | None = None) -> list[str]:
    """Return alert lines for one stock and update `fired` in place.

    Move alerts fire at each new multiple of the threshold in the same
    direction (3% → 6% → 9%). Volume fires once per day. A sudden move fires
    when the price changed by ≥ fast_pct since the previous check
    (`prev_price`, `minutes` ago); every such window is its own event.
    """
    lines = []
    fast = t.get("fast_pct")
    if fast and prev_price:
        jump = (price / prev_price - 1) * 100
        if abs(jump) >= fast - 1e-9:
            lines.append(
                f"⚡ {t['code']} {fmt_id(jump, 2, sign=True)}% dalam {minutes or 15} menit ke "
                f"{fmt_id(price, t['decimals'])} (batas ±{fmt_id(fast, 1)}%)"
            )
    step = t["move_pct"]
    if step > 0:
        level = math.floor(abs(change_pct) / step + 1e-9)
        key = f"{t['code']}:move:{'up' if change_pct > 0 else 'down'}"
        if level >= 1 and level > fired.get(key, 0):
            fired[key] = level
            icon = "🔺" if change_pct > 0 else "🔻"
            lines.append(
                f"{icon} {t['code']} {fmt_id(change_pct, 2, sign=True)}% ke "
                f"{fmt_id(price, t['decimals'])} (batas ±{fmt_id(step, 1)}%)"
            )
    vx = t.get("volume_x")
    if vx and vol_ratio is not None and vol_ratio >= vx and not fired.get(f"{t['code']}:volume"):
        fired[f"{t['code']}:volume"] = True
        lines.append(f"📊 {t['code']} volume {fmt_id(vol_ratio, 2)}x rata-rata 20 hari (batas {fmt_id(vx, 1)}x)")
    return lines


# ---------- check (network) ----------

def today_stats(symbol: str, today) -> tuple[float, float, float | None] | None:
    """(change_pct vs prev close, last price, today's volume / 20d avg) or None
    if there's no bar for today yet."""
    import yfinance as yf

    h = yf.Ticker(symbol).history(period="2mo", interval="1d", auto_adjust=False).dropna(subset=["Close"])
    if len(h) < 2 or h.index[-1].date() != today:
        return None
    price, prev = float(h["Close"].iloc[-1]), float(h["Close"].iloc[-2])
    vol = float(h["Volume"].iloc[-1])
    prior = [float(v) for v in h["Volume"].iloc[-21:-1] if v > 0]
    ratio = vol / (sum(prior) / len(prior)) if vol > 0 and len(prior) >= 10 else None
    return (price / prev - 1) * 100, price, ratio


def load_state(today: str, path: Path = STATE_PATH) -> dict:
    try:
        s = json.loads(path.read_text())
        if s.get("date") == today:
            return s
    except (OSError, json.JSONDecodeError):
        pass
    return {"date": today, "fired": {}, "last": {}}


def check(now: datetime | None = None) -> str:
    from brief.fetcher import load_config

    now = now or datetime.now(WIB)
    try:
        holidays = load_holidays(now.year)
    except HolidayConfigError:
        holidays = {}
    if not is_trading_day(now.date(), holidays)[0] or not (SESSION_START <= now.time() <= SESSION_END):
        return ""

    watchlist, _ = load_config()
    cfg = load_cfg()
    state = load_state(now.date().isoformat())
    state.setdefault("last", {})
    lines = []
    for t in targets(cfg, watchlist):
        try:
            stats = today_stats(t["symbol"], now.date())
        except Exception as e:
            print(f"alert check {t['symbol']}: {type(e).__name__}: {e}", file=sys.stderr)
            continue
        if stats:
            prev, minutes = None, None
            last = state["last"].get(t["code"])
            if last:
                minutes = int((now - datetime.fromisoformat(last["t"])).total_seconds() // 60)
                # only compare with a recent check, so a missed run (Mac asleep)
                # doesn't turn hours of drift into a "sudden" move
                if 0 < minutes <= 35:
                    prev = last["price"]
            lines += evaluate(t, stats[0], stats[1], stats[2], state["fired"], prev, minutes)
            state["last"][t["code"]] = {"price": stats[1], "t": now.isoformat(timespec="seconds")}

    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2))
    if not lines:
        return ""
    head = f"🚨 Alert IDX {now:%H:%M} WIB (data Yahoo tertunda ±15 menit)"
    return "\n".join([head, *lines])


# ---------- settings commands ----------

def _code_or_ihsg(text: str) -> str:
    return "IHSG" if text.strip().upper() == "IHSG" else normalize_code(text)


def show(cfg: dict, watchlist: dict) -> str:
    d = cfg["defaults"]
    lines = [f"⚙️ Alert: default gerak harian ±{fmt_id(d['move_pct'], 1)}%, "
             f"gerak cepat ±{fmt_id(d['fast_pct'], 1)}%/15 menit, volume {fmt_id(d['volume_x'], 1)}x"]
    idx = cfg["index"]
    lines.append("• IHSG: " + (f"±{fmt_id(idx['move_pct'], 1)}%, cepat ±{fmt_id(idx['fast_pct'], 1)}%"
                               if idx.get("enabled", True) else "mati"))
    active = {t["code"]: t for t in targets(cfg, watchlist)}
    codes = [t["symbol"].split(".")[0] for t in watchlist.get("tickers", [])]
    for code in codes + [c for c in cfg["extra"] if c not in codes]:
        tag = "" if code in codes else " (extra)"
        if code in active:
            t = active[code]
            lines.append(f"• {code}{tag}: ±{fmt_id(t['move_pct'], 1)}%, cepat ±{fmt_id(t['fast_pct'], 1)}%, "
                         f"volume {fmt_id(t['volume_x'], 1)}x")
        else:
            lines.append(f"• {code}{tag}: mati")
    lines.append("Cek tiap 15 menit, 09:00–16:15 WIB, hari bursa.")
    return "\n".join(lines)


def command(args: list[str], cfg: dict, watchlist: dict, lookup_fn=None) -> tuple[str, bool]:
    """Apply a settings command. Returns (message, changed)."""
    if not args or args == ["show"]:
        return show(cfg, watchlist), False
    op = args[0]
    if op == "set" and len(args) == 4:
        who, what, raw = _code_or_ihsg(args[1]) if args[1].lower() != "default" else "default", args[2], args[3]
        try:
            val = float(raw.replace(",", "."))
        except ValueError:
            raise WatchError(f"'{raw}' bukan angka")
        if what not in ("move", "volume", "fast") or val <= 0 or val > 50:
            raise WatchError("pakai: set <KODE|IHSG|default> move|fast <persen> atau volume <kali>")
        key = {"move": "move_pct", "volume": "volume_x", "fast": "fast_pct"}[what]
        if who == "default":
            cfg["defaults"][key] = val
        elif who == "IHSG":
            if what == "volume":
                raise WatchError("IHSG hanya punya alert gerak (move / fast)")
            cfg["index"][key] = val
        else:
            cfg["overrides"].setdefault(who, {})[key] = val
        unit = "x" if what == "volume" else "%"
        return f"✅ {who}: {what} {fmt_id(val, 1)}{unit}", True
    if op in ("on", "off") and len(args) == 2:
        who = _code_or_ihsg(args[1])
        enabled = op == "on"
        if who == "IHSG":
            cfg["index"]["enabled"] = enabled
        else:
            o = cfg["overrides"].setdefault(who, {})
            if enabled:
                o.pop("enabled", None)
                if not o:
                    cfg["overrides"].pop(who)
            else:
                o["enabled"] = False
        return f"{'🔔' if enabled else '🔕'} Alert {who} {'aktif' if enabled else 'dimatikan'}", True
    if op == "add" and len(args) == 2:
        code = normalize_code(args[1])
        if code in cfg["extra"] or any(t["symbol"] == f"{code}.JK" for t in watchlist.get("tickers", [])):
            raise WatchError(f"{code} sudah dipantau")
        if lookup_fn:
            lookup_fn(code)  # raises WatchError if the code doesn't exist
        cfg["extra"].append(code)
        return f"✅ {code} ditambahkan ke alert (di luar watchlist)", True
    if op == "remove" and len(args) == 2:
        code = normalize_code(args[1])
        if code not in cfg["extra"]:
            raise WatchError(f"{code} bukan saham extra. Untuk saham watchlist pakai: off {code}")
        cfg["extra"].remove(code)
        cfg["overrides"].pop(code, None)
        return f"🗑 {code} dihapus dari alert", True
    raise WatchError("Format: /alert show | set KODE move 3 | set KODE fast 2 | set KODE volume 2.5 | "
                     "on KODE | off KODE | add KODE | remove KODE")


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args == ["check"]:
        out = check()
        if out:
            print(out)
        return 0
    from brief.fetcher import load_config
    from brief.watchlist import lookup

    watchlist, _ = load_config()
    cfg = load_cfg()
    try:
        msg, changed = command(args, cfg, watchlist, lookup_fn=lookup)
    except WatchError as e:
        print(f"⚠️ {e}")
        return 1
    if changed:
        save_cfg(cfg)
    print(msg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
