"""Fetch market data + news and write data/YYYY-MM-DD.json. No LLM here.

Output schema (keep stable; the skill and verify.py depend on it):

{
  "generated_at": "2026-11-25T07:20:00+07:00",
  "status": "ok" | "stale" | "error",
  "status_reason": "...",
  "market_date": "2026-11-24",            # date of the latest IHSG close used
  "expected_market_date": "2026-11-24",   # last completed trading session
  "index": {
    "symbol": "^JKSE", "name": "IHSG",
    "close": 7123.45, "prev_close": 7064.1, "change_pct": 0.84,
    "change_5d_pct": -1.2, "trend_5d": [7050.1, ...],   # oldest first
    "volume": null, "volume_vs_20d": null,              # IDX index has no volume on Yahoo
    "display": {"close": "7.123,45", "change_pct": "+0,84%", "change_5d_pct": "-1,20%",
                "trend_5d": ["7.050,10", ...], "volume_vs_20d": null}
  },
  "watchlist": [ { same shape as index, plus "name" } ],
  "dividends": [
    {"symbol": "BBRI.JK", "name": "...", "ex_date": "2026-12-03",
     "amount": null, "display": {"ex_date": "03 Des 2026", "amount": null},
     "source": "yfinance calendar"}
  ],
  "news": [
    {"title": "...", "source": "CNBC Indonesia Market", "category": "market",
     "url": "https://...", "published": "2026-11-24T18:02:00+07:00",
     "summary": "...", "tickers": ["BBRI.JK"]}
  ],
  "errors": ["TLKM.JK: ...", "feed Detik Finance: ..."]   # non-fatal problems
}

Every number the brief may show has a `display` string. See verify.py.
Fatal (status "error"): IHSG itself can't be fetched. A single watchlist
ticker or feed failing is recorded in `errors` and the rest still goes out.
"""

from __future__ import annotations

import calendar
import html
import json
import os
import re
import sys
import urllib.request
from datetime import date, datetime, time, timedelta
from pathlib import Path

from brief import CONFIG_DIR, DATA_DIR
from brief.holidays import WIB, HolidayConfigError, load_holidays

MARKET_CLOSE_WIB = time(16, 15)  # IDX closes 16:00; small buffer for Yahoo
USER_AGENT = "Mozilla/5.0 (compatible; ihsg-brief/0.1)"
ID_MONTHS = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]


# ---------- formatting (Indonesian style) ----------

def fmt_id(x: float, decimals: int = 2, sign: bool = False) -> str:
    """7123.45 -> '7.123,45'; sign=True -> '+7.123,45'."""
    s = f"{x:{'+' if sign else ''},.{decimals}f}"
    return s.replace(",", "_").replace(".", ",").replace("_", ".")


def fmt_date_id(d: date) -> str:
    return f"{d.day:02d} {ID_MONTHS[d.month - 1]} {d.year}"


# ---------- config ----------

def load_config() -> tuple[dict, dict]:
    import yaml

    watchlist = yaml.safe_load((CONFIG_DIR / "watchlist.yaml").read_text())
    feeds = yaml.safe_load((CONFIG_DIR / "feeds.yaml").read_text())
    return watchlist, feeds


# ---------- trading calendar ----------

def expected_market_date(now: datetime, holidays: dict[date, str]) -> date:
    """Most recent fully completed IDX session as of `now` (WIB)."""
    d = now.date()
    if now.time() < MARKET_CLOSE_WIB:
        d -= timedelta(days=1)
    while d.weekday() >= 5 or d in holidays:
        d -= timedelta(days=1)
    return d


# ---------- quotes ----------

def _history(symbol: str, now: datetime):
    import yfinance as yf

    h = yf.Ticker(symbol).history(period="3mo", interval="1d", auto_adjust=False)
    if h.empty:
        raise RuntimeError("no price history returned")
    h = h.dropna(subset=["Close"])
    # drop today's bar if the session isn't over yet (partial/in-progress data)
    if h.index[-1].date() == now.date() and now.time() < MARKET_CLOSE_WIB:
        h = h.iloc[:-1]
    if len(h) < 6:
        raise RuntimeError(f"only {len(h)} usable rows")
    return h


