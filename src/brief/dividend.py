"""/dividen: dividend history, trend, yield and (optionally) yield on cost.

Pure Python, no LLM: every number is computed here from Yahoo data.

    brief-dividend BBRI           # history, trend, yield
    brief-dividend BBRI 3800      # + yield on cost for a buy price of Rp3.800
"""
from __future__ import annotations

import sys
from datetime import date, datetime

from .analysis import StockNotFound, _clean_company_name, resolve_stock
from .fetcher import WIB, fmt_date_id, fmt_id, load_config

YEARS_SHOWN = 5
LOT = 100


def rp(x: float) -> str:
    """Rupiah amount: no decimals when whole, else 2 (dividends like 231,22)."""
    return "Rp" + fmt_id(x, 0 if abs(x - round(x)) < 0.005 else 2)


def summarize(payments: list[tuple[date, float]], price: float, today: date,
              buy_price: float | None = None) -> dict:
    """Group payments per calendar year (by ex-date) and compute yields."""
    by_year: dict[int, list[float]] = {}
    for d, amt in sorted(payments):
        by_year.setdefault(d.year, []).append(amt)
    years = sorted(by_year)[-YEARS_SHOWN:]
    rows = [{"year": y, "total": sum(by_year[y]), "count": len(by_year[y]),
             "partial": y == today.year} for y in years]

    # Trend over complete years only (the current year may not be finished).
    full = [r for r in rows if not r["partial"]]
    trend = []
    for prev, cur in zip(full, full[1:]):
        pct = (cur["total"] - prev["total"]) / prev["total"] * 100 if prev["total"] else None
        trend.append({"year": cur["year"], "pct": pct})

    cutoff = today.replace(year=today.year - 1)
    ttm = sum(a for d, a in payments if cutoff < d <= today)
    out = {"rows": rows, "trend": trend, "ttm": ttm, "price": price,
           "yield_pct": ttm / price * 100 if price else None}
    if buy_price:
        out["buy"] = {"price": buy_price, "yoc_pct": ttm / buy_price * 100,
                      "per_lot": ttm * LOT,
                      "price_change_pct": (price - buy_price) / buy_price * 100}
    return out


def render(code: str, name: str, s: dict, payout_ratio: float | None,
           next_ex: date | None) -> str:
    lines = [f"💰 Dividen {code} — {name}", ""]
    if not s["rows"]:
        lines += ["Belum ada riwayat dividen di data Yahoo.", "",
                  "ℹ️ Data historis, bukan jaminan dividen ke depan."]
        return "\n".join(lines)

    lines.append("📅 Riwayat (per tahun, menurut ex-date)")
    for r in s["rows"]:
        note = f"{r['count']}x bayar" + (", sejauh ini" if r["partial"] else "")
        lines.append(f"{r['year']}: {rp(r['total'])} ({note})")
    lines.append("")

    if s["trend"]:
        parts = []
        for t in s["trend"]:
            if t["pct"] is None:
                continue
            word = "naik" if t["pct"] > 0 else "turun" if t["pct"] < 0 else "sama"
            parts.append(f"{t['year']} {word} {fmt_id(abs(t['pct']), 1)}%")
        if parts:
            lines += ["📈 Tren: " + " · ".join(parts), ""]

    if s["yield_pct"] is not None:
        lines.append(f"🎯 Yield 12 bulan: {rp(s['ttm'])} ÷ harga {rp(s['price'])} "
                     f"= {fmt_id(s['yield_pct'], 2)}%")
    if payout_ratio is not None:
        lines.append(f"🧮 Payout ratio: {fmt_id(payout_ratio * 100, 0)}% dari laba")
    lines.append("📅 Ex-date berikutnya: "
                 + (fmt_date_id(next_ex) if next_ex else "belum diumumkan"))

    b = s.get("buy")
    if b:
        lines += ["", f"💵 Jika beli di {rp(b['price'])}",
                  f"Yield on cost: {fmt_id(b['yoc_pct'], 2)}%",
                  f"Per lot ({LOT} lembar): {rp(b['per_lot'])} / 12 bulan terakhir",
                  f"Harga sekarang vs beli: {fmt_id(b['price_change_pct'], 2, sign=True)}%"]

    lines += ["", "ℹ️ Data historis, bukan jaminan dividen ke depan."]
    return "\n".join(lines)


def run(stock: str, buy_price: float | None = None, now: datetime | None = None) -> str:
    import yfinance as yf

    now = now or datetime.now(WIB)
    watchlist, _ = load_config()
    t = resolve_stock(stock, watchlist)
    code = t["symbol"].split(".")[0]
    tk = yf.Ticker(t["symbol"])

    hist = tk.history(period="5d")
    if hist.empty:
        raise StockNotFound(f"Kode {code} tidak ditemukan di Yahoo.")
    price = float(hist["Close"].iloc[-1])

    payments = [(ts.date(), float(v)) for ts, v in tk.dividends.items() if v > 0]
    info = tk.info or {}
    payout = info.get("payoutRatio")
    payout = float(payout) if isinstance(payout, (int, float)) and payout > 0 else None
    name = t["name"] if t.get("in_watchlist") else \
        _clean_company_name(info.get("longName") or code) or code

    next_ex = None
    try:
        ex = (tk.calendar or {}).get("Ex-Dividend Date")
        ex = ex.date() if isinstance(ex, datetime) else ex
        if isinstance(ex, date) and ex >= now.date():
            next_ex = ex
    except Exception:
        pass

    s = summarize(payments, price, now.date(), buy_price)
    return render(code, name, s, payout, next_ex)


def parse_price(text: str) -> float:
    """'3800', '3.800', 'Rp3.800', '3800,5' -> float."""
    t = text.strip().lower().removeprefix("rp").strip()
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    else:
        t = t.replace(".", "")
    v = float(t)
    if v <= 0:
        raise ValueError
    return v


USAGE = "Format: /dividen KODE  atau  /dividen KODE HARGA_BELI (contoh: /dividen BBRI 3800)"


def main() -> None:
    args = sys.argv[1:]
    if not 1 <= len(args) <= 2:
        print(USAGE)
        sys.exit(1)
    try:
        buy = parse_price(args[1]) if len(args) == 2 else None
    except ValueError:
        print(f"Harga beli '{args[1]}' tidak valid. {USAGE}")
        sys.exit(1)
    try:
        print(run(args[0], buy))
    except StockNotFound as e:
        print(f"Saham tidak ditemukan: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Gagal mengambil data dividen ({type(e).__name__}). Coba lagi nanti.")
        print(f"dividen error: {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
