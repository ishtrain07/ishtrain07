"""Renders the self-contained Habibi dashboard (docs/index.html)."""
import html
import json
import urllib.parse

CSS = """
:root{--bg:#f6f5f1;--card:#fff;--ink:#1d1d1b;--mute:#6b6a64;--line:#e4e2da;--buy:#0f7b4a;--buy-bg:#e5f4ec;
--sell:#b42318;--sell-bg:#fdecea;--warn:#a15c00;--warn-bg:#fff4e0;--acc:#4338ca;--chip:#efeee8}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#121211;--card:#1c1c1a;--ink:#ecebe6;--mute:#9c9b94;
--line:#2e2d2a;--buy:#4ccf8d;--buy-bg:#12291d;--sell:#ff8a7a;--sell-bg:#321614;--warn:#f0b454;--warn-bg:#2d2210;--acc:#a5b4fc;--chip:#262623}}
:root[data-theme=dark]{--bg:#121211;--card:#1c1c1a;--ink:#ecebe6;--mute:#9c9b94;--line:#2e2d2a;--buy:#4ccf8d;--buy-bg:#12291d;
--sell:#ff8a7a;--sell-bg:#321614;--warn:#f0b454;--warn-bg:#2d2210;--acc:#a5b4fc;--chip:#262623}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,sans-serif}
.wrap{max-width:1100px;margin:0 auto;padding:16px}
header{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:baseline;gap:8px;margin:8px 0 16px}
h1{font-size:22px;margin:0;letter-spacing:-.01em}h2{font-size:16px;margin:28px 0 10px;text-transform:uppercase;letter-spacing:.06em;color:var(--mute)}
.sub{color:var(--mute);font-size:13px}nav{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px}
nav a{font-size:13px;padding:4px 10px;border-radius:99px;background:var(--chip);color:var(--ink);text-decoration:none}
.grid{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(160px,1fr))}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px}
.kpi .v{font-size:24px;font-weight:650;font-variant-numeric:tabular-nums}.kpi .l{font-size:12px;color:var(--mute);text-transform:uppercase;letter-spacing:.05em}
.light{display:inline-flex;align-items:center;gap:8px;font-weight:650}.dot{width:12px;height:12px;border-radius:50%}
.GREEN{background:#16a34a}.YELLOW{background:#eab308}.RED{background:#dc2626}
.bar{height:8px;background:var(--chip);border-radius:99px;overflow:hidden;margin-top:8px}.bar i{display:block;height:100%;background:var(--buy)}
.order{border-left:4px solid var(--buy);background:var(--buy-bg)}.order.sell{border-left-color:var(--sell);background:var(--sell-bg)}
.order.warn{border-left-color:var(--warn);background:var(--warn-bg)}
.order h3{margin:0 0 6px;font-size:18px;display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap}
.tag{font-size:12px;font-weight:650;padding:2px 8px;border-radius:99px;background:var(--card);border:1px solid var(--line)}
.plan{display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:8px;margin:10px 0;font-variant-numeric:tabular-nums}
.plan div{background:var(--card);border-radius:8px;padding:6px 8px}.plan b{display:block;font-size:16px}.plan span{font-size:11px;color:var(--mute);text-transform:uppercase}
ul.why{margin:6px 0 0;padding-left:18px}ul.why li{margin:2px 0}
.tbl{overflow-x:auto;background:var(--card);border:1px solid var(--line);border-radius:12px}
table{border-collapse:collapse;width:100%;font-size:13px;font-variant-numeric:tabular-nums}
th,td{padding:8px 10px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}th{color:var(--mute);font-weight:600;font-size:12px}
td:first-child,th:first-child,td.l,th.l{text-align:left}tr:last-child td{border-bottom:0}
.pos{color:var(--buy)}.neg{color:var(--sell)}.mute{color:var(--mute)}
.news a{color:var(--acc);font-size:13px}.stack>*+*{margin-top:12px}
form{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:8px;align-items:end}
label{font-size:12px;color:var(--mute);display:grid;gap:4px;min-width:0}input,select,button{width:100%;min-width:0;font:inherit;padding:8px;border-radius:8px;border:1px solid var(--line);background:var(--bg);color:var(--ink)}
button{background:var(--ink);color:var(--bg);border:0;font-weight:600;cursor:pointer}
code{background:var(--chip);padding:2px 6px;border-radius:6px;font-size:13px;word-break:break-all}
.note{font-size:12px;color:var(--mute)}
details.sec{margin-top:18px;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:0 14px}
details.sec>summary{cursor:pointer;padding:12px 0;font-weight:600;list-style:none;display:flex;justify-content:space-between}
details.sec>summary::after{content:"+";color:var(--mute)}details.sec[open]>summary::after{content:"−"}
details.sec[open]{padding-bottom:14px}details.sec .tbl,details.sec .card{border-color:var(--line)}
.headline{font-size:17px;margin:16px 0 0;padding:12px 14px;border-radius:12px;background:var(--card);border:1px solid var(--line)}
@media (max-width:600px){.kpi .v{font-size:20px}}
"""