def fetch_quote(symbol: str, now: datetime, price_decimals: int) -> dict:
    """Close, % change, 5-day trend, volume vs prior-20-session average."""
    h = _history(symbol, now)
    closes = [float(c) for c in h["Close"]]
    close, prev = closes[-1], closes[-2]
    trend = closes[-5:]
    change = (close / prev - 1) * 100
    change_5d = (close / closes[-6] - 1) * 100

    vols = [float(v) for v in h["Volume"]]
    volume = vols[-1] if vols[-1] > 0 else None
    prior = [v for v in vols[-21:-1] if v > 0]
    vol_ratio = volume / (sum(prior) / len(prior)) if volume and len(prior) >= 10 else None

    return {
        "symbol": symbol,
        "market_date": h.index[-1].date().isoformat(),
        "close": round(close, 2),
        "prev_close": round(prev, 2),
        "change_pct": round(change, 2),
        "change_5d_pct": round(change_5d, 2),
        "trend_5d": [round(c, 2) for c in trend],
        "volume": volume,
        "volume_vs_20d": round(vol_ratio, 2) if vol_ratio else None,
        "display": {
            "close": fmt_id(close, price_decimals),
            "prev_close": fmt_id(prev, price_decimals),
            "change_pct": fmt_id(change, 2, sign=True) + "%",
            "change_5d_pct": fmt_id(change_5d, 2, sign=True) + "%",
            "trend_5d": [fmt_id(c, price_decimals) for c in trend],
            "volume_vs_20d": fmt_id(vol_ratio, 2) + "x" if vol_ratio else None,
        },
    }


# ---------- dividends ----------

def fetch_dividends(tickers: list[dict], today: date, days_ahead: int = 14) -> tuple[list[dict], list[str]]:
    """Upcoming ex-dates within `days_ahead`, from Yahoo's calendar.

    Yahoo gives the next ex-date but not the amount of an upcoming dividend,
    so `amount` is null. A proper source (KSEI/IDX announcements) is a later
    improvement.
    """
    import yfinance as yf

    out, errors = [], []
    horizon = today + timedelta(days=days_ahead)
    for t in tickers:
        try:
            cal = yf.Ticker(t["symbol"]).calendar or {}
            ex = cal.get("Ex-Dividend Date")
            if isinstance(ex, datetime):
                ex = ex.date()
            if isinstance(ex, date) and today <= ex <= horizon:
                out.append({
                    "symbol": t["symbol"], "name": t["name"], "ex_date": ex.isoformat(),
                    "amount": None,
                    "display": {"ex_date": fmt_date_id(ex), "amount": None},
                    "source": "yfinance calendar",
                })
        except Exception as e:
            errors.append(f"dividends {t['symbol']}: {type(e).__name__}: {e}")
    out.sort(key=lambda d: d["ex_date"])
    return out, errors


# ---------- news ----------

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def clean_text(s: str) -> str:
    return _WS.sub(" ", html.unescape(_TAG.sub(" ", s or ""))).strip()


def build_alias_patterns(tickers: list[dict]) -> dict[str, re.Pattern]:
    """Word-boundary match on ticker code + aliases. All-caps aliases (BCA, BRI)
    match case-sensitively so 'bri' inside other words doesn't count."""
    pats = {}
    for t in tickers:
        names = {t["symbol"].split(".")[0], *t.get("aliases", [])}
        upper = [re.escape(a) for a in names if a.isupper()]
        other = [re.escape(a) for a in names if not a.isupper()]
        parts = []
        if upper:
            parts.append(r"\b(?:" + "|".join(upper) + r")\b")
        if other:
            parts.append(r"(?i:\b(?:" + "|".join(other) + r")\b)")
        pats[t["symbol"]] = re.compile("|".join(parts))
    return pats


def tag_tickers(text: str, patterns: dict[str, re.Pattern]) -> list[str]:
    return [sym for sym, p in patterns.items() if p.search(text)]


