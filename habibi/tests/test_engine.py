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
    monkeypatch.setattr("habibi.paper.PATH", out / "paper_trades.csv")
    monkeypatch.setattr(run, "PAPER_PATH", out / "paper_trades.csv")
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
    dry_run = False


def test_plan_end_to_end(sandbox):
    cfg = run.load_cfg()
    cfg["strategy"] = "swing"
    run.cmd_plan(cfg, Args())
    rep = json.loads((sandbox / "output" / "latest.json").read_text())
    assert rep["regime"]["light"] in {"GREEN", "YELLOW", "RED"}
    assert len(rep["ranking"]) > 10
    assert {p["ticker"] for p in rep["positions"]} == {"AAPL", "MSFT"}
    msft = next(p for p in rep["positions"] if p["ticker"] == "MSFT")
    assert msft["shares"] == 2 and msft["partial"]
    for b in rep["buys"]:
        assert b["stop"] < b["entry"] < b["t1"] < b["t2"]
        assert b["dollars"] <= rep["account"]["equity"] * cfg["max_position_pct"] / 100 + 1
        assert b["hold_days"] >= 3
    assert rep["backtest"]["n"] > 0
    html = (sandbox / "docs" / "index.html").read_text()
    assert "Habibi Wealth Management" in html
    # intraday check reuses latest.json
    run.cmd_check(cfg, Args())


def test_momentum_mode(sandbox):
    cfg = run.load_cfg()
    cfg["strategy"] = "momentum"
    run.cmd_plan(cfg, Args())
    rep = json.loads((sandbox / "output" / "latest.json").read_text())
    assert rep["strategy"] == "momentum" and rep["rebalance"] is True
    assert len(rep["buys"]) <= cfg["max_positions"]
    for b in rep["buys"]:
        assert b["setup"] == "momentum" and b["stop"] < b["entry"] < b["t1"] < b["t2"]
    total = sum(b["dollars"] for b in rep["buys"])
    assert total <= rep["account"]["cash"] + sum(p["value"] for p in rep["positions"]) + 1
    held = {p["ticker"] for p in rep["positions"]}
    rotated = {a["ticker"] for a in rep["alerts"] if "rotated" in a["why"]}
    assert rotated <= held
    # the system's paper account bought its own picks with the same capital
    paper = rep["paper"]
    assert {p["ticker"] for p in paper["positions"]} == {b["ticker"] for b in rep["buys"]}
    assert abs(paper["account"]["equity"] - cfg["starting_capital_usd"]) < cfg["starting_capital_usd"] * 0.2
    n_paper = len((sandbox / "output" / "paper_trades.csv").read_text().splitlines())
    # second run in the same week must not rebalance again (for you or the paper account)
    run.cmd_plan(cfg, Args())
    rep2 = json.loads((sandbox / "output" / "latest.json").read_text())
    assert rep2["rebalance"] is False
    # anything still offered is a catch-up of this week's list, never a new pick
    assert {b["ticker"] for b in rep2["buys"]} <= {b["ticker"] for b in rep["buys"]}
    assert all("catch-up" in b["reason"][0] for b in rep2["buys"])
    assert not [o for o in rep2["paper"]["orders_today"] if o["side"] == "BUY"]
    assert len((sandbox / "output" / "paper_trades.csv").read_text().splitlines()) >= n_paper
    run.cmd_check(cfg, Args())
    assert "Habibi Wealth Management" in (sandbox / "docs" / "index.html").read_text()


def test_calendar():
    from habibi.strategy import add_trading_days, trading_days_between
    fri = dt.date(2026, 9, 25)
    assert add_trading_days(fri, 1) == dt.date(2026, 9, 28)
    assert trading_days_between(fri, dt.date(2026, 10, 2)) == 5
    assert add_trading_days(dt.date(2026, 11, 25), 1) == dt.date(2026, 11, 27)


