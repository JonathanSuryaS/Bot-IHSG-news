"""/fundamental: multi-year financial statements and trends (Yahoo annual data).

Pure Python, no LLM.

    brief-fundamental BBRI
"""
from __future__ import annotations

import math
import sys
from dataclasses import dataclass, field

from .analysis import StockNotFound, _clean_company_name, resolve_stock
from .fetcher import fmt_id, load_config

FOOTER = ("Sumber: Yahoo Finance (laporan tahunan). Angka bisa sedikit berbeda dari "
          "laporan resmi di idx.co.id.\nℹ️ Data historis, bukan rekomendasi beli/jual.")

# First row name that exists wins (Yahoo names differ between companies).
ROWS = {
    "revenue": ["Total Revenue", "Operating Revenue"],
    "net_income": ["Net Income Common Stockholders", "Net Income"],
    "eps": ["Basic EPS", "Diluted EPS"],
    "equity": ["Stockholders Equity", "Common Stock Equity"],
    "assets": ["Total Assets"],
    "debt": ["Total Debt"],
    "ocf": ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities",
            "Cash Flowsfromusedin Operating Activities Direct"],
    "capex": ["Capital Expenditure"],
    "dividends": ["Cash Dividends Paid", "Common Stock Dividend Paid"],
    "shares": ["Ordinary Shares Number", "Share Issued"],
}


@dataclass
class Fundamentals:
    symbol: str
    code: str
    name: str
    is_bank: bool
    years: list[int]
    data: dict[str, list[float | None]] = field(default_factory=dict)

    def get(self, key: str) -> list[float | None]:
        return self.data.get(key, [None] * len(self.years))


def _val(x) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) else v


def from_frames(symbol: str, code: str, name: str, is_bank: bool, frames: list) -> Fundamentals:
    """Build from yfinance DataFrames (rows = items, columns = year-end dates)."""
    cols = sorted({c for df in frames for c in df.columns})
    years = [c.year for c in cols]
    data: dict[str, list[float | None]] = {}
    for key, names in ROWS.items():
        for df in frames:
            row = next((n for n in names if n in df.index), None)
            if row is not None:
                data[key] = [_val(df.loc[row].get(c)) for c in cols]
                break
    # Drop years where we have neither revenue nor net income (Yahoo's empty oldest column).
    keep = [i for i in range(len(years))
            if any(data.get(k, [None] * len(years))[i] is not None for k in ("revenue", "net_income"))]
    f = Fundamentals(symbol, code, name, is_bank, [years[i] for i in keep],
                     {k: [v[i] for i in keep] for k, v in data.items()})
    derive(f)
    return f


def _div(a, b):
    return a / b if a is not None and b not in (None, 0) else None


def derive(f: Fundamentals) -> None:
    n = len(f.years)
    ni, rev, eq = f.get("net_income"), f.get("revenue"), f.get("equity")
    debt, ocf, capex = f.get("debt"), f.get("ocf"), f.get("capex")
    div, shares = f.get("dividends"), f.get("shares")
    f.data["npm"] = [_div(ni[i], rev[i]) for i in range(n)]
    f.data["roe"] = [_div(ni[i], eq[i]) for i in range(n)]
    f.data["der"] = [_div(debt[i], eq[i]) for i in range(n)]
    f.data["fcf"] = [ocf[i] + capex[i] if ocf[i] is not None and capex[i] is not None else None
                     for i in range(n)]
    paid = [abs(d) if d is not None else None for d in div]
    f.data["dividends"] = paid
    f.data["payout"] = [_div(paid[i], ni[i]) for i in range(n)]
    f.data["dps"] = [_div(paid[i], shares[i]) for i in range(n)]
    if all(v is None for v in f.get("eps")):
        f.data["eps"] = [_div(ni[i], shares[i]) for i in range(n)]


def cagr(series: list[float | None]) -> float | None:
    """Annual growth from the first to the last available positive value."""
    pts = [(i, v) for i, v in enumerate(series) if v is not None]
    if len(pts) < 2:
        return None
    (i0, a), (i1, b) = pts[0], pts[-1]
    if a <= 0 or b <= 0 or i1 == i0:
        return None
    return (b / a) ** (1 / (i1 - i0)) - 1


def load(stock: str) -> Fundamentals:
    import yfinance as yf

    watchlist, _ = load_config()
    t = resolve_stock(stock, watchlist)
    tk = yf.Ticker(t["symbol"])
    frames = [tk.income_stmt, tk.balance_sheet, tk.cashflow]
    if all(df is None or df.empty for df in frames):
        raise StockNotFound(f"Laporan keuangan {t['symbol']} tidak ada di Yahoo.")
    info = tk.info or {}
    code = t["symbol"].split(".")[0]
    name = t["name"] if t.get("in_watchlist") else \
        _clean_company_name(info.get("longName") or code) or code
    is_bank = "bank" in (info.get("industry") or "").lower()
    return from_frames(t["symbol"], code, name, is_bank, [df for df in frames if df is not None])


# ---------- text ----------

