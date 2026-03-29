"""Market data aggregator — combines Yahoo Finance and NSE with failover.

Priority: Yahoo (batch-friendly, ~2s delay) -> NSE (rate-limited, accurate)
"""

from __future__ import annotations

import asyncio
import time
from typing import AsyncIterator

import structlog

from trade_plus.market_data.base import OHLCV, LiveQuote, OptionChain
from trade_plus.market_data.nse import NSEProvider
from trade_plus.market_data.yahoo import YahooFinanceProvider

logger = structlog.get_logger()


class MarketDataAggregator:
    """Unified interface to market data sources with automatic failover."""

    def __init__(self) -> None:
        self.yahoo = YahooFinanceProvider()
        self.nse = NSEProvider()

    async def get_quote(self, symbol: str) -> LiveQuote:
        errors = []
        try:
            return await self.yahoo.get_quote(symbol)
        except Exception as e:
            errors.append(f"yahoo: {e}")
        try:
            return await self.nse.get_quote(symbol)
        except Exception as e:
            errors.append(f"nse: {e}")
        raise RuntimeError(f"All providers failed for {symbol}: {errors}")

    async def get_quotes(self, symbols: list[str]) -> dict[str, LiveQuote]:
        try:
            return await self.yahoo.get_quotes(symbols)
        except Exception as e:
            logger.warning("yahoo_batch_failed", error=str(e))
        results = {}
        for sym in symbols:
            try:
                results[sym] = await self.get_quote(sym)
            except Exception as e:
                logger.warning("quote_all_failed", symbol=sym, error=str(e))
        return results

    async def get_historical(self, symbol: str, interval: str = "1d", range_str: str = "1y") -> list[OHLCV]:
        try:
            return await self.yahoo.get_historical(symbol, interval, range_str)
        except Exception as e:
            logger.warning("yahoo_historical_failed", error=str(e))
        if interval in ("1d", "1wk", "1mo"):
            try:
                return await self.nse.get_historical(symbol, interval, range_str)
            except Exception as e:
                logger.warning("nse_historical_failed", error=str(e))
        raise RuntimeError(f"No provider could fetch historical data for {symbol}")

    async def get_option_chain(self, symbol: str, is_index: bool = True) -> OptionChain:
        return await self.nse.get_option_chain(symbol, is_index)

    async def get_all_indices(self) -> list[dict]:
        return await self.nse.get_all_indices()

    async def stream_quotes(self, symbols: list[str], interval_sec: float = 5.0) -> AsyncIterator[dict[str, LiveQuote]]:
        while True:
            try:
                quotes = await self.get_quotes(symbols)
                yield quotes
            except Exception as e:
                logger.warning("stream_error", error=str(e))
            await asyncio.sleep(interval_sec)

    async def close(self) -> None:
        await self.yahoo.close()
        await self.nse.close()
