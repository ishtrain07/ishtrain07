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

from . import data
from .indicators import add_features
from .strategy import score_snapshot, sector_strength, snapshot
from .universe import SECTOR_ETF, UNIVERSE

OUT = Path(__file__).parent / "output"
CFG = json.loads((Path(__file__).parent / "config.json").read_text())


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
        sc = score_snapshot(snap, sp.ret63, sector_strength(sub), None, CFG)
        v = float(vix.Close.loc[:d].iloc[-1]) if vix is not None else 18.0
        regime = "GREEN" if (sp.Close > sp.sma50 and sp.sma50 > sp.sma200 and v < 20) else \
                 "YELLOW" if (sp.Close > sp.sma200 and v < 28) else "RED"
        rows[d] = (regime, sc[["composite", "setup", "triggered", "eligible", "momentum", "rs",
                               "Close", "atr", "low5", "ema20", "sma50", "ret63", "rsi"]].copy())
    return rows


# ------------------------------------------------------------- swing variants
def swing_sim(feats, pre, v, start=None, end=None):
    """Daily portfolio sim. v: variant dict (see VARIANTS)."""
    dates = [d for d in pre if (start is None or d >= start) and (end is None or d <= end)]
    cash, equity_curve, open_pos, trades = 1.0, [], [], []
    for d in dates:
        # 1) exits using today's bar
        still = []
        for p in open_pos:
            b = feats[p["t"]].loc[d]
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
                    if v.get("exit_below_sma50") and b.Close < feats[p["t"]].loc[d].sma50:
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
        mv = sum(p["sh"] * feats[p["t"]].loc[d].Close for p in open_pos)
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
def rotation_sim(feats, pre, top_n=4, stop_pct=0.10, start=None, end=None, rank_col="momentum"):
    """Weekly: hold the top-N momentum names (eligible, regime not RED), equal weight."""
    dates = [d for d in pre if (start is None or d >= start) and (end is None or d <= end)]
    cash, hold, curve, trades, last_week = 1.0, {}, [], [], None
    for d in dates:
        # stops
        for t in list(hold):
            b = feats[t].loc[d]
            if b.Low <= hold[t]["stop"]:
                px = min(hold[t]["stop"], b.Open)
                cash += hold[t]["sh"] * px
                trades.append({"r": px / hold[t]["entry"] - 1, "ret": px / hold[t]["entry"] - 1, "why": "stop", "days": 0})
                del hold[t]
        equity = cash + sum(h["sh"] * feats[t].loc[d].Close for t, h in hold.items())
        curve.append((d, equity))
        week = d.isocalendar()[1]
        if week == last_week:
            continue
        last_week = week
        regime, sc = pre[d]
        target = [] if regime == "RED" else list(
            sc[sc.eligible & (sc.rsi < 80)].sort_values(rank_col, ascending=False).head(top_n).index)
        for t in list(hold):
            if t not in target:
                px = feats[t].loc[d].Close
                cash += hold[t]["sh"] * px
                trades.append({"r": px / hold[t]["entry"] - 1, "ret": px / hold[t]["entry"] - 1, "why": "rotate", "days": 0})
                del hold[t]
        new = [t for t in target if t not in hold]
        if new:
            per = min(cash / len(new), equity / top_n)
            for t in new:
                px = feats[t].loc[d].Close
                hold[t] = {"sh": per / px, "entry": px, "stop": px * (1 - stop_pct)}
                cash -= per
    return stats(curve, trades)


def buy_hold(feats, t, start, end):
    c = feats[t].Close.loc[start:end]
    curve = list(zip(c.index, c / c.iloc[0]))
    return stats(curve, [])


def stats(curve, trades):
    if not curve:
        return {}
    eq = pd.Series([e for _, e in curve], index=[d for d, _ in curve])
    dd = float((eq / eq.cummax() - 1).min())
    w25 = (eq.shift(-25) / eq - 1).dropna()
    tr = pd.DataFrame(trades)
    return {
        "total_pct": round(float(eq.iloc[-1] / eq.iloc[0] - 1) * 100, 1),
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


def main():
    tickers = sorted(set(UNIVERSE) | set(SECTOR_ETF.values()) | {"^VIX", "SPY", "QQQ"})
    prices = data.download_prices(tickers, period="3y")
    feats = {t: add_features(df) for t, df in prices.items()}
    pre = precompute(feats, 480)
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
    res["results"]["R momentum rotation top4, ranked by RS"] = {
        k: rotation_sim(feats, pre, 4, 0.10, a, b, rank_col="rs") for k, (a, b) in periods.items()}
    for t in ("SPY", "QQQ"):
        res["results"][f"Z buy & hold {t}"] = {k: buy_hold(feats, t, a, b) for k, (a, b) in periods.items()}
    OUT.mkdir(exist_ok=True)
    (OUT / "research.json").write_text(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
