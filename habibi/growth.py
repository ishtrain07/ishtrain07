"""Growth engine: a small index core plus an active weekly portfolio of stocks and sector ETFs.

  * Core: cfg["core"]["ticker"] (VOO), cfg["core"]["pct"] of the account. Never traded on bad days;
    brought back to target at quarterly rebalances.
  * Active: the rest. Reviewed once a week (the first plan run of the ISO week, i.e. Monday).
      - rank by risk-adjusted momentum (tested best on next-open fills, both halves of history)
      - buy the top N, max K per sector (sector ETFs count as their sector)
      - keep a holding while it ranks within hold_rank (a buffer that cuts churn)
      - size by inverse volatility, capped per position
      - emergency stop: entry - stop_atr x ATR (never more than stop_floor below entry)
      - optional profit-take (sell half) and 2-week trend exit
  * Cash is deployed in batches over the first weeks (cfg["deploy"]).
  * Every holding's daily move is split into "market" (beta x S&P 500) and "stock-specific",
    so a drop that is just the market falling is never treated as a reason to sell.

All decisions use the latest close; orders are placed at the next open (the backtest assumes the same).
"""
import datetime as dt

import numpy as np
import pandas as pd

from .strategy import (add_trading_days, fundamental_score, quality_gate, score_snapshot, sector_strength, snapshot,
                       trading_days_between, _ranking_table)
from .universe import SECTOR_ETF, UNIVERSE

ETFS = set(SECTOR_ETF.values()) | {"GLD", "EFA", "EEM", "QQQ", "SPY", "IWM", "SMH", "VOO", "VTI"}
SECTOR_NAMES = {"Tech": "Technology", "Semis": "Chips", "Comm": "Communication", "ConsDisc": "Consumer (discretionary)",
                "ConsStap": "Consumer staples", "Financials": "Financials", "Health": "Healthcare",
                "Industrials": "Industrials", "Energy": "Energy", "Utilities": "Utilities", "Materials": "Materials",
                "Gold": "Gold", "Intl": "International"}
# Concentration limits: at most max_per_sector names per sector (chips and software are separate sectors),
# and at most tech_like_max names across tech + chips + tech/Nasdaq funds combined.
ETF_BUCKET = {"SMH": "Semis", "QQQ": "Tech", "XLK": "Tech", "SPY": "Broad", "IWM": "Broad", "VOO": "Broad", "VTI": "Broad"}
TECH_LIKE = {"Tech", "Semis"}


def cap_bucket(t):
    return ETF_BUCKET.get(t) or UNIVERSE.get(t, "?")


def fits_caps(t, counts, max_per_sector, tech_like_max):
    """counts: {bucket: n} of names already kept/bought. True if adding t stays within both limits."""
    b = cap_bucket(t)
    if counts.get(b, 0) >= max_per_sector:
        return False
    if b in TECH_LIKE and tech_like_max is not None and sum(counts.get(x, 0) for x in TECH_LIKE) >= tech_like_max:
        return False
    return True


HEAT_ETFS = {**{k: v for k, v in SECTOR_ETF.items() if k != "ETF"}, "Gold": "GLD", "Intl": "EFA"}

LESSONS = [
    ("Diversify the bets", "Our first three picks were all tech, so one bad day for tech hit everything at once. "
                           "The new rules allow at most {max_per_sector} holdings per sector and at most {tech_like_max} across tech and chips combined."),
    ("Market move vs stock move", "If the whole market falls 3% and your stock falls 4%, only about 1% is about the company. "
                                  "A holding is only sold at the weekly review if it has ranked outside the top {hold_rank} for "
                                  "{exit_confirm} reviews in a row, or its trend is broken - one bad market week is not enough."),
    ("Position sizing", "Jumpy stocks get a smaller dollar amount so each holding can hurt the account about the same. "
                        "That lets us own volatile winners without one of them sinking the account."),
    ("Why a weekly review", "Checking prices three times a day invites panic. Trends play out over weeks; a weekly decision "
                            "on Friday's close, placed at Monday's open, is calmer and tested better."),
    ("Momentum, adjusted for risk", "We rank by how much a stock has gained over 6, 3 and 1 months divided by how much it "
                                    "normally swings. Steady climbers rank above lottery tickets."),
    ("The hold buffer", "We buy names in the top {top_n} but keep them until they fall out of the top {hold_rank}. "
                        "That stops us from selling a good holding just because it slipped a few places for a week."),
    ("Stops are insurance, not predictions", "The emergency stop sits about {stop_atr:.0f} normal daily swings below the entry. "
                                             "It is there for disasters, so it should rarely fire."),
    ("Cash in batches", "Putting money in over {batches} weeks means one unlucky entry day cannot hurt much. "
                        "It costs a little upside when markets rise, and saves a lot of regret when they fall."),
    ("Sector rotation", "Money moves between sectors as the economy shifts. Falling interest rates tend to help tech and "
                        "utilities; rising oil helps energy. The sector heat map shows where the money is going."),
    ("Taxes and the TFSA", "Gains in a TFSA are tax free, and losses give no tax benefit. So we never sell just to "
                           "'harvest' a loss, and never hold a loser just to avoid admitting it."),
]