def _get(url: str, timeout: int = 20) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def fetch_news(feeds_cfg: dict, patterns: dict[str, re.Pattern], now: datetime) -> tuple[list[dict], list[str]]:
    """Items from verified feeds within the lookback window, deduped and tagged."""
    import feedparser

    lookback = timedelta(hours=feeds_cfg.get("lookback_hours", 24))
    per_feed = feeds_cfg.get("max_items_per_feed", 15)
    max_summary = feeds_cfg.get("summary_chars", 200)
    skip = tuple(feeds_cfg.get("skip_title_prefixes", []))

    items, errors, seen = [], [], set()
    for f in feeds_cfg["feeds"]:
        if not f.get("verified"):
            continue
        try:
            parsed = feedparser.parse(_get(f["url"]))
        except Exception as e:
            errors.append(f"feed {f['name']}: {type(e).__name__}: {e}")
            continue
        if not parsed.entries:
            errors.append(f"feed {f['name']}: no entries")
            continue
        kept = []
        for e in parsed.entries:
            ts = e.get("published_parsed") or e.get("updated_parsed")
            title = clean_text(e.get("title", ""))
            link = e.get("link")
            if not (ts and title and link) or title.startswith(skip):
                continue
            published = datetime.fromtimestamp(calendar.timegm(ts), WIB)
            if now - published > lookback or published > now + timedelta(minutes=10):
                continue
            key = re.sub(r"\W+", "", title.lower())
            if key in seen:
                continue
            seen.add(key)
            summary = clean_text(e.get("summary", ""))
            if len(summary) > max_summary:
                summary = summary[:max_summary].rsplit(" ", 1)[0] + "…"
            kept.append({
                "title": title,
                "source": f["name"],
                "category": f.get("category", "economy"),
                "url": link,
                "published": published.isoformat(timespec="minutes"),
                "summary": summary,
                "tickers": tag_tickers(f"{title} {summary}", patterns),
            })
        kept.sort(key=lambda i: i["published"], reverse=True)
        items.extend(kept[:per_feed])

    # ticker-tagged first, then newest
    items.sort(key=lambda i: i["published"], reverse=True)
    items.sort(key=lambda i: not i["tickers"])  # stable: tagged first, each group newest first
    return items, errors


# ---------- assemble ----------

def build(now: datetime | None = None) -> dict:
    now = now or datetime.now(WIB)
    watchlist, feeds_cfg = load_config()
    errors: list[str] = []

    try:
        holidays = load_holidays(now.year)
    except HolidayConfigError as e:
        holidays = {}
        errors.append(f"holidays: {e} (stale check uses weekends only)")
    expected = expected_market_date(now, holidays)

    idx_cfg = watchlist["index"]
    index = fetch_quote(idx_cfg["symbol"], now, price_decimals=2)  # fatal if this fails
    index["name"] = idx_cfg["name"]
    market_date = date.fromisoformat(index["market_date"])

    rows = []
    for t in watchlist["tickers"]:
        try:
            q = fetch_quote(t["symbol"], now, price_decimals=0)
            q["name"] = t["name"]
            if q["market_date"] != index["market_date"]:
                errors.append(f"{t['symbol']}: last close {q['market_date']} differs from IHSG {index['market_date']}")
            rows.append(q)
        except Exception as e:
            errors.append(f"{t['symbol']}: {type(e).__name__}: {e}")

    dividends, div_err = fetch_dividends(watchlist["tickers"], now.date())
    news, news_err = fetch_news(feeds_cfg, build_alias_patterns(watchlist["tickers"]), now)
    errors += div_err + news_err

    status, reason = "ok", "fresh data"
    if market_date < expected:
        status = "stale"
        reason = f"latest IHSG close is {market_date}, expected {expected}"

    return {
        "generated_at": now.isoformat(timespec="seconds"),
        "status": status,
        "status_reason": reason,
        "market_date": market_date.isoformat(),
        "expected_market_date": expected.isoformat(),
        "index": index,
        "watchlist": rows,
        "dividends": dividends,
        "news": news,
        "errors": errors,
    }


def write(data: dict, out_dir: Path | None = None) -> Path:
    out_dir = out_dir or Path(os.environ.get("BRIEF_DATA_DIR") or DATA_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    day = datetime.now(WIB).date().isoformat()
    path = out_dir / f"{day}.json"
    text = json.dumps(data, ensure_ascii=False, indent=2)
    path.write_text(text)
    (out_dir / "latest.json").write_text(text)
    return path


def main() -> int:
    try:
        data = build()
    except Exception as e:  # any fatal failure -> explicit error file, never a partial brief
        data = {
            "generated_at": datetime.now(WIB).isoformat(timespec="seconds"),
            "status": "error",
            "status_reason": f"{type(e).__name__}: {e}",
        }
    path = write(data)
    n_news = len(data.get("news", []))
    print(f"{data['status']}: {data['status_reason']} | {n_news} news | wrote {path}")
    for err in data.get("errors", []):
        print(f"  warn: {err}")
    return 0 if data["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