def test_adaptive_model_no_lookahead():
    from habibi import adaptive
    from habibi.indicators import add_features
    from habibi.universe import UNIVERSE
    tickers = sorted(set(UNIVERSE) | {"SPY"})
    feats = {t: add_features(df) for t, df in fake_prices(tickers).items()}
    uni = [t for t in UNIVERSE if t in feats]
    m = adaptive.model(feats, uni)
    w = m["weights"].iloc[-1]
    assert abs(w.sum() - 1) < 1e-6 and (w >= 0).all()
    # Scores on day t must not change if we delete everything after t.
    cut = feats["SPY"].index[-30]
    m2 = adaptive.model({t: f.loc[:cut] for t, f in feats.items()}, uni)
    a, b = m["scores"].loc[cut].dropna(), m2["scores"].loc[cut].dropna()
    assert np.allclose(a.sort_index(), b.reindex(a.index).sort_index())
    assert len(adaptive.explain_today(m)) == len(adaptive.FACTORS)


def test_quality_gate():
    from habibi.strategy import quality_gate
    assert quality_gate({"revenue_growth": 0.2, "forward_pe": 15, "profit_margin": 0.1}, 20)[0]
    assert not quality_gate({"revenue_growth": -0.1, "forward_pe": 15}, 20)[0]
    assert not quality_gate({"revenue_growth": 0.3, "forward_pe": -5}, 20)[0]
    assert not quality_gate({"name": "X"}, 12)[0]           # cheap + missing data
    assert quality_gate({"name": "X"}, 300)[0]              # large + missing data
    assert quality_gate({"quote_type": "ETF"}, 10)[0]


def test_staged_entry_and_add_on():
    from habibi.indicators import add_features
    from habibi.strategy import momentum_plan
    from habibi.universe import UNIVERSE
    tickers = sorted(set(UNIVERSE) | {"SPY"})
    feats = {t: add_features(df) for t, df in fake_prices(tickers).items()}
    cfg = run.load_cfg()
    cfg.update({"initial_tranche_pct": 50, "add_on_gain_pct": 4, "max_positions": 3})
    regime = {"light": "GREEN", "max_new": 3, "risk_mult": 1.0}
    today = dt.date.today()
    first = momentum_plan(feats, {}, regime, cfg, 1000, 1000, {}, today, True)
    assert first["buys"] and all(b["dollars"] <= 1000 / 3 * 0.5 + 1 for b in first["buys"])
    t = first["target"][0]
    px = first["buys"][0]["price"] if first["buys"][0]["ticker"] == t else float(feats[t].Close.iloc[-1])
    # starter position in t is up 6%: the engine should add the second half (not on a rebalance day)
    details = {t: {"value": 170.0, "avg_cost": px / 1.06, "price": px}}
    later = momentum_plan(feats, {}, regime, cfg, 1000, 830, {t: 170.0}, today, False, details=details)
    adds = [b for b in later["buys"] if b["kind"] == "add"]
    assert len(adds) == 1 and adds[0]["ticker"] == t and 100 < adds[0]["dollars"] <= 1000 / 3 - 170 + 1
    # up only 1%: no add
    details[t]["avg_cost"] = px / 1.01
    assert not momentum_plan(feats, {}, regime, cfg, 1000, 830, {t: 170.0}, today, False, details=details)["buys"]


def test_trial_week_ramp():
    from habibi.indicators import add_features
    from habibi.strategy import momentum_plan
    from habibi.universe import UNIVERSE
    feats = {t: add_features(df) for t, df in fake_prices(sorted(set(UNIVERSE) | {"SPY"})).items()}
    cfg = run.load_cfg()
    cfg.update({"initial_tranche_pct": 100, "add_on_gain_pct": None, "ramp_pct": 50, "max_positions": 3})
    regime = {"light": "GREEN", "max_new": 3, "risk_mult": 1.0}
    today = dt.date.today()
    cfg["ramp_until"] = (today + dt.timedelta(days=3)).isoformat()
    first = momentum_plan(feats, {}, regime, cfg, 1000, 1000, {}, today, True)
    assert first["buys"] and all(b["dollars"] <= 1000 / 3 * 0.5 + 1 for b in first["buys"])
    # after the ramp: a kept half-size holding is topped up on the rebalance
    cfg["ramp_until"] = (today - dt.timedelta(days=1)).isoformat()
    t = first["target"][0]
    px = float(feats[t].Close.iloc[-1])
    later = momentum_plan(feats, {}, regime, cfg, 1000, 830, {t: 165.0}, today, True,
                          details={t: {"value": 165.0, "avg_cost": px, "price": px}})
    tops = [b for b in later["buys"] if b.get("kind") == "add"]
    assert len(tops) == 1 and tops[0]["ticker"] == t


