"""Ranking, bucketing and trade plans.

Pipeline (quant-style multi-factor model with a market-regime overlay):
  1. Regime: SPY trend + VIX decide how much risk is allowed today.
  2. Filters: price, liquidity, long-term uptrend (above 200-day).
  3. Factors (cross-sectional percentile ranks): momentum, relative strength,
     trend quality, entry setup, fundamentals, sector strength.
  4. Setups: PULLBACK (dip to 20-EMA in an uptrend that bounces) or
     BREAKOUT (new 20-day high on heavy volume).
  5. Plan: ATR-based stop, two targets (1.5R and 3R), time stop, risk-based size.
"""
import datetime as dt

import numpy as np
import pandas as pd

from .universe import NYSE_HOLIDAYS, SECTOR_ETF, UNIVERSE

WEIGHTS = {"momentum": 0.30, "rs": 0.15, "trend": 0.20, "setup": 0.25, "fund": 0.10}
_HOLIDAYS = {dt.date.fromisoformat(d) for d in NYSE_HOLIDAYS}


# ---------------------------------------------------------------- calendar
def is_trading_day(d):
    return d.weekday() < 5 and d not in _HOLIDAYS


def add_trading_days(d, n):
    while n > 0:
        d += dt.timedelta(days=1)
        if is_trading_day(d):
            n -= 1
    return d


def trading_days_between(a, b):
    """Trading days strictly after a up to and including b."""
    n, d = 0, a
    while d < b:
        d += dt.timedelta(days=1)
        if is_trading_day(d):
            n += 1
    return n


# ---------------------------------------------------------------- regime
def market_regime(spy, vix_close):
    """spy: feature frame for SPY. vix_close: latest VIX level (or None)."""
    r = spy.iloc[-1]
    vix = float(vix_close) if vix_close is not None else 18.0
    above50, above200 = r.Close > r.sma50, r.Close > r.sma200
    golden = r.sma50 > r.sma200
    if above50 and golden and vix < 20:
        light, risk_mult, max_new = "GREEN", 1.0, 4
        msg = "Uptrend confirmed and volatility calm. Full risk allowed."
    elif above200 and vix < 28:
        light, risk_mult, max_new = "YELLOW", 0.5, 2
        msg = "Market is choppy (below 50-day or VIX elevated). Half size, A-grade setups only."
    else:
        light, risk_mult, max_new = "RED", 0.0, 0
        msg = "Market below 200-day or VIX spiking. No new buys; protect capital."
    return {"light": light, "risk_mult": risk_mult, "max_new": max_new, "message": msg,
            "spy": round(float(r.Close), 2), "spy_sma50": round(float(r.sma50), 2),
            "spy_sma200": round(float(r.sma200), 2), "vix": round(vix, 2)}


def sector_strength(feats):
    """Rank sector ETFs by 1-month + 3-month return. Returns {sector: pct_rank 0..1}."""
    vals = {}
    for sector, etf in SECTOR_ETF.items():
        f = feats.get(etf)
        if f is not None and len(f) > 70 and sector != "ETF":
            r = f.iloc[-1]
            vals[sector] = 0.5 * r.ret21 + 0.5 * r.ret63
    if not vals:
        return {}
    s = pd.Series(vals).rank(pct=True)
    out = s.to_dict()
    out["ETF"] = 0.5
    return out


# ---------------------------------------------------------------- scoring
def fundamental_score(info):
    if not info or info.get("quote_type") == "ETF":
        return 50.0, []
    score, notes = 50.0, []
    g = info.get("revenue_growth")
    pe = info.get("forward_pe")
    m = info.get("profit_margin")
    if g is not None:
        if g > 0.30:
            score += 20; notes.append(f"revenue +{g:.0%} y/y")
        elif g > 0.12:
            score += 12; notes.append(f"revenue +{g:.0%} y/y")
        elif g < 0:
            score -= 15; notes.append(f"revenue shrinking {g:.0%}")
    if m is not None:
        if m > 0.15:
            score += 10
        elif m < 0:
            score -= 10; notes.append("unprofitable")
    if pe is not None and pe > 0:
        growth = max((g or 0) * 100, 1)
        peg = pe / growth
        if pe > 90:
            score -= 15; notes.append(f"expensive (fwd P/E {pe:.0f})")
        elif peg < 1.5:
            score += 10; notes.append(f"fwd P/E {pe:.0f} is cheap for its growth")
        else:
            notes.append(f"fwd P/E {pe:.0f}")
    elif pe is not None and pe <= 0:
        score -= 10
    return float(np.clip(score, 0, 100)), notes


