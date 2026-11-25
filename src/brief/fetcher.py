"""Fetch market data + news and write data/YYYY-MM-DD.json. No LLM here.

Output schema (keep stable; the skill and verify.py depend on it):

{
  "generated_at": "2026-11-25T07:20:00+07:00",
  "status": "ok" | "stale" | "error",
  "status_reason": "...",
  "market_date": "2026-11-24",            # date of the latest IHSG close
  "index": {
    "symbol": "^JKSE", "name": "IHSG",
    "close": 7123.45, "change_pct": 0.84,
    "trend_5d": [7050.1, ...],             # last 5 closes, oldest first
    "volume": 1.2e10, "volume_vs_20d": 1.15,
    "display": {"close": "7.123,45", "change_pct": "+0,84%", "volume_vs_20d": "1,15x"}
  },
  "watchlist": [ { same shape as index, plus "name" } ],
  "dividends": [
    {"symbol": "BBRI.JK", "ex_date": "2026-12-03", "amount": 150.0,
     "display": {"amount": "Rp150"}, "source": "yfinance"}
  ],
  "news": [
    {"title": "...", "source": "CNBC Indonesia", "url": "https://...",
     "published": "2026-11-24T18:02:00+07:00", "summary": "...",
     "tickers": ["BBRI.JK"]}               # tagged via watchlist aliases
  ]
}

Every number the brief may show must have a `display` string. See verify.py.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

from brief import CONFIG_DIR, DATA_DIR
from brief.holidays import WIB


def load_config() -> tuple[dict, dict]:
    import yaml

    watchlist = yaml.safe_load((CONFIG_DIR / "watchlist.yaml").read_text())
    feeds = yaml.safe_load((CONFIG_DIR / "feeds.yaml").read_text())
    return watchlist, feeds


def fetch_quote(symbol: str) -> dict:
    """yfinance history (~30d): close, % change, 5d trend, volume vs 20d avg."""
    raise NotImplementedError


def fetch_dividends(symbols: list[str], days_ahead: int = 14) -> list[dict]:
    """Upcoming ex-dates within `days_ahead`, if yfinance has them."""
    raise NotImplementedError


def fetch_news(feeds: dict, aliases: dict[str, list[str]]) -> list[dict]:
    """Items from verified feeds in the lookback window, tagged with tickers."""
    raise NotImplementedError


def is_stale(market_date: str, now: datetime) -> bool:
    """True if the latest IHSG close is older than BRIEF_MAX_STALE_HOURS."""
    raise NotImplementedError


def fmt_id(x: float, decimals: int = 2) -> str:
    """Indonesian number format: 7123.45 -> '7.123,45'."""
    s = f"{x:,.{decimals}f}"
    return s.replace(",", "_").replace(".", ",").replace("_", ".")


def build() -> dict:
    raise NotImplementedError


def write(data: dict, out_dir: Path = DATA_DIR) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    day = datetime.now(WIB).date().isoformat()
    path = out_dir / f"{day}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    (out_dir / "latest.json").write_text(path.read_text())
    return path


def main() -> int:
    try:
        data = build()
    except Exception as e:  # any failure -> explicit error file, never a partial brief
        data = {
            "generated_at": datetime.now(WIB).isoformat(),
            "status": "error",
            "status_reason": f"{type(e).__name__}: {e}",
        }
    path = write(data)
    print(f"{data['status']}: wrote {path}")
    return 0 if data["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
