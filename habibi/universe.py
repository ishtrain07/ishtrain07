"""Tradable universe: liquid US large and mid caps plus major ETFs.

No penny stocks, no illiquid names. Each ticker maps to a sector ETF so the
engine can favour stocks in leading sectors and cap sector concentration.
"""

SECTOR_ETF = {
    "Tech": "XLK",
    "Semis": "SMH",
    "Comm": "XLC",
    "ConsDisc": "XLY",
    "ConsStap": "XLP",
    "Financials": "XLF",
    "Health": "XLV",
    "Industrials": "XLI",
    "Energy": "XLE",
    "Utilities": "XLU",
    "Materials": "XLB",
    "ETF": "SPY",
}

UNIVERSE = {
    # Mag 7
    "AAPL": "Tech", "MSFT": "Tech", "NVDA": "Semis", "AMZN": "ConsDisc",
    "GOOGL": "Comm", "META": "Comm", "TSLA": "ConsDisc",
    # Large-cap tech / software
    "ORCL": "Tech", "CRM": "Tech", "ADBE": "Tech", "NOW": "Tech", "INTU": "Tech",
    "PLTR": "Tech", "SHOP": "Tech", "CRWD": "Tech", "PANW": "Tech", "ANET": "Tech",
    "SNOW": "Tech", "DDOG": "Tech", "NET": "Tech", "ZS": "Tech", "APP": "Tech",
    "IBM": "Tech", "DELL": "Tech", "FTNT": "Tech", "MDB": "Tech",
    # Semis
    "AVGO": "Semis", "AMD": "Semis", "TSM": "Semis", "MU": "Semis", "QCOM": "Semis",
    "ARM": "Semis", "LRCX": "Semis", "AMAT": "Semis", "KLAC": "Semis", "MRVL": "Semis",
    "ASML": "Semis",
    # Communication / internet
    "NFLX": "Comm", "UBER": "Tech", "SPOT": "Comm", "RDDT": "Comm", "DASH": "ConsDisc",
    # Consumer
    "COST": "ConsStap", "WMT": "ConsStap", "HD": "ConsDisc", "NKE": "ConsDisc",
    "CMG": "ConsDisc", "ONON": "ConsDisc", "DECK": "ConsDisc", "CAVA": "ConsDisc",
    "ABNB": "ConsDisc", "BKNG": "ConsDisc",
    # Financials / fintech
    "JPM": "Financials", "GS": "Financials", "MS": "Financials", "V": "Financials",
    "MA": "Financials", "AXP": "Financials", "COIN": "Financials", "HOOD": "Financials",
    "SOFI": "Financials", "PYPL": "Financials", "BX": "Financials",
    # Healthcare
    "LLY": "Health", "ISRG": "Health", "UNH": "Health", "ABBV": "Health",
    "VRTX": "Health", "HIMS": "Health",
    # Industrials / AI power & infrastructure
    "GE": "Industrials", "GEV": "Industrials", "CAT": "Industrials", "VRT": "Industrials",
    "AXON": "Industrials", "ETN": "Industrials", "RTX": "Industrials", "PWR": "Industrials",
    "CEG": "Utilities", "VST": "Utilities", "NRG": "Utilities",
    # Energy / materials
    "XOM": "Energy", "CVX": "Energy", "FCX": "Materials",
    # ETFs (lower-volatility options when single stocks are messy)
    "QQQ": "ETF", "SPY": "ETF", "SMH": "ETF", "IWM": "ETF",
}

# Macro dashboard: global markets, rates, dollar, commodities, FX.
MACRO = {
    "ES=F": "S&P 500 futures",
    "NQ=F": "Nasdaq 100 futures",
    "SPY": "S&P 500",
    "QQQ": "Nasdaq 100",
    "IWM": "Russell 2000",
    "^VIX": "VIX (fear)",
    "^TNX": "US 10Y yield",
    "DX-Y.NYB": "US Dollar index",
    "CL=F": "WTI crude",
    "GC=F": "Gold",
    "BTC-USD": "Bitcoin",
    "^N225": "Nikkei (Japan)",
    "^HSI": "Hang Seng (HK)",
    "^GDAXI": "DAX (Germany)",
    "^FTSE": "FTSE 100 (UK)",
    "^NSEI": "Nifty 50 (India)",
    "USDCAD=X": "USD/CAD",
    "USDINR=X": "USD/INR",
}

# Scheduled FOMC decision days (second day of each meeting). Verify against
# federalreserve.gov; volatility clusters around these.
FOMC_2026 = ["2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17",
             "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09"]

# NYSE full-day holidays.
NYSE_HOLIDAYS = ["2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03",
                 "2026-05-25", "2026-06-19", "2026-07-03", "2026-09-07",
                 "2026-11-26", "2026-12-25", "2027-01-01", "2027-01-18"]


def all_price_tickers():
    tickers = set(UNIVERSE) | set(MACRO) | set(SECTOR_ETF.values())
    return sorted(tickers)
