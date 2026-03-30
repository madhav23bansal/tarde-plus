"""Instrument definitions.

Currently trading NIFTYBEES only — best OI data, most liquid, tightest spreads.
Other instruments can be added later when we have proven the strategy works.

ML NOTE: When adding instruments later, each needs its own trained model.
Record all tick/level/OI data for every instrument from day 1 so ML has
enough training data (300+ trades needed per instrument).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Direction(Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    FLAT = "FLAT"


@dataclass(frozen=True)
class Instrument:
    ticker: str
    name: str
    yahoo_symbol: str
    nse_symbol: str
    nifty_token: str = "26000"  # NSE scrip token for quotes
    approx_price: float = 0.0
    shortable_intraday: bool = True


# ── The one instrument we trade ─────────────────────────────────

NIFTYBEES = Instrument(
    ticker="NIFTYBEES",
    name="Nippon Nifty 50 ETF",
    yahoo_symbol="NIFTYBEES.NS",
    nse_symbol="NIFTYBEES",
    nifty_token="26000",
    approx_price=255.0,
    shortable_intraday=True,
)

ALL_INSTRUMENTS = [NIFTYBEES]
INSTRUMENT_MAP = {i.ticker: i for i in ALL_INSTRUMENTS}

# Global market symbols — only the 5 that matter for daily bias
# Research: S&P alone captures most global sentiment
# VIX = regime detection (trending vs range day)
# Crude = direct India impact (net importer)
# USD/INR = FII flow proxy
# Nifty50 = the index NIFTYBEES tracks
GLOBAL_SYMBOLS = {
    "sp500": "^GSPC",
    "crude_oil": "CL=F",
    "india_vix": "^INDIAVIX",
    "usd_inr": "USDINR=X",
    "nifty50": "^NSEI",
}
