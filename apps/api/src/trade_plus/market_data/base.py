"""Base interface for market data providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from typing import AsyncIterator


@dataclass(slots=True)
class OHLCV:
    timestamp: float
    open: float
    high: float
    low: float
    close: float
    volume: int
    instrument: str = ""


@dataclass(slots=True)
class LiveQuote:
    instrument: str
    ltp: float
    open: float
    high: float
    low: float
    close: float  # prev close
    volume: int
    bid: float = 0.0
    ask: float = 0.0
    change: float = 0.0
    change_pct: float = 0.0
    timestamp: float = 0.0


@dataclass(slots=True)
class OptionChainEntry:
    strike: float
    expiry: str
    ce_ltp: float = 0.0
    ce_oi: int = 0
    ce_volume: int = 0
    ce_iv: float = 0.0
    ce_bid: float = 0.0
    ce_ask: float = 0.0
    pe_ltp: float = 0.0
    pe_oi: int = 0
    pe_volume: int = 0
    pe_iv: float = 0.0
    pe_bid: float = 0.0
    pe_ask: float = 0.0


@dataclass(slots=True)
class OptionChain:
    symbol: str
    spot_price: float
    expiry_dates: list[str] = field(default_factory=list)
    entries: list[OptionChainEntry] = field(default_factory=list)
    timestamp: float = 0.0


class MarketDataProvider(ABC):
    """Abstract interface for market data sources."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    async def get_quote(self, symbol: str) -> LiveQuote:
        """Get current quote for a single symbol."""
        ...

    @abstractmethod
    async def get_quotes(self, symbols: list[str]) -> dict[str, LiveQuote]:
        """Get current quotes for multiple symbols."""
        ...

    @abstractmethod
    async def get_historical(
        self,
        symbol: str,
        interval: str = "1d",
        range_str: str = "1y",
    ) -> list[OHLCV]:
        """Get historical OHLCV data."""
        ...

    async def stream_quotes(
        self,
        symbols: list[str],
        interval_sec: float = 5.0,
    ) -> AsyncIterator[LiveQuote]:
        """Poll-based streaming. Override for WebSocket sources."""
        import asyncio
        while True:
            quotes = await self.get_quotes(symbols)
            for quote in quotes.values():
                yield quote
            await asyncio.sleep(interval_sec)
