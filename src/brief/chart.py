"""/chart: candlestick image + technical summary for an IDX stock or IHSG.

Pure Python, no LLM: indicators are computed here, the text only describes
them. Nothing here predicts prices or says buy/sell.

    brief-chart BBRI                # daily candles, ~6 months
    brief-chart BBRI weekly         # weekly candles, ~2 years
    brief-chart IHSG --send         # also send image + text to Telegram
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime

from . import DATA_DIR
from .analysis import StockNotFound, _clean_company_name, resolve_stock
from .fetcher import WIB, fmt_date_id, fmt_id, load_config

FOOTER = "ℹ️ Analisis teknikal = membaca pola harga masa lalu, bukan ramalan atau rekomendasi beli/jual."

PERIODS = {
    "daily": {"fetch": "1y", "interval": "1d", "show": 120, "label": "harian, ±6 bulan",
              "unit": "hari", "ma": (20, 50)},
    "weekly": {"fetch": "5y", "interval": "1wk", "show": 104, "label": "mingguan, ±2 tahun",
               "unit": "minggu", "ma": (10, 40)},
}
PERIOD_WORDS = {"daily": "daily", "harian": "daily", "d": "daily",
                "weekly": "weekly", "mingguan": "weekly", "w": "weekly"}


@dataclass
class Bar:
    o: float
    h: float
    l: float
    c: float
    v: float


# ---------- indicators (plain lists, easy to test) ----------

def sma(xs: list[float], n: int) -> list[float | None]:
    out: list[float | None] = []
    for i in range(len(xs)):
        out.append(sum(xs[i - n + 1:i + 1]) / n if i >= n - 1 else None)
    return out


def ema(xs: list[float], n: int) -> list[float]:
    k, out = 2 / (n + 1), []
    for i, x in enumerate(xs):
        out.append(x if i == 0 else x * k + out[-1] * (1 - k))
    return out


def rsi(closes: list[float], n: int = 14) -> float | None:
    """Wilder's RSI of the last bar."""
    if len(closes) <= n:
        return None
    gains = [max(closes[i] - closes[i - 1], 0) for i in range(1, len(closes))]
    losses = [max(closes[i - 1] - closes[i], 0) for i in range(1, len(closes))]
    ag, al = sum(gains[:n]) / n, sum(losses[:n]) / n
    for g, l in zip(gains[n:], losses[n:]):
        ag, al = (ag * (n - 1) + g) / n, (al * (n - 1) + l) / n
    if al == 0:
        return 100.0
    return 100 - 100 / (1 + ag / al)


def macd(closes: list[float]) -> tuple[list[float], list[float]]:
    line = [a - b for a, b in zip(ema(closes, 12), ema(closes, 26))]
    return line, ema(line, 9)


def candle_pattern(bars: list[Bar]) -> str | None:
    """Name of a classic pattern on the last 1-2 candles, in Indonesian."""
    if len(bars) < 2:
        return None
    p, b = bars[-2], bars[-1]
    rng = b.h - b.l
    if rng <= 0:
        return None
    body = abs(b.c - b.o)
    upper, lower = b.h - max(b.o, b.c), min(b.o, b.c) - b.l
    if p.c < p.o and b.c > b.o and b.o <= p.c and b.c >= p.o:
        return "Bullish engulfing (candle hijau menelan candle merah sebelumnya)"
    if p.c > p.o and b.c < b.o and b.o >= p.c and b.c <= p.o:
        return "Bearish engulfing (candle merah menelan candle hijau sebelumnya)"
    if body <= 0.1 * rng:
        return "Doji (buka ≈ tutup: pembeli dan penjual seimbang, ragu-ragu)"
    if lower >= 2 * body and upper <= 0.3 * body + 0.1 * rng:
        return "Hammer (ekor bawah panjang: harga sempat turun lalu ditarik naik)"
    if upper >= 2 * body and lower <= 0.3 * body + 0.1 * rng:
        return "Shooting star (ekor atas panjang: harga sempat naik lalu ditekan turun)"
    if body >= 0.9 * rng:
        return ("Marubozu hijau (hampir tanpa ekor: pembeli dominan sepanjang sesi)"
                if b.c > b.o else
                "Marubozu merah (hampir tanpa ekor: penjual dominan sepanjang sesi)")
    return None


