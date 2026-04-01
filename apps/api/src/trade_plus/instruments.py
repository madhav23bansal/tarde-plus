"""Instrument definitions.

Three instruments, all sharing the same core data pipeline:
  NIFTYBEES  — tracks Nifty 50, uses Nifty OI
  BANKBEES   — tracks Bank Nifty, uses Bank Nifty OI (separate call)
  SETFNIF50  — tracks Nifty 50 (same OI as NIFTYBEES, diversification)

All share: FII/DII, India VIX, S&P 500, crude oil, USD/INR.
OI data: NIFTYBEES + SETFNIF50 use NIFTY option chain.
          BANKBEES uses BANKNIFTY option chain.

ML NOTE: Each instrument needs its own trained model (300+ trades each).
All tick/level/OI data recorded in DB from day 1 for future training.
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
    oi_index: str = "NIFTY"      # which NSE option chain to use for OI
    nifty_ratio: float = 100.0   # Nifty strike / this ratio = ETF price level
    approx_price: float = 0.0
    shortable_intraday: bool = True


# ── Active instruments ───────────────────────────────────────────

NIFTYBEES = Instrument(
    ticker="NIFTYBEES",
    name="Nippon Nifty 50 ETF",
    yahoo_symbol="NIFTYBEES.NS",
    nse_symbol="NIFTYBEES",
    oi_index="NIFTY",
    nifty_ratio=100.0,
    approx_price=255.0,
)

BANKBEES = Instrument(
    ticker="BANKBEES",
    name="Nippon Bank Nifty ETF",
    yahoo_symbol="BANKBEES.NS",
    nse_symbol="BANKBEES",
    oi_index="BANKNIFTY",       # separate option chain
    nifty_ratio=100.0,
    approx_price=520.0,
)

SETFNIF50 = Instrument(
    ticker="SETFNIF50",
    name="SBI Nifty 50 ETF",
    yahoo_symbol="SETFNIF50.NS",
    nse_symbol="SETFNIF50",
    oi_index="NIFTY",           # same OI as NIFTYBEES
    nifty_ratio=100.0,          # similar price ratio
    approx_price=240.0,
)

ALL_INSTRUMENTS = [NIFTYBEES, BANKBEES]  # SETFNIF50 removed: same index as NIFTYBEES, doubles risk
INSTRUMENT_MAP = {i.ticker: i for i in ALL_INSTRUMENTS}

# Which OI indices we need to fetch (deduplicated)
OI_INDICES = list(set(i.oi_index for i in ALL_INSTRUMENTS))  # ["NIFTY", "BANKNIFTY"]

# Global market symbols for daily bias (same for all instruments)
GLOBAL_SYMBOLS = {
    "sp500": "^GSPC",
    "crude_oil": "CL=F",
    "india_vix": "^INDIAVIX",
    "usd_inr": "USDINR=X",
    "nifty50": "^NSEI",
    "banknifty": "^NSEBANK",
}
