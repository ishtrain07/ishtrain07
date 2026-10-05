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

from . import adaptive, anomalies, data, notify
from .paper import PATH as PAPER_PATH, run_paper, win_loss
from .backtest import run_backtest
from .dashboard import render
from .indicators import add_features
from .replay import replay
from .portfolio import evaluate, load_history, load_trades, positions, system_paper
from .strategy import (add_trading_days, is_rebalance_day, market_regime, momentum_plan, rank_and_bucket,
                       trading_days_between)
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


def drawdown_state(book, cfg, today=None, persist=False):
    """Account loss limits (vs starting capital) plus a peak brake (vs highest equity).

    Peak brake: equity more than peak_brake_pct below its peak -> sell everything and
    sit in cash for brake_cool_days trading days (research variant L2).
    """
    r = book["return_pct"]
    brake = cfg.get("peak_brake_pct")
    if brake and today is not None:
        sp = OUT / "state.json"
        st = json.loads(sp.read_text()) if sp.exists() else {}
        peak = max(float(st.get("peak_equity", cfg["starting_capital_usd"])), book["equity"])
        cool_until = st.get("brake_until")
        if book["equity"] < peak * (1 - brake / 100) and book["open"]:
            cool_until = add_trading_days(today, cfg.get("brake_cool_days", 5)).isoformat()
            peak = book["equity"]
        if persist:
            st.update({"peak_equity": round(peak, 2), "brake_until": cool_until})
            sp.write_text(json.dumps(st))
        if cool_until and today.isoformat() <= cool_until:
            if book["open"]:
                return "LIQUIDATE", f"Peak brake: account fell {brake}% from its high. Sell everything; cash until {cool_until}."
            return "HALT", f"Cooling off after the peak brake: no buys until after {cool_until}."
    if r <= -cfg["max_drawdown_liquidate_pct"]:
        return "LIQUIDATE", f"Account down {r:.1f}%: loss limit hit. Sell everything and stop."
    if r <= -cfg["max_drawdown_halt_pct"]:
        return "HALT", f"Account down {r:.1f}%: no new buys until it recovers above -{cfg['max_drawdown_halt_pct']}%."
    return "OK", ""


def scan_anomalies(feats, model_scores, book, paper, ranked, cfg):
    """Learned unusual-activity flags + rank trends for holdings and the top of the ranking."""
    held = [p["ticker"] for p in book["open"]]
    paper_held = [p["ticker"] for p in (paper or {}).get("positions", [])]
    top = [x["ticker"] for x in ranked.get("ranking", [])[:10]]
    watch = list(dict.fromkeys(held + paper_held + top))
    try:
        stats = anomalies.learn(feats, model_scores)
        out = anomalies.detect(feats, watch, stats, model_scores, held=set(held),
                               sectors=UNIVERSE, max_positions=cfg["max_positions"])
        out["stats"] = stats
        return out
    except Exception as e:  # never let diagnostics break the plan
        print(f"anomaly scan failed: {e}")
        return None


def benchmark(feats, cfg, live=None):
    """S&P 500 (SPY) return since the last close before the start date: the 'market' line."""
    spy = feats.get("SPY")
    if spy is None:
        return None
    start = dt.date.fromisoformat(cfg["start_date"])
    before = spy.Close[spy.index.date < start]
    if before.empty:
        return None
    base = float(before.iloc[-1])
    last = float((live or {}).get("SPY", spy.Close.iloc[-1]))
    return {"spy_return_pct": round((last / base - 1) * 100, 2), "base": round(base, 2), "last": round(last, 2),
            "since": cfg["start_date"]}


def save_history(today, ranked, regime):
    """The day's plan is the engine's memory (stops for positions, the week's list).
    Later runs the same day merge in new orders; they never erase earlier ones."""
    path = OUT / "history" / f"{today.isoformat()}.json"
    old = json.loads(path.read_text()) if path.exists() else {}
    buys = {b["ticker"]: b for b in old.get("buys", [])}
    for b in ranked["buys"]:
        buys.setdefault(b["ticker"], b)
    path.write_text(json.dumps({"buys": list(buys.values()), "backups": ranked["backups"] or old.get("backups", []),
                                "watch": ranked["watch"], "regime": regime}, indent=1, default=str))


