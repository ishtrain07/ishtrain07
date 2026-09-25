"""Entry point.

  python -m habibi.run plan      # morning: full research, ranking, orders, dashboard, notification
  python -m habibi.run check     # intraday: re-check open positions, send SELL alerts
"""
import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

from . import data, notify
from .backtest import run_backtest
from .dashboard import render
from .indicators import add_features
from .portfolio import evaluate, load_history, load_trades, positions, system_paper
from .strategy import market_regime, rank_and_bucket, trading_days_between
from .universe import FOMC_2026, MACRO, UNIVERSE, all_price_tickers

ROOT = Path(__file__).parent
OUT = ROOT / "output"
DOCS = ROOT.parent / "docs"
ET = ZoneInfo("America/New_York")


def load_cfg():
    return json.loads((ROOT / "config.json").read_text())


def macro_table(feats):
    rows = []
    for t, label in MACRO.items():
        f = feats.get(t)
        if f is None or len(f) < 25:
            continue
        c = f.Close
        rows.append({"ticker": t, "label": label, "last": round(float(c.iloc[-1]), 2),
                     "d1": round(float(c.iloc[-1] / c.iloc[-2] - 1) * 100, 2),
                     "d5": round(float(c.iloc[-1] / c.iloc[-6] - 1) * 100, 2),
                     "m1": round(float(c.iloc[-1] / c.iloc[-22] - 1) * 100, 2)})
    return rows


def macro_read(macro, regime, today):
    m = {r["ticker"]: r for r in macro}
    notes = []
    if "^VIX" in m:
        v = m["^VIX"]["last"]
        notes.append(f"VIX {v:.1f}: " + ("calm, dips tend to get bought." if v < 16 else
                     "normal." if v < 20 else "elevated, expect bigger swings; size down." if v < 28 else
                     "fear spike, stay defensive."))
    if "^TNX" in m:
        chg = m["^TNX"]["m1"]
        notes.append(f"10Y yield {m['^TNX']['last']:.2f}% ({chg:+.1f}% over a month): " +
                     ("rising yields pressure high-P/E growth stocks." if chg > 3 else
                      "falling yields support growth/tech." if chg < -3 else "stable, neutral."))
    if "DX-Y.NYB" in m:
        chg = m["DX-Y.NYB"]["m1"]
        notes.append(f"Dollar {chg:+.1f}% over a month: " + ("strong dollar is a headwind for multinationals." if chg > 1.5
                     else "weaker dollar helps US multinationals and commodities." if chg < -1.5 else "neutral."))
    if "CL=F" in m and abs(m["CL=F"]["d5"]) > 5:
        notes.append(f"Oil moved {m['CL=F']['d5']:+.1f}% this week: watch energy and inflation expectations.")
    overnight = [f"{m[t]['label'].split(' (')[0]} {m[t]['d1']:+.1f}%" for t in ("^N225", "^HSI", "^GDAXI", "^NSEI") if t in m]
    if overnight:
        notes.append("Global overnight: " + ", ".join(overnight) + ".")
    fut = [f"{m[t]['label']} {m[t]['d1']:+.2f}%" for t in ("ES=F", "NQ=F") if t in m]
    if fut:
        notes.append("US futures: " + ", ".join(fut) + ".")
    for d in FOMC_2026:
        days = (dt.date.fromisoformat(d) - today).days
        if 0 <= days <= 10:
            notes.append(f"Fed decision on {d} ({days} days): avoid opening big positions the day before.")
    if today.month in (1, 4, 7, 10) and today.day >= 10:
        notes.append("Earnings season: the engine blocks buys that would be held through a report.")
    notes.append(regime["message"])
    return notes


def build_features(prices):
    return {t: add_features(df) for t, df in prices.items()}


def sent_alerts():
    p = OUT / "alerts_sent.json"
    return json.loads(p.read_text()) if p.exists() else {}


