"""Unit tests for research.rotation_sim extensions (synthetic prices, no network)."""
import numpy as np
import pandas as pd
import pytest

from habibi import research


def make(paths, start="2026-01-05"):
    """paths: {ticker: list of (open, high, low, close)} -> feats dict."""
    n = len(next(iter(paths.values())))
    idx = pd.bdate_range(start, periods=n)
    feats = {}
    for t, rows in paths.items():
        a = np.array(rows, dtype=float)
        feats[t] = pd.DataFrame({"Open": a[:, 0], "High": a[:, 1], "Low": a[:, 2], "Close": a[:, 3]}, index=idx)
        feats[t]["ema20"] = feats[t].Close
    return feats, idx


def flat(n, px=100.0):
    return [(px, px, px, px)] * n


def make_pre(idx, ranks):
    """ranks: {date_index: {ticker: score}} (score held until changed)."""
    pre, cur = {}, None
    for i, d in enumerate(idx):
        cur = ranks.get(i, cur)
        sc = pd.DataFrame({"score": pd.Series(cur)})
        sc["eligible"] = True
        sc["rsi"] = 50.0
        sc["Close"] = 100.0
        pre[d] = ("GREEN", sc)
    return pre


def test_capped_target():
    smap = {"A1": "A", "A2": "A", "A3": "A", "B1": "B", "C1": "C"}
    ranked = ["A1", "A2", "A3", "B1", "C1"]
    assert research.capped_target([], ranked, 3, 1, smap) == ["A1", "B1", "C1"]
    assert research.capped_target([], ranked, 3, 2, smap) == ["A1", "A2", "B1"]
    # kept holdings take their group's slots first
    assert research.capped_target(["A3"], ranked, 3, 1, smap) == ["A3", "B1", "C1"]


def test_sector_cap_changes_holdings():
    n = 6
    rising = [(100, 100, 100, 100)] + [(100 + 2 * i, 100 + 2 * i, 100 + 2 * i, 100 + 2 * i) for i in range(1, n)]
    feats, idx = make({"A1": flat(n), "A2": flat(n), "A3": flat(n), "B1": rising})
    pre = make_pre(idx, {0: {"A1": 4, "A2": 3, "A3": 2, "B1": 1}})
    smap = {"A1": "A", "A2": "A", "A3": "A", "B1": "B"}
    kw = dict(top_n=3, rank_col="score", stop_pct=0.5, sector_map=smap)
    uncapped = research.rotation_sim(feats, pre, return_curve=True, **kw)
    capped = research.rotation_sim(feats, pre, sector_cap=1, return_curve=True, **kw)
    assert uncapped[-1][1] == pytest.approx(1.0)        # holds the three flat A names
    # cap 1: A1 + B1, two of three slots; B1 gained 10% on a 1/3 slot
    assert capped[-1][1] == pytest.approx(1 + (110 / 100 - 1) / 3)


def test_profit_take_then_breakeven_stop():
    # day0 buy at 100; day1 high 106 -> half sold at 105; day2 low 99 -> rest stopped at breakeven 100
    path = [(100, 100, 100, 100), (101, 106, 101, 104), (103, 103, 99, 99), (99, 99, 99, 99)]
    feats, idx = make({"X": path})
    pre = make_pre(idx, {0: {"X": 1}})
    kw = dict(top_n=1, rank_col="score", stop_pct=0.08)
    res = research.rotation_sim(feats, pre, profit_take=0.05, **kw)
    curve = research.rotation_sim(feats, pre, profit_take=0.05, return_curve=True, **kw)
    assert curve[-1][1] == pytest.approx(0.5 * 1.05 + 0.5 * 1.00)
    assert res["trades"] == 1 and res["win_rate"] == 100.0
    # without profit-take the 8% stop is not hit and it rides to 99
    plain = research.rotation_sim(feats, pre, return_curve=True, **kw)
    assert plain[-1][1] == pytest.approx(0.99)


def test_profit_take_gap_fills_at_open_and_costs_apply():
    path = [(100, 100, 100, 100), (110, 112, 109, 111), (111, 111, 111, 111)]
    feats, idx = make({"X": path})
    pre = make_pre(idx, {0: {"X": 1}})
    c = 0.01
    curve = research.rotation_sim(feats, pre, top_n=1, rank_col="score", profit_take=0.05, cost=c, return_curve=True)
    sh = (1 - c) / 100
    expect = sh / 2 * 110 * (1 - c) + sh / 2 * 111
    assert curve[-1][1] == pytest.approx(expect)


def test_signal_lag_uses_previous_day_ranking():
    n = 4
    up = [(100 + i, 100 + i, 100 + i, 100 + i) for i in range(n)]
    feats, idx = make({"X": flat(n), "Y": up}, start="2026-01-02")  # Fri, then a new week on Mon
    # Friday's snapshot ranks Y first; Monday's own snapshot ranks X first
    pre = make_pre(idx, {0: {"X": 1, "Y": 2}, 1: {"X": 2, "Y": 1}})
    kw = dict(top_n=1, rank_col="score", stop_pct=0.5, start=idx[1])
    same = research.rotation_sim(feats, pre, return_curve=True, **kw)
    lag = research.rotation_sim(feats, pre, signal_lag=1, return_curve=True, **kw)
    assert same[-1][1] == pytest.approx(1.0)                  # bought X (flat) on Monday's close signal
    assert lag[-1][1] == pytest.approx(103 / 101)             # bought Y using Friday's signal


def test_stats_and_horizon():
    idx = pd.bdate_range("2026-01-05", periods=60)
    eq = pd.Series(np.linspace(1, 1.2, 60), index=idx)
    st = research.stats(list(zip(idx, eq)), [], traded=2.0)
    assert st["cagr_pct"] > 0 and st["sharpe"] > 0 and st["worst_month_pct"] >= 0
    assert st["turnover_x_yr"] > 0
    h = research.horizon_dist(eq, 10)
    assert h["windows"] == 50 and h["p_loss"] == 0 and h["dd_worst"] == 0
