"""Actual trades (trades.csv) -> positions, P&L, sell alerts, and you-vs-system."""
import datetime as dt
import json
from pathlib import Path

import pandas as pd

from .backtest import simulate_trade
from .strategy import add_trading_days, trading_days_between

HISTORY = Path(__file__).parent / "output" / "history"


def load_trades(path):
    df = pd.read_csv(path, dtype={"note": str})
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df["ticker"] = df["ticker"].str.upper().str.strip()
    df["side"] = df["side"].str.upper().str.strip()
    df["fees"] = df["fees"].fillna(0)
    return df.sort_values("date", kind="stable")


def load_history():
    plans = {}
    for p in sorted(HISTORY.glob("*.json")):
        try:
            plans[p.stem] = json.loads(p.read_text())
        except Exception:
            pass
    return plans


def find_plan(history, ticker, buy_date):
    """System plan for ticker issued on buy_date or up to 3 trading days before."""
    for back in range(0, 6):
        d = (buy_date - dt.timedelta(days=back)).isoformat()
        day = history.get(d)
        if not day:
            continue
        for p in day.get("buys", []) + day.get("backups", []):
            if p["ticker"] == ticker:
                return p, d
    return None, None


def positions(trades, feats, history, cfg):
    cash = float(cfg["starting_capital_usd"])
    realized = 0.0
    book = {}
    closed = []
    for _, t in trades.iterrows():
        pos = book.setdefault(t.ticker, {"shares": 0.0, "cost": 0.0, "bought": 0.0,
                                         "sold": 0.0, "first_buy": t.date, "fills": []})
        if t.side == "BUY":
            if pos["shares"] <= 1e-9:
                pos.update({"shares": 0.0, "cost": 0.0, "bought": 0.0, "sold": 0.0,
                            "first_buy": t.date, "fills": []})
            pos["shares"] += t.shares
            pos["bought"] += t.shares
            pos["cost"] += t.shares * t.price + t.fees
            pos["fills"].append({"date": t.date.isoformat(), "price": t.price, "shares": t.shares})
            cash -= t.shares * t.price + t.fees
        elif t.side == "SELL":
            avg = pos["cost"] / pos["shares"] if pos["shares"] else t.price
            pnl = (t.price - avg) * t.shares - t.fees
            realized += pnl
            cash += t.shares * t.price - t.fees
            closed.append({"date": t.date.isoformat(), "ticker": t.ticker, "shares": t.shares,
                           "price": t.price, "avg_cost": round(avg, 2), "pnl": round(pnl, 2),
                           "pnl_pct": round((t.price / avg - 1) * 100, 2)})
            pos["cost"] -= avg * t.shares
            pos["shares"] -= t.shares
            pos["sold"] += t.shares

    open_pos = []
    for tk, p in book.items():
        if p["shares"] <= 1e-9:
            continue
        avg = p["cost"] / p["shares"]
        plan, plan_date = find_plan(history, tk, p["first_buy"])
        f = feats.get(tk)
        mode = "momentum" if (plan and plan.get("setup") == "momentum") or (
            not plan and cfg.get("strategy") == "momentum") else "swing"
        if plan:
            stop, t1, t2, hold = plan["stop"], plan["t1"], plan["t2"], plan["hold_days"]
        elif mode == "momentum":
            stop, t1, t2, hold = avg * (1 - cfg.get("momentum_stop_pct", 10) / 100), avg * 1.05, avg * 1.10, 60
        else:
            a = float(f.loc[:pd.Timestamp(p["first_buy"])].atr.iloc[-1]) if f is not None else avg * 0.03
            dist = min(1.5 * a, 0.08 * avg)
            stop, t1, t2, hold = avg - dist, avg + 1.5 * dist, avg + 3 * dist, 7
        open_pos.append({"ticker": tk, "shares": round(p["shares"], 4), "avg_cost": round(avg, 2),
                         "first_buy": p["first_buy"].isoformat(), "stop": round(stop, 2),
                         "t1": round(t1, 2), "t2": round(t2, 2), "hold_days": hold,
                         "sell_by": add_trading_days(p["first_buy"], hold).isoformat(),
                         "partial": p["sold"] > 0, "system_pick": plan is not None, "mode": mode,
                         "plan_entry": plan["entry"] if plan else None, "plan_date": plan_date,
                         "fills": p["fills"]})
    return {"cash": round(cash, 2), "realized": round(realized, 2), "open": open_pos,
            "closed": closed}