GLOSSARY = [
    ("Momentum", "How much a price has risen over recent months. Winners tend to keep winning for a while."),
    ("ATR", "Average True Range: the size of a normal day's move, in dollars. Used to set stops and sizes."),
    ("Stop", "A pre-set price where we sell to cap the damage if something goes badly wrong."),
    ("50-day / 200-day average", "The average price over the last 50 / 200 trading days. Above = uptrend."),
    ("Beta", "How much a stock usually moves when the S&P 500 moves 1%. Beta 1.5 = moves about 1.5%."),
    ("Rebalance", "Bringing each part of the account back to its target share."),
    ("Sector ETF", "One fund that holds a whole sector (e.g. XLE = US energy companies)."),
    ("CDR", "Canadian Depositary Receipt: a CAD-priced, currency-hedged version of a US stock on the Canadian exchange."),
    ("Drawdown", "How far the account is below its highest value."),
    ("VIX", "The market's 'fear gauge'. Below 20 is calm; above 28 is stressed."),
]

# Large US names with a Canadian Depositary Receipt (CAD-hedged) at the time of writing; verify on Cboe Canada.
CDR = {"AAPL", "AMZN", "AMD", "AVGO", "BRK-B", "COST", "CRM", "CRWD", "CVX", "DIS", "GOOGL", "GS", "HD", "IBM", "INTC",
       "JNJ", "JPM", "KO", "LLY", "MA", "MCD", "META", "MSFT", "NFLX", "NKE", "NVDA", "ORCL", "PEP", "PFE", "PG", "PYPL",
       "SBUX", "SHOP", "TSLA", "UBER", "UNH", "V", "VZ", "WMT", "XOM", "ABBV", "AMAT", "BAC", "CAT", "GE", "QCOM",
       "SNOW", "PLTR", "UPS", "MU", "NOW", "ADBE", "ISRG", "BKNG", "ANET"}
CAD_HEDGED_CORE = "VSP (Vanguard S&P 500, CAD-hedged) or ZUE (BMO S&P 500, CAD-hedged)"


# ------------------------------------------------------------------ helpers
def _day_move(f, today, px=None):
    """Latest session move in %: today's live price (if the bar is today's) vs the prior close."""
    c = f.Close
    last = float(px) if (px is not None and c.index[-1].date() == today) else float(c.iloc[-1])
    return (last / float(c.iloc[-2]) - 1) * 100


def beta(feats, t, n=120):
    f, s = feats.get(t), feats.get("SPY")
    if f is None or s is None:
        return 1.0
    r = f.Close.pct_change().tail(n)
    m = s.Close.pct_change().reindex(r.index)
    ok = r.notna() & m.notna()
    if ok.sum() < 30 or m[ok].var() == 0:
        return 1.0
    return float(np.clip(np.cov(r[ok], m[ok])[0, 1] / m[ok].var(), 0.2, 3.0))


def market_vs_stock(feats, t, today, live=None):
    """Split the latest daily and 5-day move into market (beta x SPY) and stock-specific parts."""
    f, s = feats.get(t), feats.get("SPY")
    if f is None or s is None or len(f) < 10:
        return None
    b = beta(feats, t)
    d_stock = _day_move(f, today, (live or {}).get(t))
    d_spy = _day_move(s, today, (live or {}).get("SPY"))
    w_stock = (float((live or {}).get(t, f.Close.iloc[-1])) / float(f.Close.iloc[-6]) - 1) * 100
    w_spy = (float((live or {}).get("SPY", s.Close.iloc[-1])) / float(s.Close.iloc[-6]) - 1) * 100
    mkt_d, mkt_w = b * d_spy, b * w_spy
    spec_d, spec_w = d_stock - mkt_d, w_stock - mkt_w
    sd = float(f.Close.pct_change().tail(60).std() * 100) or 1.0
    if spec_d < -2.5 * sd:
        verdict = "stock-specific drop: check the news"
    elif abs(spec_d) <= max(1.0, 0.75 * sd):
        verdict = "moving with the market"
    elif spec_d > 0:
        verdict = "stronger than the market"
    else:
        verdict = "a bit weaker than the market"
    return {"beta": round(b, 2), "day_pct": round(d_stock, 2), "day_market_pct": round(mkt_d, 2),
            "day_specific_pct": round(spec_d, 2), "week_pct": round(w_stock, 2), "week_market_pct": round(mkt_w, 2),
            "week_specific_pct": round(spec_w, 2), "verdict": verdict}


