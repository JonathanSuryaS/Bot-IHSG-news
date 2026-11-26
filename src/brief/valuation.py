"""/valuasi: two-stage DCF (non-banks) or dividend discount model (banks),
with a sensitivity table and an Excel model whose formulas stay live.

Pure Python, no LLM. Assumptions live in config/valuation.yaml.

    brief-valuation BBRI            # text
    brief-valuation BBRI --send     # text + Excel file to Telegram

The result is an estimate that depends entirely on the assumptions. It's an
educational model, not a target price or a recommendation.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from . import CONFIG_DIR, DATA_DIR
from .analysis import StockNotFound
from .fetcher import WIB, fmt_id
from .fundamental import Fundamentals, cagr
from .fundamental import load as load_fundamentals

FOOTER = ("ℹ️ Model edukasi: hasilnya estimasi yang sepenuhnya bergantung pada asumsi, "
          "bukan target harga atau rekomendasi beli/jual.")


@dataclass
class Inputs:
    method: str            # "ddm" or "dcf"
    c0: float              # base cash per share (dividend or FCF), Rp
    c0_label: str
    g1: float              # stage-1 growth (fraction)
    g1_label: str
    gt: float              # terminal growth
    rf: float
    beta: float
    beta_label: str
    erp: float
    years: int
    price: float
    shares: float

    @property
    def r(self) -> float:
        return self.rf + self.beta * self.erp


def load_cfg() -> dict:
    import yaml

    return yaml.safe_load((CONFIG_DIR / "valuation.yaml").read_text())


# ---------- the model ----------

def two_stage(c0: float, g1: float, gt: float, r: float, years: int) -> dict | None:
    """Value per share = PV of `years` growing cash flows + PV of a Gordon terminal value."""
    if r <= gt:
        return None
    flows = [c0 * (1 + g1) ** t for t in range(1, years + 1)]
    pv = [cf / (1 + r) ** t for t, cf in enumerate(flows, start=1)]
    tv = flows[-1] * (1 + gt) / (r - gt)
    pv_tv = tv / (1 + r) ** years
    return {"flows": flows, "pv": pv, "pv_stage1": sum(pv), "tv": tv, "pv_tv": pv_tv,
            "value": sum(pv) + pv_tv}


def sensitivity(i: Inputs, r_steps: list[float], g_steps: list[float]) -> dict:
    rs = [i.r + s / 100 for s in r_steps]
    gs = [i.gt + s / 100 for s in g_steps]
    grid = [[(two_stage(i.c0, i.g1, g, r, i.years) or {}).get("value") for r in rs] for g in gs]
    return {"r": rs, "g": gs, "grid": grid}


# ---------- inputs from data ----------

def blume_beta(stock_closes: list[float], index_closes: list[float]) -> float | None:
    sr = [b / a - 1 for a, b in zip(stock_closes, stock_closes[1:])]
    ir = [b / a - 1 for a, b in zip(index_closes, index_closes[1:])]
    n = min(len(sr), len(ir))
    if n < 20:
        return None
    sr, ir = sr[-n:], ir[-n:]
    ms, mi = sum(sr) / n, sum(ir) / n
    cov = sum((a - ms) * (b - mi) for a, b in zip(sr, ir)) / (n - 1)
    var = sum((b - mi) ** 2 for b in ir) / (n - 1)
    if var == 0:
        return None
    return 0.67 * (cov / var) + 0.33


def _weekly_closes(symbol: str):
    import yfinance as yf

    df = yf.Ticker(symbol).history(period="2y", interval="1wk")["Close"].dropna()
    return df


def market_beta(symbol: str) -> float | None:
    s, m = _weekly_closes(symbol), _weekly_closes("^JKSE")
    both = s.to_frame("s").join(m.to_frame("m"), how="inner").dropna()
    return blume_beta(list(both["s"]), list(both["m"]))


def ttm_dividend(symbol: str, today: date) -> float:
    import yfinance as yf

    divs = yf.Ticker(symbol).dividends
    cutoff = today - timedelta(days=365)
    return float(sum(v for ts, v in divs.items() if cutoff < ts.date() <= today))


def last_price(symbol: str) -> float:
    import yfinance as yf

    h = yf.Ticker(symbol).history(period="5d")
    if h.empty:
        raise StockNotFound(f"Harga {symbol} tidak tersedia.")
    return float(h["Close"].iloc[-1])


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def build_inputs(f: Fundamentals, cfg: dict, price: float, beta_auto: float | None,
                 ttm_div: float) -> Inputs:
    ov = (cfg.get("overrides") or {}).get(f.code, {})
    shares = next((v for v in reversed(f.get("shares")) if v), None)
    if not shares:
        raise StockNotFound(f"Jumlah saham {f.code} tidak tersedia.")
    first, last = f.years[0], f.years[-1]

    method = ov.get("method") or ("ddm" if f.is_bank else "dcf")
    fcf = [v for v in f.get("fcf") if v is not None][-3:]
    avg_fcf = sum(fcf) / len(fcf) if fcf else None
    if method == "dcf" and (avg_fcf is None or avg_fcf <= 0):
        method = "ddm"  # negative/unknown free cash flow: fall back to dividends

    if method == "ddm":
        c0 = ttm_div or next((v for v in reversed(f.get("dps")) if v), 0.0)
        c0_label = "Dividen/saham 12 bulan terakhir"
        g_hist, g_src = cagr(f.get("eps")), f"CAGR EPS {first}–{last}"
    else:
        c0 = avg_fcf / shares
        c0_label = f"Free cash flow/saham (rata-rata {len(fcf)} tahun)"
        g_hist, g_src = cagr(f.get("revenue")), f"CAGR pendapatan {first}–{last}"
    if not c0 or c0 <= 0:
        raise StockNotFound(f"{f.code}: tidak ada dividen atau free cash flow positif untuk dimodelkan.")

    lo, hi = cfg["stage1_growth_min_pct"] / 100, cfg["stage1_growth_max_pct"] / 100
    if ov.get("stage1_growth") is not None or cfg["stage1_growth"] != "auto":
        g1 = float(ov.get("stage1_growth", cfg["stage1_growth"])) / 100
        g1_label = "asumsi manual"
    else:
        g1 = _clip(g_hist if g_hist is not None else 0.0, lo, hi)
        g1_label = g_src + ("" if g_hist is not None and lo <= g_hist <= hi
                            else f", dibatasi {fmt_id(lo * 100, 0)}–{fmt_id(hi * 100, 0)}%")

    if ov.get("beta") is not None or cfg["beta"] != "auto":
        beta, beta_label = float(ov.get("beta", cfg["beta"])), "asumsi manual"
    elif beta_auto is None:
        beta, beta_label = 1.0, "default (data kurang)"
    else:
        beta = _clip(beta_auto, cfg["beta_min"], cfg["beta_max"])
        beta_label = "vs IHSG, 2 thn mingguan, Blume-adjusted"

    return Inputs(method, c0, c0_label, g1, g1_label, cfg["terminal_growth_pct"] / 100,
                  cfg["risk_free_pct"] / 100, beta, beta_label,
                  cfg["equity_risk_premium_pct"] / 100, int(cfg["stage1_years"]), price, shares)


# ---------- text ----------

def pct(x: float, d: int = 1) -> str:
    return fmt_id(x * 100, d) + "%"


def rp(x: float | None) -> str:
    return "n/a" if x is None else "Rp" + fmt_id(x, 0)


def render(f: Fundamentals, i: Inputs, res: dict, sens: dict, excel: bool) -> str:
    mname = ("DDM 2 tahap (dividend discount model)" if i.method == "ddm"
             else "DCF 2 tahap (free cash flow)")
    v = res["value"]
    gap = (i.price - v) / v
    flat = [x for row in sens["grid"] for x in row if x is not None]
    lines = [f"💎 Valuasi {f.code} — {f.name}", f"Model: {mname}",
             f"Harga terakhir: {rp(i.price)}", "",
             "🧩 Asumsi",
             f"• {i.c0_label}: {rp(i.c0)}",
             f"• Pertumbuhan {i.years} tahun: {pct(i.g1)}/thn ({i.g1_label})",
             f"• Pertumbuhan jangka panjang: {pct(i.gt)}/thn",
             f"• Cost of equity (r): {pct(i.rf)} + beta {fmt_id(i.beta, 2)} × {pct(i.erp)} = {pct(i.r)}",
             f"  (beta: {i.beta_label})", "",
             "🧮 Hasil",
             f"Nilai intrinsik estimasi: {rp(v)}/saham",
             f"• Nilai {i.years} tahun pertama: {rp(res['pv_stage1'])} · "
             f"nilai sesudahnya (terminal): {rp(res['pv_tv'])} ({pct(res['pv_tv'] / v, 0)} dari total)",
             f"• Harga sekarang {pct(abs(gap), 0)} "
             + ("di bawah" if gap < 0 else "di atas") + " estimasi dasar", "",
             "📊 Sensitivitas (nilai/saham)"]
    for g, row in zip(sens["g"], sens["grid"]):
        lines.append(f"g {pct(g)}: " + " · ".join(
            f"r {pct(r)} → {fmt_id(x, 0) if x is not None else 'n/a'}" for r, x in zip(sens["r"], row)))
    if flat:
        lines.append(f"Rentang: {rp(min(flat))} – {rp(max(flat))}")
    if i.method == "dcf":
        lines += ["", "ℹ️ FCF dari laporan konsolidasi (termasuk porsi anak usaha milik pihak lain), "
                  "jadi estimasi bisa terlalu tinggi untuk grup seperti ASII/TLKM."]
    lines += ["",
              "⚠️ Nilai terminal biasanya >50% dari total, jadi asumsi jangka panjang paling "
              "menentukan. Ubah r atau g sedikit, hasilnya berubah banyak.",
              "Rumus: /formula CAGR · data historis: /fundamental " + f.code]
    if excel:
        lines.append("📎 File Excel terlampir: ubah sel biru di sheet Asumsi, semua angka ikut berubah.")
    lines += ["", FOOTER]
    return "\n".join(lines)


# ---------- Excel ----------

def write_excel(f: Fundamentals, i: Inputs, sens: dict, path) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    blue = Font(color="1F4E99", bold=True)
    bold = Font(bold=True)
    head = PatternFill("solid", fgColor="DDE7F3")
    inp = PatternFill("solid", fgColor="FFF7D6")
    pct_fmt, rp_fmt = "0.0%", "#,##0"

    wb = Workbook()
    a = wb.active
    a.title = "Asumsi"
    a["A1"] = f"Valuasi {f.code} — {f.name}"
    a["A1"].font = Font(bold=True, size=14)
    a["A2"] = ("Sel kuning/biru = input. Ubah, semua sheet ikut dihitung ulang. "
               "Model edukasi, bukan rekomendasi.")
    rows = [
        ("Metode", "DDM (dividen)" if i.method == "ddm" else "DCF (free cash flow)", None, False),
        ("Harga saham terakhir (Rp)", i.price, rp_fmt, True),
        (i.c0_label + " (Rp)", i.c0, "#,##0.00", True),
        ("Pertumbuhan tahap 1 (g1)", i.g1, pct_fmt, True),
        ("Jumlah tahun tahap 1", i.years, "0", False),
        ("Pertumbuhan terminal (g)", i.gt, pct_fmt, True),
        ("Risk-free rate (SBN 10 thn)", i.rf, pct_fmt, True),
        ("Beta", i.beta, "0.00", True),
        ("Equity risk premium", i.erp, pct_fmt, True),
        ("Cost of equity r = rf + beta × ERP", "=B10+B11*B12", pct_fmt, False),
        ("Jumlah saham beredar", i.shares, rp_fmt, False),
    ]
    for n, (label, val, fmt, is_input) in enumerate(rows, start=4):
        a.cell(n, 1, label)
        c = a.cell(n, 2, val)
        if fmt:
            c.number_format = fmt
        if is_input:
            c.font, c.fill = blue, inp
    a["C6"] = i.c0_label
    a["C7"] = i.g1_label
    a["C11"] = i.beta_label
    a.column_dimensions["A"].width = 42
    a.column_dimensions["B"].width = 18
    a.column_dimensions["C"].width = 50
    # Named shortcuts used below
    P, C0, G1, GT, R = "Asumsi!$B$5", "Asumsi!$B$6", "Asumsi!$B$7", "Asumsi!$B$9", "Asumsi!$B$13"

    m = wb.create_sheet("Model")
    for col, h in enumerate(["Tahun ke-", "Arus kas/saham (Rp)", "Faktor diskon", "Nilai sekarang (Rp)"], 1):
        m.cell(1, col, h).font = bold
        m.cell(1, col).fill = head
    for t in range(1, i.years + 1):
        r_ = t + 1
        m.cell(r_, 1, t)
        m.cell(r_, 2, f"={C0}*(1+{G1})^A{r_}").number_format = "#,##0.00"
        m.cell(r_, 3, f"=1/(1+{R})^A{r_}").number_format = "0.0000"
        m.cell(r_, 4, f"=B{r_}*C{r_}").number_format = "#,##0.00"
    last = i.years + 1
    t0 = last + 2
    labels = [
        ("Jumlah nilai sekarang tahap 1", f"=SUM(D2:D{last})"),
        ("Nilai terminal di tahun terakhir", f"=B{last}*(1+{GT})/({R}-{GT})"),
        ("Nilai sekarang terminal", f"=B{t0 + 1}*C{last}"),
        ("Nilai intrinsik per saham", f"=B{t0}+B{t0 + 2}"),
        ("Porsi terminal dari total", f"=B{t0 + 2}/B{t0 + 3}"),
        ("Harga sekarang vs estimasi", f"={P}/B{t0 + 3}-1"),
    ]
    for k, (label, formula) in enumerate(labels):
        m.cell(t0 + k, 1, label).font = bold if k == 3 else Font()
        c = m.cell(t0 + k, 2, formula)
        c.number_format = pct_fmt if k >= 4 else rp_fmt
        if k == 3:
            c.font = bold
    m.column_dimensions["A"].width = 34
    for col in "BCD":
        m.column_dimensions[col].width = 20

    s = wb.create_sheet("Sensitivitas")
    s["A1"] = "Nilai per saham (Rp): baris = pertumbuhan terminal g, kolom = cost of equity r"
    s["A1"].font = bold
    s["A3"] = "g \\ r"
    s["A3"].font = bold
    r_steps = [x / 100 for x in load_cfg()["sensitivity_r_steps_pct"]]
    g_steps = [x / 100 for x in load_cfg()["sensitivity_g_steps_pct"]]
    for j, dr in enumerate(r_steps):
        c = s.cell(3, j + 2, f"={R}+({dr})")
        c.number_format, c.font, c.fill = pct_fmt, bold, head
    n = i.years
    for k, dg in enumerate(g_steps):
        row = k + 4
        c = s.cell(row, 1, f"={GT}+({dg})")
        c.number_format, c.font, c.fill = pct_fmt, bold, head
        for j in range(len(r_steps)):
            col = get_column_letter(j + 2)
            rr, gg = f"{col}$3", f"$A{row}"
            stage1 = "+".join(f"{C0}*(1+{G1})^{t}/(1+{rr})^{t}" for t in range(1, n + 1))
            term = f"{C0}*(1+{G1})^{n}*(1+{gg})/(({rr}-{gg})*(1+{rr})^{n})"
            s.cell(row, j + 2, f'=IF({rr}<={gg},"n/a",{stage1}+{term})').number_format = rp_fmt
    for col in range(1, len(r_steps) + 2):
        s.column_dimensions[get_column_letter(col)].width = 14

    h = wb.create_sheet("Historis")
    h.cell(1, 1, "Rp (triliun kecuali disebut)").font = bold
    for j, y in enumerate(f.years):
        c = h.cell(1, j + 2, y)
        c.font, c.fill = bold, head
    hist = [("Pendapatan", "revenue", 1e12, "#,##0.0"), ("Laba bersih", "net_income", 1e12, "#,##0.0"),
            ("EPS (Rp)", "eps", 1, "#,##0"), ("Ekuitas", "equity", 1e12, "#,##0.0"),
            ("ROE", "roe", 1, pct_fmt), ("Net margin", "npm", 1, pct_fmt),
            ("Utang", "debt", 1e12, "#,##0.0"), ("Arus kas operasi", "ocf", 1e12, "#,##0.0"),
            ("Capex", "capex", 1e12, "#,##0.0"), ("Free cash flow", "fcf", 1e12, "#,##0.0"),
            ("Dividen dibayar", "dividends", 1e12, "#,##0.0"), ("Payout ratio", "payout", 1, pct_fmt),
            ("Dividen/saham (Rp)", "dps", 1, "#,##0.0")]
    row = 2
    for label, key, div, fmt in hist:
        vals = f.get(key)
        if all(v is None for v in vals):
            continue
        h.cell(row, 1, label)
        for j, v in enumerate(vals):
            if v is not None:
                h.cell(row, j + 2, v / div).number_format = fmt
        row += 1
    h.column_dimensions["A"].width = 24

    note = wb.create_sheet("Catatan")
    text = [
        "Cara kerja model",
        "1. Tahap 1: arus kas per saham tumbuh g1 per tahun selama N tahun, lalu didiskon dengan r.",
        "2. Terminal: setelah tahun N, arus kas tumbuh g selamanya (rumus Gordon: CF×(1+g)/(r−g)).",
        "3. Nilai intrinsik = jumlah nilai sekarang tahap 1 + nilai sekarang terminal.",
        "4. Bank memakai dividen (DDM) karena utang bank = bahan baku, free cash flow tidak bermakna.",
        "5. Non-bank memakai free cash flow = arus kas operasi − capex (versi sederhana, didiskon r).",
        "   FCF konsolidasi termasuk porsi minoritas, sehingga bisa terlalu tinggi untuk grup usaha.",
        "",
        "Keterbatasan",
        "• Data Yahoo Finance; bisa berbeda dari laporan resmi (idx.co.id).",
        "• Hasil sangat sensitif terhadap r dan g: lihat sheet Sensitivitas.",
        "• Model edukasi, bukan target harga atau rekomendasi beli/jual.",
        "",
        f"Dibuat: {datetime.now(WIB).strftime('%Y-%m-%d %H:%M')} WIB",
    ]
    for n_, t in enumerate(text, start=1):
        note.cell(n_, 1, t).font = bold if t in ("Cara kerja model", "Keterbatasan") else Font()
    note.column_dimensions["A"].width = 100
    for ws in wb.worksheets:
        for r_ in ws.iter_rows():
            for c in r_:
                c.alignment = Alignment(vertical="center")
    wb.save(path)


# ---------- entry ----------

def run(stock: str, excel: bool = True, now: datetime | None = None) -> tuple[str, str | None]:
    now = now or datetime.now(WIB)
    cfg = load_cfg()
    f = load_fundamentals(stock)
    price = last_price(f.symbol)
    try:
        beta = market_beta(f.symbol)
    except Exception:
        beta = None
    i = build_inputs(f, cfg, price, beta, ttm_dividend(f.symbol, now.date()))
    res = two_stage(i.c0, i.g1, i.gt, i.r, i.years)
    if res is None:
        raise StockNotFound("cost of equity harus lebih besar dari pertumbuhan terminal (cek config/valuation.yaml)")
    sens = sensitivity(i, cfg["sensitivity_r_steps_pct"], cfg["sensitivity_g_steps_pct"])
    path = None
    if excel:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        path = DATA_DIR / f"valuasi-{f.code}.xlsx"
        write_excel(f, i, sens, path)
    return render(f, i, res, sens, excel), (str(path) if path else None)


def main() -> None:
    args = sys.argv[1:]
    send = "--send" in args
    args = [a for a in args if a != "--send"]
    if len(args) != 1:
        print("Format: /valuasi KODE (contoh: /valuasi BBRI)")
        sys.exit(1)
    code = 0
    try:
        text, xlsx = run(args[0])
    except StockNotFound as e:
        text, xlsx, code = f"Valuasi tidak bisa dibuat: {e}", None, 1
    except Exception as e:
        print(f"valuation error: {type(e).__name__}: {e}", file=sys.stderr)
        text, xlsx, code = f"Gagal membuat valuasi ({type(e).__name__}). Coba lagi nanti.", None, 2
    if send:
        from .report import send_telegram
        send_telegram(text)
        if xlsx:
            send_telegram(f"MEDIA:{xlsx}")
    print(text)
    if xlsx:
        print(f"[excel] {xlsx}")
    sys.exit(code)


if __name__ == "__main__":
    main()
