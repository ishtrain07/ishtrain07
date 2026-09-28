# Habibi Wealth Management

A rules-based swing trading engine for a small (~$2,000 USD) Wealthsimple account.
Every weekday it researches ~90 liquid US stocks and ETFs, then publishes **straight
decisions**: what to buy (shares, limit price, stop, targets, sell-by date), what to
sell, and why. It tracks the trades you actually make and alerts you when to exit.

> Not financial advice. No strategy guarantees profits. The engine's job is to take
> good-odds trades with small, pre-defined losses, and to sit in cash when nothing qualifies.

## Daily rhythm (times ET / IST)

| ET | IST | What happens |
|---|---|---|
| 09:00 | 18:30 | **Morning plan**: macro + global markets, regime light, full ranking, today's BUY/SELL orders, email + push |
| 09:30 | 19:00 | Market opens: place the limit orders from the dashboard |
| 11:30, 13:30, 15:30 | 21:00, 23:00, 01:00 | **Position checks**: stop / target / time-stop hits trigger an urgent SELL alert |

## What you do

1. Open the dashboard after the 09:00 ET run.
2. Place the **SELL** orders first, then the **BUY** limit orders (fractional shares are fine on Wealthsimple).
3. Log every fill: use the dashboard's *Log a trade* form, or add a line to `habibi/trades.csv`:
   `2026-09-28,NVDA,BUY,2.5,181.20,0,note`
4. When a SELL alert arrives, sell and log it.

## How it decides

See the *Method* section on the dashboard. In short: a market regime light (S&P trend + VIX),
then liquidity and uptrend filters, then a multi-factor score (momentum, relative strength, trend,
entry setup, fundamentals, sector). BUY needs a triggered PULLBACK or BREAKOUT setup, and no
earnings report inside the hold window. Exits are an ATR stop, half off at 1.5R, the rest at 3R
or on the trailing stop, a time stop, and always out before earnings. Each trade risks 1.5% of the account.
New buys stop at -10% and everything goes to cash at -13%.

## Setup (one time)

1. **Merge this branch into `main`**: scheduled GitHub Actions only run on the default branch.
2. **Dashboard**: Settings → Pages → *Deploy from a branch* → `main` / `/docs`.
   It will be at https://ishtrain07.github.io/ishtrain07/
3. **Phone push**: install the free **ntfy** app, subscribe to a hard-to-guess topic (e.g. `habibi-8f3k2q`),
   and add it as repo secret `NTFY_TOPIC` (Settings → Secrets and variables → Actions).
4. **Email**: create a Gmail App Password (Google Account → Security → App passwords), then add
   secrets `SMTP_USER` (your Gmail), `SMTP_PASSWORD` (the app password), `ALERT_EMAIL` (recipient).
5. Optional: enable Issues (Settings → General → Features) and set repo variable `HABIBI_ISSUES=1`
   to get alerts as GitHub issues too and to log trades from the dashboard in one tap.
6. Edit `habibi/config.json` → `starting_capital_usd` to the exact USD amount that lands in the account.

Run manually: Actions → *Habibi engine* → *Run workflow*.

## Run locally

```bash
pip install -r habibi/requirements.txt
python -m habibi.run plan --no-notify     # full research, writes docs/index.html
python -m habibi.run check --no-notify    # positions only
python -m pytest habibi/tests -q          # synthetic-data tests
```

## Files

| Path | Purpose |
|---|---|
| `config.json` | capital, risk limits, goal |
| `trades.csv` | **your actual trades** (source of truth for positions) |
| `universe.py` | tickers, sectors, macro symbols, FOMC and holiday calendars |
| `strategy.py` | regime, scoring, buckets, trade plans |
| `portfolio.py` | positions, P&L, sell alerts, system-vs-you paper tracking |
| `backtest.py` | historical test of the same rules |
| `output/` | `latest.json`, daily `history/` plans (the engine's memory), backtest |
| `../docs/index.html` | the dashboard |