def test_catch_up_and_history_merge(sandbox):
    cfg = run.load_cfg()
    cfg["strategy"] = "momentum"
    (sandbox / "trades.csv").write_text("date,ticker,side,shares,price,fees,note\n")
    run.cmd_plan(cfg, Args())                       # rebalance day: sets this week's list
    rep = json.loads((sandbox / "output" / "latest.json").read_text())
    week = [b["ticker"] for b in rep["buys"]]
    assert week
    hist = sandbox / "output" / "history" / f"{dt.date.today().isoformat()}.json"
    run.cmd_plan(cfg, Args())                       # same week, you still hold nothing -> catch-up buys
    rep2 = json.loads((sandbox / "output" / "latest.json").read_text())
    assert rep2["rebalance"] is False
    assert [b["ticker"] for b in rep2["buys"]] == week
    assert all("catch-up" in b["reason"][0] for b in rep2["buys"])
    assert not [o for o in rep2["paper"]["orders_today"] if o["side"] == "BUY"]   # paper already holds them
    # the day's saved plan still has the original list after the second run
    assert [b["ticker"] for b in json.loads(hist.read_text())["buys"]] == week


def test_anomalies_learn_and_detect():
    from habibi import adaptive, anomalies
    from habibi.indicators import add_features
    from habibi.universe import UNIVERSE
    prices = fake_prices(sorted(set(UNIVERSE) | {"SPY"}))
    t = "AAPL"
    df = prices[t]
    # inject a crash on the last day: big drop on 4x volume with a gap down
    df.iloc[-1, df.columns.get_loc("Open")] = df.Close.iloc[-2] * 0.90
    df.iloc[-1, df.columns.get_loc("Close")] = df.Close.iloc[-2] * 0.85
    df.iloc[-1, df.columns.get_loc("Low")] = df.Close.iloc[-2] * 0.84
    df.iloc[-1, df.columns.get_loc("Volume")] = df.Volume.iloc[-21:-1].mean() * 4
    feats = {k: add_features(v) for k, v in prices.items()}
    m = adaptive.model(feats, [u for u in UNIVERSE if u in feats])
    stats = anomalies.learn(feats, m["scores"])
    assert "baseline_avg_pct" in stats and set(anomalies.LABELS) <= set(stats)
    out = anomalies.detect(feats, [t, "MSFT"], stats, m["scores"], held={t}, sectors=UNIVERSE)
    types = {f["type"] for f in out["flags"] if f["ticker"] == t}
    assert {"big_drop", "gap_down", "volume_spike"} <= types
    assert all(f["held"] for f in out["flags"] if f["ticker"] == t)
    assert out["rank_trends"] and out["rank_trends"][0]["ticker"] == t


def test_hold_rank_buffer():
    from habibi.indicators import add_features
    from habibi.strategy import momentum_plan
    from habibi.universe import UNIVERSE
    feats = {t: add_features(df) for t, df in fake_prices(sorted(set(UNIVERSE) | {"SPY"})).items()}
    cfg = run.load_cfg()
    cfg.update({"ramp_until": None, "max_positions": 3, "hold_rank": None})
    regime = {"light": "GREEN", "max_new": 3, "risk_mult": 1.0}
    today = dt.date.today()
    ranked = momentum_plan(feats, {}, regime, cfg, 1000, 1000, {}, today, True)["universe"]
    fifth = [r["ticker"] for r in ranked if r.get("rank") == 5][0]
    held = {fifth: 300.0}
    # default: rank #5 is outside the top 3, so it rotates out
    assert fifth in momentum_plan(feats, {}, regime, cfg, 1000, 700, held, today, True)["rotate_out"]
    # with a top-5 buffer it is kept and only two new names are bought
    cfg["hold_rank"] = 5
    plan = momentum_plan(feats, {}, regime, cfg, 1000, 700, held, today, True)
    assert fifth not in plan["rotate_out"] and fifth in plan["target"]
    assert len([b for b in plan["buys"] if b["kind"] == "new"]) == 2


