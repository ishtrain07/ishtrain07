"""CDR study: can the strategy run on CAD-hedged Canadian Depositary Receipts instead of US shares?

1. Which universe names have a CDR (Yahoo ".NE" quote whose daily returns track the US stock).
2. How closely each CDR tracks its US share (return gap, tracking error) and how liquid it is.
3. The live strategy (learning model top 3, hold while top-5, 8% stop, 10% brake) backtested on
   only the CDR-available names, with a CDR trading cost, vs the full US universe in a USD account.

  python -m habibi.cdr          # writes habibi/output/cdr.json
"""
import json

import numpy as np
import pandas as pd

from . import adaptive, data
from .indicators import add_features
from .research import OUT, precompute, rotation_sim
from .universe import SECTOR_ETF, UNIVERSE

STOCKS = [t for t, s in UNIVERSE.items() if s != "ETF"]
LIVE = dict(top_n=3, rank_col="adaptive", stop_pct=0.08, dd_brake=0.10, hold_rank=5)


def cdr_match(us, cdr):
    """Tracking stats of a CDR vs its US share over their common dates."""
    a = us.Close.pct_change()
    b = cdr.Close.pct_change()
    j = pd.concat([a, b], axis=1, keys=["us", "cdr"]).dropna()
    j = j[(j.us.abs() < 0.35) & (j.cdr.abs() < 0.35)]   # drop unadjusted split days
    if len(j) < 40:
        return None
    gap = j.cdr - j.us
    dollar_vol = (cdr.Close * cdr.Volume).tail(60).median()
    return {"days": int(len(j)), "corr": round(float(j.us.corr(j.cdr)), 3),
            "gap_ann_pct": round(float(gap.mean() * 252 * 100), 2),
            "tracking_err_ann_pct": round(float(gap.std() * np.sqrt(252) * 100), 2),
            "median_cad_volume_60d": round(float(dollar_vol), 0),
            "cdr_price": round(float(cdr.Close.iloc[-1]), 2)}


def cdr_prices(stocks):
    """Yahoo ".NE" daily bars, one ticker at a time with retries (batch requests get throttled).
    yfinance only: the Stooq fallback would map these to the wrong symbols."""
    import time
    import yfinance as yf
    out, seen = {}, {}
    for t in stocks:
        for attempt in range(3):
            try:
                df = yf.Ticker(f"{t}.NE").history(period="1y", interval="1d", auto_adjust=True)
                df = df.dropna(subset=["Close"])
                df.index = df.index.tz_localize(None).normalize()
                seen[t] = len(df)
                if len(df) > 40:
                    out[f"{t}.NE"] = df
                break
            except Exception as e:
                seen[t] = f"error: {e}"
                time.sleep(2 * (attempt + 1))
        time.sleep(0.4)
    print("CDR quotes found:", {t: n for t, n in seen.items() if n})
    return out


def quote_spreads(tickers):
    import yfinance as yf
    out = {}
    for t in tickers:
        try:
            info = yf.Ticker(f"{t}.NE").info
            bid, ask = info.get("bid"), info.get("ask")
            if bid and ask and ask > bid > 0:
                out[t] = round((ask - bid) / ((ask + bid) / 2) * 100, 3)
        except Exception as e:
            print("quote failed", t, e)
    return out


def main():
    us_tickers = sorted(set(UNIVERSE) | set(SECTOR_ETF.values()) | {"^VIX", "SPY", "QQQ"})
    prices = data.download_prices(us_tickers, period="3y")
    cdr_px = cdr_prices(STOCKS)

    match = {}
    for t in STOCKS:
        c = cdr_px.get(f"{t}.NE")
        if c is None or t not in prices:
            continue
        m = cdr_match(prices[t], c)
        if m:
            print("candidate", t, m)
        if m and m["corr"] > 0.7:
            match[t] = m
    avail = sorted(match)
    spreads = quote_spreads(avail)
    for t, s in spreads.items():
        match[t]["quoted_spread_pct"] = s
    print(len(avail), "CDRs:", avail)

    feats = {t: add_features(df) for t, df in prices.items()}
    pre = precompute(feats, 480)
    uni = [t for t in UNIVERSE if t in feats and len(feats[t]) > 260]
    m = adaptive.model(feats, uni)
    for d, (regime, sc) in pre.items():
        sc["adaptive"] = m["scores"].loc[d].reindex(sc.index) if d in m["scores"].index else np.nan
    pre_cdr = {d: (r, sc[sc.index.isin(avail)]) for d, (r, sc) in pre.items()}

    med_spread = float(np.median(list(spreads.values()))) / 100 if spreads else 0.003
    dates = list(pre)
    mid = dates[len(dates) // 2]
    periods = {"full": (dates[0], dates[-1]), "half1": (dates[0], mid), "half2": (mid, dates[-1])}
    runs = {
        "US shares, USD account (0.1% cost)": (pre, 0.001),
        "US shares, CAD account (1.5% FX fee)": (pre, 0.015),
        f"CDRs only, half the median spread + hedge ({med_spread / 2 + 0.0005:.2%})": (pre_cdr, med_spread / 2 + 0.0005),
        "CDRs only, pessimistic 0.5% per side": (pre_cdr, 0.005),
    }
    res = {"cdr_available": avail, "cdr_count": len(avail), "universe_stocks": len(STOCKS), "match": match,
           "median_quoted_spread_pct": round(med_spread * 100, 3),
           "periods": {k: [str(a.date()), str(b.date())] for k, (a, b) in periods.items()}, "results": {}}
    for name, (p, cost) in runs.items():
        res["results"][name] = {k: rotation_sim(feats, p, start=a, end=b, cost=cost, **LIVE)
                                for k, (a, b) in periods.items()}
        print(name, res["results"][name]["full"])

    last = dates[-1]
    _, sc = pre[last]
    ranked = sc[sc.eligible & (sc.rsi < 80)].sort_values("adaptive", ascending=False)
    res["today_top10"] = [{"ticker": t, "rank": i + 1, "cdr": t in avail} for i, t in enumerate(ranked.index[:10])]
    OUT.mkdir(exist_ok=True)
    (OUT / "cdr.json").write_text(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
