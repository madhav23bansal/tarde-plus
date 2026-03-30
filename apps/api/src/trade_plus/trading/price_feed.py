"""Fast price feed — fetches live prices for all instruments.

Uses yfinance fast_info for near-real-time LTP (~300ms/symbol).
Designed for 30-second scalping cycles.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import structlog

logger = structlog.get_logger()

_executor = ThreadPoolExecutor(max_workers=4)


@dataclass(slots=True)
class PriceTick:
    instrument: str
    price: float
    bid: float
    ask: float
    volume: int
    day_high: float
    day_low: float
    day_open: float
    prev_close: float
    timestamp: float       # when we fetched it
    fetch_ms: float        # how long the fetch took


def _fetch_one(yahoo_sym: str, instrument: str) -> PriceTick:
    """Fetch a single instrument's price. Runs in thread pool."""
    import yfinance as yf
    start = time.time()
    try:
        t = yf.Ticker(yahoo_sym)
        info = t.fast_info
        price = float(getattr(info, "last_price", 0) or 0)
        prev = float(getattr(info, "previous_close", 0) or 0)
        day_high = float(getattr(info, "day_high", 0) or 0)
        day_low = float(getattr(info, "day_low", 0) or 0)
        open_price = float(getattr(info, "open", 0) or 0)
        vol = int(getattr(info, "last_volume", 0) or 0)

        return PriceTick(
            instrument=instrument,
            price=price,
            bid=price * 0.9998,   # approximate spread for liquid ETFs
            ask=price * 1.0002,
            volume=vol,
            day_high=day_high,
            day_low=day_low,
            day_open=open_price,
            prev_close=prev,
            timestamp=time.time(),
            fetch_ms=round((time.time() - start) * 1000, 1),
        )
    except Exception as e:
        logger.warning("price_fetch_failed", instrument=instrument, error=str(e))
        return PriceTick(
            instrument=instrument, price=0, bid=0, ask=0, volume=0,
            day_high=0, day_low=0, day_open=0, prev_close=0,
            timestamp=time.time(), fetch_ms=round((time.time() - start) * 1000, 1),
        )


async def fetch_prices(instruments: dict[str, str]) -> dict[str, PriceTick]:
    """Fetch prices for all instruments in parallel.

    Args:
        instruments: {ticker: yahoo_symbol} mapping

    Returns:
        {ticker: PriceTick}
    """
    import asyncio
    loop = asyncio.get_event_loop()

    start = time.time()
    futures = {
        ticker: loop.run_in_executor(_executor, _fetch_one, yahoo_sym, ticker)
        for ticker, yahoo_sym in instruments.items()
    }

    results = {}
    for ticker, fut in futures.items():
        results[ticker] = await fut

    total_ms = round((time.time() - start) * 1000, 1)
    valid = sum(1 for t in results.values() if t.price > 0)
    logger.debug("prices_fetched", count=valid, total_ms=total_ms)

    return results