def test_catch_up_skips_names_that_left_top_n():
    from habibi.indicators import add_features
    from habibi.strategy import momentum_plan
    from habibi.universe import UNIVERSE
    feats = {t: add_features(df) for t, df in fake_prices(sorted(set(UNIVERSE) | {"SPY"})).items()}
    cfg = run.load_cfg()
    cfg.update({"ramp_until": None, "max_positions": 3})
    regime = {"light": "GREEN", "max_new": 3, "risk_mult": 1.0}
    today = dt.date.today()
    ranked = momentum_plan(feats, {}, regime, cfg, 1000, 1000, {}, today, True)["universe"]
    by_rank = {r["rank"]: r["ticker"] for r in ranked if r.get("rank")}
    second, seventh = by_rank[2], by_rank[7]
    plan = momentum_plan(feats, {}, regime, cfg, 1000, 1000, {}, today, False,
                         catch_up={seventh: 0.0, second: 0.0})
    assert [b["ticker"] for b in plan["buys"]] == [second]


def test_growth_mode(sandbox):
    cfg = run.load_cfg()
    assert cfg["strategy"] == "growth"
    today = dt.date.today()
    cfg["phase_start"] = (today - dt.timedelta(days=2)).isoformat()   # AAPL/MSFT were bought before the phase
    run.cmd_plan(cfg, Args())
    rep = json.loads((sandbox / "output" / "latest.json").read_text())
    assert rep["strategy"] == "growth" and rep["rebalance"] is True
    held = {p["ticker"]: p for p in rep["positions"]}
    assert set(held) == {"AAPL", "MSFT"}
    for p in held.values():
        assert p["split"] and {"day_market_pct", "day_specific_pct", "verdict"} <= set(p["split"])
        assert p["stop_anchor"] == "phase start" and p["active_stop"] < p["price"] * 1.5
    active = [b for b in rep["buys"] if b["kind"] == "new"]
    core = [b for b in rep["buys"] if b["kind"] == "core"]
    assert core and core[0]["ticker"] == cfg["core"]["ticker"]
    kept = [t for t in held if t not in rep["sells"]]
    assert len(active) + len(kept) <= cfg["growth"]["top_n"]
    for b in active:
        assert b["shares"] > 0 and b["stop"] < b["entry"] <= b["limit"] and b["target"] > b["entry"]
    sold_value = sum(held[t]["value"] for t in rep["sells"])
    assert sum(b["dollars"] for b in rep["buys"]) <= rep["account"]["cash"] + sold_value + 1
    sectors = {}
    for t in kept + [b["ticker"] for b in active]:
        s = run.growth.cap_bucket(t)
        sectors[s] = sectors.get(s, 0) + 1
    assert max(sectors.values()) <= cfg["growth"]["max_per_sector"]
    assert rep["deploy"]["batches_left"] == cfg["deploy"]["batches"] - 1
    assert rep["sector_heat"] and rep["macro_tilts"] and rep["lesson"]["title"]
    assert isinstance(rep["reentry"], list)
    tech = [t for t in kept + [b["ticker"] for b in active] if run.growth.cap_bucket(t) in run.growth.TECH_LIKE]
    assert len(tech) <= cfg["growth"]["tech_like_max"]
    assert rep["phase"]["checks"][0]["goal_pct"] == cfg["goal"]["low_pct"]
    assert rep["paper"]["positions"]                                  # paper account followed the plan
    # Wednesday-style rerun in the same week: no new decisions, only catch-ups of Monday's list
    run.cmd_plan(cfg, Args())
    rep2 = json.loads((sandbox / "output" / "latest.json").read_text())
    assert rep2["rebalance"] is False
    assert {b["ticker"] for b in rep2["buys"]} <= {b["ticker"] for b in rep["buys"]}
    assert all(b["kind"].endswith("catchup") for b in rep2["buys"])
    assert not [o for o in rep2["paper"]["orders_today"] if o["side"] == "BUY"]
    assert rep2["deploy"]["batches_left"] == rep["deploy"]["batches_left"]
    run.cmd_check(cfg, Args())
    html = (sandbox / "docs" / "index.html").read_text()
    assert "Where the money is" in html and "Lesson of the week" in html
    for bad in (">None<", "nan%", "undefined"):
        assert bad not in html


