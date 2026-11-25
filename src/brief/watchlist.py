"""Manage config/watchlist.yaml from the command line (and Telegram via /watch).

Usage:
  brief-watch list
  brief-watch add BMRI          # validates the code on Yahoo, fills name + aliases
  brief-watch remove ASII

Prints one short human-readable result line (the skill relays it as-is).
Exit 0 = done, 1 = refused (unknown code, duplicate, limit), 2 = bad usage.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from brief import CONFIG_DIR

WATCHLIST_PATH = CONFIG_DIR / "watchlist.yaml"
MAX_TICKERS = 15  # keeps data.json and the brief short

HEADER = """\
# Watchlist for the daily brief and /analysis peers.
# Managed by `brief-watch` (Telegram: /watch). Hand edits are fine, but
# comments other than this header are not preserved.
# aliases are used to tag news items with the stock.

"""


class WatchError(ValueError):
    pass


def load(path: Path = WATCHLIST_PATH) -> dict:
    import yaml

    return yaml.safe_load(path.read_text())


def save(data: dict, path: Path = WATCHLIST_PATH) -> None:
    import yaml

    body = yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100)
    path.write_text(HEADER + body)


def normalize_code(text: str) -> str:
    code = re.sub(r"\.JK$", "", text.strip().upper())
    if not re.fullmatch(r"[A-Z]{4}", code):
        raise WatchError(f"'{text}' bukan kode saham IDX 4 huruf (contoh: BMRI)")
    return code


def _clean_name(name: str) -> str:
    name = re.sub(r"\b(PT|Tbk|Persero)\b\.?", "", name, flags=re.I)
    return re.sub(r"\s+", " ", re.sub(r"[().,]", " ", name)).strip()


def lookup(code: str) -> dict:
    """Check the code exists on Yahoo and build a watchlist entry."""
    import yfinance as yf

    t = yf.Ticker(f"{code}.JK")
    h = t.history(period="5d", interval="1d")
    if h.empty:
        raise WatchError(f"{code} tidak ditemukan di data bursa")
    try:
        info = t.info or {}
    except Exception:
        info = {}
    name = _clean_name(info.get("longName") or info.get("shortName") or code)
    aliases = [code] + ([name] if name and name != code else [])
    return {"symbol": f"{code}.JK", "name": name, "aliases": aliases}


def add(code_text: str, path: Path = WATCHLIST_PATH, lookup_fn=lookup) -> str:
    code = normalize_code(code_text)
    data = load(path)
    tickers = data.setdefault("tickers", [])
    if any(t["symbol"] == f"{code}.JK" for t in tickers):
        raise WatchError(f"{code} sudah ada di watchlist")
    if len(tickers) >= MAX_TICKERS:
        raise WatchError(f"watchlist penuh ({MAX_TICKERS} saham); hapus satu dulu")
    entry = lookup_fn(code)
    tickers.append(entry)
    save(data, path)
    return f"✅ {code} ({entry['name']}) ditambahkan. Watchlist: {codes(data)}"


def remove(code_text: str, path: Path = WATCHLIST_PATH) -> str:
    code = normalize_code(code_text)
    data = load(path)
    tickers = data.get("tickers", [])
    keep = [t for t in tickers if t["symbol"] != f"{code}.JK"]
    if len(keep) == len(tickers):
        raise WatchError(f"{code} tidak ada di watchlist. Watchlist: {codes(data)}")
    if not keep:
        raise WatchError("watchlist tidak boleh kosong; tambah saham lain dulu")
    data["tickers"] = keep
    save(data, path)
    return f"🗑 {code} dihapus. Watchlist: {codes(data)}"


def codes(data: dict) -> str:
    return ", ".join(t["symbol"].split(".")[0] for t in data.get("tickers", [])) or "(kosong)"


def show(path: Path = WATCHLIST_PATH) -> str:
    data = load(path)
    lines = [f"📋 Watchlist ({len(data.get('tickers', []))}/{MAX_TICKERS}):"]
    lines += [f"• {t['symbol'].split('.')[0]} — {t['name']}" for t in data.get("tickers", [])]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    try:
        if args == ["list"] or not args:
            print(show())
        elif len(args) == 2 and args[0] == "add":
            print(add(args[1]))
        elif len(args) == 2 and args[0] == "remove":
            print(remove(args[1]))
        else:
            print("Format: /watch list | /watch add KODE | /watch remove KODE")
            return 2
    except WatchError as e:
        print(f"⚠️ {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
