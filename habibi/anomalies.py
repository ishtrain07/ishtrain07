"""Unusual-activity detection that learns from history.

Each signal type is event-studied across the whole universe over the last
~year: after the signal fired, what did the stock do over the next 5 trading
days compared with an average day? Today's flags carry that track record, and
their severity (caution / positive / neutral) comes from it, not from a guess.
Move-size thresholds are relative to each stock's own volatility.
"""
import numpy as np
import pandas as pd

from .universe import UNIVERSE

HORIZON = 5
LOOKBACK = 260

LABELS = {
    "big_drop": "Unusually large one-day drop (>3x its normal daily move)",
    "big_jump": "Unusually large one-day jump (>3x its normal daily move)",
    "volume_spike": "Volume more than 3x its 20-day average",
    "gap_down": "Gapped down more than 5% at the open",
    "gap_up": "Gapped up more than 5% at the open",
    "lost_50dma": "Closed below its 50-day average (was above yesterday)",
    "new_high": "Closed at a 52-week high",
    "rank_drop": "Fell out of the model's top 5 (was top 3 within the last 5 days)",
}


def signal_frame(f):
    """Boolean signal columns for one ticker's feature frame."""
    c = f.Close
    ret = c.pct_change()
    vol = ret.rolling(60, min_periods=30).std().shift(1)
    z = ret / vol
    gap = f.Open / c.shift(1) - 1
    return pd.DataFrame({
        "big_drop": z < -3,
        "big_jump": z > 3,
        "volume_spike": f.vol_ratio > 3,
        "gap_down": gap < -0.05,
        "gap_up": gap > 0.05,
        "lost_50dma": (c < f.sma50) & (c.shift(1) >= f.sma50.shift(1)),
        "new_high": c >= c.rolling(252, min_periods=120).max(),
    }, index=f.index)


def rank_drop_frame(scores):
    """date x ticker booleans: rank > 5 today, but rank <= 3 at some point in the prior 5 days."""
    ranks = scores.rank(axis=1, ascending=False)
    was_top = (ranks <= 3).rolling(5, min_periods=1).max().shift(1).fillna(0).astype(bool)
    return (ranks > 5) & was_top, ranks


def learn(feats, scores=None):
    """Event study over the universe. Returns per-signal stats and the baseline."""
    fwd_all, by_sig = [], {k: [] for k in LABELS}
    rank_drop = rank_drop_frame(scores)[0] if scores is not None else None
    for t in UNIVERSE:
        f = feats.get(t)
        if f is None or len(f) < 200:
            continue
        f = f.iloc[-(LOOKBACK + HORIZON):]
        fwd = f.Close.shift(-HORIZON) / f.Close - 1
        sig = signal_frame(f)
        if rank_drop is not None and t in rank_drop.columns:
            sig["rank_drop"] = rank_drop[t].reindex(f.index).fillna(False).astype(bool)
        valid = fwd.notna()
        fwd_all.append(fwd[valid])
        for k in by_sig:
            if k in sig:
                hits = fwd[valid & sig[k].fillna(False)]
                if len(hits):
                    by_sig[k].append(hits)
    base = pd.concat(fwd_all) if fwd_all else pd.Series(dtype=float)
    b_mean = float(base.mean()) if len(base) else 0.0
    stats = {"baseline_avg_pct": round(b_mean * 100, 2),
             "baseline_down_pct": round(float((base < 0).mean() * 100), 1) if len(base) else None}
    for k, parts in by_sig.items():
        s = pd.concat(parts) if parts else pd.Series(dtype=float)
        n = int(len(s))
        if n < 15:
            stats[k] = {"n": n, "avg_pct": None, "down_pct": None, "edge_pct": None, "verdict": "too few cases"}
            continue
        avg = float(s.mean())
        edge = avg - b_mean
        down = float((s < 0).mean() * 100)
        verdict = "caution" if edge < -0.005 else "positive" if edge > 0.005 else "neutral"
        stats[k] = {"n": n, "avg_pct": round(avg * 100, 2), "down_pct": round(down, 1),
                    "edge_pct": round(edge * 100, 2), "verdict": verdict}
    return stats


def detect(feats, tickers, stats, scores=None, held=None, sectors=None, max_positions=3):
    """Today's flags for the given tickers, each with its learned track record."""
    flags = []
    rank_drop, ranks = rank_drop_frame(scores) if scores is not None else (None, None)
    for t in tickers:
        f = feats.get(t)
        if f is None or len(f) < 70:
            continue
        sig = signal_frame(f).iloc[-1]
        fired = [k for k, v in sig.items() if bool(v)]
        if rank_drop is not None and t in rank_drop.columns and bool(rank_drop[t].iloc[-1]):
            fired.append("rank_drop")
        r = f.iloc[-1]
        for k in fired:
            s = stats.get(k, {})
            flags.append({
                "ticker": t, "type": k, "label": LABELS[k], "held": bool(held and t in held),
                "price": round(float(r.Close), 2), "day_pct": round(float(r.Close / f.Close.iloc[-2] - 1) * 100, 2),
                "n": s.get("n"), "avg_pct": s.get("avg_pct"), "down_pct": s.get("down_pct"),
                "edge_pct": s.get("edge_pct"), "verdict": s.get("verdict", "too few cases"),
            })
    # Holdings: show everything. Others: only signals with a learned edge (less noise).
    flags = [f for f in flags if f["held"] or f["verdict"] in ("caution", "positive")]
    order = {"caution": 0, "positive": 1, "neutral": 2, "too few cases": 3}
    flags.sort(key=lambda x: (not x["held"], order.get(x["verdict"], 4), x["ticker"]))

    trends = []
    if ranks is not None:
        for t in tickers:
            if t not in ranks.columns:
                continue
            series = ranks[t].dropna().iloc[-10:]
            if series.empty:
                continue
            now, wk = int(series.iloc[-1]), int(series.iloc[max(-6, -len(series))])
            trends.append({"ticker": t, "held": bool(held and t in held), "rank": now, "rank_5d_ago": wk,
                           "change": wk - now, "path": [int(x) for x in series.tolist()],
                           "warning": bool(held and t in held and now > max_positions + 2)})
        trends.sort(key=lambda x: (not x["held"], x["rank"]))

    concentration = None
    if held and sectors:
        counts = pd.Series([sectors.get(t, "?") for t in held]).value_counts()
        if len(held) >= 2 and counts.iloc[0] / len(held) > 0.6:
            concentration = f"{counts.index[0]} makes up {counts.iloc[0]} of your {len(held)} holdings: one sector shock hits everything."
    return {"flags": flags, "rank_trends": trends, "concentration": concentration}
