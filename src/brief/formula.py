"""/formula: explain financial ratios, optionally with a live value for a stock.

Pure Python, no LLM. Text lives in config/formulas.yaml.

    brief-formula               # list of all terms
    brief-formula ROE           # what ROE means, formula, example, how to read
    brief-formula ROE BBRI      # same + BBRI's current ROE from Yahoo
"""
from __future__ import annotations

import re
import sys

from . import CONFIG_DIR
from .analysis import StockNotFound, resolve_stock
from .fetcher import fmt_id, load_config

FOOTER = "ℹ️ Edukasi, bukan rekomendasi beli/jual."


def load() -> dict:
    import yaml

    return yaml.safe_load((CONFIG_DIR / "formulas.yaml").read_text())


def _key(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().upper())


def find(cfg: dict, text: str) -> str | None:
    k = _key(text)
    for code, t in cfg["terms"].items():
        names = {code, *(_key(a) for a in t.get("aliases", []))}
        if k in names or k.replace("/", "") in {n.replace("/", "") for n in names}:
            return code
    return None


def fmt_value(v, kind: str) -> str | None:
    if not isinstance(v, (int, float)):
        return None
    if kind == "ratio":
        return fmt_id(v, 2) + "x"
    if kind == "pct":
        return fmt_id(v * 100, 2) + "%"
    if kind == "pct_nonzero":
        return None if v == 0 else fmt_id(v * 100, 2) + "%"
    if kind == "rp":
        return "Rp" + fmt_id(v, 0 if abs(v) >= 100 else 2)
    if kind == "rp_t":
        return "Rp" + fmt_id(v / 1e12, 2) + " T"
    if kind == "der":
        return fmt_id(v / 100, 2) + "x"
    return None


def menu(cfg: dict) -> str:
    lines = ["📚 Daftar rumus", ""]
    for g in cfg["groups"]:
        lines.append(g["name"])
        lines.append(" · ".join(g["terms"]))
        lines.append("")
    lines += ["Ketik /formula ROE untuk penjelasan,",
              "atau /formula ROE BBRI untuk nilai BBRI sekarang.", "", FOOTER]
    return "\n".join(lines)


def card(t: dict, live: tuple[str, str] | None = None) -> str:
    lines = [f"📘 {t['name']}", "",
             f"Apa artinya: {t['meaning']}",
             f"Sumber data: {t['source']}", "",
             f"🧮 Rumus: {t['formula']}",
             f"Contoh: {t['example']}", "",
             f"👀 Cara baca: {t['read']}"]
    if live:
        code, value = live
        lines += ["", f"📍 {code} sekarang: {value}"]
    lines += ["", FOOTER]
    return "\n".join(lines)


def live_value(t: dict, stock: str) -> tuple[str, str]:
    import yfinance as yf

    watchlist, _ = load_config()
    s = resolve_stock(stock, watchlist)
    code = s["symbol"].split(".")[0]
    if not t.get("yahoo"):
        return code, "tidak ada di data Yahoo (dihitung dari portofolio/riwayat)"
    info = yf.Ticker(s["symbol"]).info or {}
    if not info.get("regularMarketPrice") and not info.get("currentPrice"):
        raise StockNotFound(f"Kode {code} tidak ditemukan di Yahoo.")
    v = fmt_value(info.get(t["yahoo"]), t.get("kind", "ratio"))
    return code, v or "tidak tersedia untuk saham ini"


def run(args: list[str]) -> str:
    cfg = load()
    if not args:
        return menu(cfg)
    # Last arg is a stock if it's a 4-letter code / watchlist name and the rest is a term.
    term, stock = " ".join(args), None
    if find(cfg, term) is None and len(args) >= 2:
        term, stock = " ".join(args[:-1]), args[-1]
    code = find(cfg, term)
    if code is None:
        return f"Rumus '{term}' belum ada.\n\n" + menu(cfg)
    t = cfg["terms"][code]
    return card(t, live_value(t, stock) if stock else None)


def main() -> None:
    try:
        print(run(sys.argv[1:]))
    except StockNotFound as e:
        print(f"Saham tidak ditemukan: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Gagal mengambil data ({type(e).__name__}). Coba lagi nanti.")
        print(f"formula error: {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