def dispatch_alerts(alerts, cfg, today):
    sent = sent_alerts()
    today_s = today.isoformat()
    for a in alerts:
        key = f"{today_s}|{a['ticker']}|{a['action']}"
        if key in sent:
            continue
        title = f"SELL ALERT {a['ticker']}: {a['action']} ~{a['shares']} sh @ ~{a['price']}"
        notify.send_all(title, a["why"] + "\nThen log the sale in trades.csv / the dashboard form.",
                        priority="urgent", tags="rotating_light", click=cfg.get("dashboard_url"),
                        labels=["habibi", "sell-alert"])
        sent[key] = dt.datetime.now(ET).isoformat()
    sent = {k: v for k, v in sent.items() if k[:10] >= (today - dt.timedelta(days=14)).isoformat()}
    (OUT / "alerts_sent.json").write_text(json.dumps(sent, indent=1))


def drawdown_state(book, cfg):
    r = book["return_pct"]
    if r <= -cfg["max_drawdown_liquidate_pct"]:
        return "LIQUIDATE", f"Account down {r:.1f}%: loss limit hit. Sell everything and stop."
    if r <= -cfg["max_drawdown_halt_pct"]:
        return "HALT", f"Account down {r:.1f}%: no new buys until it recovers above -{cfg['max_drawdown_halt_pct']}%."
    return "OK", ""


def cmd_plan(cfg, args):
    now = dt.datetime.now(ET)
    today = now.date()
    tickers = sorted(set(all_price_tickers()) | set(load_trades(ROOT / "trades.csv").get("ticker", [])))
    prices = data.download_prices(tickers, period="2y")
    if "SPY" not in prices:
        sys.exit("SPY data unavailable - aborting")
    feats = build_features(prices)
    vix = feats.get("^VIX")
    regime = market_regime(feats["SPY"], float(vix.Close.iloc[-1]) if vix is not None else None)

    funds_path = OUT / "fundamentals.json"
    if args.skip_fundamentals and funds_path.exists():
        funds = json.loads(funds_path.read_text())
    else:
        funds = data.fundamentals([t for t in UNIVERSE if t in feats])
        funds_path.write_text(json.dumps(funds, indent=1, default=str))

    history = load_history()
    trades = load_trades(ROOT / "trades.csv")
    book = positions(trades, feats, history, cfg)
    live = data.latest_prices([p["ticker"] for p in book["open"]]) if book["open"] else {}
    alerts = evaluate(book, feats, live, funds, cfg, today)
    dd_state, dd_msg = drawdown_state(book, cfg)
    if dd_state == "LIQUIDATE":
        for p in book["open"]:
            if not any(a["ticker"] == p["ticker"] for a in alerts):
                alerts.append({"ticker": p["ticker"], "action": "SELL ALL", "why": dd_msg,
                               "price": p["price"], "shares": p["shares"]})

    selling = {a["ticker"] for a in alerts if a["action"] == "SELL ALL"}
    open_tickers = [p["ticker"] for p in book["open"] if p["ticker"] not in selling]
    ranked = rank_and_bucket(feats, funds, regime, cfg, book["equity"], book["cash"],
                             open_tickers, today, halted=dd_state != "OK")
    for b in ranked["buys"]:
        b["news"] = data.news(b["ticker"])

    macro = macro_table(feats)
    bt_path = OUT / "backtest.json"
    if args.backtest or not bt_path.exists() or today.weekday() == 0:
        bt = run_backtest(feats, cfg)
        bt["run_date"] = today.isoformat()
        bt_path.write_text(json.dumps(bt, indent=1, default=str))
    bt = json.loads(bt_path.read_text())

    goal_date = dt.date.fromisoformat(cfg["goal_date"])
    report = {
        "generated_at": now.strftime("%Y-%m-%d %H:%M ET"), "date": today.isoformat(), "mode": "plan",
        "regime": regime, "macro": macro, "macro_read": macro_read(macro, regime, today),
        "account": {k: book[k] for k in ("cash", "realized", "unrealized", "market_value", "equity", "return_pct")},
        "drawdown_state": dd_state, "drawdown_msg": dd_msg,
        "positions": book["open"], "closed": book["closed"], "alerts": alerts,
        "trading_days_left": trading_days_between(today, goal_date),
        "system_paper": system_paper({**history, today.isoformat(): ranked}, feats, cfg, cfg["start_date"]),
        "backtest": bt, "config": cfg, **ranked,
    }
    brief = OUT / "brief.md"
    if brief.exists():
        report["brief"] = brief.read_text()[:4000]
    (OUT / "history" / f"{today.isoformat()}.json").write_text(
        json.dumps({"buys": ranked["buys"], "backups": ranked["backups"], "watch": ranked["watch"],
                    "regime": regime}, indent=1, default=str))
    write_outputs(report)

    if not args.no_notify:
        dispatch_alerts(alerts, cfg, today)
        notify.send_all(*morning_message(report), click=cfg.get("dashboard_url"),
                        labels=["habibi", "daily-plan"])