def evaluate(book, feats, live, funds, cfg, today):
    """Attach current price, P&L and an action (HOLD / SELL ...) to each open position."""
    mv = 0.0
    alerts = []
    for p in book["open"]:
        tk = p["ticker"]
        f = feats.get(tk)
        last_close = float(f.Close.iloc[-1]) if f is not None else p["avg_cost"]
        px = live.get(tk, last_close)
        p["price"] = round(px, 2)
        p["value"] = round(px * p["shares"], 2)
        p["pnl"] = round((px - p["avg_cost"]) * p["shares"], 2)
        p["pnl_pct"] = round((px / p["avg_cost"] - 1) * 100, 2)
        mv += p["value"]
        held = trading_days_between(dt.date.fromisoformat(p["first_buy"]), today)
        p["days_held"] = held

        stop = p["stop"]
        if p["partial"] and f is not None:
            since = f.loc[pd.Timestamp(p["first_buy"]):]
            trail = float(since.Close.max() - 2 * f.atr.iloc[-1])
            stop = max(p["avg_cost"], trail)
        p["active_stop"] = round(stop, 2)

        er = ((funds or {}).get(tk) or {}).get("next_earnings")
        er_days = trading_days_between(today, dt.date.fromisoformat(er)) if er else None
        below50 = f is not None and last_close < float(f.sma50.iloc[-1])

        if p.get("mode") == "momentum":
            p["active_stop"] = p["stop"]
            if px <= p["stop"]:
                act, why = "SELL ALL", f"hit the {cfg.get('momentum_stop_pct', 10)}% stop at {p['stop']:.2f}"
            else:
                act, why = "HOLD", (f"held while it stays top-{cfg['max_positions']}; reviewed every Monday; "
                                    f"stop {p['stop']:.2f} ({(p['stop'] / px - 1) * 100:+.1f}%)")
        elif px <= stop:
            act, why = "SELL ALL", f"hit stop {stop:.2f}" + (" (trailing)" if p["partial"] else "")
        elif px >= p["t2"]:
            act, why = "SELL ALL", f"reached target 2 ({p['t2']:.2f}) - bank it"
        elif px >= p["t1"] and not p["partial"]:
            act, why = "SELL HALF", f"reached target 1 ({p['t1']:.2f}); sell half, stop moves to breakeven {p['avg_cost']:.2f}"
        elif er_days is not None and er_days <= 1:
            act, why = "SELL ALL", f"earnings {er} - do not hold through the report"
        elif held >= p["hold_days"]:
            act, why = "SELL ALL", f"time stop: {held} trading days held (plan was {p['hold_days']}); free the cash"
        elif below50:
            act, why = "SELL ALL", "closed below 50-day average - trend broken"
        else:
            act = "HOLD"
            why = (f"stop {stop:.2f} ({(stop / px - 1) * 100:+.1f}%), next target "
                   f"{(p['t2'] if p['partial'] else p['t1']):.2f}, sell by {p['sell_by']}")
        p["action"], p["why"] = act, why
        if act != "HOLD":
            alerts.append({"ticker": tk, "action": act, "why": why, "price": p["price"],
                           "shares": p["shares"] if act == "SELL ALL" else round(p["shares"] / 2, 2)})

    equity = book["cash"] + mv
    start = float(cfg["starting_capital_usd"])
    book.update({"market_value": round(mv, 2), "equity": round(equity, 2),
                 "return_pct": round((equity / start - 1) * 100, 2),
                 "unrealized": round(sum(p["pnl"] for p in book["open"]), 2)})
    return alerts


def system_paper(history, feats, cfg, start_date):
    """Paper-trade every BUY the system issued since start_date with the same exit rules."""
    rows = []
    for d, day in sorted(history.items()):
        if d < start_date:
            continue
        for p in day.get("buys", []):
            f = feats.get(p["ticker"])
            if f is None:
                continue
            fut = f.loc[pd.Timestamp(d):]
            fut = fut.iloc[1:] if len(fut) and fut.index[0] == pd.Timestamp(d) else fut
            a = (p["entry"] - p["stop"]) / 1.5
            res = simulate_trade(fut.iloc[:p["hold_days"]], p["entry"], p["stop"], p["t1"],
                                 p["t2"], p["hold_days"], a)
            row = {"date": d, "ticker": p["ticker"], "entry": p["entry"], "shares": p["shares"]}
            if res:
                row.update(res)
                row["pnl"] = round(res["pnl_per_share"] * p["shares"], 2)
                row["status"] = "closed"
            else:
                last = float(f.Close.iloc[-1])
                row.update({"status": "open", "pnl": round((last - p["entry"]) * p["shares"], 2)})
            rows.append(row)
    total = sum(r["pnl"] for r in rows)
    return {"trades": rows, "pnl": round(total, 2),
            "return_pct": round(total / float(cfg["starting_capital_usd"]) * 100, 2)}