def cmd_plan(cfg, args):
    now = dt.datetime.now(ET)
    today = now.date()
    tickers = sorted(set(all_price_tickers()) | set(load_trades(ROOT / "trades.csv").get("ticker", []))
                     | (set(load_trades(PAPER_PATH).get("ticker", [])) if PAPER_PATH.exists() else set()))
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
    paper_held = sorted(set(load_trades(PAPER_PATH).ticker)) if PAPER_PATH.exists() and not load_trades(PAPER_PATH).empty else []
    held_all = sorted({p["ticker"] for p in book["open"]} | set(paper_held))
    live = data.latest_prices(held_all) if held_all else {}
    alerts = evaluate(book, feats, live, funds, cfg, today)
    dd_state, dd_msg = drawdown_state(book, cfg, today, persist=not args.dry_run)
    rebalance, learned_scores, model_scores = False, None, None
    if dd_state == "LIQUIDATE":
        for p in book["open"]:
            if not any(a["ticker"] == p["ticker"] for a in alerts):
                alerts.append({"ticker": p["ticker"], "action": "SELL ALL", "why": dd_msg,
                               "price": p["price"], "shares": p["shares"]})

    selling = {a["ticker"] for a in alerts if a["action"] == "SELL ALL"}
    open_tickers = [p["ticker"] for p in book["open"] if p["ticker"] not in selling]
    if cfg.get("strategy") == "momentum":
        state_path = OUT / "state.json"
        state = json.loads(state_path.read_text()) if state_path.exists() else {}
        rebalance = is_rebalance_day(today, state.get("last_rebalance")) and dd_state == "OK"
        holdings = {p["ticker"]: p["value"] for p in book["open"] if p["ticker"] not in selling}
        learned = None
        if cfg.get("ranker") == "adaptive":
            uni = [t for t in UNIVERSE if t in feats and len(feats[t]) > 260]
            m = adaptive.model(feats, uni)
            learned_scores, learned = m["scores"].iloc[-1], adaptive.explain_today(m)
            model_scores = m["scores"]
        details = {p["ticker"]: p for p in book["open"] if p["ticker"] not in selling}
        catch_up = None
        if not rebalance and state.get("last_rebalance"):
            week_plan = history.get(state["last_rebalance"], {})
            catch_up = {b["ticker"]: b["stop"] for b in week_plan.get("buys", []) if b.get("kind") != "add"}
        ranked = momentum_plan(feats, funds, regime, cfg, book["equity"], book["cash"], holdings, today,
                               rebalance if dd_state == "OK" else False, learned_scores, details,
                               catch_up if dd_state == "OK" else None)
        if dd_state != "OK":
            ranked["buys"] = []
        ranked["learned"] = learned
        for t in ranked["rotate_out"]:
            p = next(p for p in book["open"] if p["ticker"] == t)
            p["action"], p["why"] = "SELL ALL", f"rotated out: fell below #{cfg.get('hold_rank') or cfg['max_positions']} on the ranking this week"
            alerts.append({"ticker": t, "action": "SELL ALL", "why": p["why"], "price": p["price"], "shares": p["shares"]})
        if rebalance and not args.dry_run:
            state["last_rebalance"] = today.isoformat()
            state_path.write_text(json.dumps(state))
    else:
        ranked = rank_and_bucket(feats, funds, regime, cfg, book["equity"], book["cash"],
                                 open_tickers, today, halted=dd_state != "OK")
    for b in ranked["buys"]:
        b["news"] = data.news(b["ticker"])
    paper = run_paper(feats, funds, regime, cfg, today, history, live, execute=not args.dry_run,
                      rebalance=rebalance, learned=learned_scores, plan_day=True)

    macro = macro_table(feats)
    bt_path = OUT / "backtest.json"
    if args.backtest or not bt_path.exists() or today.weekday() == 0:
        bt = run_backtest(feats, cfg)
        bt["run_date"] = today.isoformat()
        bt_path.write_text(json.dumps(bt, indent=1, default=str))
    bt = json.loads(bt_path.read_text())
    rp = None
    if cfg.get("strategy") != "momentum":
        rp = replay(feats, funds, cfg, 10)
        (OUT / "replay.json").write_text(json.dumps(rp, indent=1, default=str))
    research_path = OUT / "research.json"
    research = json.loads(research_path.read_text()) if research_path.exists() else None

    goal_date = dt.date.fromisoformat(cfg["goal_date"])
    report = {
        "generated_at": now.strftime("%Y-%m-%d %H:%M ET"), "date": today.isoformat(), "mode": "plan",
        "regime": regime, "macro": macro, "macro_read": macro_read(macro, regime, today),
        "account": {k: book[k] for k in ("cash", "realized", "unrealized", "market_value", "equity", "return_pct")},
        "drawdown_state": dd_state, "drawdown_msg": dd_msg,
        "positions": book["open"], "closed": book["closed"], "alerts": alerts,
        "trading_days_left": trading_days_between(today, goal_date),
        "system_paper": system_paper({**history, today.isoformat(): ranked}, feats, cfg, cfg["start_date"])
        if cfg.get("strategy") != "momentum" else {},
        "strategy": cfg.get("strategy", "swing"), "rebalance": ranked.get("rebalance"), "paper": paper,
        "record": win_loss(book["closed"]), "benchmark": benchmark(feats, cfg),
        "anomalies": scan_anomalies(feats, model_scores, book, paper, ranked, cfg),
        "backtest": bt, "replay": rp, "research": research, "config": cfg, **ranked,
    }
    brief = OUT / "brief.md"
    if brief.exists():
        report["brief"] = brief.read_text()[:4000]
    if not args.dry_run:
        save_history(today, ranked, regime)
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
    paper_trades = load_trades(PAPER_PATH) if PAPER_PATH.exists() else trades.iloc[0:0]
    held = sorted((set(trades.ticker) if not trades.empty else set())
                  | (set(paper_trades.ticker) if not paper_trades.empty else set()))
    if not held:
        print("No positions to check.")
        return
    prices = data.download_prices(sorted(set(held) | {"SPY"}), period="1y")
    feats = build_features(prices)
    history = load_history()
    book = positions(trades, feats, history, cfg)
    live = data.latest_prices(held)
    funds = json.loads((OUT / "fundamentals.json").read_text()) if (OUT / "fundamentals.json").exists() else {}
    alerts = evaluate(book, feats, live, funds, cfg, today)
    dd_state, dd_msg = drawdown_state(book, cfg, today, persist=not args.dry_run)
    report.update({"generated_at": now.strftime("%Y-%m-%d %H:%M ET") + " (position check)",
                   "account": {k: book[k] for k in ("cash", "realized", "unrealized", "market_value", "equity", "return_pct")},
                   "positions": book["open"], "closed": book["closed"], "alerts": alerts,
                   "drawdown_state": dd_state, "drawdown_msg": dd_msg, "record": win_loss(book["closed"]),
                   "benchmark": benchmark(feats, cfg, live)})
    regime = report.get("regime") or {"light": "YELLOW", "max_new": 0, "risk_mult": 0}
    report["paper"] = run_paper(feats, funds, regime, cfg, today, history, live, execute=not args.dry_run)
    prev = report.get("anomalies") or {}
    if prev.get("stats"):
        try:
            held_now = {p["ticker"] for p in book["open"]}
            fresh = anomalies.detect(feats, sorted(held_now), prev["stats"], held=held_now,
                                     sectors=UNIVERSE, max_positions=cfg["max_positions"])
            report["anomalies"] = {**prev, "flags": fresh["flags"] + [f for f in prev.get("flags", [])
                                                                      if f["ticker"] not in held_now],
                                   "concentration": fresh["concentration"]}
        except Exception as e:
            print(f"anomaly check failed: {e}")
    write_outputs(report)
    if not args.no_notify:
        dispatch_alerts(alerts, cfg, today)


def write_outputs(report):
    OUT.mkdir(exist_ok=True)
    DOCS.mkdir(exist_ok=True)
    brief = OUT / "brief.json"
    if brief.exists():
        try:
            b = json.loads(brief.read_text())
            if b.get("date") == report.get("date", "")[:10] or b.get("date") == dt.datetime.now(ET).date().isoformat():
                report["analyst"] = b
        except Exception:
            pass
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
    ap.add_argument("--dry-run", action="store_true", help="don't advance the weekly rebalance marker")
    args = ap.parse_args()
    cfg = load_cfg()
    (OUT / "history").mkdir(parents=True, exist_ok=True)
    (cmd_plan if args.mode == "plan" else cmd_check)(cfg, args)


if __name__ == "__main__":
    main()
