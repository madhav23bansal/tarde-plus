"""Instrument definitions and sector-specific configuration.

Each instrument knows:
  - What it trades as on NSE
  - What drives its price (sector-specific factors)
  - What global data to collect for prediction
  - Yahoo Finance symbols for reference prices
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Sector(Enum):
    INDEX = "index"
    GOLD = "gold"
    SILVER = "silver"
    BANKING = "banking"


class Direction(Enum):
    LONG = "LONG"    # Buy first, sell later — profit if price goes UP
    SHORT = "SHORT"  # Sell first, buy later — profit if price goes DOWN
    FLAT = "FLAT"    # No position


@dataclass(frozen=True)
class Instrument:
    """An instrument we can trade on NSE."""
    ticker: str                    # NSE ticker (e.g., NIFTYBEES)
    name: str                      # Human-readable name
    sector: Sector                 # Which sector this belongs to
    yahoo_symbol: str              # For price data via yfinance
    nse_symbol: str                # For NSE API calls

    # What global reference prices drive this instrument
    global_drivers: list[str] = field(default_factory=list)

    # Yahoo symbols for those global drivers
    driver_symbols: dict[str, str] = field(default_factory=dict)

    # Can we short this intraday on Zerodha?
    shortable_intraday: bool = True

    # Approximate price per unit (for position sizing estimates)
    approx_price: float = 0.0

    # Minimum quantity
    min_qty: int = 1


# ─── Instrument Registry ────────────────────────────────────────────

NIFTYBEES = Instrument(
    ticker="NIFTYBEES",
    name="Nippon Nifty 50 ETF",
    sector=Sector.INDEX,
    yahoo_symbol="NIFTYBEES.NS",
    nse_symbol="NIFTYBEES",
    approx_price=270.0,
    global_drivers=[
        "sp500", "nasdaq", "dow",           # US markets
        "nikkei", "hangseng",               # Asian markets
        "us_futures",                        # S&P futures
        "crude_oil",                         # India is net importer
        "usd_inr",                           # FII flow proxy
        "us_10y_yield",                      # FII allocation driver
        "india_vix",                         # Fear gauge
    ],
    driver_symbols={
        "sp500": "^GSPC",
        "nasdaq": "^IXIC",
        "dow": "^DJI",
        "nikkei": "^N225",
        "hangseng": "^HSI",
        "us_futures": "ES=F",
        "crude_oil": "CL=F",
        "usd_inr": "USDINR=X",
        "us_10y_yield": "^TNX",
        "india_vix": "^INDIAVIX",
        "nifty50": "^NSEI",
    },
)

GOLDBEES = Instrument(
    ticker="GOLDBEES",
    name="Nippon Gold ETF",
    sector=Sector.GOLD,
    yahoo_symbol="GOLDBEES.NS",
    nse_symbol="GOLDBEES",
    approx_price=68.0,
    global_drivers=[
        "gold_comex",                        # Primary driver
        "dxy",                               # USD strength (inverse)
        "us_10y_yield",                      # Opportunity cost (inverse)
        "us_futures",                        # Risk-on/off
        "usd_inr",                           # INR conversion effect
        "silver",                            # Correlated metal
        "india_vix",                         # Risk appetite
    ],
    driver_symbols={
        "gold_comex": "GC=F",
        "dxy": "DX-Y.NYB",
        "us_10y_yield": "^TNX",
        "us_futures": "ES=F",
        "usd_inr": "USDINR=X",
        "silver": "SI=F",
        "india_vix": "^INDIAVIX",
        "crude_oil": "CL=F",
    },
)

SILVERBEES = Instrument(
    ticker="SILVERBEES",
    name="Nippon Silver ETF",
    sector=Sector.SILVER,
    yahoo_symbol="SILVERBEES.NS",
    nse_symbol="SILVERBEES",
    approx_price=98.0,
    global_drivers=[
        "silver_comex",                      # Primary driver
        "gold_comex",                        # Correlated
        "gold_silver_ratio",                 # Mean-reverts
        "dxy",                               # USD strength (inverse)
        "us_10y_yield",                      # Opportunity cost
        "usd_inr",                           # INR conversion
        "copper",                            # Industrial demand proxy
    ],
    driver_symbols={
        "silver_comex": "SI=F",
        "gold_comex": "GC=F",
        "dxy": "DX-Y.NYB",
        "us_10y_yield": "^TNX",
        "usd_inr": "USDINR=X",
        "copper": "HG=F",
        "india_vix": "^INDIAVIX",
    },
)

BANKBEES = Instrument(
    ticker="BANKBEES",
    name="Nippon Bank Nifty ETF",
    sector=Sector.BANKING,
    yahoo_symbol="BANKBEES.NS",
    nse_symbol="BANKBEES",
    approx_price=510.0,
    global_drivers=[
        "sp500",                             # Global risk
        "us_10y_yield",                      # Rate environment
        "usd_inr",                           # FII flow proxy
        "india_vix",                         # Fear gauge
        "us_futures",                        # Overnight sentiment
        "nifty50",                           # Broad market
    ],
    driver_symbols={
        "sp500": "^GSPC",
        "us_10y_yield": "^TNX",
        "usd_inr": "USDINR=X",
        "india_vix": "^INDIAVIX",
        "us_futures": "ES=F",
        "nifty50": "^NSEI",
        "banknifty": "^NSEBANK",
    },
)


# All instruments we track
ALL_INSTRUMENTS = [NIFTYBEES, GOLDBEES, SILVERBEES, BANKBEES]

INSTRUMENT_MAP: dict[str, Instrument] = {i.ticker: i for i in ALL_INSTRUMENTS}


def get_instrument(ticker: str) -> Instrument:
    if ticker not in INSTRUMENT_MAP:
        raise ValueError(f"Unknown instrument: {ticker}. Available: {list(INSTRUMENT_MAP.keys())}")
    return INSTRUMENT_MAP[ticker]
