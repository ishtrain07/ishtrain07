"""Adaptive factor model: learns from previous days which signals are working.

Every day, for each factor, it measures the information coefficient (IC): the rank
correlation between the factor 5 trading days ago and the return since then,
across the whole universe (~110 stocks = ~110 fresh observations per day).
Factors with a positive recent IC get more weight; factors that stopped
working fade out. Learned weights are shrunk 50/50 toward a prior
(risk-adjusted momentum) so one noisy week can't flip the model.

No lookahead: weights used on day t only use returns that ended on or before t.
"""
import numpy as np
import pandas as pd

HORIZON = 5          # predict the next week
HALFLIFE = 15        # trading days; recent days count more
WINDOW = 60          # trading days of IC history
SHRINK = 0.5         # weight on the prior

FACTORS = {
    "risk_adj_mom": "Momentum / volatility (6-3-1 month)",
    "mom_126": "6-month momentum",
    "mom_21": "1-month momentum",
    "rs_63": "3-month strength vs S&P",
    "near_high": "Closeness to 52-week high",
    "trend": "Trend alignment (20/50/200 day)",
    "low_vol": "Low volatility",
    "reversal_5": "Short-term dip (5-day loser)",
    "volume_surge": "Volume surge",
}
PRIOR = {"risk_adj_mom": 1.0}


def factor_panels(feats, tickers):
    """{factor: DataFrame(date x ticker)} using only data up to each date."""
    cols = {}
    spy = feats["SPY"].Close
    for t in tickers:
        f = feats[t]
        c = f.Close
        mom = 0.5 * f.ret126 + 0.3 * f.ret63 + 0.2 * f.ret21
        atrp = f.atr / c
        cols[t] = pd.DataFrame({
            "risk_adj_mom": mom / atrp,
            "mom_126": f.ret126,
            "mom_21": f.ret21,
            "rs_63": f.ret63 - spy.pct_change(63).reindex(f.index),
            "near_high": c / c.rolling(252, min_periods=120).max(),
            "trend": (c > f.ema20).astype(float) + (c > f.sma50) + (f.sma50 > f.sma200),
            "low_vol": -atrp,
            "reversal_5": -c.pct_change(5),
            "volume_surge": f.vol_ratio,
            "_close": c,
        })
    panels = {}
    for k in list(FACTORS) + ["_close"]:
        panels[k] = pd.DataFrame({t: cols[t][k] for t in tickers}).sort_index()
    return panels


def daily_ic(panels):
    """IC per day per factor: rank-corr(factor at t-H, return t-H -> t)."""
    close = panels["_close"]
    fwd = close / close.shift(HORIZON) - 1           # return ending at t
    out = {}
    for k in FACTORS:
        lagged = panels[k].shift(HORIZON)             # factor known at t-H
        a = lagged.rank(axis=1, pct=True)
        b = fwd.rank(axis=1, pct=True)
        valid = a.notna() & b.notna()
        a, b = a.where(valid), b.where(valid)
        am, bm = a.sub(a.mean(axis=1), axis=0), b.sub(b.mean(axis=1), axis=0)
        num = (am * bm).sum(axis=1)
        den = np.sqrt((am ** 2).sum(axis=1) * (bm ** 2).sum(axis=1))
        ic = num / den.replace(0, np.nan)
        out[k] = ic.where(valid.sum(axis=1) >= 15)
    return pd.DataFrame(out)


def learned_weights(ic):
    """Weights per day (date x factor) from the trailing IC history."""
    ew = ic.rolling(WINDOW, min_periods=20).apply(
        lambda x: np.nansum(x * 0.5 ** (np.arange(len(x))[::-1] / HALFLIFE)) /
        np.nansum(0.5 ** (np.arange(len(x))[::-1] / HALFLIFE) * ~np.isnan(x)), raw=True)
    pos = ew.clip(lower=0)
    total = pos.sum(axis=1)
    learned = pos.div(total.replace(0, np.nan), axis=0)
    prior = pd.Series({k: PRIOR.get(k, 0.0) for k in FACTORS})
    prior = prior / prior.sum()
    w = learned.mul(1 - SHRINK).add(prior * SHRINK, axis=1)
    w[total <= 0] = prior.values          # nothing working -> fall back to the prior
    return w.fillna(pd.Series(prior)), ew


def adaptive_scores(panels, weights):
    """Composite score (date x ticker), 0-100, from percentile-ranked factors."""
    score = None
    for k in FACTORS:
        r = panels[k].rank(axis=1, pct=True) * 100
        part = r.mul(weights[k], axis=0)
        score = part if score is None else score.add(part, fill_value=0)
    return score


def model(feats, tickers):
    """Everything the live engine and research need."""
    panels = factor_panels(feats, tickers)
    ic = daily_ic(panels)
    w, ew_ic = learned_weights(ic)
    scores = adaptive_scores(panels, w)
    return {"panels": panels, "ic": ic, "weights": w, "ew_ic": ew_ic, "scores": scores}


def explain_today(m):
    """Latest learned weights and IC, for the dashboard."""
    w = m["weights"].iloc[-1]
    ic = m["ew_ic"].iloc[-1]
    rows = [{"factor": FACTORS[k], "key": k, "weight": round(float(w[k]) * 100, 1),
             "recent_ic": None if pd.isna(ic[k]) else round(float(ic[k]), 3)} for k in FACTORS]
    return sorted(rows, key=lambda r: -r["weight"])