def snapshot(feats, date=None):
    """One row per ticker with the latest (or as-of `date`) indicator values."""
    rows = {}
    for t, f in feats.items():
        if t not in UNIVERSE:
            continue
        sub = f if date is None else f.loc[:date]
        if len(sub) < 210:
            continue
        rows[t] = sub.iloc[-1]
    return pd.DataFrame(rows).T


def classify_setup(r):
    """Return (setup_name, setup_score, triggered, note)."""
    uptrend = r.Close > r.sma50 and r.sma50 > r.sma200
    if r.dist_ema20_atr > 3.0 or r.rsi > 76:
        return "extended", 0.0, False, f"extended {r.dist_ema20_atr:.1f} ATR above 20-EMA, RSI {r.rsi:.0f}"
    if r.Close >= r.hi20_prev and r.vol_ratio >= 1.4 and r.rsi < 76:
        return "breakout", 100.0, True, f"new 20-day high on {r.vol_ratio:.1f}x volume"
    if uptrend and -1.2 <= r.dist_ema20_atr <= 0.6 and 35 <= r.rsi <= 58:
        if r.Close > r.prev_close and r.Close > r.Open:
            return "pullback", 95.0, True, f"bounced off 20-EMA (RSI {r.rsi:.0f})"
        return "pullback", 65.0, False, f"sitting on 20-EMA support (RSI {r.rsi:.0f}), no bounce yet"
    if r.Close >= 0.97 * r.hi20_prev and r.rsi < 72:
        return "breakout", 60.0, False, f"{(r.hi20_prev / r.Close - 1):.1%} below 20-day high"
    return "none", 30.0, False, "no clean entry"


def score_snapshot(snap, spy_ret63, sector_rank, funds, cfg):
    """Adds factor scores, composite and setup columns. Returns filtered DataFrame."""
    s = snap.copy()
    for c in s.columns:
        s[c] = pd.to_numeric(s[c], errors="coerce")
    s["sector"] = [UNIVERSE[t] for t in s.index]
    s["eligible"] = (s.Close >= cfg["min_price"]) & (s.dollar_vol >= cfg["min_dollar_volume"]) \
        & (s.Close > s.sma200)
    mom_raw = 0.5 * s.ret126 + 0.3 * s.ret63 + 0.2 * s.ret21
    s["momentum"] = mom_raw.rank(pct=True) * 100
    s["rs"] = (s.ret63 - spy_ret63).rank(pct=True) * 100
    s["trend"] = 25.0 * ((s.Close > s.ema20).astype(int) + (s.Close > s.sma50).astype(int)
                         + (s.sma50 > s.sma200).astype(int) + (s.sma50_slope > 0).astype(int))
    setups = s.apply(classify_setup, axis=1, result_type="expand")
    setups.columns = ["setup", "setup_score", "triggered", "setup_note"]
    s = s.join(setups)
    fs = {t: fundamental_score((funds or {}).get(t)) for t in s.index}
    s["fund"] = [fs[t][0] for t in s.index]
    s["fund_notes"] = [fs[t][1] for t in s.index]
    s["composite"] = sum(WEIGHTS[k] * s[k if k != "setup" else "setup_score"] for k in WEIGHTS)
    # Sector tilt: +/-5 points for leading/lagging sectors.
    s["sector_rank"] = [sector_rank.get(sec, 0.5) for sec in s.sector]
    s["composite"] += (s.sector_rank - 0.5) * 10
    return s.sort_values("composite", ascending=False)


# ---------------------------------------------------------------- plans
def make_plan(r, setup, equity, cash, cfg, risk_mult, today, earnings=None):
    entry = float(r.Close)
    a = float(r.atr)
    swing_stop = float(r.low5) - 0.2 * a
    dist = np.clip(entry - swing_stop, 1.0 * a, 2.0 * a)
    dist = min(dist, 0.08 * entry)
    stop = entry - dist
    t1, t2 = entry + 1.5 * dist, entry + 3.0 * dist
    hold = cfg["hold_days"].get(setup, 7)
    if earnings:
        days_to_er = trading_days_between(today, dt.date.fromisoformat(earnings))
        hold = min(hold, days_to_er - 1)
    risk_dollars = equity * cfg["risk_per_trade_pct"] / 100 * risk_mult
    shares = risk_dollars / dist if dist > 0 else 0
    cap = min(equity * cfg["max_position_pct"] / 100, max(cash, 0))
    shares = min(shares, cap / entry)
    shares = round(shares, 2) if cfg.get("fractional_shares") else float(int(shares))
    return {
        "entry": round(entry, 2), "limit": round(entry * 1.005, 2),
        "stop": round(stop, 2), "t1": round(t1, 2), "t2": round(t2, 2),
        "stop_pct": round(-dist / entry * 100, 1), "t1_pct": round(1.5 * dist / entry * 100, 1),
        "t2_pct": round(3 * dist / entry * 100, 1),
        "hold_days": int(hold), "sell_by": add_trading_days(today, max(int(hold), 1)).isoformat(),
        "shares": shares, "dollars": round(shares * entry, 2),
        "risk_dollars": round(shares * dist, 2),
    }


