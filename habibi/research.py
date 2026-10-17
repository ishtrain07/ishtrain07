"""Strategy research: portfolio-level simulation of rule variants.

Unlike backtest.py (trade-by-trade), this enforces the real account limits:
max open positions, risk-based sizing, 30% position cap, cash. Every variant
is reported on two halves of history so a variant must work out-of-sample,
not just once.

  python -m habibi.research          # writes habibi/output/research.json
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import adaptive, data
from .indicators import add_features
from .strategy import score_snapshot, sector_strength, snapshot
from .universe import SECTOR_ETF, UNIVERSE

OUT = Path(__file__).parent / "output"
CFG = json.loads((Path(__file__).parent / "config.json").read_text())

# Sector groups for the concentration cap: universe sectors, with the sector ETFs mapped to
# what they actually hold (SMH is a semis basket, QQQ is mostly tech).
RESEARCH_SECTOR = {**UNIVERSE, "SMH": "Semis", "QQQ": "Tech"}
# Coarser theme groups: the live weakness is one AI-hardware trade spread over several GICS
# sectors (chips, networking/servers, power and cooling), so group those together.
AI_HARDWARE = {"NVDA", "AVGO", "AMD", "TSM", "MU", "QCOM", "ARM", "LRCX", "AMAT", "KLAC", "MRVL", "ASML",
               "INTC", "CRDO", "ALAB", "ON", "SMH", "ANET", "DELL", "SMCI", "CLS", "CIEN", "NBIS",
               "VRT", "GEV", "ETN", "PWR", "CEG", "VST", "NRG"}
THEME = {t: ("AIHardware" if t in AI_HARDWARE else sec) for t, sec in RESEARCH_SECTOR.items()}


def precompute(feats, days):
    """Scored universe for each date (the expensive part, shared by all variants)."""
    spy = feats["SPY"]
    vix = feats.get("^VIX")
    dates = spy.index[-days:]
    rows = {}
    for d in dates:
        sub = {t: f.loc[:d] for t, f in feats.items()}
        snap = snapshot(sub)
        if snap.empty:
            continue
        sp = spy.loc[d]
        fresh = [t for t in snap.index if feats[t].loc[:d].index[-1] == d]
        snap = snap.loc[fresh]
        sc = score_snapshot(snap, sp.ret63, sector_strength(sub), None, CFG)
        v = float(vix.Close.loc[:d].iloc[-1]) if vix is not None else 18.0
        regime = "GREEN" if (sp.Close > sp.sma50 and sp.sma50 > sp.sma200 and v < 20) else \
                 "YELLOW" if (sp.Close > sp.sma200 and v < 28) else "RED"
        mom = 0.5 * sc.ret126 + 0.3 * sc.ret63 + 0.2 * sc.ret21
        sc["risk_adj_mom"] = mom / (sc.atr / sc.Close)
        rows[d] = (regime, sc[["composite", "setup", "triggered", "eligible", "momentum", "rs", "risk_adj_mom",
                               "Close", "atr", "low5", "ema20", "sma50", "ret63", "rsi"]].copy())
    return rows


def bar(feats, t, d):
    f = feats[t]
    return f.loc[d] if d in f.index else None


def last_close(feats, t, d):
    return float(feats[t].Close.loc[:d].iloc[-1])


# ------------------------------------------------------------- swing variants
def swing_sim(feats, pre, v, start=None, end=None):
    """Daily portfolio sim. v: variant dict (see VARIANTS)."""
    dates = [d for d in pre if (start is None or d >= start) and (end is None or d <= end)]
    cash, equity_curve, open_pos, trades = 1.0, [], [], []
    for d in dates:
        # 1) exits using today's bar
        still = []
        for p in open_pos:
            b = bar(feats, p["t"], d)
            if b is None:
                still.append(p)
                continue
            p["days"] += 1
            exit_px, why = None, None
            if b.Low <= p["stop"]:
                exit_px, why = min(p["stop"], b.Open), "stop"
            else:
                if v["t1_r"] and not p["half"] and b.High >= p["t1"]:
                    cash += p["sh"] * 0.5 * p["t1"]; p["realized"] += p["sh"] * 0.5 * (p["t1"] - p["entry"])
                    p["sh"] *= 0.5; p["half"] = True; p["stop"] = max(p["stop"], p["entry"])
                if v["t2_r"] and b.High >= p["t2"]:
                    exit_px, why = p["t2"], "target"
                else:
                    p["hc"] = max(p["hc"], b.Close)
                    if v["trail_atr"] and (p["half"] or not v["t1_r"]):
                        p["stop"] = max(p["stop"], p["hc"] - v["trail_atr"] * p["atr"])
                    if v.get("exit_below_sma50") and b.Close < b.sma50:
                        exit_px, why = b.Close, "trend"
                    elif p["days"] >= v["hold"]:
                        exit_px, why = b.Close, "time"
            if exit_px is not None:
                cash += p["sh"] * exit_px
                pnl = p["realized"] + p["sh"] * (exit_px - p["entry"])
                trades.append({"r": pnl / (p["sh0"] * p["risk"]), "why": why, "days": p["days"],
                               "ret": pnl / (p["sh0"] * p["entry"])})
            else:
                still.append(p)
        open_pos = still
        mv = sum(p["sh"] * last_close(feats, p["t"], d) for p in open_pos)
        equity = cash + mv
        equity_curve.append((d, equity))

        # 2) entries at today's close
        regime, sc = pre[d]
        if regime == "RED" or (regime == "YELLOW" and not v.get("trade_yellow", True)):
            continue
        slots = v["max_pos"] - len(open_pos)
        if slots <= 0:
            continue
        cand = v["select"](sc, regime)
        held = {p["t"] for p in open_pos}
        risk_mult = 1.0 if regime == "GREEN" else 0.5
        for t, r in cand.iterrows():
            if slots <= 0 or t in held:
                continue
            a, entry = float(r.atr), float(r.Close)
            dist = np.clip(entry - (float(r.low5) - 0.2 * a), v["stop_min"] * a, v["stop_max"] * a)
            dist = min(dist, v.get("stop_cap", 0.08) * entry)
            sh = min(equity * v["risk"] * risk_mult / dist, equity * v["pos_cap"] / entry, cash / entry)
            if sh * entry < 0.02 * equity:
                break
            cash -= sh * entry
            open_pos.append({"t": t, "sh": sh, "sh0": sh, "entry": entry, "risk": dist, "atr": a,
                             "stop": entry - dist, "t1": entry + (v["t1_r"] or 0) * dist,
                             "t2": entry + (v["t2_r"] or 0) * dist, "half": False, "realized": 0.0,
                             "hc": entry, "days": 0})
            slots -= 1
    return stats(equity_curve, trades)


# ------------------------------------------------------------- momentum rotation
def rotation_sim(feats, pre, top_n=4, stop_pct=0.10, start=None, end=None, rank_col="momentum",
                 exit_below_ema20=False, entry_green_only=False, dd_brake=None, cool_days=5, max_rsi=80,
                 initial_frac=1.0, add_gain=None, cost=0.0, hold_rank=None, sector_cap=None,
                 sector_map=None, profit_take=None, pt_frac=0.5, signal_lag=0, return_curve=False):
    """Weekly: hold the top-N ranked names (eligible, regime not RED), equal weight.

    exit_below_ema20: daily exit when a holding closes below its 20-EMA.
    entry_green_only: new buys only when the market light is GREEN.
    dd_brake: if equity falls this far below its peak, go to cash for cool_days.
    initial_frac / add_gain: staged entry - buy initial_frac of a full slot, add the rest
    once the holding is up add_gain and still in the current top-N.
    cost: fraction lost on every buy and every sell (e.g. 0.015 = Wealthsimple's 1.5% FX fee).
    hold_rank: keep a holding while it ranks within this many (default top_n); new buys still
    come from the top-N. A buffer above top_n cuts turnover.
    sector_cap: at most this many names per group in the target (groups from sector_map,
    default RESEARCH_SECTOR). Applied in rank order, kept holdings first.
    profit_take: sell pt_frac of a holding once its high reaches entry * (1 + profit_take)
    (filled at the target, or at the open on a gap up), then move the remainder's stop to
    breakeven (effective from the next bar: intraday order is unknown).
    signal_lag: 1 = rank on the previous day's snapshot and trade at today's close (strict
    no-look-ahead check); 0 = rank and trade on the same close (original behaviour).
    Trade "ret" is net of costs and blends any partial sale.
    """
    smap = sector_map or RESEARCH_SECTOR
    dates = [d for d in pre if (start is None or d >= start) and (end is None or d <= end)]
    cash, hold, curve, trades, last_week = 1.0, {}, [], [], None
    peak, cool = 1.0, 0
    target = []
    traded = 0.0
    all_dates = list(pre)
    prev_of = {d: all_dates[i - 1] for i, d in enumerate(all_dates) if i > 0}

    def sell(t, px, why):
        nonlocal cash, traded
        h = hold[t]
        proceeds = h["sh"] * px * (1 - cost)
        cash += proceeds
        traded += h["sh"] * px
        trades.append({"r": px / h["entry"] - 1, "ret": (h["proceeds"] + proceeds) / h["basis"] - 1,
                       "why": why, "days": 0})
        del hold[t]

    for d in dates:
        for t in list(hold):
            b = bar(feats, t, d)
            if b is None:
                continue
            h = hold[t]
            if b.Low <= h["stop"]:
                sell(t, min(h["stop"], b.Open), "stop")
                continue
            if exit_below_ema20 and b.Close < b.ema20:
                sell(t, b.Close, "ema20")
                continue
            if profit_take and not h["half"] and b.High >= h["entry"] * (1 + profit_take):
                px = max(h["entry"] * (1 + profit_take), b.Open)
                sh = h["sh"] * pt_frac
                cash += sh * px * (1 - cost)
                traded += sh * px
                h["proceeds"] += sh * px * (1 - cost)
                h["sh"] -= sh
                h["half"] = True
                h["stop"] = max(h["stop"], h["entry"])
        if add_gain:
            for t, h in hold.items():
                px = last_close(feats, t, d)
                if not h["added"] and t in target and px >= h["entry"] * (1 + add_gain) and cash > 0:
                    amt = min(h["full"] * (1 - initial_frac), cash)
                    add_sh = amt * (1 - cost) / px
                    h["entry"] = (h["entry"] * h["sh"] + amt) / (h["sh"] + add_sh)
                    h["sh"] += add_sh
                    h["basis"] += amt
                    traded += amt
                    h["stop"] = max(h["stop"], h["entry"] * (1 - stop_pct))
                    h["added"] = True
                    cash -= amt
        equity = cash + sum(h["sh"] * last_close(feats, t, d) for t, h in hold.items())
        peak = max(peak, equity)
        if dd_brake and equity < peak * (1 - dd_brake) and hold:
            for t in list(hold):
                sell(t, last_close(feats, t, d), "brake")
            cool, peak = cool_days, equity
        curve.append((d, equity))
        if cool > 0:
            cool -= 1
            continue
        week = d.isocalendar()[1]
        if week == last_week:
            continue
        last_week = week
        sig_d = prev_of.get(d) if signal_lag else d
        if sig_d is None:
            continue
        regime, sc = pre[sig_d]
        ok = sc.eligible & (sc.rsi < max_rsi)
        if exit_below_ema20:
            ok &= sc.Close > sc.ema20
        ranked = list(sc[ok].sort_values(rank_col, ascending=False).index)
        if signal_lag:  # must still have a bar today to trade it
            ranked = [t for t in ranked if bar(feats, t, d) is not None]
        if regime == "RED":
            target = []
        else:
            keep = [t for t in ranked[:hold_rank or top_n] if t in hold][:top_n]
            target = keep + [t for t in ranked if t not in keep][:top_n - len(keep)]
            if sector_cap:
                target = capped_target(keep, ranked, top_n, sector_cap, smap)
        for t in list(hold):
            if t not in target:
                sell(t, last_close(feats, t, d), "rotate")
        if entry_green_only and regime != "GREEN":
            continue
        new = [t for t in target if t not in hold]
        if new:
            per = min(cash / len(new), equity / top_n)
            for t in new:
                px = last_close(feats, t, d)
                amt = per * initial_frac
                hold[t] = {"sh": amt * (1 - cost) / px, "entry": px, "stop": px * (1 - stop_pct), "full": per,
                           "added": initial_frac >= 1, "half": False, "basis": amt, "proceeds": 0.0}
                cash -= amt
                traded += amt
    if return_curve:
        return curve
    return stats(curve, trades, traded)


def capped_target(keep, ranked, top_n, cap, smap):
    """Top-N target with at most `cap` names per group: kept holdings first (in rank order), then
    the best-ranked names whose group still has room."""
    out, n = [], {}
    for t in keep + [t for t in ranked if t not in keep]:
        if len(out) >= top_n:
            break
        g = smap.get(t, t)
        if n.get(g, 0) < cap:
            out.append(t)
            n[g] = n.get(g, 0) + 1
    return out


def horizon_dist(curve_or_series, h=10):
    """Distribution of h-trading-day returns and in-window drawdowns over all rolling windows."""
    eq = curve_or_series if isinstance(curve_or_series, pd.Series) else \
        pd.Series([e for _, e in curve_or_series], index=[d for d, _ in curve_or_series])
    v = eq.values
    rets, dds = [], []
    for i in range(len(v) - h):
        w = v[i:i + h + 1]
        rets.append(w[-1] / w[0] - 1)
        dds.append((w / np.maximum.accumulate(w) - 1).min())
    if not rets:
        return {}
    r, dd = np.array(rets) * 100, np.array(dds) * 100
    q = lambda a, p: round(float(np.percentile(a, p)), 1)
    return {"windows": len(r), "mean": round(float(r.mean()), 2), "median": q(r, 50), "p5": q(r, 5),
            "p25": q(r, 25), "p75": q(r, 75), "p95": q(r, 95), "p_loss": round(float((r < 0).mean() * 100), 1),
            "p_gain5": round(float((r >= 5).mean() * 100), 1), "p_lose5": round(float((r <= -5).mean() * 100), 1),
            "dd_median": q(dd, 50), "dd_p5": q(dd, 5), "dd_worst": round(float(dd.min()), 1)}


def buy_hold(feats, t, start, end):
    c = feats[t].Close.loc[start:end]
    curve = list(zip(c.index, c / c.iloc[0]))
    return stats(curve, [])


def stats(curve, trades, traded=None):
    if not curve:
        return {}
    eq = pd.Series([e for _, e in curve], index=[d for d, _ in curve])
    dd = float((eq / eq.cummax() - 1).min())
    n = len(eq)
    yrs = max(n - 1, 1) / 252
    dr = eq.pct_change().dropna()
    sharpe = float(dr.mean() / dr.std() * np.sqrt(252)) if len(dr) > 1 and dr.std() > 0 else None
    m = eq.resample("ME").last()
    monthly = pd.concat([pd.Series([eq.iloc[0]]), m.reset_index(drop=True)]).pct_change().dropna()
    w25 = (eq.shift(-25) / eq - 1).dropna()
    tr = pd.DataFrame(trades)
    return {
        "total_pct": round(float(eq.iloc[-1] / eq.iloc[0] - 1) * 100, 1),
        "cagr_pct": round(float((eq.iloc[-1] / eq.iloc[0]) ** (1 / yrs) - 1) * 100, 1),
        "sharpe": round(sharpe, 2) if sharpe is not None else None,
        "worst_month_pct": round(float(monthly.min()) * 100, 1) if len(monthly) else None,
        "turnover_x_yr": round(float(traded / eq.mean() / yrs), 1) if traded is not None else None,
        "max_dd_pct": round(dd * 100, 1),
        "trades": int(len(tr)),
        "win_rate": round(float((tr.ret > 0).mean() * 100), 1) if len(tr) else None,
        "avg_r": round(float(tr.r.mean()), 2) if len(tr) and "r" in tr else None,
        "p25_20": round(float((w25 >= 0.20).mean() * 100), 1) if len(w25) else None,
        "p25_10": round(float((w25 >= 0.10).mean() * 100), 1) if len(w25) else None,
        "p25_loss": round(float((w25 < 0).mean() * 100), 1) if len(w25) else None,
        "med25": round(float(w25.median() * 100), 1) if len(w25) else None,
    }


# ------------------------------------------------------------- variant catalogue
def sel_current(sc, regime):
    thr = 65 if regime == "GREEN" else 72
    return sc[sc.eligible & sc.triggered & (sc.composite >= thr)]


def sel_breakout(sc, regime):
    return sc[sc.eligible & sc.triggered & (sc.setup == "breakout") & (sc.composite >= 65)]


def sel_leader_pullback(sc, regime):
    return sc[sc.eligible & sc.triggered & (sc.setup == "pullback") & (sc.momentum >= 70) & (sc.rs >= 70)]


def sel_leaders_any(sc, regime):
    return sc[sc.eligible & sc.triggered & (sc.momentum >= 75)].sort_values("momentum", ascending=False)


BASE = {"max_pos": 4, "risk": 0.015, "pos_cap": 0.30, "stop_min": 1.0, "stop_max": 2.0,
        "t1_r": 1.5, "t2_r": 3.0, "trail_atr": 2.0, "hold": 7, "select": sel_current}

VARIANTS = {
    "A current rules": {},
    "B current, hold 15, trail 3ATR, no T2": {"hold": 15, "t2_r": None, "trail_atr": 3.0},
    "C breakouts only": {"select": sel_breakout},
    "D breakouts, let winners run": {"select": sel_breakout, "hold": 20, "t1_r": None, "t2_r": None,
                                     "trail_atr": 3.0, "exit_below_sma50": True},
    "E leader pullbacks": {"select": sel_leader_pullback},
    "F leader pullbacks, let run": {"select": sel_leader_pullback, "hold": 20, "t1_r": None,
                                    "t2_r": None, "trail_atr": 3.0, "exit_below_sma50": True},
    "G leaders any setup, let run": {"select": sel_leaders_any, "hold": 20, "t1_r": None,
                                     "t2_r": None, "trail_atr": 3.0, "exit_below_sma50": True},
    "H leaders, wide stop, let run": {"select": sel_leaders_any, "hold": 25, "t1_r": None, "t2_r": None,
                                      "stop_min": 2.0, "stop_max": 3.0, "stop_cap": 0.12,
                                      "trail_atr": 3.5, "exit_below_sma50": True},
    "I leaders, 3 positions, risk 2%": {"select": sel_leaders_any, "max_pos": 3, "risk": 0.02,
                                        "pos_cap": 0.35, "hold": 20, "t1_r": None, "t2_r": None,
                                        "trail_atr": 3.0, "exit_below_sma50": True},
}


# ------------------------------------------------------------- 2026-10 sector cap / profit-take study
SLIP = 0.0005                     # slippage per side on top of the spread/commission cost
COST_USD, COST_FX = 0.001 + SLIP, 0.015 + SLIP
BASELINE = dict(top_n=3, rank_col="adaptive", stop_pct=0.08, dd_brake=0.10, hold_rank=5, cost=COST_USD)
CAP_VARIANTS = {
    "S1 sector cap 1": dict(sector_cap=1),
    "S2 sector cap 2": dict(sector_cap=2),
    "S3 AI-hardware theme cap 1": dict(sector_cap=1, sector_map=THEME),
    "S4 AI-hardware theme cap 2": dict(sector_cap=2, sector_map=THEME),
}
PT_VARIANTS = {
    "P1 sell half at +5%, stop to breakeven": dict(profit_take=0.05),
    "P2 sell half at +8%, stop to breakeven": dict(profit_take=0.08),
}


def pick_best(results, names, period="half1"):
    """Best variant by in-sample (half1) Sharpe only, so half2 stays out-of-sample."""
    return max(names, key=lambda n: results[n][period].get("sharpe") or -9)


def sector_study(feats, pre, periods):
    """Baseline (live rules) vs sector caps, partial profit-take and the combination.

    The 'best' cap and profit-take are chosen on half1 only; half2 is the out-of-sample test.
    """
    run = lambda kw: {k: rotation_sim(feats, pre, start=a, end=b, **kw) for k, (a, b) in periods.items()}
    out = {"baseline": "top3 adaptive, hold while top-5, 8% stop, 10% brake, 0.1%+0.05% slip per side",
           "selection": "best cap / profit-take by half1 Sharpe; half2 is out-of-sample", "results": {}}
    r = out["results"]
    r["S0 baseline (live rules)"] = run(BASELINE)
    r["S0L baseline, signal lagged 1 day"] = run(dict(BASELINE, signal_lag=1))
    for name, kw in {**CAP_VARIANTS, **PT_VARIANTS}.items():
        r[name] = run(dict(BASELINE, **kw))
    cap, pt = pick_best(r, list(CAP_VARIANTS)), pick_best(r, list(PT_VARIANTS))
    combo = dict(BASELINE, **CAP_VARIANTS[cap], **PT_VARIANTS[pt])
    out["picked"] = {"cap": cap, "profit_take": pt}
    r["C1 combined: best cap + best profit-take"] = run(combo)
    r["C1L combined, signal lagged 1 day"] = run(dict(combo, signal_lag=1))
    best = max(["S0 baseline (live rules)", cap, pt, "C1 combined: best cap + best profit-take"],
               key=lambda n: r[n]["half1"].get("sharpe") or -9)
    best_kw = {"S0 baseline (live rules)": BASELINE, cap: dict(BASELINE, **CAP_VARIANTS[cap]),
               pt: dict(BASELINE, **PT_VARIANTS[pt]), "C1 combined: best cap + best profit-take": combo}[best]
    out["picked"]["overall"] = best
    r["X0 baseline at 1.5% FX per side"] = run(dict(BASELINE, cost=COST_FX))
    r["X1 best at 1.5% FX per side"] = run(dict(best_kw, cost=COST_FX))
    for t in ("SPY", "QQQ"):
        r[f"Z buy & hold {t}"] = {k: buy_hold(feats, t, a, b) for k, (a, b) in periods.items()}
    # 10-trading-day horizon: every rolling 2-week window over the full period
    a, b = periods["full"]
    spy = feats["SPY"].Close.loc[a:b]
    out["horizon10"] = {
        "baseline": horizon_dist(curve_of(feats, pre, BASELINE, a, b)),
        "best": horizon_dist(curve_of(feats, pre, best_kw, a, b)),
        "SPY": horizon_dist(spy / spy.iloc[0]),
    }
    for name, v in r.items():
        print(name, v["half1"].get("sharpe"), v["half2"].get("sharpe"), v["full"])
    print("picked", out["picked"], "horizon10", out["horizon10"])
    return out


def curve_of(feats, pre, kw, start, end):
    return rotation_sim(feats, pre, start=start, end=end, return_curve=True, **kw)


def main():
    tickers = sorted(set(UNIVERSE) | set(SECTOR_ETF.values()) | {"^VIX", "SPY", "QQQ"})
    prices = data.download_prices(tickers, period="3y")
    feats = {t: add_features(df) for t, df in prices.items()}
    pre = precompute(feats, 480)
    uni = [t for t in UNIVERSE if t in feats and len(feats[t]) > 260]
    m = adaptive.model(feats, uni)
    eq_w = pd.DataFrame(1 / len(adaptive.FACTORS), index=m["weights"].index, columns=m["weights"].columns)
    eq_scores = adaptive.adaptive_scores(m["panels"], eq_w)
    for d, (regime, sc) in pre.items():
        sc["adaptive"] = m["scores"].loc[d].reindex(sc.index) if d in m["scores"].index else np.nan
        sc["equal_mf"] = eq_scores.loc[d].reindex(sc.index) if d in eq_scores.index else np.nan
    dates = list(pre)
    mid = dates[len(dates) // 2]
    periods = {"full": (dates[0], dates[-1]), "half1": (dates[0], mid), "half2": (mid, dates[-1])}
    res = {"periods": {k: [str(a.date()), str(b.date())] for k, (a, b) in periods.items()}, "results": {}}
    for name, over in VARIANTS.items():
        v = {**BASE, **over}
        res["results"][name] = {k: swing_sim(feats, pre, v, a, b) for k, (a, b) in periods.items()}
        print(name, res["results"][name]["full"])
    for n in (3, 4, 5):
        name = f"R momentum rotation top{n} weekly"
        res["results"][name] = {k: rotation_sim(feats, pre, n, 0.10, a, b) for k, (a, b) in periods.items()}
        print(name, res["results"][name]["full"])
    rot = {
        "R2 top3 risk-adjusted momentum": dict(top_n=3, rank_col="risk_adj_mom"),
        "R3 top3, 7% stop, exit < 20-EMA": dict(top_n=3, stop_pct=0.07, exit_below_ema20=True),
        "R4 top3 risk-adj, 7% stop, exit < 20-EMA": dict(top_n=3, stop_pct=0.07, exit_below_ema20=True, rank_col="risk_adj_mom"),
        "R5 R4 + 10% drawdown brake": dict(top_n=3, stop_pct=0.07, exit_below_ema20=True, rank_col="risk_adj_mom", dd_brake=0.10),
        "R6 R3 + 10% drawdown brake": dict(top_n=3, stop_pct=0.07, exit_below_ema20=True, dd_brake=0.10),
        "R7 top4 risk-adj, 8% stop, green entries, brake 12%": dict(top_n=4, stop_pct=0.08, rank_col="risk_adj_mom",
                                                               entry_green_only=True, dd_brake=0.12),
        "R8 top3 momentum, 8% stop, brake 10%": dict(top_n=3, stop_pct=0.08, dd_brake=0.10),
    }
    rot.update({
        "L1 LEARNING model top3 weekly, 10% stop": dict(top_n=3, rank_col="adaptive"),
        "L2 LEARNING model top3 weekly, 8% stop, brake 10%": dict(top_n=3, rank_col="adaptive", stop_pct=0.08, dd_brake=0.10),
        "L3 LEARNING model top4 weekly": dict(top_n=4, rank_col="adaptive"),
        "L0 equal-weight factors, no learning (control)": dict(top_n=3, rank_col="equal_mf"),
        "L4 L2 + staged entry (50% now, add 50% at +4%)": dict(top_n=3, rank_col="adaptive", stop_pct=0.08, dd_brake=0.10,
                                                            initial_frac=0.5, add_gain=0.04),
        "L5 L2 + staged entry (50% now, add at +2%)": dict(top_n=3, rank_col="adaptive", stop_pct=0.08, dd_brake=0.10,
                                                        initial_frac=0.5, add_gain=0.02),
        "L6 L2 concentrated: top 2": dict(top_n=2, rank_col="adaptive", stop_pct=0.08, dd_brake=0.10),
        "L7 L2 top 2 + staged entry": dict(top_n=2, rank_col="adaptive", stop_pct=0.08, dd_brake=0.10,
                                           initial_frac=0.5, add_gain=0.04),
    })
    l2 = dict(top_n=3, rank_col="adaptive", stop_pct=0.08, dd_brake=0.10)
    rot.update({
        "F1 L2 + 1.5% FX fee each way (no USD account)": dict(l2, cost=0.015),
        "F2 L2 hold while top-5 + 1.5% FX fee": dict(l2, cost=0.015, hold_rank=5),
        "F3 L2 + 0.1% cost (USD account, spread only)": dict(l2, cost=0.001),
        "F4 L2 hold while top-4 + 0.1% cost": dict(l2, cost=0.001, hold_rank=4),
        "F5 L2 hold while top-5 + 0.1% cost": dict(l2, cost=0.001, hold_rank=5),
        "F6 L2 hold while top-6 + 0.1% cost": dict(l2, cost=0.001, hold_rank=6),
    })
    for name, kw in rot.items():
        res["results"][name] = {k: rotation_sim(feats, pre, start=a, end=b, **kw) for k, (a, b) in periods.items()}
        print(name, res["results"][name]["full"])
    for t in ("SPY", "QQQ"):
        res["results"][f"Z buy & hold {t}"] = {k: buy_hold(feats, t, a, b) for k, (a, b) in periods.items()}
    res["sector_study"] = sector_study(feats, pre, periods)
    res["learned_weights_now"] = adaptive.explain_today(m)
    OUT.mkdir(exist_ok=True)
    (OUT / "research.json").write_text(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