def test_market_vs_stock_split():
    from habibi import growth
    from habibi.indicators import add_features
    prices = fake_prices(["SPY", "AAPL"])
    # make AAPL = 1.5x SPY's daily moves, then a market-wide -3% day
    spy = prices["SPY"].Close.copy()
    r = spy.pct_change().fillna(0) * 1.5
    prices["AAPL"]["Close"] = 100 * (1 + r).cumprod()
    feats = {k: add_features(v) for k, v in prices.items()}
    today = feats["SPY"].index[-1].date() + dt.timedelta(days=1)
    s = growth.market_vs_stock(feats, "AAPL", today)
    assert abs(s["beta"] - 1.5) < 0.05
    assert abs(s["day_specific_pct"]) < 0.2 and s["verdict"] == "moving with the market"


def test_growth_preview_before_phase_start_saves_nothing(sandbox):
    cfg = run.load_cfg()
    cfg["phase_start"] = (dt.date.today() + dt.timedelta(days=3)).isoformat()
    run.cmd_plan(cfg, Args())
    rep = json.loads((sandbox / "output" / "latest.json").read_text())
    assert rep["preview"] and "PREVIEW" in (sandbox / "docs" / "index.html").read_text()
    assert not (sandbox / "output" / "growth_state.json").exists()
    run.cmd_check(cfg, Args())
    assert not (sandbox / "output" / "growth_state.json").exists()


def test_growth_week_rules():
    """Stale sells from last week are ignored; a rank exit needs two reviews; catch-ups respect a halt."""
    from habibi import growth
    from habibi.indicators import add_features
    from habibi.portfolio import positions
    from habibi.universe import UNIVERSE
    feats = {t: add_features(df) for t, df in fake_prices(sorted(set(UNIVERSE) | {"SPY", "VOO"})).items()}
    cfg = run.load_cfg()
    today = dt.date.today()
    cfg["phase_start"] = (today - dt.timedelta(days=30)).isoformat()
    regime = {"light": "GREEN", "max_new": 4, "risk_mult": 1.0, "message": ""}
    empty = pd.DataFrame(columns=["date", "ticker", "side", "shares", "price", "fees", "note"])
    book = positions(empty, feats, {}, cfg)
    growth.evaluate_growth(book, feats, {}, {}, cfg, today, {}, "real")
    state = {}
    plan = growth.growth_plan(feats, {}, regime, cfg, book, today, True, state)
    pick = next(b["ticker"] for b in plan["buys"] if b["kind"] == "new")
    # a holding that ranks badly: first review puts it on notice, the second sells it
    worst = [t for t in UNIVERSE if t in feats and t not in {b["ticker"] for b in plan["buys"]}][-1]
    tr = pd.DataFrame([{"date": today - dt.timedelta(days=20), "ticker": worst, "side": "BUY", "shares": 1.0,
                        "price": float(feats[worst].Close.iloc[-20]), "fees": 0.0, "note": ""}])
    book2 = positions(tr, feats, {}, cfg)
    growth.evaluate_growth(book2, feats, {}, {}, cfg, today, {}, "real")
    st2 = {}
    cfg["growth"]["trend_exit"] = False
    cfg["growth"]["exit_confirm"] = 2
    p1 = growth.growth_plan(feats, {}, regime, cfg, book2, today, True, st2)
    rank_ok = worst not in p1["sells"]
    if worst in p1["warn"]:
        p2 = growth.growth_plan(feats, {}, regime, cfg, book2, today + dt.timedelta(days=7), True, st2)
        assert worst in p2["sells"]
    else:
        assert rank_ok
    # last week's sell list must not fire this week
    st3 = {"real": {"week": {"date": (today - dt.timedelta(days=7)).isoformat(), "sells": {worst: "old reason"}}}}
    book3 = positions(tr, feats, {}, cfg)
    alerts = growth.evaluate_growth(book3, feats, {}, {}, cfg, today, st3, "real")
    assert not [a for a in alerts if a["why"] == "old reason"]
    # midweek catch-ups are dropped while halted
    later = growth.growth_plan(feats, {}, regime, cfg, book, today, False, state, halted=True)
    assert not [b for b in later["buys"] if b["kind"] == "new-catchup"]
    assert pick


