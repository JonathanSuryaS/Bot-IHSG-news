"""Build data for the after-market closing report. No LLM here.

Usage: brief-closing        (writes data/YYYY-MM-DD-close.json, prints a summary)
The report itself is written by `brief-report closing` (report.py).

Run after the session is final (cron 16:45 WIB). Compares today's close with
yesterday's close (what the morning brief showed), lists the alerts that fired
today, regional markets and rupiah at the close, today's news, and what's
scheduled for the next days.

Schema:
{
  "generated_at": "...", "date": "2026-11-26",
  "status": "ok" | "not_trading_day" | "not_ready" | "error", "status_reason": "...",
  "index": {"symbol", "name", "close", "prev_close", "change_pct", "day_high", "day_low",
            "volume_vs_20d", "display": {...}},
  "watchlist": [ same shape + "vs_index_pts", display.vs_index ],
  "movers": {"top_gainer": "BBCA", "top_loser": "TLKM"},       # codes only
  "alerts_today": [{"code": "TLKM", "type": "move", "direction": "down"}, ...],
  "global": [ same shape as the morning brief's global, at the time of the close ],
  "morning_global": [ the morning brief's global block, for comparison ] | null,
  "news": [ news published today, same shape as the morning brief ],
  "upcoming": {"dividends": [... next 7 days], "earnings": [... next 14 days]},
  "errors": [...]
}
Every number the report may show has a `display` string (see verify.py).
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

from brief import DATA_DIR
from brief.analysis import history_rows, upcoming_earnings
from brief.fetcher import (
    MARKET_CLOSE_WIB, build_alias_patterns, fetch_dividends, fetch_global, fetch_news,
    fmt_id, load_config,
)
from brief.holidays import WIB, HolidayConfigError, is_trading_day, load_holidays


def day_block(rows: list[dict], today: str, decimals: int) -> dict:
    """Today's close vs yesterday's, from daily rows (oldest→newest)."""
    if len(rows) < 2 or rows[-1]["date"] != today:
        raise LookupError("no bar for today yet")
    t, y = rows[-1], rows[-2]
    change = (t["close"] / y["close"] - 1) * 100
    prior = [r["volume"] for r in rows[-21:-1] if r["volume"] > 0]
    ratio = t["volume"] / (sum(prior) / len(prior)) if t["volume"] > 0 and len(prior) >= 10 else None
    f = lambda x: fmt_id(x, decimals)  # noqa: E731
    return {
        "close": round(t["close"], 2), "prev_close": round(y["close"], 2),
        "change_pct": round(change, 2),
        "day_high": round(t["high"], 2), "day_low": round(t["low"], 2),
        "volume_vs_20d": round(ratio, 2) if ratio else None,
        "display": {
            "close": f(t["close"]), "prev_close": f(y["close"]),
            "change_pct": fmt_id(change, 2, sign=True) + "%",
            "day_high": f(t["high"]), "day_low": f(t["low"]),
            "volume_vs_20d": fmt_id(ratio, 2) + "x" if ratio else None,
        },
    }


def alerts_today(state_path: Path, today: str) -> list[dict]:
    try:
        state = json.loads(state_path.read_text())
    except (OSError, json.JSONDecodeError):
        return []
    if state.get("date") != today:
        return []
    out = []
    for key in state.get("fired", {}):
        parts = key.split(":")
        if len(parts) == 3:
            out.append({"code": parts[0], "type": parts[1], "direction": parts[2]})
        elif len(parts) == 2:
            out.append({"code": parts[0], "type": parts[1], "direction": None})
    return out


def build(now: datetime | None = None, data_dir: Path = DATA_DIR) -> dict:
    now = now or datetime.now(WIB)
    today = now.date().isoformat()
    base = {"generated_at": now.isoformat(timespec="seconds"), "date": today}

    try:
        holidays = load_holidays(now.year)
    except HolidayConfigError:
        holidays = {}
    if not is_trading_day(now.date(), holidays)[0]:
        return {**base, "status": "not_trading_day", "status_reason": "bursa libur"}
    if now.time() < MARKET_CLOSE_WIB:
        return {**base, "status": "not_ready", "status_reason": "sesi belum selesai"}

    watchlist, feeds_cfg = load_config()
    errors: list[str] = []
    try:
        index = day_block(history_rows(watchlist["index"]["symbol"], now), today, 2)
    except LookupError:
        return {**base, "status": "not_ready", "status_reason": "data penutupan IHSG belum ada di Yahoo"}
    index.update(symbol=watchlist["index"]["symbol"], name=watchlist["index"]["name"])

    rows = []
    for t in watchlist["tickers"]:
        try:
            b = day_block(history_rows(t["symbol"], now), today, 0)
            vs = b["change_pct"] - index["change_pct"]
            b.update(symbol=t["symbol"], code=t["symbol"].split(".")[0], name=t["name"],
                     vs_index_pts=round(vs, 2))
            b["display"]["vs_index"] = fmt_id(vs, 2, sign=True) + " poin"
            rows.append(b)
        except Exception as e:
            errors.append(f"{t['symbol']}: {type(e).__name__}: {e}")

    movers = {}
    if rows:
        movers = {"top_gainer": max(rows, key=lambda r: r["change_pct"])["code"],
                  "top_loser": min(rows, key=lambda r: r["change_pct"])["code"]}

    global_now, g_err = fetch_global(now)
    news, n_err = fetch_news(feeds_cfg, build_alias_patterns(watchlist["tickers"]), now)
    news = [n for n in news if n["published"][:10] == today]
    dividends, d_err = fetch_dividends(watchlist["tickers"], now.date() + timedelta(days=1), days_ahead=7)
    earnings, e_err = upcoming_earnings(watchlist["tickers"], now.date() + timedelta(days=1), days_ahead=14)
    errors += g_err + n_err + d_err + e_err

    morning_global = None
    try:
        morning_global = json.loads((data_dir / f"{today}.json").read_text()).get("global")
    except (OSError, json.JSONDecodeError):
        pass

    return {
        **base, "status": "ok", "status_reason": "fresh data",
        "index": index, "watchlist": rows, "movers": movers,
        "alerts_today": alerts_today(data_dir / "alerts-state.json", today),
        "global": global_now, "morning_global": morning_global,
        "news": news[:60],
        "upcoming": {"dividends": dividends, "earnings": earnings},
        "errors": errors,
    }


def build_and_save(now: datetime | None = None, data_dir: Path = DATA_DIR) -> tuple[dict, Path]:
    try:
        data = build(now, data_dir)
    except Exception as e:
        data = {"generated_at": datetime.now(WIB).isoformat(timespec="seconds"),
                "status": "error", "status_reason": f"{type(e).__name__}: {e}"}
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / f"{data.get('date', datetime.now(WIB).date().isoformat())}-close.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    return data, path


def main() -> int:
    data, path = build_and_save()
    print(f"{data['status']}: {data['status_reason']} | {len(data.get('news', []))} news today | wrote {path}")
    for err in data.get("errors", []):
        print(f"  warn: {err}")
    return 0 if data["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