def sector_heat(feats):
    rows = []
    for sec, etf in HEAT_ETFS.items():
        f = feats.get(etf)
        if f is None or len(f) < 70:
            continue
        r = f.iloc[-1]
        c = f.Close
        rows.append({"sector": SECTOR_NAMES.get(sec, sec), "key": sec, "etf": etf,
                     "d1": round(float(c.iloc[-1] / c.iloc[-2] - 1) * 100, 2),
                     "w1": round(float(c.iloc[-1] / c.iloc[-6] - 1) * 100, 2),
                     "m1": round(float(r.ret21) * 100, 1), "m3": round(float(r.ret63) * 100, 1),
                     "trend": "up" if r.Close > r.sma50 > r.sma200 else "down" if r.Close < r.sma200 else "mixed"})
    rows.sort(key=lambda x: -(0.5 * x["m1"] + 0.5 * x["m3"]))
    for i, x in enumerate(rows, 1):
        x["rank"] = i
    return rows


def macro_tilts(macro, heat):
    """Plain-English read of what the macro backdrop favours, cross-checked with where money is moving."""
    m = {r["ticker"]: r for r in macro}
    lead = [h["sector"] for h in heat[:3]]
    lag = [h["sector"] for h in heat[-3:]]
    notes = [f"Money is flowing into {', '.join(lead)} and out of {', '.join(lag)} (1- and 3-month sector returns)."]
    if "^TNX" in m:
        ch = m["^TNX"]["m1"]
        if ch < -3:
            notes.append("Falling long-term rates usually help growth stocks, utilities and real-asset sectors.")
        elif ch > 3:
            notes.append("Rising long-term rates usually pressure expensive growth stocks and favour banks and value.")
    if "CL=F" in m and abs(m["CL=F"]["m1"]) > 5:
        notes.append(f"Oil {m['CL=F']['m1']:+.0f}% over a month: " +
                     ("supports energy stocks, a headwind for airlines and consumers." if m["CL=F"]["m1"] > 0
                      else "a headwind for energy stocks, relief for consumers and transport."))
    if "DX-Y.NYB" in m and abs(m["DX-Y.NYB"]["m1"]) > 1.5:
        notes.append("A weaker dollar helps international stocks, gold and materials." if m["DX-Y.NYB"]["m1"] < 0
                     else "A stronger dollar is a headwind for international stocks, gold and US multinationals.")
    if "^VIX" in m and m["^VIX"]["last"] >= 24:
        notes.append("Fear is elevated: expect bigger daily swings. The ranking already favours steadier names "
                     "(gains are divided by volatility); new buys stop only if the market light turns RED.")
    if "USDCAD=X" in m:
        notes.append(f"USD/CAD {m['USDCAD=X']['last']:.2f} ({m['USDCAD=X']['m1']:+.1f}% over a month): new CAD money is "
                     f"best put into CAD-hedged versions (CDRs, {CAD_HEDGED_CORE.split(' (')[0]}) to skip the FX fee.")
    return notes


def next_review(today):
    d = today + dt.timedelta(days=(7 - today.weekday()) % 7 or 7)
    return d.isoformat()


# ------------------------------------------------------------------ exits for held positions
def _atr_on(f, day):
    sub = f.loc[:pd.Timestamp(day)]
    return float(sub.atr.iloc[-1]) if len(sub) else float(f.atr.iloc[-1])


def anchor_stops(book, feats, cfg, state, key):
    """Each holding's emergency stop, fixed once and stored in state[key]['stops'].

    New positions: avg cost - stop_atr x ATR on the buy date (floored at -stop_floor).
    Positions bought before the growth engine started: re-anchored at the phase start (price - stop_atr x ATR),
    because the old 8% stops belonged to a different rulebook.
    """
    g = cfg["growth"]
    st = state.setdefault(key, {}).setdefault("stops", {})
    phase = dt.date.fromisoformat(cfg["phase_start"])
    held = {p["ticker"] for p in book["open"]}
    for t in list(st):
        if t not in held:
            del st[t]
    for p in book["open"]:
        t = p["ticker"]
        f = feats.get(t)
        if t == cfg["core"]["ticker"] or f is None:
            continue
        first = dt.date.fromisoformat(p["first_buy"])
        rec = st.get(t)
        if rec and rec.get("first_buy") == p["first_buy"]:
            continue
        if first < phase:
            base_px = float(f.Close.loc[:pd.Timestamp(phase - dt.timedelta(days=1))].iloc[-1])
            a = _atr_on(f, phase - dt.timedelta(days=1))
            anchor = "phase start"
        else:
            base_px, a, anchor = p["avg_cost"], _atr_on(f, first), "entry"
        stop = max(base_px - g["stop_atr"] * a, base_px * (1 - g["stop_floor_pct"] / 100))
        st[t] = {"stop": round(stop, 2), "atr": round(a, 2), "base": round(base_px, 2), "anchor": anchor,
                 "first_buy": p["first_buy"]}
    return st