def build_reason(r, info):
    bits = [r.setup_note]
    bits.append(f"3-mo return {r.ret63:+.0%} (stronger than {r.rs:.0f}% of the universe vs S&P)")
    if r.Close > r.sma50 > r.sma200:
        bits.append("above rising 50 & 200-day averages")
    bits += list(r.fund_notes)[:2]
    if info and info.get("target_mean") and r.Close:
        up = info["target_mean"] / r.Close - 1
        bits.append(f"analyst mean target {up:+.0%} away")
    return bits


def rank_and_bucket(feats, funds, regime, cfg, equity, cash, open_tickers, today,
                    halted=False):
    spy = feats["SPY"].iloc[-1]
    snap = snapshot(feats)
    scored = score_snapshot(snap, spy.ret63, sector_strength(feats), funds, cfg)

    open_sectors = pd.Series([UNIVERSE.get(t, "?") for t in open_tickers]).value_counts().to_dict()
    slots = min(cfg["max_positions"] - len(open_tickers), regime["max_new"])
    buys, backups, watch, extended, avoid = [], [], [], [], []
    spendable = cash - equity * cfg["min_cash_pct"] / 100

    for t, r in scored.iterrows():
        info = (funds or {}).get(t) or {}
        er = info.get("next_earnings")
        er_days = trading_days_between(today, dt.date.fromisoformat(er)) if er else None
        base = {"ticker": t, "name": info.get("name", t), "sector": r.sector,
                "price": round(float(r.Close), 2), "score": round(float(r.composite), 1),
                "momentum": round(float(r.momentum)), "rs": round(float(r.rs)),
                "trend": round(float(r.trend)), "fund": round(float(r.fund)),
                "setup": r.setup, "rsi": round(float(r.rsi)),
                "fwd_pe": info.get("forward_pe"), "next_earnings": er,
                "reason": build_reason(r, info)}
        if t in open_tickers:
            continue
        if not r.eligible:
            base["why_not"] = "below 200-day average / illiquid"
            avoid.append(base); continue
        if er_days is not None and er_days <= 4:
            base["why_not"] = f"earnings in {er_days} trading days (gap risk)"
            avoid.append(base); continue
        if r.setup == "extended":
            base["action"] = f"Wait for a pullback toward {r.ema20:.2f} (20-EMA)"
            extended.append(base); continue

        grade_ok = r.composite >= cfg["buy_score_threshold"]
        if regime["light"] == "YELLOW":
            grade_ok = r.composite >= cfg["buy_score_threshold"] + 7
        if r.triggered and grade_ok and not halted and regime["light"] != "RED":
            plan = make_plan(r, r.setup, equity, spendable, cfg, regime["risk_mult"], today, er)
            if plan["hold_days"] < 3:
                base["why_not"] = "earnings too close to hold"
                avoid.append(base); continue
            base.update(plan)
            sector_full = open_sectors.get(r.sector, 0) >= cfg["max_per_sector"]
            if len(buys) < slots and not sector_full and plan["shares"] > 0:
                buys.append(base)
                open_sectors[r.sector] = open_sectors.get(r.sector, 0) + 1
                spendable -= plan["dollars"]
            else:
                backups.append(base)
        elif r.composite >= cfg["watch_score_threshold"] and r.setup in ("pullback", "breakout"):
            if r.setup == "breakout":
                base["action"] = f"Buy if it closes above {r.hi20_prev:.2f} on strong volume"
            else:
                base["action"] = f"Buy on a green day holding above {r.ema20:.2f}"
            watch.append(base)
    return {"buys": buys, "backups": backups[:5], "watch": watch[:10],
            "extended": extended[:8], "avoid": avoid[:10],
            "ranking": _ranking_table(scored, funds)}


def _ranking_table(scored, funds):
    rows = []
    for t, r in scored.head(40).iterrows():
        info = (funds or {}).get(t) or {}
        rows.append({"ticker": t, "sector": r.sector, "score": round(float(r.composite), 1),
                     "price": round(float(r.Close), 2), "ret21": round(float(r.ret21) * 100, 1),
                     "ret63": round(float(r.ret63) * 100, 1), "rsi": round(float(r.rsi)),
                     "setup": r.setup, "triggered": bool(r.triggered),
                     "eligible": bool(r.eligible), "fwd_pe": info.get("forward_pe"),
                     "next_earnings": info.get("next_earnings")})
    return rows


