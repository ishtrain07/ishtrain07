"""Technical indicators on OHLCV DataFrames (columns: Open High Low Close Volume)."""
import numpy as np
import pandas as pd


def sma(s, n):
    return s.rolling(n, min_periods=n).mean()


def ema(s, n):
    return s.ewm(span=n, adjust=False, min_periods=n).mean()


def rsi(close, n=14):
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    rs = gain / loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(100)


def atr(df, n=14):
    prev = df["Close"].shift()
    tr = pd.concat([df["High"] - df["Low"],
                    (df["High"] - prev).abs(),
                    (df["Low"] - prev).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def macd_hist(close, fast=12, slow=26, signal=9):
    line = ema(close, fast) - ema(close, slow)
    return line - ema(line, signal)


def add_features(df):
    """Return a copy of df with every indicator the strategy uses."""
    d = df.copy()
    c = d["Close"]
    d["ema20"] = ema(c, 20)
    d["sma50"] = sma(c, 50)
    d["sma200"] = sma(c, 200)
    d["rsi"] = rsi(c)
    d["atr"] = atr(d)
    d["macd_h"] = macd_hist(c)
    d["ret21"] = c.pct_change(21)
    d["ret63"] = c.pct_change(63)
    d["ret126"] = c.pct_change(126)
    d["hi20_prev"] = d["High"].shift(1).rolling(20).max()
    d["low5"] = d["Low"].rolling(5).min()
    d["vol_ratio"] = d["Volume"] / d["Volume"].shift(1).rolling(20).mean()
    d["dollar_vol"] = (c * d["Volume"]).rolling(20).mean()
    d["dist_ema20_atr"] = (c - d["ema20"]) / d["atr"]
    d["sma50_slope"] = d["sma50"] / d["sma50"].shift(10) - 1
    d["prev_high"] = d["High"].shift(1)
    d["prev_close"] = c.shift(1)
    return d
