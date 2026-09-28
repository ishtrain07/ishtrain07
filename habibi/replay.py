"""Walk-forward replay: what would the engine have told you each morning, and what happened?

For each of the last N trading days D, the engine only sees data up to the close
of D-1 (exactly what the 09:00 ET run sees). Orders are filled on day D if the
open or the low reaches the limit price, then managed with the plan's exits.

  python -m habibi.replay [days]      # writes habibi/output/replay.json
"""
import json
import sys
from pathlib import Path

import pandas as pd

from . import data
from .backtest import simulate_trade
from .indicators import add_features
from .strategy import market_regime, rank_and_bucket
from .universe import SECTOR_ETF, UNIVERSE

ROOT = Path(__file__).parent
OUT = ROOT / "output"


def replay(feats, funds, cfg, days=10):
    spy_idx = feats["SPY"].index
    out = []
    for D in spy_idx[-days:]:
        trunc = {t: f.loc[:D - pd.Timedelta(days=1)] for t, f in feats.items()}
        trunc = {t: f for t, f in trunc.items() if len(f) > 30}
        vix = trunc.get("^VIX")
        regime = market_regime(trunc["SPY"], float(vix.Close.iloc[-1]) if vix is not None else None)
        cap = float(cfg["starting_capital_usd"])
        ranked = rank_and_bucket(trunc, funds, regime, cfg, cap, cap, [], D.date())
        picks = []
        for b in ranked["buys"][:3]:
            fut = feats[b["ticker"]].loc[D:]
            day = fut.iloc[0]
            if day.Open <= b["limit"]:
                fill = float(day.Open)
            elif day.Low <= b["limit"]:
                fill = b["limit"]
            else:
                picks.append({**_brief(b), "filled": False, "note": f"gapped up to {day.Open:.2f}, no fill (never chase)"})
                continue
            dist = fill - b["stop"]
            res = simulate_trade(fut, fill, b["stop"], b["t1"], b["t2"], b["hold_days"], max(dist, 0.01) / 1.5)
            row = {**_brief(b), "filled": True, "fill": round(fill, 2)}
            if res:
                row.update({"status": "closed", "exit_date": res["exit_date"], "exit_price": res["exit_price"],
                            "exit_reason": res["exit_reason"], "pnl": round(res["pnl_per_share"] * b["shares"], 2),
                            "pnl_pct": round(res["pnl_per_share"] / fill * 100, 2)})
            else:
                last = float(fut.Close.iloc[-1])
                row.update({"status": "open", "last": round(last, 2),
                            "pnl": round((last - fill) * b["shares"], 2), "pnl_pct": round((last / fill - 1) * 100, 2)})
            picks.append(row)
        out.append({"date": D.date().isoformat(), "regime": regime["light"], "picks": picks,
                    "watch": [w["ticker"] for w in ranked["watch"][:5]]})
    filled = [p for d in out for p in d["picks"] if p.get("filled")]
    return {
        "days": out,
        "n_picks": sum(len(d["picks"]) for d in out),
        "n_filled": len(filled),
        "n_winners": sum(1 for p in filled if p["pnl"] > 0),
        "pnl": round(sum(p["pnl"] for p in filled), 2),
        "empty_days": sum(1 for d in out if not d["picks"]),
    }


def _brief(b):
    return {k: b[k] for k in ("ticker", "setup", "score", "shares", "limit", "stop", "t1", "t2", "hold_days", "reason")}


def main():
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    cfg = json.loads((ROOT / "config.json").read_text())
    tickers = sorted(set(UNIVERSE) | set(SECTOR_ETF.values()) | {"^VIX", "SPY"})
    feats = {t: add_features(df) for t, df in data.download_prices(tickers, period="2y").items()}
    fp = OUT / "fundamentals.json"
    funds = json.loads(fp.read_text()) if fp.exists() else {}
    res = replay(feats, funds, cfg, days)
    (OUT / "replay.json").write_text(json.dumps(res, indent=1, default=str))
    for d in res["days"]:
        print(d["date"], d["regime"], [(p["ticker"], p.get("status", "no fill"), p.get("pnl")) for p in d["picks"]])
    print({k: v for k, v in res.items() if k != "days"})


if __name__ == "__main__":
    main()
