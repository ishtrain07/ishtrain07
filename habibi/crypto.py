"""Crypto sleeve research: does a simple trend rule beat buy-and-hold on BTC / ETH (and QNT)?

Rules tested (daily closes, signal acts next day, 0.25% cost per switch):
  hold       : buy and hold
  trend50_200: hold while close > 50-day and 50-day > 200-day, else cash
  trend20_100: same with 20/100
  dual       : equal-weight BTC+ETH, each only while above its 50/200 trend
Each is reported on the full window and on two separate halves.

  python -m habibi.crypto        # writes habibi/output/crypto.json
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import data

OUT = Path(__file__).parent / "output"
COST = 0.0025


def stats(eq):
    eq = eq.dropna()
    if len(eq) < 30:
        return {}
    dd = (eq / eq.cummax() - 1).min()
    rets = eq.pct_change().dropna()
    w25 = (eq.shift(-25) / eq - 1).dropna()
    return {"total_pct": round(float(eq.iloc[-1] / eq.iloc[0] - 1) * 100, 1),
            "max_dd_pct": round(float(dd) * 100, 1),
            "vol_pct": round(float(rets.std() * np.sqrt(365)) * 100, 1),
            "p25_loss": round(float((w25 < 0).mean() * 100), 1) if len(w25) else None,
            "med25": round(float(w25.median() * 100), 1) if len(w25) else None}


def trend_equity(close, fast, slow):
    on = (close > close.rolling(fast).mean()) & (close.rolling(fast).mean() > close.rolling(slow).mean())
    pos = on.shift(1).fillna(False).astype(float)          # act the day after the signal
    ret = close.pct_change().fillna(0) * pos
    ret -= pos.diff().abs().fillna(0) * COST
    return (1 + ret).cumprod(), on


def main():
    tick = {"BTC": "BTC-USD", "ETH": "ETH-USD", "QNT": "QNT-USD"}
    px = data.download_prices(list(tick.values()), period="3y")
    closes = {k: px[v].Close for k, v in tick.items() if v in px}
    res = {"results": {}, "now": {}}
    idx = closes["BTC"].index[200:]
    mid = idx[len(idx) // 2]
    periods = {"full": (idx[0], idx[-1]), "half1": (idx[0], mid), "half2": (mid, idx[-1])}
    curves = {}
    for k, c in closes.items():
        c = c.loc[idx[0] - pd.Timedelta(days=1):]
        curves[f"{k} buy & hold"] = c / c.iloc[0]
        for f, s in ((50, 200), (20, 100)):
            full = closes[k]
            eq, on = trend_equity(full, f, s)
            curves[f"{k} trend {f}/{s}"] = eq
            if (f, s) == (50, 200):
                res["now"][k] = {"price": round(float(full.iloc[-1]), 2), "in_trend": bool(on.iloc[-1]),
                                 "sma50": round(float(full.rolling(50).mean().iloc[-1]), 2),
                                 "sma200": round(float(full.rolling(200).mean().iloc[-1]), 2)}
    if "BTC" in closes and "ETH" in closes:
        b, _ = trend_equity(closes["BTC"], 50, 200)
        e, _ = trend_equity(closes["ETH"], 50, 200)
        curves["BTC+ETH dual trend 50/200"] = (b.pct_change().fillna(0) * 0.5 + e.pct_change().fillna(0) * 0.5 + 1).cumprod()
    for name, eq in curves.items():
        res["results"][name] = {}
        for p, (a, z) in periods.items():
            seg = eq.loc[a:z]
            res["results"][name][p] = stats(seg / seg.iloc[0]) if len(seg) else {}
        print(name, res["results"][name]["full"])
    res["periods"] = {k: [str(a.date()), str(z.date())] for k, (a, z) in periods.items()}
    OUT.mkdir(exist_ok=True)
    (OUT / "crypto.json").write_text(json.dumps(res, indent=1))
    print(res["now"])


if __name__ == "__main__":
    main()