def analyze(bars: list[Bar], ma: tuple[int, int]) -> dict:
    closes = [b.c for b in bars]
    last = bars[-1]
    fast, slow = sma(closes, ma[0])[-1], sma(closes, ma[1])[-1]
    line, signal = macd(closes)
    hist = [a - b for a, b in zip(line, signal)]
    cross = None
    for i in range(max(1, len(hist) - 3), len(hist)):
        if hist[i - 1] <= 0 < hist[i]:
            cross = "up"
        elif hist[i - 1] >= 0 > hist[i]:
            cross = "down"
    win = bars[-20:]
    vols = [b.v for b in bars[-21:-1]]
    avg_vol = sum(vols) / len(vols) if vols else 0
    return {
        "close": last.c,
        "change_pct": (last.c - bars[-2].c) / bars[-2].c * 100 if len(bars) > 1 else None,
        "ma_fast": fast, "ma_slow": slow,
        "rsi": rsi(closes),
        "macd_hist": hist[-1], "macd_cross": cross,
        "support": min(b.l for b in win), "resistance": max(b.h for b in win),
        "vol_ratio": last.v / avg_vol if avg_vol else None,
        "pattern": candle_pattern(bars),
    }


# ---------- text ----------

def describe(a: dict, ma: tuple[int, int], unit: str, dec: int) -> list[str]:
    f = lambda x: fmt_id(x, dec)  # noqa: E731
    c = a["close"]
    lines = ["📏 Tren (moving average)"]
    if a["ma_fast"] is not None and a["ma_slow"] is not None:
        pos = lambda m: "di atas" if c > m else "di bawah"  # noqa: E731
        lines.append(f"Harga {f(c)} {pos(a['ma_fast'])} MA{ma[0]} ({f(a['ma_fast'])}) "
                     f"dan {pos(a['ma_slow'])} MA{ma[1]} ({f(a['ma_slow'])})")
        if c > a["ma_fast"] > a["ma_slow"]:
            lines.append("→ susunan naik (uptrend): harga > MA pendek > MA panjang")
        elif c < a["ma_fast"] < a["ma_slow"]:
            lines.append("→ susunan turun (downtrend): harga < MA pendek < MA panjang")
        else:
            lines.append("→ campuran: belum ada tren yang jelas (sideways/transisi)")
    else:
        lines.append("Data belum cukup untuk moving average.")

    lines += ["", "⚡ Momentum"]
    r = a["rsi"]
    if r is not None:
        zone = ("jenuh beli (overbought, sudah naik kencang)" if r >= 70 else
                "jenuh jual (oversold, sudah turun dalam)" if r <= 30 else "netral")
        lines.append(f"RSI 14: {fmt_id(r, 1)} → {zone}")
    macd_word = "positif (momentum naik)" if a["macd_hist"] > 0 else "negatif (momentum turun)"
    cross = {"up": ", baru saja cross ke atas", "down": ", baru saja cross ke bawah"}.get(
        a["macd_cross"], "")
    lines.append(f"MACD: {macd_word}{cross}")

    lines += ["", f"🧱 Area harga 20 {unit} terakhir",
              f"Support (terendah): {f(a['support'])} · Resistance (tertinggi): {f(a['resistance'])}"]
    if a["vol_ratio"] is not None:
        lines.append(f"Volume terakhir: {fmt_id(a['vol_ratio'], 1)}x rata-rata 20 {unit}")

    lines += ["", "🕯 Candle terakhir", a["pattern"] or "Tidak ada pola khusus"]
    return lines


# ---------- data + image ----------

def load_bars(symbol: str, p: dict):
    import yfinance as yf

    df = yf.Ticker(symbol).history(period=p["fetch"], interval=p["interval"], auto_adjust=False)
    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    df = df[df["High"] > 0]
    return df