def morning_message(rep):
    lines = [f"Market: {rep['regime']['light']} - {rep['regime']['message']}",
             f"Account ${rep['account']['equity']:,.0f} ({rep['account']['return_pct']:+.1f}%), "
             f"{rep['trading_days_left']} trading days to goal", ""]
    if rep["drawdown_msg"]:
        lines.append("!! " + rep["drawdown_msg"])
    for a in rep["alerts"]:
        lines.append(f"SELL {a['ticker']}: {a['action']} - {a['why']}")
    for b in rep["buys"]:
        lines.append(f"BUY {b['ticker']} {b['shares']} sh (~${b['dollars']:,.0f}) limit {b['limit']} | "
                     f"stop {b['stop']} | T1 {b['t1']} T2 {b['t2']} | sell by {b['sell_by']}")
    if not rep["buys"]:
        lines.append("No new buys today - cash is a position.")
    for p in rep["positions"]:
        if p["action"] == "HOLD":
            lines.append(f"HOLD {p['ticker']} {p['pnl_pct']:+.1f}% - {p['why']}")
    title = f"Habibi {rep['date']}: {len(rep['buys'])} buy, {len(rep['alerts'])} sell, market {rep['regime']['light']}"
    return title, "\n".join(lines)


def cmd_check(cfg, args):
    now = dt.datetime.now(ET)
    today = now.date()
    latest = OUT / "latest.json"
    if not latest.exists():
        return cmd_plan(cfg, args)
    report = json.loads(latest.read_text())
    trades = load_trades(ROOT / "trades.csv")
    held = sorted(set(trades.ticker)) if not trades.empty else []
    if not held:
        print("No positions to check.")
        return
    prices = data.download_prices(sorted(set(held) | {"SPY"}), period="1y")
    feats = build_features(prices)
    history = load_history()
    book = positions(trades, feats, history, cfg)
    live = data.latest_prices([p["ticker"] for p in book["open"]]) if book["open"] else {}
    funds = json.loads((OUT / "fundamentals.json").read_text()) if (OUT / "fundamentals.json").exists() else {}
    alerts = evaluate(book, feats, live, funds, cfg, today)
    dd_state, dd_msg = drawdown_state(book, cfg)
    report.update({"generated_at": now.strftime("%Y-%m-%d %H:%M ET") + " (position check)",
                   "account": {k: book[k] for k in ("cash", "realized", "unrealized", "market_value", "equity", "return_pct")},
                   "positions": book["open"], "closed": book["closed"], "alerts": alerts,
                   "drawdown_state": dd_state, "drawdown_msg": dd_msg})
    write_outputs(report)
    if not args.no_notify:
        dispatch_alerts(alerts, cfg, today)


def write_outputs(report):
    OUT.mkdir(exist_ok=True)
    DOCS.mkdir(exist_ok=True)
    (OUT / "latest.json").write_text(json.dumps(report, indent=1, default=str))
    html = render(report)
    (DOCS / "index.html").write_text(html)
    (OUT / "dashboard.html").write_text(html)
    print(f"wrote dashboard: {len(report.get('buys', []))} buys, {len(report.get('alerts', []))} alerts")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["plan", "check"])
    ap.add_argument("--no-notify", action="store_true")
    ap.add_argument("--backtest", action="store_true", help="force a backtest refresh")
    ap.add_argument("--skip-fundamentals", action="store_true")
    args = ap.parse_args()
    cfg = load_cfg()
    (OUT / "history").mkdir(parents=True, exist_ok=True)
    (cmd_plan if args.mode == "plan" else cmd_check)(cfg, args)


if __name__ == "__main__":
    main()
