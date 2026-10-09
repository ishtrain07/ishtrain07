"""The system's own paper account: same starting capital, follows every order automatically.

Buys are recorded at the limit price (conservative: the worst price you'd pay),
sells at the price when the alert fired. Stored in output/paper_trades.csv, so
"You vs the system" is a like-for-like race on the same rules.
"""
from pathlib import Path

from .portfolio import evaluate, load_trades, positions
from .strategy import momentum_plan, rank_and_bucket

PATH = Path(__file__).parent / "output" / "paper_trades.csv"
HEADER = "date,ticker,side,shares,price,fees,note\n"


def _append(rows):
    if not PATH.exists():
        PATH.write_text(HEADER)
    with PATH.open("a") as f:
        for r in rows:
            f.write(",".join(str(r[k]) for k in ("date", "ticker", "side", "shares", "price", "fees", "note")) + "\n")


def run_paper(feats, funds, regime, cfg, today, history, live, execute, rebalance=False, learned=None,
              plan_day=False):
    # The paper account keeps its own capital, so changing the real account size doesn't break its ledger.
    cfg = {**cfg, "starting_capital_usd": cfg.get("paper_capital_usd", cfg["starting_capital_usd"])}
    if not PATH.exists():
        PATH.parent.mkdir(parents=True, exist_ok=True)
        PATH.write_text(HEADER)
    book = positions(load_trades(PATH), feats, history, cfg)
    alerts = evaluate(book, feats, live, funds, cfg, today)
    orders = []
    for a in alerts:
        shares = a["shares"]
        orders.append({"date": today.isoformat(), "ticker": a["ticker"], "side": "SELL", "shares": shares,
                       "price": a["price"], "fees": 0, "note": a["action"].replace(",", " ")})
    selling = {a["ticker"] for a in alerts if a["action"] == "SELL ALL"}
    freed = sum(a["price"] * a["shares"] for a in alerts)
    holdings = {p["ticker"]: p["value"] for p in book["open"] if p["ticker"] not in selling}
    if cfg.get("strategy") == "momentum":
        details = {p["ticker"]: p for p in book["open"] if p["ticker"] not in selling}
        plan = momentum_plan(feats, funds, regime, cfg, book["equity"], book["cash"] + freed,
                             holdings, today, rebalance, learned, details) if plan_day \
            else {"buys": [], "rotate_out": []}
        for t in plan["rotate_out"]:
            p = next(p for p in book["open"] if p["ticker"] == t)
            orders.append({"date": today.isoformat(), "ticker": t, "side": "SELL", "shares": p["shares"],
                           "price": p["price"], "fees": 0, "note": "rotated out"})
    else:
        plan = rank_and_bucket(feats, funds, regime, cfg, book["equity"], book["cash"] + freed,
                               list(holdings), today) if plan_day else {"buys": []}
    for b in plan["buys"][:cfg["max_positions"]]:
        orders.append({"date": today.isoformat(), "ticker": b["ticker"], "side": "BUY", "shares": b["shares"],
                       "price": b["limit"], "fees": 0, "note": b.get("kind", b["setup"])})
    if execute and orders:
        _append(orders)
    book = positions(load_trades(PATH), feats, history, cfg)
    evaluate(book, feats, live, funds, cfg, today)
    return {"account": {k: book[k] for k in ("cash", "realized", "unrealized", "market_value", "equity", "return_pct")},
            "record": win_loss(book["closed"]),
            "positions": book["open"], "closed": book["closed"], "orders_today": orders, "executed": execute}


def win_loss(closed):
    """Win/loss record from closed (sold) lots."""
    wins = [c for c in closed if c["pnl"] > 0]
    losses = [c for c in closed if c["pnl"] <= 0]
    n = len(closed)
    return {"trades": n, "wins": len(wins), "losses": len(losses),
            "win_rate": round(len(wins) / n * 100, 1) if n else None,
            "avg_win_pct": round(sum(c["pnl_pct"] for c in wins) / len(wins), 2) if wins else None,
            "avg_loss_pct": round(sum(c["pnl_pct"] for c in losses) / len(losses), 2) if losses else None,
            "net": round(sum(c["pnl"] for c in closed), 2)}
