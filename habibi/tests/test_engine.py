"""End-to-end test on synthetic prices (no network)."""
import datetime as dt
import json

import numpy as np
import pandas as pd
import pytest

from habibi import data, run
from habibi.universe import all_price_tickers


def fake_prices(tickers, period="2y"):
    rng = np.random.default_rng(7)
    idx = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=520)
    out = {}
    for i, t in enumerate(tickers):
        drift = 0.0012 if i % 3 else -0.0004
        r = rng.normal(drift, 0.018, len(idx))
        c = 100 * np.exp(np.cumsum(r))
        o = c * (1 + rng.normal(0, 0.004, len(idx)))
        out[t] = pd.DataFrame({"Open": o, "High": np.maximum(o, c) * 1.01, "Low": np.minimum(o, c) * 0.99,
                               "Close": c, "Volume": rng.integers(2e6, 9e6, len(idx)).astype(float)}, index=idx)
    if "^VIX" in out:
        out["^VIX"]["Close"] = 15.0
    return out


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    out = tmp_path / "output"
    (out / "history").mkdir(parents=True)
    monkeypatch.setattr(run, "OUT", out)
    monkeypatch.setattr(run, "DOCS", tmp_path / "docs")
    monkeypatch.setattr("habibi.portfolio.HISTORY", out / "history")
    monkeypatch.setattr(data, "download_prices", fake_prices)
    monkeypatch.setattr(data, "latest_prices", lambda t: {})
    monkeypatch.setattr(data, "news", lambda t, n=3: [])
    monkeypatch.setattr(data, "fundamentals", lambda ts: {t: {"name": t, "forward_pe": 25, "revenue_growth": 0.2,
                                                              "profit_margin": 0.2, "next_earnings": None} for t in ts})
    trades = tmp_path / "trades.csv"
    buy_day = (dt.date.today() - dt.timedelta(days=6)).isoformat()
    trades.write_text("date,ticker,side,shares,price,fees,note\n"
                      f"{buy_day},AAPL,BUY,2,100,0,test\n{buy_day},MSFT,BUY,3,90,0,\n"
                      f"{dt.date.today().isoformat()},MSFT,SELL,1,95,0,\n")
    monkeypatch.setattr(run, "ROOT", tmp_path)
    (tmp_path / "config.json").write_text((run.Path(run.__file__).parent / "config.json").read_text())
    return tmp_path


class Args:
    no_notify = True
    backtest = True
    skip_fundamentals = False


def test_plan_end_to_end(sandbox):
    cfg = run.load_cfg()
    run.cmd_plan(cfg, Args())
    rep = json.loads((sandbox / "output" / "latest.json").read_text())
    assert rep["regime"]["light"] in {"GREEN", "YELLOW", "RED"}
    assert len(rep["ranking"]) > 10
    assert {p["ticker"] for p in rep["positions"]} == {"AAPL", "MSFT"}
    msft = next(p for p in rep["positions"] if p["ticker"] == "MSFT")
    assert msft["shares"] == 2 and msft["partial"]
    for b in rep["buys"]:
        assert b["stop"] < b["entry"] < b["t1"] < b["t2"]
        assert b["dollars"] <= cfg["starting_capital_usd"] * cfg["max_position_pct"] / 100 + 1
        assert b["hold_days"] >= 3
    assert rep["backtest"]["n"] > 0
    html = (sandbox / "docs" / "index.html").read_text()
    assert "Habibi Wealth Management" in html
    # intraday check reuses latest.json
    run.cmd_check(cfg, Args())


def test_calendar():
    from habibi.strategy import add_trading_days, trading_days_between
    fri = dt.date(2026, 9, 25)
    assert add_trading_days(fri, 1) == dt.date(2026, 9, 28)
    assert trading_days_between(fri, dt.date(2026, 10, 2)) == 5
    assert add_trading_days(dt.date(2026, 11, 25), 1) == dt.date(2026, 11, 27)