def evaluate_growth(book, feats, live, funds, cfg, today, state, key="real"):
    """Price every position and set HOLD / SELL ALL / SELL HALF using the growth rules."""
    g = cfg["growth"]
    core = cfg["core"]["ticker"]
    stops = anchor_stops(book, feats, cfg, state, key)
    wk = state.get(key, {}).get("week") or {}
    same_week = bool(wk.get("date")) and dt.date.fromisoformat(wk["date"]).isocalendar()[:2] == today.isocalendar()[:2]
    week_sells = wk.get("sells", {}) if same_week else {}
    mv, alerts = 0.0, []
    for p in book["open"]:
        t = p["ticker"]
        f = feats.get(t)
        last = float(f.Close.iloc[-1]) if f is not None else p["avg_cost"]
        px = float((live or {}).get(t, last))
        stale = f is None or (today - f.index[-1].date()).days > 5
        p["data_warning"] = (f"no fresh price data for {t}: stop and P&L may be out of date" if stale else None)
        units = (cfg.get("cdr_holdings") or {}).get(t)
        if units:
            p["cdr_units"] = units
        p.update({"price": round(px, 2), "value": round(px * p["shares"], 2),
                  "pnl": round((px - p["avg_cost"]) * p["shares"], 2),
                  "pnl_pct": round((px / p["avg_cost"] - 1) * 100, 2),
                  "days_held": trading_days_between(dt.date.fromisoformat(p["first_buy"]), today),
                  "sleeve": "core" if t == core else "active", "cdr": t in CDR,
                  "split": market_vs_stock(feats, t, today, live) if f is not None else None})
        mv += p["value"]
        if t == core:
            p.update({"action": "HOLD", "why": "core index fund: held through ups and downs; topped up toward its target share from cash at weekly reviews",
                      "active_stop": None, "t1": None, "t2": None, "rule": "core"})
            continue
        rec = stops.get(t, {})
        stop = rec.get("stop")
        pt = g.get("profit_take_pct")
        target = round(p["avg_cost"] * (1 + pt / 100), 2) if pt else None
        if p.get("partial") and f is not None and g.get("trail_atr"):
            hi = float(f.Close.loc[pd.Timestamp(p["first_buy"]):].max())
            stop = max(stop or 0, p["avg_cost"], hi - g["trail_atr"] * float(f.atr.iloc[-1]))
        p["active_stop"], p["t1"], p["t2"] = (round(stop, 2) if stop else None), target, None
        p["stop_anchor"] = rec.get("anchor")
        if stop and px <= stop:
            act, why, rule = "SELL ALL", (f"emergency stop {stop:.2f} hit ({g['stop_atr']:.0f} normal daily swings below "
                                          f"the {rec.get('anchor', 'entry')} price)"), "stop"
        elif t in week_sells:
            act, why, rule = "SELL ALL", week_sells[t], "weekly review"
        elif target and px >= target and not p.get("partial"):
            act, why, rule = "SELL HALF", f"up {p['pnl_pct']:.0f}%: profit-take rule (sell half at +{pt:.0f}%, trail the rest)", "profit"
        else:
            act, rule = "HOLD", "hold"
            dist = (stop / px - 1) * 100 if stop else None
            why = (f"held while it ranks in the top {g['hold_rank']}; next review {next_review(today)}"
                   + (f"; emergency stop {stop:.2f} ({dist:+.0f}%)" if stop else "")
                   + (f"; take half at {target:.2f}" if target else ""))
        p.update({"action": act, "why": why, "rule": rule})
        if act != "HOLD":
            a = {"ticker": t, "action": act, "why": why, "price": p["price"], "rule": rule,
                 "shares": p["shares"] if act == "SELL ALL" else round(p["shares"] / 2, 4)}
            if units:
                n = units if act == "SELL ALL" else max(1, int(units // 2))
                a["units_note"] = f"you hold {units} {t} CDRs (CAD): sell {n} CDRs" + (" (all)" if act == "SELL ALL" else "")
            alerts.append(a)
    equity = book["cash"] + mv
    book.update({"market_value": round(mv, 2), "equity": round(equity, 2),
                 "return_pct": round((equity / float(cfg["starting_capital_usd"]) - 1) * 100, 2),
                 "unrealized": round(sum(p["pnl"] for p in book["open"]), 2)})
    return alerts


# ------------------------------------------------------------------ weekly plan
def _rank(feats, funds, cfg):
    spy = feats["SPY"].iloc[-1]
    snap = snapshot(feats)
    sc = score_snapshot(snap, spy.ret63, sector_strength(feats), funds, cfg)
    mom = 0.5 * sc.ret126 + 0.3 * sc.ret63 + 0.2 * sc.ret21
    sc["risk_adj_mom"] = mom / (sc.atr / sc.Close)
    return sc


def growth_plan(feats, funds, regime, cfg, book, today, rebalance, state, key="real", halted=False):
    g = cfg["growth"]
    core_t, core_pct = cfg["core"]["ticker"], cfg["core"]["pct"] / 100
    st = state.setdefault(key, {})
    sc = _rank(feats, funds, cfg)
    sc = sc.drop(index=[t for t in (core_t, "SPY") if t in sc.index])
    if not g.get("etfs", True):
        sc = sc.drop(index=[t for t in sc.index if t in ETFS])
    ok = sc.eligible & (sc.rsi < g.get("max_rsi", 80)) & sc.risk_adj_mom.notna()
    ranked = sc[ok].sort_values("risk_adj_mom", ascending=False)
    order = list(ranked.index)
    rank_of = {t: i + 1 for i, t in enumerate(order)}
    # Holdings are judged on the same ranking but without the "overbought" entry filter (RSI is for buying, not selling).
    okh = sc.eligible & sc.risk_adj_mom.notna() if g.get("hold_ignores_rsi", True) else ok
    hold_rank_of = {t: i + 1 for i, t in enumerate(sc[okh].sort_values("risk_adj_mom", ascending=False).index)}

    blocked, avoid = {}, []
    for t in order[:40]:
        info = (funds or {}).get(t) or {}
        er = info.get("next_earnings")
        if er and 0 <= trading_days_between(today, dt.date.fromisoformat(er)) <= 3:
            blocked[t] = f"reports earnings {er}: no new buy this week"
        good, why = quality_gate(info, float(ranked.loc[t].Close))
        if not good:
            blocked[t] = f"fundamentals check: {why}"
    held = {p["ticker"]: p for p in book["open"]}
    active_held = {t: p for t, p in held.items() if t != core_t}
    equity = book["equity"]

    sells, buys, warn = {}, [], {}
    can_buy = not halted and regime["light"] != "RED"
    if rebalance:
        below = st.setdefault("below50", {})
        out_wk = st.setdefault("out_weeks", {})
        need = g.get("exit_confirm", 1)
        for t in active_held:
            r = sc.loc[t] if t in sc.index else None
            if r is None:
                continue
            below[t] = below.get(t, 0) + 1 if r.Close < r.sma50 else 0
            if g.get("trend_exit") and below[t] >= 2:
                sells[t] = "trend broken: second weekly close below its 50-day average"
            elif hold_rank_of.get(t, 999) > g["hold_rank"]:
                out_wk[t] = out_wk.get(t, 0) + 1
                where = f"#{hold_rank_of[t]}" if t in hold_rank_of else "below its 200-day average (a long-term downtrend)"
                if out_wk[t] >= need:
                    sells[t] = (f"weekly review: now {where}, outside the top {g['hold_rank']} for {out_wk[t]} review(s) in a row; "
                                "the money moves to a stronger name")
                else:
                    warn[t] = (f"on notice: now {where}, outside the top {g['hold_rank']}. Sold at the next review only if "
                               "it is still outside; one bad week is not enough")
            else:
                out_wk[t] = 0
        for d in (below, out_wk):
            for t in list(d):
                if t not in active_held:
                    del d[t]
        keep = [t for t in active_held if t not in sells]
        if can_buy:
            sectors = pd.Series([cap_bucket(t) for t in keep]).value_counts().to_dict()
            for t in order:
                if len(keep) + len(buys) >= g["top_n"]:
                    break
                if t in held or t in blocked:
                    continue
                s = cap_bucket(t)
                if not fits_caps(t, sectors, g["max_per_sector"], g.get("tech_like_max")):
                    continue
                sectors[s] = sectors.get(s, 0) + 1
                buys.append(t)

    # ---- sizing and the cash-deployment batch
    active_target = equity * (1 - core_pct)
    reserve = equity * cfg.get("min_cash_pct", 2) / 100
    freed = sum(active_held[t]["value"] for t in sells)
    cash_avail = max(book["cash"] + freed - reserve, 0)
    dep = st.setdefault("deploy", {"batches_left": cfg["deploy"]["batches"]})
    batches_left = max(dep.get("batches_left", 0), 0)
    idle = max(cash_avail - freed, 0)
    budget = (freed + idle / batches_left) if (rebalance and batches_left > 0) else cash_avail
    core_val = held[core_t]["value"] if core_t in held else 0.0
    core_gap = max(equity * core_pct - core_val, 0)
    iv = {t: 1 / max(float(ranked.loc[t].atr / ranked.loc[t].Close), 1e-4) for t in buys}
    avg_iv = (sum(iv.values()) / len(iv)) if iv else 1
    want = {t: min(iv[t] / avg_iv / g["top_n"], g["pos_cap_pct"] / 100) * active_target for t in buys}
    gap_total = core_gap + sum(want.values())
    scale = min(1.0, budget / gap_total) if gap_total > 0 else 0
    orders = []

    def make_order(t, dollars, kind, why):
        r = ranked.loc[t] if t in ranked.index else sc.loc[t]
        px = float(r.Close)
        a = float(r.atr)
        sh = round(dollars / px, 4 if t in ETFS or t == core_t else 2)
        stop = max(px - g["stop_atr"] * a, px * (1 - g["stop_floor_pct"] / 100))
        info = (funds or {}).get(t) or {}
        pt = g.get("profit_take_pct")
        return {"ticker": t, "name": info.get("name", t), "sector": SECTOR_NAMES.get(UNIVERSE.get(t, ""), "Index"),
                "kind": kind, "price": round(px, 2), "entry": round(px, 2), "limit": round(px * 1.01, 2),
                "shares": sh, "dollars": round(sh * px, 2), "stop": round(stop, 2),
                "stop_pct": round((stop / px - 1) * 100, 1), "target": round(px * (1 + pt / 100), 2) if pt else None,
                "target_pct": pt, "rank": rank_of.get(t), "etf": t in ETFS, "cdr": t in CDR,
                "weekly_move_pct": round(a * 5 ** 0.5 / px * 100, 1), "next_earnings": info.get("next_earnings"),
                "fwd_pe": info.get("forward_pe"), "reason": why, "setup": "growth",
                "quality": round(float(r.fund)) if "fund" in r else None,
                "score": round(float(r.composite), 1) if "composite" in r else None,
                "momentum": round(float(r.momentum)) if "momentum" in r else None,
                "rsi": round(float(r.rsi)) if "rsi" in r else None,
                "sell_by": f"reviewed {next_review(today)}", "hold_days": 60,
                "t1": round(px * (1 + pt / 100), 2) if pt else round(px + a * 5 ** 0.5, 2),
                "t2": round(px + 2 * a * 5 ** 0.5, 2),
                "t1_pct": pt or round(a * 5 ** 0.5 / px * 100, 1), "t2_pct": round(2 * a * 5 ** 0.5 / px * 100, 1),
                "risk_dollars": round(sh * (px - stop), 2), "trend": None, "rs": None, "fund": None}

    if rebalance and core_gap * scale >= 5 and core_t in feats:
        f = feats[core_t]
        px = float(f.Close.iloc[-1])
        amt = core_gap * scale
        sh = round(amt / px, 4)
        orders.append({"ticker": core_t, "name": cfg["core"].get("name", core_t), "sector": "Index", "kind": "core",
                       "price": round(px, 2), "entry": round(px, 2), "limit": round(px * 1.01, 2), "shares": sh,
                       "dollars": round(sh * px, 2), "stop": None, "stop_pct": None, "target": None, "rank": None,
                       "etf": True, "cdr": False, "setup": "core", "score": None, "momentum": None, "rsi": None,
                       "reason": [f"core index: {cfg['core']['pct']}% of the account in the S&P 500, held long term",
                                  f"cash goes in over {cfg['deploy']['batches']} weekly batches; new CAD money can use {CAD_HEDGED_CORE}"],
                       "sell_by": "held long term", "hold_days": 999, "t1": None, "t2": None, "t1_pct": None,
                       "t2_pct": None, "risk_dollars": 0, "next_earnings": None, "fwd_pe": None,
                       "weekly_move_pct": round(float(f.atr.iloc[-1]) * 5 ** 0.5 / px * 100, 1)})
    for t in buys:
        r = ranked.loc[t]
        dollars = want[t] * scale
        if dollars < max(25, 0.01 * equity):
            continue
        why = [f"#{rank_of[t]} on risk-adjusted momentum: 6-mo {r.ret126:+.0%}, 3-mo {r.ret63:+.0%}, 1-mo {r.ret21:+.0%}",
               f"{SECTOR_NAMES.get(UNIVERSE.get(t, ''), '')}: keeps the portfolio to max {g['max_per_sector']} per sector",
               f"sized for its swings: a normal week moves it about {float(r.atr) * 5 ** 0.5 / float(r.Close) * 100:.0f}%"]
        why += list(r.fund_notes)[:1] if isinstance(r.get("fund_notes"), list) else []
        if t in CDR:
            why.append("also available as a CAD-hedged CDR (use it if paying with Canadian dollars)")
        orders.append(make_order(t, dollars, "new", why))

    if rebalance:
        st["week"] = {"date": today.isoformat(), "orders": orders, "sells": sells, "warn": warn}
        if orders and batches_left > 0:
            dep["batches_left"] = batches_left - 1
            dep.setdefault("done", []).append(today.isoformat())
    else:
        # Later in the week: re-show this week's orders not yet filled, if still sensible to buy.
        wk = st.get("week") or {}
        if wk.get("date") and dt.date.fromisoformat(wk["date"]).isocalendar()[:2] == today.isocalendar()[:2]:
            for o in wk.get("orders", []):
                t = o["ticker"]
                if t in held or t not in feats:
                    continue
                px = float(feats[t].Close.iloc[-1])
                if px > o["limit"] * 1.03:
                    continue
                if o["kind"] != "core" and (not can_buy or t in blocked or rank_of.get(t, 999) > g["hold_rank"]):
                    continue
                o2 = dict(o, price=round(px, 2), entry=round(px, 2), limit=round(px * 1.01, 2),
                          shares=round(o["dollars"] / px, 4 if o["etf"] else 2), kind=o["kind"] + "-catchup")
                o2["reason"] = ["catch-up from Monday's list: only if you did NOT already buy it (log your fills so this disappears)"] + list(o["reason"])
                orders.append(o2)
            sells = {t: w for t, w in (wk.get("sells") or {}).items() if t in held}

    # ---- idea of the week: a strong name outside the main picks, from a sector we don't hold
    held_sectors = {UNIVERSE.get(t) for t in list(active_held) + buys}
    idea = None
    for t in order[: max(40, g["top_n"] * 4)]:
        if t in held or t in buys or t in blocked or t in ETFS:
            continue
        r = ranked.loc[t]
        if UNIVERSE.get(t) in held_sectors:
            continue
        if r.Close > r.sma50 and 35 <= r.rsi <= 62:
            idea = {"ticker": t, "name": ((funds or {}).get(t) or {}).get("name", t), "price": round(float(r.Close), 2),
                    "rank": rank_of[t], "sector": SECTOR_NAMES.get(UNIVERSE.get(t, ""), ""), "rsi": round(float(r.rsi)),
                    "ret63": round(float(r.ret63) * 100, 1), "cdr": t in CDR,
                    "why": (f"#{rank_of[t]} overall and from a sector we don't own yet; in an uptrend (above its 50-day) "
                            f"but not stretched (RSI {r.rsi:.0f}). Optional: a half-size position, or watch it.")}
            break
    watch = [{"ticker": t, "rank": rank_of[t], "price": round(float(ranked.loc[t].Close), 2),
              "sector": SECTOR_NAMES.get(UNIVERSE.get(t, ""), ""), "ret63": round(float(ranked.loc[t].ret63) * 100, 1),
              "rsi": round(float(ranked.loc[t].rsi)), "action": "next in line",
              "score": round(float(ranked.loc[t].risk_adj_mom), 1), "setup": "growth"}
             for t in order if t not in held and t not in buys and t not in blocked][:6]
    for t, why in blocked.items():
        if rank_of.get(t, 99) <= g["top_n"] + 3:
            avoid.append({"ticker": t, "why_not": why})

    active_val = sum(p["value"] for p in active_held.values())
    sleeves = {"core": {"ticker": core_t, "value": round(core_val, 2), "pct": round(core_val / equity * 100, 1) if equity else 0,
                        "target_pct": cfg["core"]["pct"]},
               "active": {"value": round(active_val, 2), "pct": round(active_val / equity * 100, 1) if equity else 0,
                          "target_pct": 100 - cfg["core"]["pct"], "n": len(active_held)},
               "cash": {"value": round(book["cash"], 2), "pct": round(book["cash"] / equity * 100, 1) if equity else 0}}
    deploy = {"batches_total": cfg["deploy"]["batches"], "batches_left": dep.get("batches_left", 0),
              "done": dep.get("done", []), "this_batch": round(sum(o["dollars"] for o in orders), 2) if rebalance else 0,
              "cash_after": round(book["cash"] + freed - sum(o["dollars"] for o in orders), 2)}
    reentry = reentry_watch(feats, funds, sc, hold_rank_of, g, held)
    rk = _ranking_table(sc.loc[ranked.index], funds)
    for x in rk:
        x["cdr"] = x["ticker"] in CDR
    return {"buys": orders, "sells": sells, "warn": warn, "watch": watch, "idea": idea, "avoid": avoid, "backups": [],
            "extended": [], "sleeves": sleeves, "deploy": deploy, "rebalance": rebalance,
            "target": [t for t in active_held if t not in sells] + buys, "rotate_out": list(sells),
            "ranking": rk, "next_review": next_review(today), "reentry": reentry}


REENTRY_PRIORITY = ["AMD", "NVDA", "CRWD", "SNOW", "AVGO", "TSM", "MU", "PLTR", "NET", "PANW", "ANET", "META", "MSFT", "GOOGL", "AMZN"]


def reentry_watch(feats, funds, sc, hold_rank_of, g, held, n=10):
    """Quality companies that have fallen hard: fundamentals say 'good business', the trend says 'not yet'.

    A name becomes a buy again only through the normal weekly ranking (back in the top hold_rank and above its
    50-day average). This list shows how close each one is, so the decision is made by rules, not by fear or hype.
    """
    rows = []
    for t in sc.index:
        if t in ETFS or t not in feats:
            continue
        f = feats[t]
        if len(f) < 200:
            continue
        info = (funds or {}).get(t) or {}
        px = float(f.Close.iloc[-1])
        hi = float(f.High.tail(252).max())
        off = (px / hi - 1) * 100
        if off > -15:
            continue
        good, why = quality_gate(info, px)
        g_rev, pe, tgt = info.get("revenue_growth"), info.get("forward_pe"), info.get("target_mean")
        if not good or (g_rev is not None and g_rev < 0.08):
            continue
        q, notes = fundamental_score(info)
        sma50 = float(f.sma50.iloc[-1])
        rank = hold_rank_of.get(t)
        above = px > sma50
        in_rank = rank is not None and rank <= g["hold_rank"]
        if above and in_rank:
            status, ready = f"RE-ENTRY SIGNAL: above its 50-day and ranked #{rank}; the weekly review can buy it", True
        else:
            need = []
            if not above:
                need.append(f"close above its 50-day (${sma50:,.2f}, {(sma50 / px - 1) * 100:+.1f}% away)")
            if not in_rank:
                need.append(f"rank back inside the top {g['hold_rank']} (now {'#' + str(rank) if rank else 'unranked: below its 200-day'})")
            status, ready = "waiting: needs to " + " and ".join(need), False
        peg = round(pe / (g_rev * 100), 2) if (pe and g_rev and g_rev > 0 and pe > 0) else None
        rows.append({"ticker": t, "name": info.get("name", t), "sector": SECTOR_NAMES.get(UNIVERSE.get(t, ""), ""),
                     "price": round(px, 2), "off_high_pct": round(off, 1), "revenue_growth_pct":
                     round(g_rev * 100, 1) if g_rev is not None else None, "fwd_pe": round(pe, 1) if pe else None,
                     "peg": peg, "analyst_upside_pct": round((tgt / px - 1) * 100, 1) if tgt else None,
                     "quality": round(q), "quality_notes": notes[:2], "status": status, "ready": ready,
                     "held": t in held, "cdr": t in CDR,
                     "_prio": (0 if t in held else 1, REENTRY_PRIORITY.index(t) if t in REENTRY_PRIORITY else 99, -q)})
    rows.sort(key=lambda x: x["_prio"])
    for r in rows:
        r.pop("_prio")
    return rows[:n]


def checkpoints(cfg, equity, state, spy_last):
    """Progress toward the 3- and 6-month profit goals since the growth phase started."""
    ph = state.setdefault("phase", {})
    ph.setdefault("equity", round(equity, 2))
    ph.setdefault("spy", round(spy_last, 2))
    start = dt.date.fromisoformat(cfg["phase_start"])
    ret = (equity / ph["equity"] - 1) * 100
    spy_ret = (spy_last / ph["spy"] - 1) * 100 if ph.get("spy") else None
    out = []
    for months, goal in ((3, cfg["goal"]["low_pct"]), (6, cfg["goal"]["high_pct"])):
        d = (pd.Timestamp(start) + pd.DateOffset(months=months)).date()
        out.append({"label": f"{months}-month check", "date": d.isoformat(), "goal_pct": goal,
                    "progress": round(max(0.0, min(100.0, ret / goal * 100)), 0) if goal else 0})
    return {"start": cfg["phase_start"], "start_equity": ph["equity"], "return_pct": round(ret, 2),
            "spy_return_pct": round(spy_ret, 2) if spy_ret is not None else None, "checks": out,
            "take_profit_rule": cfg["goal"].get("take_profit_rule")}


def lesson(today, cfg):
    i = today.isocalendar()[1] % len(LESSONS)
    t, body = LESSONS[i]
    g = cfg["growth"]
    return {"title": t, "body": body.format(max_per_sector=g["max_per_sector"], tech_like_max=g.get("tech_like_max"), hold_rank=g["hold_rank"],
                                            exit_confirm=g.get("exit_confirm", 1), top_n=g["top_n"],
                                            stop_atr=g["stop_atr"], batches=cfg["deploy"]["batches"])}