def _t(v):  # trillions
    return "–" if v is None else fmt_id(v / 1e12, 1)


def _p(v):
    return "–" if v is None else fmt_id(v * 100, 1) + "%"


def _rp(v):
    return "–" if v is None else fmt_id(v, 0)


def _x(v):
    return "–" if v is None else fmt_id(v, 2) + "x"


def _line(label: str, vals: list, fmt, growth: bool = False) -> str | None:
    if all(v is None for v in vals):
        return None
    s = f"{label}: " + " · ".join(fmt(v) for v in vals)
    if growth:
        g = cagr(vals)
        if g is not None:
            s += f" (CAGR {fmt_id(g * 100, 1, sign=True)}%/thn)"
    return s


def _direction(vals: list) -> str:
    pts = [v for v in vals if v is not None]
    ups = sum(1 for a, b in zip(pts, pts[1:]) if b > a)
    return f"naik {ups} dari {len(pts) - 1} tahun" if len(pts) > 1 else "data kurang"


def summary_lines(f: Fundamentals) -> list[str]:
    out = []
    rev, ni, roe = f.get("revenue"), f.get("net_income"), f.get("roe")
    if any(v is not None for v in rev):
        out.append(f"Pendapatan {_direction(rev)}; laba bersih {_direction(ni)}.")
    r = [v for v in roe if v is not None]
    if r:
        avg = sum(r) / len(r)
        word = "tinggi (>15%)" if avg > 0.15 else "sedang (10–15%)" if avg >= 0.10 else "rendah (<10%)"
        out.append(f"ROE rata-rata {_p(avg)}: {word}.")
    npm = [v for v in f.get("npm") if v is not None]
    if len(npm) >= 2:
        word = "membaik" if npm[-1] > npm[0] else "menurun" if npm[-1] < npm[0] else "stabil"
        out.append(f"Net margin {word} ({_p(npm[0])} → {_p(npm[-1])}).")
    if not f.is_bank:
        der = [v for v in f.get("der") if v is not None]
        if der:
            out.append(f"DER terakhir {_x(der[-1])}"
                       + (": utang lebih besar dari modal." if der[-1] > 1 else ": utang di bawah modal."))
        fcf = [v for v in f.get("fcf") if v is not None]
        if fcf:
            neg = sum(1 for v in fcf if v < 0)
            out.append("Free cash flow selalu positif." if neg == 0 else
                       f"Free cash flow negatif di {neg} dari {len(fcf)} tahun.")
    pay = [v for v in f.get("payout") if v is not None]
    if pay and pay[-1] > 1:
        out.append("Dividen tahun terakhir melebihi laba (payout >100%).")
    return out


def render(f: Fundamentals) -> str:
    lines = [f"📊 Fundamental {f.code} — {f.name}",
             f"Laporan tahunan, Rp triliun kecuali disebut lain"
             + (" · bank" if f.is_bank else ""),
             "Tahun: " + " · ".join(str(y) for y in f.years), ""]
    body = [
        _line("💵 Pendapatan", f.get("revenue"), _t, True),
        _line("💰 Laba bersih", f.get("net_income"), _t, True),
        _line("📐 Net margin", f.get("npm"), _p),
        _line("🧾 EPS (Rp)", f.get("eps"), _rp, True),
        "",
        _line("🏦 Ekuitas", f.get("equity"), _t, True),
        _line("📈 ROE", f.get("roe"), _p),
    ]
    if not f.is_bank:
        body += [_line("💳 Utang", f.get("debt"), _t), _line("⚖️ DER", f.get("der"), _x), "",
                 _line("🔄 Arus kas operasi", f.get("ocf"), _t),
                 _line("🏗 Capex", f.get("capex"), _t),
                 _line("💧 Free cash flow", f.get("fcf"), _t)]
    body += ["", _line("💸 Dividen dibayar", f.get("dividends"), _t),
             _line("🧮 Payout ratio", f.get("payout"), _p),
             "(dividen yang dibayar tahun ini biasanya dari laba tahun lalu)"
             if any(v is not None for v in f.get("dividends")) else None]
    lines += [b for b in body if b is not None]
    lines += ["", "🔎 Ringkasan"] + [f"• {s}" for s in summary_lines(f)]
    if f.is_bank:
        lines.append("• Bank: utang & free cash flow tidak dipakai (dana nasabah = bahan baku bank).")
    lines += ["", "ROE = laba ÷ ekuitas akhir tahun. Penjelasan rumus: /formula ROE", "", FOOTER]
    # collapse double blank lines
    out = []
    for l in lines:
        if l == "" and out and out[-1] == "":
            continue
        out.append(l)
    return "\n".join(out)


def main() -> None:
    args = sys.argv[1:]
    if len(args) != 1:
        print("Format: /fundamental KODE (contoh: /fundamental BBRI)")
        sys.exit(1)
    try:
        print(render(load(args[0])))
    except StockNotFound as e:
        print(f"Saham tidak ditemukan: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Gagal mengambil laporan keuangan ({type(e).__name__}). Coba lagi nanti.")
        print(f"fundamental error: {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
