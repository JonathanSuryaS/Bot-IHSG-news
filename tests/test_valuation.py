from datetime import date

import pandas as pd
import pytest

from brief.fundamental import cagr, from_frames, render as render_fund
from brief.valuation import Inputs, blume_beta, build_inputs, sensitivity, two_stage

CFG = {"risk_free_pct": 6.5, "equity_risk_premium_pct": 7.0, "beta": "auto",
       "beta_min": 0.6, "beta_max": 1.8, "stage1_years": 5, "stage1_growth": "auto",
       "stage1_growth_min_pct": 0.0, "stage1_growth_max_pct": 12.0,
       "terminal_growth_pct": 5.0, "overrides": {}}


def frames(bank=False):
    cols = [pd.Timestamp(f"{y}-12-31") for y in (2025, 2024, 2023, 2022, 2021)]
    nan = float("nan")
    IS = pd.DataFrame({c: v for c, v in zip(cols, [
        {"Total Revenue": 146e12, "Net Income Common Stockholders": 20e12, "Basic EPS": 200},
        {"Total Revenue": 140e12, "Net Income Common Stockholders": 19e12, "Basic EPS": 190},
        {"Total Revenue": 130e12, "Net Income Common Stockholders": 18e12, "Basic EPS": 180},
        {"Total Revenue": 120e12, "Net Income Common Stockholders": 16e12, "Basic EPS": 160},
        {"Total Revenue": nan, "Net Income Common Stockholders": nan, "Basic EPS": nan}])})
    BS = pd.DataFrame({c: {"Stockholders Equity": 100e12, "Total Debt": 50e12,
                           "Ordinary Shares Number": 100e9} for c in cols})
    CF = pd.DataFrame({c: {"Cash Flowsfromusedin Operating Activities Direct": 40e12,
                           "Capital Expenditure": -25e12, "Cash Dividends Paid": -15e12} for c in cols})
    return from_frames("TEST.JK", "TEST", "Test Corp", bank, [IS, BS, CF])


def test_fundamentals_drop_empty_year_and_derive():
    f = frames()
    assert f.years == [2022, 2023, 2024, 2025]
    assert f.get("fcf")[-1] == 15e12
    assert f.get("roe")[-1] == pytest.approx(0.2)
    assert f.get("dividends")[-1] == 15e12  # made positive
    assert cagr(f.get("revenue")) == pytest.approx((146 / 120) ** (1 / 3) - 1)
    text = render_fund(f)
    assert "Free cash flow selalu positif" in text and "2022 · 2023 · 2024 · 2025" in text


def test_two_stage_matches_gordon_when_growth_equal():
    # With g1 == gt the two-stage value equals the Gordon model c0*(1+g)/(r-g).
    res = two_stage(100, 0.05, 0.05, 0.12, 5)
    assert res["value"] == pytest.approx(100 * 1.05 / 0.07)
    assert two_stage(100, 0.05, 0.12, 0.12, 5) is None


def test_build_inputs_dcf_and_bank_ddm():
    i = build_inputs(frames(), CFG, price=2000, beta_auto=0.9, ttm_div=150)
    assert i.method == "dcf" and i.c0 == pytest.approx(150)  # 15T / 100bn shares
    assert i.r == pytest.approx(0.065 + 0.9 * 0.07)
    b = build_inputs(frames(bank=True), CFG, price=2000, beta_auto=3.0, ttm_div=150)
    assert b.method == "ddm" and b.c0 == 150 and b.beta == 1.8  # clipped


def test_sensitivity_grid_shape_and_order():
    i = Inputs("ddm", 100, "x", 0.05, "x", 0.05, 0.065, 1.0, "x", 0.07, 5, 1500, 1e9)
    s = sensitivity(i, [-2, -1, 0, 1, 2], [-1, 0, 1])
    assert len(s["grid"]) == 3 and len(s["grid"][0]) == 5
    mid = s["grid"][1]
    assert mid == sorted(mid, reverse=True)  # higher r -> lower value


def test_blume_beta():
    m = [100 * (1.01 ** k if k % 2 else 0.99 ** k) for k in range(60)]
    assert blume_beta(m, m) == pytest.approx(1.0)
    assert blume_beta([1.0] * 5, [1.0] * 5) is None
