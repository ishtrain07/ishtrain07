"""Market data: prices (yfinance, Stooq fallback), fundamentals, earnings, news."""
import datetime as dt
import io
import time

import pandas as pd
import requests

COLS = ["Open", "High", "Low", "Close", "Volume"]


def _clean(df):
    df = df[[c for c in COLS if c in df.columns]].dropna(subset=["Close"])
    df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
    return df[~df.index.duplicated(keep="last")]


def download_prices(tickers, period="2y"):
    """Return {ticker: OHLCV DataFrame}. Tries a yfinance batch, then fills gaps from Stooq."""
    import yfinance as yf

    out = {}
    for attempt in range(3):
        missing = [t for t in tickers if t not in out]
        if not missing:
            break
        try:
            raw = yf.download(missing, period=period, interval="1d", group_by="ticker",
                              auto_adjust=True, threads=True, progress=False)
            for t in missing:
                try:
                    df = raw[t] if isinstance(raw.columns, pd.MultiIndex) else raw
                    df = _clean(df)
                    if len(df) > 30:
                        out[t] = df
                except KeyError:
                    pass
        except Exception as e:  # network / rate limit
            print(f"yfinance batch failed (attempt {attempt + 1}): {e}")
        time.sleep(2 * (attempt + 1))

    for t in [t for t in tickers if t not in out]:
        df = _stooq(t)
        if df is not None:
            out[t] = df
    missing = [t for t in tickers if t not in out]
    if missing:
        print(f"No price data for: {', '.join(missing)}")
    return out


def _stooq(ticker):
    if ticker.startswith("^") or "=" in ticker or "-" in ticker:
        return None
    sym = ticker.lower().replace(".", "-") + ".us"
    try:
        r = requests.get(f"https://stooq.com/q/d/l/?s={sym}&i=d", timeout=15)
        df = pd.read_csv(io.StringIO(r.text), parse_dates=["Date"], index_col="Date")
        df = _clean(df)
        return df.iloc[-520:] if len(df) > 30 else None
    except Exception:
        return None


def latest_prices(tickers):
    """Intraday last price for position checks (falls back silently)."""
    import yfinance as yf

    prices = {}
    try:
        raw = yf.download(list(tickers), period="1d", interval="5m", group_by="ticker",
                          progress=False, auto_adjust=True, threads=True)
        for t in tickers:
            try:
                df = raw[t] if isinstance(raw.columns, pd.MultiIndex) else raw
                s = df["Close"].dropna()
                if len(s):
                    prices[t] = float(s.iloc[-1])
            except KeyError:
                pass
    except Exception as e:
        print(f"intraday fetch failed: {e}")
    return prices


def fundamentals(tickers):
    """Forward/trailing P/E, growth, margins, next earnings date. Best effort per ticker."""
    import yfinance as yf

    out = {}
    today = dt.date.today()
    for t in tickers:
        info = {}
        try:
            tk = yf.Ticker(t)
            raw = tk.info or {}
            info = {
                "name": raw.get("shortName") or t,
                "forward_pe": raw.get("forwardPE"),
                "trailing_pe": raw.get("trailingPE"),
                "revenue_growth": raw.get("revenueGrowth"),
                "earnings_growth": raw.get("earningsGrowth"),
                "profit_margin": raw.get("profitMargins"),
                "market_cap": raw.get("marketCap"),
                "target_mean": raw.get("targetMeanPrice"),
                "recommendation": raw.get("recommendationKey"),
                "quote_type": raw.get("quoteType"),
            }
            info["next_earnings"] = _next_earnings(tk, raw, today)
        except Exception as e:
            print(f"fundamentals failed for {t}: {e}")
        out[t] = info
        time.sleep(0.15)
    return out


def _next_earnings(tk, raw, today):
    candidates = []
    for key in ("earningsTimestamp", "earningsTimestampStart"):
        ts = raw.get(key)
        if ts:
            candidates.append(dt.datetime.utcfromtimestamp(ts).date())
    try:
        cal = tk.calendar
        dates = cal.get("Earnings Date", []) if isinstance(cal, dict) else []
        candidates += [d if isinstance(d, dt.date) else pd.Timestamp(d).date() for d in dates]
    except Exception:
        pass
    future = sorted(d for d in candidates if d >= today)
    return future[0].isoformat() if future else None


def news(ticker, n=3):
    import yfinance as yf

    items = []
    try:
        for it in (yf.Ticker(ticker).news or [])[: n * 2]:
            c = it.get("content", it)
            title = c.get("title")
            url = (c.get("canonicalUrl") or {}).get("url") if isinstance(c.get("canonicalUrl"), dict) else c.get("link")
            src = (c.get("provider") or {}).get("displayName") if isinstance(c.get("provider"), dict) else c.get("publisher")
            if title:
                items.append({"title": title, "url": url, "source": src})
            if len(items) >= n:
                break
    except Exception:
        pass
    return items
