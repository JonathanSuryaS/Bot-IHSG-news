"""Build data for an on-demand weekly/monthly analysis. No LLM here.

Usage: brief-analyze --period week|month --stock BBCA
Writes data/analysis-week.json or data/analysis-month.json.

--stock accepts a watchlist name/alias (BCA, Telkom) or any 4-letter IDX
code (BMRI, GOTO). The stock is the report's focus; the other watchlist
stocks are included as `peers` for comparison.

Periods are rolling windows ending at the latest completed session:
  week  = last 5 trading sessions,  news from the last 7 calendar days
  month = last 21 trading sessions, news from the last 30 calendar days

Schema:
{
  "generated_at": "...", "status": "ok" | "not_found" | "error", "status_reason": "...",
  "period": "week", "sessions": 5, "start_date": "2026-11-19", "end_date": "2026-11-25",
  "index": { performance block, see perf() },
  "focus": { performance block + "name" + "vs_index_pts" + "valuation" + "in_watchlist" },
  "peers": [ same shape, the other watchlist stocks ],
  "news": {
    "coverage": {"days_requested": 7, "snapshots_found": 1, "first": "...", "last": "..."},
    "focus_items": [ news mentioning the focus stock ],
    "items": [ other market/economy news, same shape as fetcher news items ]
  },
  "outlook": {
    "dividends": [ ex-dates in the next 30 days ],
    "earnings": [ {"symbol", "name", "date", "display": {"date"}} in the next 60 days ]
  },
  "errors": [ non-fatal problems ]
}

Every number the report may show has a `display` string (see verify.py).
News only goes back as far as the saved daily snapshots in data/, because
RSS feeds keep just the last day or two. `news.coverage` says how much exists.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from brief import DATA_DIR
from brief.fetcher import _history, build_alias_patterns, fetch_dividends, fmt_date_id, fmt_id, load_config
from brief.holidays import WIB

PERIODS = {
    "week": {"sessions": 5, "news_days": 7, "news_cap": 80},
    "month": {"sessions": 21, "news_days": 30, "news_cap": 150},
}
SNAPSHOT_NAME = re.compile(r"^\d{4}-\d{2}-\d{2}\.json$")


def pct(a: float, b: float) -> float:
    return (a / b - 1) * 100


def perf(rows: list[dict], n: int, price_decimals: int) -> dict:
    """Performance over the last `n` sessions.

    `rows` are daily bars oldest→newest: {"date", "close", "high", "low", "volume"}.
    Needs n+1 rows (the close before the window is the starting point); volume
    comparison uses the n sessions before the window when available.
    """
    if len(rows) < n + 1:
        raise ValueError(f"need {n + 1} sessions, have {len(rows)}")
    window = rows[-n:]
    base = rows[-n - 1]["close"]
    last = window[-1]["close"]

    daily = []
    prev = base
    for r in window:
        daily.append((r["date"], pct(r["close"], prev)))
        prev = r["close"]
    best = max(daily, key=lambda x: x[1])
    worst = min(daily, key=lambda x: x[1])
    hi = max(window, key=lambda r: r["high"])
    lo = min(window, key=lambda r: r["low"])

    vols = [r["volume"] for r in window if r["volume"] > 0]
    prior = [r["volume"] for r in rows[-2 * n - 1:-n - 1] if r["volume"] > 0] if len(rows) >= 2 * n + 1 else []
    vol_ratio = (sum(vols) / len(vols)) / (sum(prior) / len(prior)) if len(vols) >= n // 2 and len(prior) >= n // 2 else None

    change = pct(last, base)
    f = lambda x: fmt_id(x, price_decimals)  # noqa: E731
    return {
        "start_close": round(base, 2),
        "end_close": round(last, 2),
        "change_pct": round(change, 2),
        "high": round(hi["high"], 2), "high_date": hi["date"],
        "low": round(lo["low"], 2), "low_date": lo["date"],
        "best_day": {"date": best[0], "change_pct": round(best[1], 2)},
        "worst_day": {"date": worst[0], "change_pct": round(worst[1], 2)},
        "up_days": sum(1 for _, c in daily if c > 0),
        "down_days": sum(1 for _, c in daily if c < 0),
        "volume_vs_prev_period": round(vol_ratio, 2) if vol_ratio else None,
        "display": {
            "start_close": f(base),
            "end_close": f(last),
            "change_pct": fmt_id(change, 2, sign=True) + "%",
            "high": f(hi["high"]), "high_date": fmt_date_id(date.fromisoformat(hi["date"])),
            "low": f(lo["low"]), "low_date": fmt_date_id(date.fromisoformat(lo["date"])),
            "best_day": f"{fmt_date_id(date.fromisoformat(best[0]))} ({fmt_id(best[1], 2, sign=True)}%)",
            "worst_day": f"{fmt_date_id(date.fromisoformat(worst[0]))} ({fmt_id(worst[1], 2, sign=True)}%)",
            "volume_vs_prev_period": fmt_id(vol_ratio, 2) + "x" if vol_ratio else None,
        },
    }


def history_rows(symbol: str, now: datetime) -> list[dict]:
    h = _history(symbol, now)
    return [
        {
            "date": idx.date().isoformat(),
            "close": float(r["Close"]),
            "high": float(r["High"]),
            "low": float(r["Low"]),
            "volume": float(r["Volume"]),
        }
        for idx, r in h.iterrows()
    ]


def _num(info: dict, key: str) -> float | None:
    v = info.get(key)
    return float(v) if isinstance(v, (int, float)) and v == v else None  # v == v drops NaN


def valuation(symbol: str, close: float) -> dict:
    """Valuation from Yahoo's quote summary. Fractions are converted to %.

    Uses the trailing dividend yield (dividends actually paid in the last 12
    months), not Yahoo's `dividendYield`, which is a forward estimate.
    """
    import yfinance as yf

    info = yf.Ticker(symbol).info or {}
    pe = _num(info, "trailingPE")
    pbv = _num(info, "priceToBook")
    dy = _num(info, "trailingAnnualDividendYield")
    roe = _num(info, "returnOnEquity")
    eg = _num(info, "earningsGrowth")
    mcap = _num(info, "marketCap")
    hi52 = _num(info, "fiftyTwoWeekHigh")
    lo52 = _num(info, "fiftyTwoWeekLow")
    from_hi = pct(close, hi52) if hi52 else None

    def d(x, fmt):
        return fmt(x) if x is not None else None

    return {
        "pe": pe, "pbv": pbv,
        "dividend_yield_pct": dy * 100 if dy is not None else None,
        "roe_pct": roe * 100 if roe is not None else None,
        "earnings_growth_pct": eg * 100 if eg is not None else None,
        "market_cap_idr": mcap,
        "high_52w": hi52, "low_52w": lo52, "from_52w_high_pct": from_hi,
        "display": {
            "pe": d(pe, lambda x: fmt_id(x, 1) + "x"),
            "pbv": d(pbv, lambda x: fmt_id(x, 2) + "x"),
            "dividend_yield": d(dy, lambda x: fmt_id(x * 100, 2) + "%"),
            "roe": d(roe, lambda x: fmt_id(x * 100, 1) + "%"),
            "earnings_growth": d(eg, lambda x: fmt_id(x * 100, 1, sign=True) + "%"),
            "market_cap": d(mcap, lambda x: "Rp" + fmt_id(x / 1e12, 1) + " T"),
            "high_52w": d(hi52, lambda x: fmt_id(x, 0)),
            "low_52w": d(lo52, lambda x: fmt_id(x, 0)),
            "from_52w_high": d(from_hi, lambda x: fmt_id(x, 1, sign=True) + "%"),
        },
        "notes": "earnings_growth = latest quarter vs same quarter last year (Yahoo)",
    }


def upcoming_earnings(tickers: list[dict], today: date, days_ahead: int = 60) -> tuple[list[dict], list[str]]:
    import yfinance as yf

    out, errors = [], []
    for t in tickers:
        try:
            dates = (yf.Ticker(t["symbol"]).calendar or {}).get("Earnings Date") or []
            for d in dates:
                d = d.date() if isinstance(d, datetime) else d
                if isinstance(d, date) and today <= d <= today + timedelta(days=days_ahead):
                    out.append({"symbol": t["symbol"], "name": t["name"], "date": d.isoformat(),
                                "display": {"date": fmt_date_id(d)}})
                    break
        except Exception as e:
            errors.append(f"earnings {t['symbol']}: {type(e).__name__}: {e}")
    out.sort(key=lambda x: x["date"])
    return out, errors


def news_from_snapshots(data_dir: Path, today: date, days: int, cap: int) -> dict:
    """Merge news from saved daily snapshots in the last `days` calendar days."""
    start = today - timedelta(days=days - 1)
    files = sorted(
        p for p in data_dir.glob("*.json")
        if SNAPSHOT_NAME.match(p.name) and start <= date.fromisoformat(p.stem) <= today
    )
    items, seen = [], set()
    for p in files:
        try:
            snap = json.loads(p.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        for n in snap.get("news", []):
            key = re.sub(r"\W+", "", n.get("title", "").lower())
            if key and key not in seen:
                seen.add(key)
                items.append(n)
    items.sort(key=lambda i: i.get("published", ""), reverse=True)
    items.sort(key=lambda i: not i.get("tickers"))  # watchlist-tagged first
    return {
        "coverage": {
            "days_requested": days,
            "snapshots_found": len(files),
            "first": files[0].stem if files else None,
            "last": files[-1].stem if files else None,
        },
        "items": items[:cap],
    }


class StockNotFound(ValueError):
    pass


def resolve_stock(text: str, watchlist: dict) -> dict:
    """Map what the user typed (BBCA, bbca.jk, BCA, Telkom...) to a ticker entry.

    Watchlist aliases match first (case-insensitive, whole name). Otherwise a
    4-letter IDX code is accepted as-is; it's validated later by fetching its
    price history.
    """
    raw = text.strip()
    code = re.sub(r"\.JK$", "", raw.upper())
    for t in watchlist["tickers"]:
        names = {t["symbol"].split(".")[0], t["name"], *t.get("aliases", [])}
        if raw.lower() in {n.lower() for n in names} or code == t["symbol"].split(".")[0]:
            return {**t, "in_watchlist": True}
    if re.fullmatch(r"[A-Z]{4}", code):
        return {"symbol": f"{code}.JK", "name": code, "aliases": [code], "in_watchlist": False}
    raise StockNotFound(
        f"'{raw}' is not a watchlist name or a 4-letter IDX code (e.g. BMRI, GOTO)"
    )


def _clean_company_name(name: str) -> str:
    name = re.sub(r"\b(PT|Tbk|Persero)\b\.?", "", name, flags=re.I)
    return re.sub(r"[().,]", " ", name).strip()


def stock_block(t: dict, now: datetime, n: int, index_change: float, errors: list[str]) -> dict:
    p = perf(history_rows(t["symbol"], now), n, price_decimals=0)
    vs = p["change_pct"] - index_change
    p.update(symbol=t["symbol"], name=t["name"], vs_index_pts=round(vs, 2))
    p["display"]["vs_index"] = fmt_id(vs, 2, sign=True) + " poin"
    try:
        p["valuation"] = valuation(t["symbol"], p["end_close"])
    except Exception as e:
        p["valuation"] = None
        errors.append(f"valuation {t['symbol']}: {type(e).__name__}: {e}")
    return p


def build(period: str, stock: str, now: datetime | None = None, data_dir: Path = DATA_DIR) -> dict:
    now = now or datetime.now(WIB)
    cfg = PERIODS[period]
    n = cfg["sessions"]
    watchlist, _ = load_config()
    errors: list[str] = []

    focus_t = resolve_stock(stock, watchlist)

    idx_rows = history_rows(watchlist["index"]["symbol"], now)  # fatal if this fails
    index = perf(idx_rows, n, price_decimals=2)
    index.update(symbol=watchlist["index"]["symbol"], name=watchlist["index"]["name"])

    try:
        focus = stock_block(focus_t, now, n, index["change_pct"], errors)
    except Exception as e:
        raise StockNotFound(f"no price data for {focus_t['symbol']} ({type(e).__name__}: {e})")
    if not focus_t["in_watchlist"] and focus.get("valuation") is not None:
        # better display name + news aliases for stocks outside the watchlist
        try:
            import yfinance as yf
            info = yf.Ticker(focus_t["symbol"]).info or {}
            long_name = info.get("longName") or info.get("shortName")
            if long_name:
                focus["name"] = focus_t["name"] = long_name
                focus_t["aliases"] = [focus_t["aliases"][0], _clean_company_name(long_name)]
        except Exception:
            pass
    focus["in_watchlist"] = focus_t["in_watchlist"]

    peers = []
    for t in watchlist["tickers"]:
        if t["symbol"] == focus_t["symbol"]:
            continue
        try:
            peers.append(stock_block(t, now, n, index["change_pct"], errors))
        except Exception as e:
            errors.append(f"{t['symbol']}: {type(e).__name__}: {e}")

    outlook_tickers = [focus_t] + [t for t in watchlist["tickers"] if t["symbol"] != focus_t["symbol"]]
    dividends, div_err = fetch_dividends(outlook_tickers, now.date(), days_ahead=30)
    earnings, earn_err = upcoming_earnings(outlook_tickers, now.date())
    errors += div_err + earn_err

    news = news_from_snapshots(data_dir, now.date(), cfg["news_days"], cap=10_000)
    pattern = build_alias_patterns([focus_t])[focus_t["symbol"]]
    focus_news = [i for i in news["items"]
                  if focus_t["symbol"] in i.get("tickers", [])
                  or pattern.search(f"{i.get('title', '')} {i.get('summary', '')}")]
    focus_urls = {i["url"] for i in focus_news}
    general = [i for i in news["items"] if i["url"] not in focus_urls]

    return {
        "generated_at": now.isoformat(timespec="seconds"),
        "status": "ok",
        "status_reason": "fresh data",
        "period": period,
        "sessions": n,
        "start_date": idx_rows[-n]["date"],
        "end_date": idx_rows[-1]["date"],
        "index": index,
        "focus": focus,
        "peers": peers,
        "news": {
            "coverage": news["coverage"],
            "focus_items": focus_news[:30],
            "items": general[: cfg["news_cap"] // 2],
        },
        "outlook": {"dividends": dividends, "earnings": earnings},
        "errors": errors,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="brief-analyze")
    ap.add_argument("--period", choices=sorted(PERIODS), required=True)
    ap.add_argument("--stock", required=True, help="ticker code or watchlist name, e.g. BBCA, Telkom")
    args = ap.parse_args(argv)
    try:
        data = build(args.period, args.stock)
    except StockNotFound as e:
        data = {"status": "not_found", "status_reason": str(e)}
    except Exception as e:
        data = {"status": "error", "status_reason": f"{type(e).__name__}: {e}"}
    data.setdefault("generated_at", datetime.now(WIB).isoformat(timespec="seconds"))
    data.setdefault("period", args.period)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / f"analysis-{args.period}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    cov = data.get("news", {}).get("coverage", {})
    focus = data.get("focus", {})
    print(f"{data['status']}: {data['status_reason']} | {args.period} {focus.get('symbol', args.stock)} "
          f"{data.get('start_date')}→{data.get('end_date')} | news from "
          f"{cov.get('snapshots_found', 0)}/{cov.get('days_requested', '?')} days, "
          f"{len(data.get('news', {}).get('focus_items', []))} about the stock | wrote {path}")
    for err in data.get("errors", []):
        print(f"  warn: {err}")
    return 0 if data["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
