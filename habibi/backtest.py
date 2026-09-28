"""Historical test of the exact same rules, plus the trade simulator used for
paper-tracking the system's own picks.

Caveats (shown on the dashboard): today's universe is used for the past
(survivorship bias), fundamentals and earnings dates are not applied
historically, fills assume the signal-day close, and a bar that touches both
stop and target counts as a stop (conservative).
"""
import datetime as dt

import numpy as np
import pandas as pd

from .strategy import score_snapshot, snapshot, sector_strength


def simulate_trade(bars, entry, stop, t1, t2, hold_days, atr):
    """bars: OHLC after entry day. Returns dict with exit info and R multiple.

    Rules: stop -> exit all. T1 -> sell half, stop to breakeven, then trail at
    highest close - 2 ATR. T2 -> exit rest. Time stop at hold_days close.
    """
    risk = entry - stop
    half_done, realized, cur_stop, high_close = False, 0.0, stop, entry
    for i, (d, b) in enumerate(bars.iterrows(), start=1):
        if b.Low <= cur_stop:
            px = min(cur_stop, b.Open)
            pnl = realized + (0.5 if half_done else 1.0) * (px - entry)
            return _res(d, px, pnl, risk, i, "stop" if not half_done else "trail/breakeven")
        if not half_done and b.High >= t1:
            half_done, realized = True, 0.5 * (t1 - entry)
            cur_stop = entry
        if half_done and b.High >= t2:
            return _res(d, t2, realized + 0.5 * (t2 - entry), risk, i, "target 2")
        high_close = max(high_close, b.Close)
        if half_done:
            cur_stop = max(cur_stop, high_close - 2 * atr)
        if i >= hold_days:
            pnl = realized + (0.5 if half_done else 1.0) * (b.Close - entry)
            return _res(d, b.Close, pnl, risk, i, "time stop")
    return None  # still open


def _res(d, px, pnl, risk, days, why):
    return {"exit_date": pd.Timestamp(d).date().isoformat(), "exit_price": round(float(px), 2),
            "pnl_per_share": float(pnl), "r": float(pnl / risk) if risk > 0 else 0.0,
            "days": days, "exit_reason": why}


def run_backtest(feats, cfg, lookback_days=400):
    spy = feats["SPY"]
    vix = feats.get("^VIX")
    dates = spy.index[-lookback_days:-1]
    trades = []
    for d in dates:
        sp = spy.loc[:d].iloc[-1]
        v = float(vix["Close"].loc[:d].iloc[-1]) if vix is not None and len(vix.loc[:d]) else 18
        if not (sp.Close > sp.sma200 and v < 28):
            continue
        green = sp.Close > sp.sma50 and sp.sma50 > sp.sma200 and v < 20
        thr = cfg["buy_score_threshold"] + (0 if green else 7)
        sub = {t: f.loc[:d] for t, f in feats.items()}
        snap = snapshot(sub)
        if snap.empty:
            continue
        sc = score_snapshot(snap, sp.ret63, sector_strength(sub), None, cfg)
        picks = sc[sc.eligible & sc.triggered & (sc.composite >= thr)].head(4 if green else 2)
        for t, r in picks.iterrows():
            a = float(r.atr)
            entry = float(r.Close)
            dist = min(np.clip(entry - (float(r.low5) - 0.2 * a), a, 2 * a), 0.08 * entry)
            hold = cfg["hold_days"].get(r.setup, 7)
            fut = feats[t].loc[d:].iloc[1:hold + 1]
            res = simulate_trade(fut, entry, entry - dist, entry + 1.5 * dist, entry + 3 * dist, hold, a)
            if res:
                res.update({"date": d.date().isoformat(), "ticker": t, "setup": r.setup,
                            "entry": round(entry, 2), "ret_pct": res["pnl_per_share"] / entry * 100})
                trades.append(res)
    return summarize(trades, cfg)


def summarize(trades, cfg):
    if not trades:
        return {"n": 0}
    df = pd.DataFrame(trades)
    by_setup = {}
    for s, g in df.groupby("setup"):
        by_setup[s] = {"n": int(len(g)), "win_rate": round(float((g.r > 0).mean() * 100), 1),
                       "avg_r": round(float(g.r.mean()), 2)}
    # Portfolio approximation: each trade risks risk_per_trade_pct of equity.
    # Group by exit date so returns compound in time order.
    risk = cfg["risk_per_trade_pct"] / 100
    daily = df.groupby("exit_date").r.sum().sort_index() * risk
    equity = (1 + daily).cumprod()
    dd = (equity / equity.cummax() - 1).min()
    # How often did a ~5-week window (25 trading days of exits) reach +20%?
    eq_full = equity.reindex(pd.date_range(equity.index.min(), equity.index.max(), freq="B").strftime("%Y-%m-%d")).ffill()
    win25 = (eq_full.shift(-25) / eq_full - 1).dropna()
    return {
        "n": int(len(df)),
        "win_rate": round(float((df.r > 0).mean() * 100), 1),
        "avg_r": round(float(df.r.mean()), 2),
        "avg_win_pct": round(float(df[df.r > 0].ret_pct.mean()), 2) if (df.r > 0).any() else 0,
        "avg_loss_pct": round(float(df[df.r <= 0].ret_pct.mean()), 2) if (df.r <= 0).any() else 0,
        "avg_days": round(float(df.days.mean()), 1),
        "total_return_pct": round(float((equity.iloc[-1] - 1) * 100), 1),
        "max_drawdown_pct": round(float(dd * 100), 1),
        "p_25d_gain_20pct": round(float((win25 >= 0.20).mean() * 100), 1) if len(win25) else None,
        "p_25d_gain_10pct": round(float((win25 >= 0.10).mean() * 100), 1) if len(win25) else None,
        "p_25d_loss": round(float((win25 < 0).mean() * 100), 1) if len(win25) else None,
        "median_25d_pct": round(float(win25.median() * 100), 1) if len(win25) else None,
        "by_setup": by_setup,
        "exit_reasons": df.exit_reason.value_counts().to_dict(),
        "from": df.date.min(), "to": df.date.max(),
        "recent": df.sort_values("date").tail(15).to_dict("records"),
    }
