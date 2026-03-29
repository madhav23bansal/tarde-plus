"""Abstract broker adapter interface.

All broker implementations (Zerodha, Dhan, Upstox, Mock) must implement this.
The engine only talks to this interface — never to a specific broker directly.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import AsyncIterator


@dataclass(slots=True)
class Quote:
    instrument: str
    ltp: Decimal
    bid: Decimal
    ask: Decimal
    volume: int
    oi: int
    exchange: str = "NSE"
    timestamp: float = 0.0


@dataclass(slots=True)
class OrderResponse:
    broker_order_id: str
    status: str
    message: str = ""


@dataclass(slots=True)
class OrderBook:
    """A single order entry from the broker's order book."""
    broker_order_id: str
    instrument: str
    side: str
    order_type: str
    quantity: int
    filled_qty: int
    price: Decimal
    avg_fill_price: Decimal
    status: str
    timestamp: float = 0.0


@dataclass(slots=True)
class Position:
    instrument: str
    quantity: int
    avg_price: Decimal
    pnl: Decimal
    exchange: str = "NSE"


class BrokerAdapter(ABC):
    """Abstract interface that all broker adapters must implement."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Broker identifier (e.g., 'zerodha', 'dhan', 'mock')."""
        ...

    @abstractmethod
    async def connect(self) -> None:
        """Authenticate and establish connection."""
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Clean shutdown of all connections."""
        ...

    @abstractmethod
    async def subscribe_ticks(self, instruments: list[str]) -> AsyncIterator[Quote]:
        """Subscribe to live tick stream via WebSocket.

        Yields Quote objects as they arrive from the exchange.
        """
        ...

    @abstractmethod
    async def place_order(
        self,
        instrument: str,
        side: str,
        order_type: str,
        quantity: int,
        price: Decimal | None = None,
        trigger_price: Decimal | None = None,
    ) -> OrderResponse:
        """Place an order with the broker."""
        ...

    @abstractmethod
    async def cancel_order(self, broker_order_id: str) -> OrderResponse:
        """Cancel a pending/open order."""
        ...

    @abstractmethod
    async def get_orders(self) -> list[OrderBook]:
        """Fetch today's order book."""
        ...

    @abstractmethod
    async def get_positions(self) -> list[Position]:
        """Fetch current positions."""
        ...

    @abstractmethod
    async def get_ltp(self, instruments: list[str]) -> dict[str, Decimal]:
        """Get last traded price for instruments."""
        ...