def e(x):
    return html.escape("" if x is None else str(x))


def pct(x, d=1):
    if x is None:
        return "-"
    cls = "pos" if x > 0 else "neg" if x < 0 else ""
    return f'<span class="{cls}">{x:+.{d}f}%</span>'


def money(x):
    if x is None:
        return "-"
    cls = "pos" if x > 0 else "neg" if x < 0 else ""
    return f'<span class="{cls}">{"+" if x > 0 else ""}${x:,.2f}</span>'


def render(r):
    cfg = r["config"]
    acct = r["account"]
    goal = cfg["goal_return_pct"]
    progress = max(0, min(100, acct["return_pct"] / goal * 100)) if goal else 0
    reg = r["regime"]
    parts = [f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Habibi Wealth Management</title>
<style>{CSS}</style></head><body><div class="wrap">
<header><div><h1>Habibi Wealth Management</h1><div class="sub">Updated {e(r['generated_at'])} · refreshes 9:00 ET + position checks 11:30 / 13:30 / 15:30 ET</div></div>
<div class="light"><span class="dot {e(reg['light'])}"></span>Market {e(reg['light'])}</div></header>
<nav><a href="#orders">Orders</a><a href="#positions">Positions</a><a href="#log">Log a trade</a></nav>
<div class="grid">
<div class="card kpi"><div class="l">Account value</div><div class="v">${acct['equity']:,.2f}</div><div class="sub">cash ${acct['cash']:,.2f}</div></div>
<div class="card kpi"><div class="l">Return</div><div class="v">{pct(acct['return_pct'], 2)}</div><div class="sub">realized {money(acct['realized'])} · open {money(acct['unrealized'])}</div></div>
<div class="card kpi"><div class="l">Goal +{goal}% by {e(cfg['goal_date'])}</div><div class="v">{progress:.0f}%</div><div class="bar"><i style="width:{progress:.0f}%"></i></div></div>
<div class="card kpi"><div class="l">Trading days left</div><div class="v">{r['trading_days_left']}</div><div class="sub">loss limit -{cfg['max_drawdown_halt_pct']}% halt</div></div>
</div>"""]

    parts.append(f'<div class="headline"><b>Today:</b> {e(_headline(r))}<div class="note">{e(reg["message"])}</div></div>')
    if r.get("drawdown_msg"):
        parts.append(f'<div class="card order sell" style="margin-top:12px"><b>{e(r["drawdown_msg"])}</b></div>')

    # ---- orders
    parts.append('<h2 id="orders">Today\'s orders</h2><div class="stack">')
    for a in r["alerts"]:
        parts.append(f'<div class="card order sell"><h3><span>SELL {e(a["ticker"])}</span><span class="tag">{e(a["action"])}</span></h3>'
                     f'<div>Sell <b>{a["shares"]}</b> shares at market (~${a["price"]}). {e(a["why"])}</div></div>')
    for b in r.get("buys", []):
        parts.append(_buy_card(b))
    if not r["alerts"] and not r.get("buys"):
        parts.append('<div class="card order warn"><b>No trades today.</b> Nothing meets the bar, and cash is a position. '
                     'Forcing trades is how accounts lose money.</div>')
    parts.append("</div>")
    if r.get("backups"):
        parts.append('<p class="note">Backups (qualify but no slot / sector limit): ' +
                     ", ".join(f'<b>{e(b["ticker"])}</b> ({b["score"]})' for b in r["backups"]) + "</p>")

    # ---- positions
    parts.append('<h2 id="positions">Open positions</h2>')
    if r["positions"]:
        rows = "".join(
            f'<tr><td><b>{e(p["ticker"])}</b>{"" if p["system_pick"] else " <span class=mute>(own pick)</span>"}</td>'
            f'<td>{p["shares"]}</td><td>${p["avg_cost"]}</td><td>${p["price"]}</td><td>{money(p["pnl"])}</td><td>{pct(p["pnl_pct"])}</td>'
            f'<td>${p["active_stop"]}</td><td>${p["t1"]} / ${p["t2"]}</td><td>{p["days_held"]}/{p["hold_days"]}</td><td>{e(p["sell_by"])}</td>'
            f'<td class="l"><b class="{"neg" if p["action"] != "HOLD" else "pos"}">{e(p["action"])}</b> <span class="mute">{e(p["why"])}</span></td></tr>'
            for p in r["positions"])
        parts.append('<div class="tbl"><table><tr><th>Ticker</th><th>Shares</th><th>Avg cost</th><th>Price</th><th>P&amp;L</th><th>%</th>'
                     f'<th>Stop</th><th>T1 / T2</th><th>Days</th><th>Sell by</th><th class="l">Action</th></tr>{rows}</table></div>')
    else:
        parts.append('<div class="card mute">No open positions. Log your fills below so the engine can track and alert you.</div>')

    # ---- watch / extended / avoid
    parts.append(f'<h2>Details</h2><details class="sec" id="watch"><summary>Watchlist: buy only if the trigger happens ({len(r.get("watch", []))})</summary>')
    if r.get("watch"):
        parts.append(_simple_table(r["watch"], [("Ticker", "ticker"), ("Score", "score"), ("Price", "price"),
                                                ("Setup", "setup"), ("RSI", "rsi"), ("Trigger", "action")]))
    else:
        parts.append('<div class="card mute">Nothing on watch.</div>')
    if r.get("extended"):
        parts.append('<p class="note"><b>Strong but stretched (do not chase):</b> ' +
                     "; ".join(f'{e(x["ticker"])}: {e(x["action"])}' for x in r["extended"]) + "</p>")
    if r.get("avoid"):
        parts.append('<p class="note"><b>Avoid today:</b> ' +
                     "; ".join(f'{e(x["ticker"])} ({e(x["why_not"])})' for x in r["avoid"][:8]) + "</p>")

    parts.append("</details>")
    # ---- macro
    parts.append('<details class="sec" id="macro"><summary>Macro and global read</summary><ul class="why">' +
                 "".join(f"<li>{e(n)}</li>" for n in r["macro_read"]) + "</ul>")
    if r.get("brief"):
        parts.append(f'<div class="card" style="margin-top:12px"><b>Analyst brief</b><div style="white-space:pre-wrap">{e(r["brief"])}</div></div>')
    mrows = "".join(f'<tr><td class="l">{e(m["label"])}</td><td>{m["last"]:,}</td><td>{pct(m["d1"], 2)}</td>'
                    f'<td>{pct(m["d5"])}</td><td>{pct(m["m1"])}</td></tr>' for m in r["macro"])
    parts.append(f'<div class="tbl" style="margin-top:12px"><table><tr><th class="l">Market</th><th>Last</th><th>1D</th><th>5D</th><th>1M</th></tr>{mrows}</table></div></details>')

    # ---- ranking
    parts.append('<details class="sec" id="ranking"><summary>Full ranking (top 40 of the universe)</summary>')
    rk = "".join(
        f'<tr><td><b>{e(x["ticker"])}</b></td><td class="l">{e(x["sector"])}</td><td>{x["score"]}</td><td>${x["price"]}</td>'
        f'<td>{pct(x["ret21"])}</td><td>{pct(x["ret63"])}</td><td>{x["rsi"]}</td><td class="l">{e(x["setup"])}{" ✓" if x["triggered"] else ""}</td>'
        f'<td>{"-" if not x["fwd_pe"] else round(x["fwd_pe"], 1)}</td><td>{e(x["next_earnings"] or "-")}</td>'
        f'<td>{"" if x["eligible"] else "<span class=neg>no</span>"}</td></tr>' for x in r.get("ranking", []))
    parts.append(f'<div class="tbl"><table><tr><th>Ticker</th><th class="l">Sector</th><th>Score</th><th>Price</th><th>1M</th><th>3M</th>'
                 f'<th>RSI</th><th class="l">Setup</th><th>Fwd P/E</th><th>Earnings</th><th>Trend ok</th></tr>{rk}</table></div></details>')

    parts.append(_log_form(cfg))
    for title, body in (("You vs the system", _tracking(r)), ("Backtest: does this rulebook work?", _backtest(r.get("backtest") or {})),
                        ("How decisions are made", _method(cfg))):
        parts.append(f'<details class="sec"><summary>{title}</summary>{body}</details>')
    parts.append('<p class="note" style="margin-top:32px">Rules-based signals for personal use, not financial advice. '
                 'No strategy guarantees profits; every trade can lose money. Size positions so a stop-out never hurts.</p>')
    parts.append("</div></body></html>")
    return "\n".join(parts)


def _buy_card(b):
    news = "".join(f'<li><a href="{e(n["url"])}" target="_blank" rel="noopener">{e(n["title"])}</a> '
                   f'<span class="mute">{e(n.get("source"))}</span></li>' for n in b.get("news", []) if n.get("url"))
    er = f' · earnings {e(b["next_earnings"])}' if b.get("next_earnings") else ""
    return f"""<div class="card order"><h3><span>BUY {e(b['ticker'])} <span class="mute" style="font-weight:400;font-size:14px">{e(b['name'])}</span></span>
<span class="tag">{e(b['setup']).upper()} · score {b['score']}</span></h3>
<div>Buy <b>{b['shares']} shares</b> (~<b>${b['dollars']:,.0f}</b>) with a <b>limit order at ${b['limit']}</b>. Risking ${b['risk_dollars']:.0f} if stopped.</div>
<div class="plan"><div><span>Entry</span><b>${b['entry']}</b></div><div><span>Stop-loss</span><b class="neg">${b['stop']}</b>{b['stop_pct']}%</div>
<div><span>Target 1 (sell ½)</span><b class="pos">${b['t1']}</b>+{b['t1_pct']}%</div><div><span>Target 2 (sell rest)</span><b class="pos">${b['t2']}</b>+{b['t2_pct']}%</div>
<div><span>Hold max</span><b>{b['hold_days']} days</b>sell by {e(b['sell_by'])}</div></div>
<b>Why</b><ul class="why">{''.join(f'<li>{e(x)}</li>' for x in b['reason'][:3])}</ul>
<div class="note">Momentum {b['momentum']} · RS {b['rs']} · Trend {b['trend']} · Fundamentals {b['fund']} · RSI {b['rsi']}{er}</div>
{f'<ul class="why news">{news}</ul>' if news else ''}</div>"""


def _simple_table(rows, cols):
    head = "".join(f'<th class="{"l" if i in (0, len(cols) - 1) else ""}">{c}</th>' for i, (c, _) in enumerate(cols))
    body = "".join("<tr>" + "".join(f'<td class="{"l" if i in (0, len(cols) - 1) else ""}">{e(x.get(k))}</td>'
                                    for i, (_, k) in enumerate(cols)) + "</tr>" for x in rows)
    return f'<div class="tbl"><table><tr>{head}</tr>{body}</table></div>'


def _log_form(cfg):
    repo = cfg["github_repo"]
    edit = f"https://github.com/{repo}/edit/main/habibi/trades.csv"
    issue = f"https://github.com/{repo}/issues/new?labels=trade&title="
    return f"""<details class="sec" id="log" open><summary>Log a trade you actually made</summary><div>
<form onsubmit="return mk(event)"><label>Date<input id="d" type="date" required></label>
<label>Ticker<input id="t" required placeholder="NVDA" style="text-transform:uppercase"></label>
<label>Side<select id="s"><option>BUY</option><option>SELL</option></select></label>
<label>Shares<input id="n" type="number" step="0.0001" required></label>
<label>Fill price (USD)<input id="p" type="number" step="0.0001" required></label>
<label>Note<input id="o" placeholder="optional"></label><button>Create log line</button></form>
<div id="out" style="margin-top:12px;display:none"><div>1. Copy this line: <code id="line"></code> <button type="button" onclick="cp()">Copy</button></div>
<div style="margin-top:6px">2. <a id="ed" href="{e(edit)}" target="_blank">Open trades.csv on GitHub</a>, paste it as a new last line, then Commit.
The next engine run picks it up. <span class="mute">(Or send it to Claude in chat.)</span></div>
<div class="note" style="margin-top:6px">If Issues are enabled on the repo: <a id="is" target="_blank">submit as an issue</a> and the robot appends it for you.</div></div></div>
<script>
document.getElementById('d').valueAsDate=new Date();
function mk(ev){{ev.preventDefault();const v=id=>document.getElementById(id).value.trim();
const l=[v('d'),v('t').toUpperCase(),v('s'),v('n'),v('p'),0,v('o').replace(/,/g,' ')].join(',');
document.getElementById('line').textContent=l;document.getElementById('out').style.display='block';
document.getElementById('is').href={json.dumps(issue)}+encodeURIComponent('TRADE '+l)+'&body='+encodeURIComponent(l);return false}}
function cp(){{navigator.clipboard&&navigator.clipboard.writeText(document.getElementById('line').textContent)}}
</script></details>"""


def _tracking(r):
    sp = r.get("system_paper") or {}
    closed = r.get("closed") or []
    you = r["account"]["return_pct"]
    out = [f'<h2 id="track">You vs the system</h2><div class="grid">'
           f'<div class="card kpi"><div class="l">Your account</div><div class="v">{pct(you, 2)}</div></div>'
           f'<div class="card kpi"><div class="l">System paper (all its buys)</div><div class="v">{pct(sp.get("return_pct"), 2)}</div>'
           f'<div class="sub">{len(sp.get("trades", []))} signals since {e(r["config"]["start_date"])}</div></div></div>']
    if closed:
        out.append('<h2>Your closed trades</h2>' + _simple_table(closed, [("Date", "date"), ("Ticker", "ticker"), ("Shares", "shares"),
                                                                           ("Sold at", "price"), ("Avg cost", "avg_cost"), ("P&L $", "pnl"), ("P&L %", "pnl_pct")]))
    if sp.get("trades"):
        out.append('<h2>System picks (paper)</h2>' + _simple_table(sp["trades"][-20:], [
            ("Date", "date"), ("Ticker", "ticker"), ("Entry", "entry"), ("Status", "status"),
            ("Exit", "exit_price"), ("Why", "exit_reason"), ("P&L $", "pnl")]))
    missed = [p for p in r.get("positions", []) if p.get("system_pick") and p.get("plan_entry")]
    if missed:
        out.append('<p class="note">Fill quality vs plan: ' + "; ".join(
            f'{e(p["ticker"])} paid ${p["avg_cost"]} vs plan ${p["plan_entry"]} ({(p["avg_cost"] / p["plan_entry"] - 1) * 100:+.2f}%)'
            for p in missed) + "</p>")
    return "".join(out)


def _backtest(bt):
    if not bt.get("n"):
        return '<h2 id="backtest">Backtest</h2><div class="card mute">Backtest not available yet.</div>'
    setups = "; ".join(f'{k}: {v["n"]} trades, {v["win_rate"]}% win, {v["avg_r"]}R avg' for k, v in bt["by_setup"].items())
    return f"""<h2 id="backtest">Backtest of these exact rules ({e(bt['from'])} to {e(bt['to'])})</h2><div class="grid">
<div class="card kpi"><div class="l">Trades</div><div class="v">{bt['n']}</div><div class="sub">avg {bt['avg_days']} days held</div></div>
<div class="card kpi"><div class="l">Win rate</div><div class="v">{bt['win_rate']}%</div><div class="sub">avg win {bt['avg_win_pct']}% · loss {bt['avg_loss_pct']}%</div></div>
<div class="card kpi"><div class="l">Expectancy</div><div class="v">{bt['avg_r']}R</div><div class="sub">per trade, in units of risk</div></div>
<div class="card kpi"><div class="l">Max drawdown</div><div class="v">{bt['max_drawdown_pct']}%</div><div class="sub">total {bt['total_return_pct']:+}%</div></div>
<div class="card kpi"><div class="l">Odds of +20% in 5 weeks</div><div class="v">{bt.get('p_25d_gain_20pct')}%</div><div class="sub">+10%: {bt.get('p_25d_gain_10pct')}% · loss: {bt.get('p_25d_loss')}%</div></div>
</div><p class="note">{e(setups)}. Median 5-week return {bt.get('median_25d_pct')}%. Caveats: uses today's stock list (survivorship bias), no historical
earnings filter, fills at signal-day close. Treat as a sanity check, not a promise. Refreshed weekly ({e(bt.get('run_date'))}).</p>"""


def _method(cfg):
    return f"""<h2 id="method">How decisions are made</h2><div class="card"><ol class="why">
<li><b>Market light</b>: S&amp;P 500 vs its 50/200-day averages + VIX. GREEN = up to {cfg['max_positions']} positions at full risk; YELLOW = half risk, top grades only; RED = no buys.</li>
<li><b>Filters</b>: price &gt; ${cfg['min_price']}, &gt;${cfg['min_dollar_volume'] / 1e6:.0f}M traded daily, above the 200-day average. No penny stocks, no downtrends.</li>
<li><b>Score 0-100</b> (quant multi-factor, ranked across ~90 names): momentum 30% (6/3/1-month), relative strength vs S&amp;P 15%, trend quality 20%,
entry setup 25%, fundamentals 10% (growth, margins, forward P/E vs growth), ±5 for leading/lagging sector.</li>
<li><b>Setups</b>: PULLBACK = dip to the 20-day EMA in an uptrend that bounces green (RSI 35-58). BREAKOUT = new 20-day high on ≥1.4x volume. Stretched stocks (&gt;3 ATR above EMA or RSI &gt; 76) are never chased.</li>
<li><b>BUY</b> = score ≥ {cfg['buy_score_threshold']} + setup triggered today + no earnings inside the hold window + slot free (max {cfg['max_per_sector']} per sector).</li>
<li><b>Exits</b>: stop = recent swing low or 1-2 ATR (never more than 8%). Sell half at 1.5x risk and move the stop to breakeven, sell the rest at 3x risk or on the trailing stop.
Time stop after {cfg['hold_days']['pullback']} days (pullback) / {cfg['hold_days']['breakout']} (breakout). Always out before earnings.</li>
<li><b>Sizing</b>: each trade risks {cfg['risk_per_trade_pct']}% of the account (~${cfg['starting_capital_usd'] * cfg['risk_per_trade_pct'] / 100:.0f}); max {cfg['max_position_pct']}% in one stock.
Account down {cfg['max_drawdown_halt_pct']}% = stop buying; down {cfg['max_drawdown_liquidate_pct']}% = go to cash.</li></ol></div>"""


def _headline(r):
    sells = [f'{a["action"].lower()} {a["ticker"]}' for a in r["alerts"]]
    buys = [f'buy {b["ticker"]}' for b in r.get("buys", [])]
    holds = [p["ticker"] for p in r.get("positions", []) if p.get("action") == "HOLD"]
    bits = sells + buys
    if holds:
        bits.append("hold " + ", ".join(holds))
    return (", ".join(bits).capitalize() + ".") if bits else "Nothing to do. Stay in cash and check back tomorrow."