# ---------------------------------------------------------------- momentum rotation mode
def is_rebalance_day(today, last_rebalance):
    """First trading day of a new ISO week (normally Monday)."""
    if not last_rebalance:
        return True
    return today.isocalendar()[:2] != dt.date.fromisoformat(last_rebalance).isocalendar()[:2]


def momentum_plan(feats, funds, regime, cfg, equity, cash, holdings, today, rebalance):
    """Risk-adjusted momentum rotation (research variant R2).

    Each week hold the top-N eligible names ranked by momentum / volatility.
    Sell anything that drops out of the top-N; 10% hard stop checked daily.
    """
    spy = feats["SPY"].iloc[-1]
    snap = snapshot(feats)
    sc = score_snapshot(snap, spy.ret63, sector_strength(feats), funds, cfg)
    mom = 0.5 * sc.ret126 + 0.3 * sc.ret63 + 0.2 * sc.ret21
    sc["risk_adj_mom"] = mom / (sc.atr / sc.Close)
    n = cfg["max_positions"]
    ok = sc.eligible & (sc.rsi < 80)
    ranked = sc[ok].sort_values("risk_adj_mom", ascending=False)
    target = [] if regime["light"] == "RED" else list(ranked.head(n).index)

    rotate_out = [t for t in holdings if rebalance and t not in target]
    buys, avoid = [], []
    if rebalance and regime["light"] != "RED":
        keep = [t for t in holdings if t in target]
        new = [t for t in target if t not in holdings]
        spendable = cash + sum(holdings[t] for t in rotate_out) - equity * cfg["min_cash_pct"] / 100
        per = min(spendable / max(len(new), 1), equity / n) if new else 0
        for t in new:
            r = sc.loc[t]
            info = (funds or {}).get(t) or {}
            er = info.get("next_earnings")
            if er and trading_days_between(today, dt.date.fromisoformat(er)) <= 3:
                avoid.append({"ticker": t, "why_not": f"earnings {er}: wait until after the report"})
                continue
            entry, a = float(r.Close), float(r.atr)
            shares = per / entry
            shares = round(shares, 2) if cfg.get("fractional_shares") else float(int(shares))
            stop = entry * (1 - cfg.get("momentum_stop_pct", 10) / 100)
            wk = a * 5 ** 0.5  # typical one-week move
            review = add_trading_days(today, 5)
            buys.append({
                "ticker": t, "name": info.get("name", t), "sector": r.sector, "price": round(entry, 2),
                "score": round(float(r.composite), 1), "momentum": round(float(r.momentum)),
                "rs": round(float(r.rs)), "trend": round(float(r.trend)), "fund": round(float(r.fund)),
                "rsi": round(float(r.rsi)), "setup": "momentum", "fwd_pe": info.get("forward_pe"),
                "next_earnings": er, "entry": round(entry, 2), "limit": round(entry * 1.005, 2),
                "stop": round(stop, 2), "t1": round(entry + wk, 2), "t2": round(entry + 2 * wk, 2),
                "stop_pct": round((stop / entry - 1) * 100, 1), "t1_pct": round(wk / entry * 100, 1),
                "t2_pct": round(2 * wk / entry * 100, 1), "hold_days": 60,
                "sell_by": f"reviewed {review.isoformat()}", "shares": shares,
                "dollars": round(shares * entry, 2), "risk_dollars": round(shares * (entry - stop), 2),
                "reason": [
                    f"#{list(ranked.index).index(t) + 1} on risk-adjusted momentum: 6-mo {r.ret126:+.0%}, 3-mo {r.ret63:+.0%}, 1-mo {r.ret21:+.0%}",
                    f"stronger than {r.rs:.0f}% of the universe vs the S&P; above its 200-day average",
                ] + list(r.fund_notes)[:1],
            })
        if keep:
            avoid.append({"ticker": ", ".join(keep), "why_not": "already held and still top-ranked: keep"})
    next_up = [{"ticker": t, "score": round(float(ranked.loc[t].risk_adj_mom), 1), "price": round(float(ranked.loc[t].Close), 2),
                "setup": "momentum", "rsi": round(float(ranked.loc[t].rsi)),
                "action": "next in line if a holding drops out"} for t in ranked.index[n:n + 5]]
    return {"buys": buys, "backups": [], "watch": next_up, "extended": [], "avoid": avoid,
            "rotate_out": rotate_out, "target": target, "rebalance": rebalance,
            "ranking": _ranking_table(sc.loc[ranked.index], funds)}