def test_quality_dip_sleeve():
    from habibi import growth
    from habibi.indicators import add_features
    from habibi.portfolio import positions
    from habibi.universe import UNIVERSE
    prices = fake_prices(sorted(set(UNIVERSE) | {"SPY", "VOO"}))
    # NVDA: steady climb, then a 30% fall over the last month
    df = prices["NVDA"]
    n = len(df)
    path = np.concatenate([np.linspace(100, 200, n - 22), np.linspace(200, 140, 22)])
    for c in ("Open", "High", "Low", "Close"):
        df[c] = path * {"Open": 1.0, "High": 1.01, "Low": 0.99, "Close": 1.0}[c]
    feats = {t: add_features(d) for t, d in prices.items()}
    funds = {t: {"name": t, "forward_pe": 25, "revenue_growth": 0.05, "profit_margin": 0.1} for t in UNIVERSE}
    funds["NVDA"] = {"name": "NVIDIA", "forward_pe": 11, "revenue_growth": 1.06, "profit_margin": 0.64,
                     "target_mean": 300, "market_cap": 4e12, "next_earnings": None}
    cfg = run.load_cfg()
    today = dt.date.today()
    regime = {"light": "GREEN", "max_new": 4, "risk_mult": 1.0, "message": ""}
    empty = pd.DataFrame(columns=["date", "ticker", "side", "shares", "price", "fees", "note"])
    book = positions(empty, feats, {}, cfg)
    growth.evaluate_growth(book, feats, {}, funds, cfg, today, {}, "real")
    plan = growth.growth_plan(feats, funds, regime, cfg, book, today, True, {})
    v = [b for b in plan["buys"] if b["kind"] == "value"]
    assert [b["ticker"] for b in v] == ["NVDA"]
    full = book["equity"] * cfg["value"]["max_name_pct"] / 100
    assert v[0]["dollars"] <= full / 2 + 1 and v[0]["quality"] >= 80 and v[0]["peg"] < 1
    # once held (note "value"), the weekly momentum review never sells it on rank
    tr = pd.DataFrame([{"date": today - dt.timedelta(days=3), "ticker": "NVDA", "side": "BUY", "shares": 0.5,
                        "price": 145.0, "fees": 0.0, "note": "value sleeve"}])
    book2 = positions(tr, feats, {}, cfg)
    alerts = growth.evaluate_growth(book2, feats, {}, funds, cfg, today, {}, "real")
    nv = next(p for p in book2["open"] if p["ticker"] == "NVDA")
    assert nv["sleeve"] == "value" and nv["action"] == "HOLD" and not alerts
    plan2 = growth.growth_plan(feats, funds, regime, cfg, book2, today, True, {})
    assert "NVDA" not in plan2["sells"] and plan2["sleeves"]["value"]["n"] == 1
    # the business story breaks -> sell
    funds["NVDA"]["revenue_growth"] = -0.10
    book3 = positions(tr, feats, {}, cfg)
    alerts = growth.evaluate_growth(book3, feats, {}, funds, cfg, today, {}, "real")
    assert alerts and alerts[0]["rule"] == "story"