def draw(df, full_closes: list[float], title: str, ma: tuple[int, int], a: dict, path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    up, down = "#16a34a", "#dc2626"
    fig, (ax, axv) = plt.subplots(2, 1, figsize=(10, 6), dpi=130, sharex=True,
                                  gridspec_kw={"height_ratios": [4, 1]})
    for i, (o, h, l, c) in enumerate(zip(df["Open"], df["High"], df["Low"], df["Close"])):
        col = up if c >= o else down
        ax.vlines(i, l, h, color=col, linewidth=0.8)
        ax.bar(i, max(abs(c - o), (h - l) * 0.01), bottom=min(o, c), color=col, width=0.7)
        axv.bar(i, df["Volume"].iloc[i], color=col, width=0.7, alpha=0.6)
    xs = range(len(df))
    for n, colr in zip(ma, ("#2563eb", "#f59e0b")):
        ax.plot(xs, sma(full_closes, n)[-len(df):], color=colr, linewidth=1.2, label=f"MA{n}")
    n = len(df)
    lo, hi = float(df["Low"].min()), float(df["High"].max())
    pad = (hi - lo) * 0.05
    ax.set_ylim(lo - pad, hi + pad)
    axv.yaxis.set_major_formatter(plt.FuncFormatter(
        lambda v, _: f"{v / 1e9:.1f} M" if v >= 1e9 else f"{v / 1e6:.0f} jt"))
    for y, lab in ((a["support"], "support"), (a["resistance"], "resistance")):
        ax.hlines(y, n - 20, n - 1, colors="#6b7280", linestyles="--", linewidth=1)
        ax.text(n - 0.5, y, f" {lab}", va="center", fontsize=8, color="#374151")
    ax.set_title(title, loc="left", fontsize=12)
    ax.legend(loc="upper left", fontsize=8, frameon=False)
    ax.grid(alpha=0.2)
    axv.grid(alpha=0.2)
    axv.set_ylabel("Volume", fontsize=8)
    step = max(1, n // 8)
    axv.set_xticks(list(range(0, n, step)))
    axv.set_xticklabels([d.strftime("%d %b %y") for d in df.index[::step]], fontsize=8)
    ax.set_xlim(-1, n + 6)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def trend_word(a: dict) -> str:
    c, f, sl = a["close"], a["ma_fast"], a["ma_slow"]
    if f is None or sl is None:
        return "data belum cukup"
    if c > f > sl:
        return "uptrend (harga > MA pendek > MA panjang)"
    if c < f < sl:
        return "downtrend (harga < MA pendek < MA panjang)"
    return "campuran / sideways (belum ada tren jelas)"


def technical_display(a: dict, ma: tuple[int, int], unit: str, dec: int) -> dict:
    """Display strings for an LLM report (every number pre-formatted)."""
    f = lambda x: None if x is None else fmt_id(x, dec)  # noqa: E731
    r = a["rsi"]
    return {
        "close": f(a["close"]),
        "ma_fast_label": f"MA{ma[0]}", "ma_fast": f(a["ma_fast"]),
        "ma_slow_label": f"MA{ma[1]}", "ma_slow": f(a["ma_slow"]),
        "trend": trend_word(a),
        "rsi_14": None if r is None else fmt_id(r, 1),
        "rsi_zone": None if r is None else ("jenuh beli (overbought)" if r >= 70 else
                                            "jenuh jual (oversold)" if r <= 30 else "netral"),
        "macd": ("positif (momentum naik)" if a["macd_hist"] > 0 else "negatif (momentum turun)")
                + {"up": ", baru cross ke atas", "down": ", baru cross ke bawah"}.get(a["macd_cross"], ""),
        "support_20": f(a["support"]), "resistance_20": f(a["resistance"]),
        "window": f"20 {unit} terakhir",
        "volume_vs_20": None if a["vol_ratio"] is None else fmt_id(a["vol_ratio"], 1) + "x",
        "last_candle_pattern": a["pattern"] or "tidak ada pola khusus",
    }


def technical(stock: str, period: str = "daily", now: datetime | None = None,
              closed_only: bool = False) -> dict:
    """Compute indicators and draw the chart. Returns text-ready pieces + image path."""
    now = now or datetime.now(WIB)
    p = PERIODS[period]
    watchlist, _ = load_config()
    if stock.strip().upper() in {"IHSG", "JKSE", "^JKSE", "COMPOSITE"}:
        symbol, code, name, dec = "^JKSE", "IHSG", "Indeks Harga Saham Gabungan", 2
    else:
        t = resolve_stock(stock, watchlist)
        symbol, code, dec = t["symbol"], t["symbol"].split(".")[0], 0
        name = t["name"]
    full = load_bars(symbol, p)
    if closed_only and period == "daily" and len(full) and full.index[-1].date() == now.date() \
            and (now.hour, now.minute) < (16, 15):
        full = full.iloc[:-1]  # same sessions as /analysis (today's bar not final yet)
    if len(full) < 30:
        raise StockNotFound(f"Kode {code} tidak ditemukan atau datanya terlalu sedikit.")

    bars = [Bar(r.Open, r.High, r.Low, r.Close, r.Volume) for r in full.itertuples()]
    a = analyze(bars, p["ma"])
    last_day = full.index[-1].date()
    partial = period == "daily" and last_day == now.date() and (now.hour, now.minute) < (16, 15)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / f"chart-{code}-{period}.png"
    draw(full.iloc[-p["show"]:], [b.c for b in bars], f"{code} · {p['label']}", p["ma"], a, path)
    return {"symbol": symbol, "code": code, "name": name, "dec": dec, "period": period,
            "p": p, "a": a, "last_day": last_day, "partial": partial, "image": str(path),
            "display": {**technical_display(a, p["ma"], p["unit"], dec),
                        "chart": p["label"],
                        "data_until": fmt_date_id(last_day)
                        + (" (sesi berjalan, belum close)" if partial else "")}}


def run(stock: str, period: str = "daily", now: datetime | None = None) -> tuple[str, str]:
    """Returns (text, image path)."""
    t = technical(stock, period, now)
    p, a, code, name, dec = t["p"], t["a"], t["code"], t["name"], t["dec"]
    if name == code:
        import yfinance as yf
        name = _clean_company_name((yf.Ticker(t["symbol"]).info or {}).get("longName") or code) or code
    head = [f"📈 Chart {code} — {name} ({p['label']})",
            (f"Minggu mulai {fmt_date_id(t['last_day'])}" if period == "weekly" else
             f"Data sampai {fmt_date_id(t['last_day'])}")
            + (" (sesi berjalan, belum close)" if t["partial"] else ""),
            ""]
    if a["change_pct"] is not None:
        head.insert(2, f"Terakhir: {fmt_id(a['close'], dec)} "
                       f"({fmt_id(a['change_pct'], 2, sign=True)}% vs {p['unit']} sebelumnya)")
    text = "\n".join(head + describe(a, p["ma"], p["unit"], dec) + ["", FOOTER])
    return text, t["image"]


USAGE = "Format: /chart KODE [daily|weekly] (contoh: /chart BBRI, /chart IHSG weekly)"


def main() -> None:
    args = sys.argv[1:]
    send = "--send" in args
    args = [a for a in args if a != "--send"]
    if not 1 <= len(args) <= 2 or (len(args) == 2 and args[1].lower() not in PERIOD_WORDS):
        print(USAGE)
        sys.exit(1)
    period = PERIOD_WORDS[args[1].lower()] if len(args) == 2 else "daily"
    try:
        text, img = run(args[0], period)
    except StockNotFound as e:
        text, img = f"Saham tidak ditemukan: {e}", None
    except Exception as e:
        print(f"chart error: {type(e).__name__}: {e}", file=sys.stderr)
        text, img = f"Gagal membuat chart ({type(e).__name__}). Coba lagi nanti.", None
    if send:
        from .report import send_telegram
        if img:
            send_telegram(f"MEDIA:{img}")
        send_telegram(text)
    print(text)
    if img:
        print(f"[image] {img}")


if __name__ == "__main__":
    main()
