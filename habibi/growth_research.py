"""Growth-engine research: core index + active weekly stock/ETF picks, tested honestly.

Differences from research.py (which assumed you buy at the signal day's close):
  * Signals use Friday's close; orders fill at the NEXT trading day's OPEN (how you trade).
  * 0.1% cost on every buy and sell (spread; USD account, no FX fee).
  * Results on two halves of history, so a rule must work on data it was not tuned on.
  * Outcomes measured on 3- and 6-month windows (the horizon we care about now).

Account = core_frac in SPY (rebalanced quarterly) + the rest in the active sleeve.

  python -m habibi.growth_research      # writes habibi/output/growth_research.json
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import adaptive, data
from .indicators import add_features
from .research import precompute
from .universe import SECTOR_ETF, UNIVERSE

OUT = Path(__file__).parent / "output"
ETF_SECTORS = {"Gold", "Intl"}


def bucket(t):
    """Sector bucket for the per-sector cap: chips and tech ETFs count as tech."""
    from .growth import cap_bucket
    return cap_bucket(t)


def is_etf(t):
    return t in set(SECTOR_ETF.values()) | {"GLD", "EFA", "EEM", "QQQ", "SPY", "IWM", "SMH"}


# ------------------------------------------------------------------ active sleeve
def active_sim(feats, pre, dates, p):
    """Weekly-rebalanced active sleeve. Returns (equity Series, trades list)."""
    cost = p.get("cost", 0.001)
    cash, hold, curve, trades = 1.0, {}, [], []
    below = {}  # ticker -> consecutive weekly closes below its 50-day
    out_wk = {}  # ticker -> consecutive weekly reviews ranked outside hold_rank
    pending = None  # orders decided at a signal close, filled at next open

    def px(t, d, field="Close"):
        f = feats[t]
        if d in f.index:
            return float(f.loc[d, field])
        return float(f.Close.loc[:d].iloc[-1])

    def sell(t, price, why, frac=1.0):
        nonlocal cash
        h = hold[t]
        sh = h["sh"] * frac
        cash += sh * price * (1 - cost)
        h["realized"] += sh * (price * (1 - cost)) - sh * h["entry"]
        h["sh"] -= sh
        if frac >= 1 or h["sh"] <= 1e-12:
            trades.append({"t": t, "ret": h["realized"] / (h["sh0"] * h["entry"]), "why": why})
            del hold[t]

    for i, d in enumerate(dates):
        # 1) fill yesterday's decisions at today's open
        if pending:
            for t in pending["sell"]:
                if t in hold:
                    sell(t, px(t, d, "Open"), pending["why"].get(t, "rotate"))
            eq_open = cash + sum(h["sh"] * px(t, d, "Open") for t, h in hold.items())
            for t, w in pending["buy"]:
                if t in hold:
                    continue
                o = px(t, d, "Open")
                amt = min(w * eq_open, cash)
                if amt < 0.02 * eq_open:
                    continue
                sh = amt * (1 - cost) / o
                cash -= amt
                a = pending["atr"][t]
                stop = o - p["stop_atr"] * a if p.get("stop_atr") else None
                if p.get("stop_floor") and stop is not None:
                    stop = max(stop, o * (1 - p["stop_floor"]))
                hold[t] = {"sh": sh, "sh0": sh, "entry": o, "stop": stop, "atr": a, "hi": o,
                           "half": False, "realized": 0.0}
            pending = None
        # 2) daily risk checks on today's bar
        for t in list(hold):
            f = feats[t]
            if d not in f.index:
                continue
            b = f.loc[d]
            h = hold[t]
            if h["stop"] is not None and b.Low <= h["stop"]:
                sell(t, min(h["stop"], float(b.Open)), "stop")
                continue
            pt = p.get("profit_take")
            if pt and not h["half"] and b.High >= h["entry"] * (1 + pt):
                sell(t, max(h["entry"] * (1 + pt), float(b.Open)), "profit", frac=0.5)
                if t in hold:
                    h["half"] = True
                    h["stop"] = max(h["stop"] or 0, h["entry"])
            if t in hold:
                h["hi"] = max(h["hi"], float(b.Close))
                if h["half"] and p.get("trail_atr"):
                    h["stop"] = max(h["stop"] or 0, h["hi"] - p["trail_atr"] * h["atr"])
        equity = cash + sum(h["sh"] * px(t, d) for t, h in hold.items())
        curve.append((d, equity))

        # 3) weekly decision at the last close of the week; fills next open
        nxt = dates[i + 1] if i + 1 < len(dates) else None
        if nxt is None or nxt.isocalendar()[1] == d.isocalendar()[1]:
            continue
        regime, sc = pre[d]
        ok = sc.eligible & (sc.rsi < p.get("max_rsi", 80)) & sc[p["rank_col"]].notna()
        if not p.get("etfs", True):
            ok &= ~pd.Series([is_etf(t) for t in sc.index], index=sc.index)
        if p.get("etfs_only"):
            ok &= pd.Series([is_etf(t) for t in sc.index], index=sc.index)
        if p.get("excluded"):
            ok &= ~sc.index.isin(p["excluded"])
        ranked = sc[ok].sort_values(p["rank_col"], ascending=False)
        order = list(ranked.index)
        sells, why = set(), {}
        # trend exit: N consecutive weekly closes below the 50-day (or below the 200-day)
        for t in hold:
            if t not in sc.index:
                continue
            r = sc.loc[t]
            if p.get("trend_exit") == "sma50x2":
                below[t] = below.get(t, 0) + 1 if r.Close < r.sma50 else 0
                if below[t] >= 2:
                    sells.add(t); why[t] = "trend"
            elif p.get("trend_exit") == "sma200" and not r.eligible:
                sells.add(t); why[t] = "trend"
        if regime == "RED" and p.get("red_to_cash"):
            sells |= set(hold); why.update({t: "regime" for t in hold})
        hold_rank = p.get("hold_rank", p["top_n"])
        hold_order = order
        if p.get("hold_ignores_rsi"):
            okh = sc.eligible & sc[p["rank_col"]].notna()
            if p.get("excluded"):
                okh &= ~sc.index.isin(p["excluded"])
            hold_order = list(sc[okh].sort_values(p["rank_col"], ascending=False).index)
        for t in hold:
            if t not in hold_order[:hold_rank]:
                out_wk[t] = out_wk.get(t, 0) + 1
                if out_wk[t] >= p.get("exit_confirm", 1):
                    sells.add(t); why.setdefault(t, "rotate")
            else:
                out_wk[t] = 0
        keep = [t for t in hold if t not in sells]
        buys = []
        if not (regime == "RED" and p.get("no_buys_red", True)):
            sectors = pd.Series([bucket(t) for t in keep]).value_counts().to_dict()
            for t in order:
                if len(keep) + len(buys) >= p["top_n"]:
                    break
                if t in hold:
                    continue
                s = bucket(t)
                from .growth import fits_caps
                if not fits_caps(t, sectors, p.get("max_per_sector", 2), p.get("tech_like_max", 2)):
                    continue
                sectors[s] = sectors.get(s, 0) + 1
                buys.append(t)
        if buys:
            ymult = 0.5 if (p.get("yellow_half") and regime == "YELLOW") else 1.0
            if p.get("sizing") == "invvol":
                iv = {t: 1 / max(float(ranked.loc[t].atr / ranked.loc[t].Close), 1e-4) for t in buys}
                avg = sum(iv.values()) / len(iv)
                w = {t: ymult * min(iv[t] / avg / p["top_n"], p.get("pos_cap", 0.30)) for t in buys}
            else:
                w = {t: ymult / p["top_n"] for t in buys}
        pending = {"sell": sells, "why": why, "buy": [(t, w[t]) for t in buys] if buys else [],
                   "atr": {t: float(ranked.loc[t].atr) for t in buys}}
    return pd.Series([e for _, e in curve], index=[d for d, _ in curve]), trades


def combine(active, spy_close, core_frac):
    """core_frac in SPY + rest in the active sleeve, rebalanced every quarter."""
    spy = spy_close.reindex(active.index).ffill()
    eq, core, act = [], core_frac, 1 - core_frac
    last_q = None
    prev_a, prev_s = active.iloc[0], spy.iloc[0]
    for d in active.index:
        core *= spy.loc[d] / prev_s
        act *= active.loc[d] / prev_a
        prev_a, prev_s = active.loc[d], spy.loc[d]
        q = (d.year, (d.month - 1) // 3)
        if last_q is not None and q != last_q:
            tot = core + act
            core, act = tot * core_frac, tot * (1 - core_frac)
        last_q = q
        eq.append(core + act)
    return pd.Series(eq, index=active.index)


def stats(eq, trades=None):
    dd = float((eq / eq.cummax() - 1).min())
    out = {"total_pct": round(float(eq.iloc[-1] / eq.iloc[0] - 1) * 100, 1),
           "max_dd_pct": round(dd * 100, 1)}
    for n, lab in ((63, "3m"), (126, "6m")):
        w = (eq.shift(-n) / eq - 1).dropna()
        if len(w):
            out.update({f"p{lab}_gain10": round(float((w >= 0.10).mean() * 100), 1),
                        f"p{lab}_gain20": round(float((w >= 0.20).mean() * 100), 1),
                        f"p{lab}_loss": round(float((w < 0).mean() * 100), 1),
                        f"med{lab}": round(float(w.median() * 100), 1),
                        f"worst{lab}": round(float(w.min() * 100), 1)})
    if trades is not None:
        tr = pd.DataFrame(trades)
        out["trades"] = int(len(tr))
        if len(tr):
            out["win_rate"] = round(float((tr.ret > 0).mean() * 100), 1)
            out["exits"] = tr.why.value_counts().to_dict()
    return out


BASE = dict(rank_col="adaptive", top_n=5, hold_rank=12, max_per_sector=2, stop_atr=3.0,
            stop_floor=0.30, trend_exit="sma50x2", profit_take=0.25, trail_atr=3.0,
            sizing="invvol", pos_cap=0.30, etfs=True, cost=0.001)

VARIANTS = {
    "G0 base: learning model top5, sector cap 2, 3xATR stop, 2-week trend exit, half at +25%": {},
    "G1 no profit-take": dict(profit_take=None),
    "G2 profit-take at +15%": dict(profit_take=0.15),
    "G3 tighter: 2xATR stop": dict(stop_atr=2.0),
    "G4 wider: 4xATR stop": dict(stop_atr=4.0),
    "G5 no trend exit (stop + rank only)": dict(trend_exit=None),
    "G6 exit only below 200-day": dict(trend_exit="sma200"),
    "G7 hold buffer top-8": dict(hold_rank=8),
    "G8 hold buffer top-20": dict(hold_rank=20),
    "G9 top 4": dict(top_n=4),
    "G10 top 6": dict(top_n=6),
    "G11 equal weight": dict(sizing="equal"),
    "G12 stocks only (no ETFs)": dict(etfs=False),
    "G13 rank: risk-adjusted momentum": dict(rank_col="risk_adj_mom"),
    "G14 rank: multi-factor composite (incl. sector tilt)": dict(rank_col="composite"),
    "G15 rank: learning model + sector/macro tilt": dict(rank_col="blend"),
    "G16 RED market -> active sleeve to cash": dict(red_to_cash=True),
    "G17 old style: top3, no stop, rank-only exits, equal weight": dict(top_n=3, hold_rank=5, stop_atr=None,
                                                                        stop_floor=None, trend_exit=None,
                                                                        profit_take=None, sizing="equal"),
}
R = dict(rank_col="risk_adj_mom")
VARIANTS.update({
    "R1 risk-adj: no profit-take": dict(R, profit_take=None),
    "R2 risk-adj: no trend exit": dict(R, trend_exit=None),
    "R3 risk-adj: no profit-take, no trend exit": dict(R, profit_take=None, trend_exit=None),
    "R4 risk-adj: top 4": dict(R, top_n=4),
    "R5 risk-adj: top 4, no profit-take": dict(R, top_n=4, profit_take=None),
    "R6 risk-adj: hold buffer top-8": dict(R, hold_rank=8),
    "R7 risk-adj: hold buffer top-15": dict(R, hold_rank=15),
    "R8 risk-adj: stocks only": dict(R, etfs=False),
    "R9 risk-adj: 4xATR stop": dict(R, stop_atr=4.0),
    "R10 risk-adj: 2.5xATR stop": dict(R, stop_atr=2.5),
    "R11 risk-adj: 0.5% cost each way (stress)": dict(R, cost=0.005),
    "R12 risk-adj: profit-take at +35%": dict(R, profit_take=0.35),
    "R13 risk-adj: equal weight": dict(R, sizing="equal"),
    "R14 risk-adj: max 1 per sector": dict(R, max_per_sector=1),
    "R15 risk-adj: RED market -> cash": dict(R, red_to_cash=True),
    "R16 risk-adj: top 6": dict(R, top_n=6),
    "R17 risk-adj: no stop at all": dict(R, stop_atr=None, stop_floor=None),
    "S0 risk-adj, top5, hold top-8, 3xATR stop, half at +25%, trend exit, tech max 2": dict(R, hold_rank=8),
    "S1 CHOSEN minus the 15 biggest winners (hindsight-bias check)": dict(R, hold_rank=8, exclude_winners=15),
    "S2 CHOSEN minus the 30 biggest winners (harsher check)": dict(R, hold_rank=8, exclude_winners=30),
    "S3 sector/asset ETFs only, top 3": dict(R, hold_rank=5, top_n=3, etfs_only=True),
    "S4 S0 + holds ranked without the RSI filter": dict(R, hold_rank=8, hold_ignores_rsi=True),
    "S5 S0 + rank exit needs 2 weekly reviews in a row": dict(R, hold_rank=8, exit_confirm=2),
    "S6 S0 + both (no-RSI holds, 2-week rank exit)": dict(R, hold_rank=8, hold_ignores_rsi=True, exit_confirm=2),
    "S7 S6 minus the 15 biggest winners": dict(R, hold_rank=8, hold_ignores_rsi=True, exit_confirm=2, exclude_winners=15),
    "S8 S6 + YELLOW market = half-size new buys": dict(R, hold_rank=8, hold_ignores_rsi=True, exit_confirm=2, yellow_half=True),
    "T2 S0, tech+chips max 2 combined": dict(R, hold_rank=8, tech_like_max=2),
    "T3 CHOSEN: S0 with tech+chips max 3 combined (2 per sector)": dict(R, hold_rank=8, tech_like_max=3),
    "T4 S0, tech+chips max 4 (2 software + 2 chips)": dict(R, hold_rank=8, tech_like_max=4),
    "T3x T3 minus the 15 biggest winners": dict(R, hold_rank=8, tech_like_max=3, exclude_winners=15),
    "T4x T4 minus the 15 biggest winners": dict(R, hold_rank=8, tech_like_max=4, exclude_winners=15),
    "T3e T3 stocks only (no ETFs)": dict(R, hold_rank=8, tech_like_max=3, etfs=False),
})


def main():
    tickers = sorted(set(UNIVERSE) | set(SECTOR_ETF.values()) | {"^VIX", "SPY", "QQQ"})
    prices = data.download_prices(tickers, period="3y")
    feats = {t: add_features(df) for t, df in prices.items()}
    pre = precompute(feats, 500)
    uni = [t for t in UNIVERSE if t in feats and len(feats[t]) > 260]
    m = adaptive.model(feats, uni)
    for d, (regime, sc) in pre.items():
        sc["adaptive"] = m["scores"].loc[d].reindex(sc.index) if d in m["scores"].index else np.nan
        # learning-model rank blended with sector strength (where money is rotating = the macro tide)
        sub = {t: f.loc[:d] for t, f in feats.items() if t in set(SECTOR_ETF.values())}
        from .strategy import sector_strength
        sr = sector_strength(sub)
        sec = pd.Series([sr.get(UNIVERSE.get(t, "?"), 0.5) for t in sc.index], index=sc.index)
        sc["blend"] = 0.75 * sc["adaptive"].rank(pct=True) + 0.25 * sec
    dates = [d for d in pre]
    mid = dates[len(dates) // 2]
    periods = {"full": dates, "half1": [d for d in dates if d <= mid], "half2": [d for d in dates if d >= mid]}
    spy = feats["SPY"].Close
    res = {"periods": {k: [str(v[0].date()), str(v[-1].date())] for k, v in periods.items()},
           "notes": "signal at Friday close, fill next open, 0.1% cost each way; account = core SPY + active",
           "results": {}}
    d0, d1 = dates[0], dates[-1]
    total = {t: float(feats[t].Close.loc[d1] / feats[t].Close.loc[:d0].iloc[-1] - 1)
             for t in UNIVERSE if t in feats and d1 in feats[t].index and len(feats[t].Close.loc[:d0])}
    winners = sorted(total, key=total.get, reverse=True)
    res["biggest_winners"] = {t: round(total[t] * 100) for t in winners[:30]}
    for name, over in VARIANTS.items():
        p = {**BASE, **over}
        if p.get("exclude_winners"):
            p["excluded"] = set(winners[:p["exclude_winners"]])
        row = {}
        for k, ds in periods.items():
            act, tr = active_sim(feats, pre, ds, p)
            row[k] = {"active_only": stats(act, tr),
                      "20_80": stats(combine(act, spy, 0.20)),
                      "30_70": stats(combine(act, spy, 0.30)),
                      "40_60": stats(combine(act, spy, 0.40))}
        res["results"][name] = row
        print(name, row["full"]["30_70"], flush=True)
    res["results"]["Z buy & hold SPY"] = {k: {"20_80": stats(spy.reindex(ds).ffill()), "30_70": stats(spy.reindex(ds).ffill())}
                                         for k, ds in periods.items()}
    res["results"]["Z buy & hold QQQ"] = {k: {"20_80": stats(feats["QQQ"].Close.reindex(ds).ffill()),
                                             "30_70": stats(feats["QQQ"].Close.reindex(ds).ffill())}
                                         for k, ds in periods.items()}
    OUT.mkdir(exist_ok=True)
    (OUT / "growth_research.json").write_text(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
