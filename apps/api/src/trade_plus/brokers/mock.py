"""Mock broker adapter for development and testing.

Simulates realistic broker behavior including:
- Random tick generation based on NSE market patterns
- Order fill simulation with slippage
- Position tracking
"""

from __future__ import annotations

import asyncio
import random
import time
from decimal import Decimal
from typing import AsyncIterator

import structlog

from trade_plus.brokers.base import (
    BrokerAdapter,
    OrderBook,
    OrderResponse,
    Position,
    Quote,
)

logger = structlog.get_logger()

# Simulated NSE instruments with realistic price ranges
MOCK_INSTRUMENTS = {
    "NSE:RELIANCE": {"base": 2450.0, "volatility": 0.002},
    "NSE:TCS": {"base": 3800.0, "volatility": 0.0015},
    "NSE:HDFCBANK": {"base": 1650.0, "volatility": 0.0018},
    "NSE:INFY": {"base": 1520.0, "volatility": 0.002},
    "NSE:ICICIBANK": {"base": 1180.0, "volatility": 0.0022},
    "NSE:NIFTY25MARFUT": {"base": 23500.0, "volatility": 0.001},
    "NSE:BANKNIFTY25MARFUT": {"base": 50200.0, "volatility": 0.0015},
    "NSE:SBIN": {"base": 780.0, "volatility": 0.0025},
    "NSE:BHARTIARTL": {"base": 1680.0, "volatility": 0.0018},
    "NSE:ITC": {"base": 440.0, "volatility": 0.0012},
}


class MockBroker(BrokerAdapter):
    """Mock broker for development and backtesting."""

    def __init__(self, tick_interval: float = 0.5) -> None:
        self._tick_interval = tick_interval
        self._prices: dict[str, float] = {}
        self._orders: list[OrderBook] = []
        self._positions: dict[str, Position] = {}
        self._order_counter = 0
        self._connected = False

    @property
    def name(self) -> str:
        return "mock"

    async def connect(self) -> None:
        # Initialize prices from base values
        for inst, config in MOCK_INSTRUMENTS.items():
            self._prices[inst] = config["base"]
        self._connected = True
        logger.info("mock_broker_connected", instruments=len(MOCK_INSTRUMENTS))

    async def disconnect(self) -> None:
        self._connected = False
        logger.info("mock_broker_disconnected")

    async def subscribe_ticks(self, instruments: list[str]) -> AsyncIterator[Quote]:
        """Generate simulated tick data with realistic random walk."""
        if not self._connected:
            raise RuntimeError("Broker not connected")

        resolved = []
        for inst in instruments:
            if inst in MOCK_INSTRUMENTS:
                resolved.append(inst)
            else:
                logger.warning("unknown_instrument", instrument=inst)

        if not resolved:
            raise ValueError(f"No valid instruments to subscribe: {instruments}")

        logger.info("mock_tick_stream_started", instruments=resolved)

        while self._connected:
            for inst in resolved:
                config = MOCK_INSTRUMENTS[inst]
                vol = config["volatility"]

                # Random walk with mean reversion
                current = self._prices[inst]
                base = config["base"]
                mean_revert = (base - current) * 0.001  # slow pull to base
                change = current * random.gauss(0, vol) + mean_revert
                new_price = round(current + change, 2)

                # Ensure price stays positive
                new_price = max(new_price, current * 0.95)
                self._prices[inst] = new_price

                spread = round(new_price * 0.0002, 2)  # ~2 bps spread
                volume = random.randint(100, 5000) * 10

                yield Quote(
                    instrument=inst,
                    ltp=Decimal(str(new_price)),
                    bid=Decimal(str(round(new_price - spread, 2))),
                    ask=Decimal(str(round(new_price + spread, 2))),
                    volume=volume,
                    oi=0,
                    exchange="NSE",
                    timestamp=time.time(),
                )

            await asyncio.sleep(self._tick_interval)

    async def place_order(
        self,
        instrument: str,
        side: str,
        order_type: str,
        quantity: int,
        price: Decimal | None = None,
        trigger_price: Decimal | None = None,
    ) -> OrderResponse:
        self._order_counter += 1
        oid = f"MOCK-{self._order_counter:06d}"

        # Simulate fill with slippage
        base_price = self._prices.get(instrument, 0.0)
        slippage = base_price * random.uniform(0.0001, 0.0005)
        fill_price = base_price + slippage if side == "BUY" else base_price - slippage
        fill_price = round(fill_price, 2)

        # Simulate ~50ms order latency
        await asyncio.sleep(random.uniform(0.03, 0.08))

        order = OrderBook(
            broker_order_id=oid,
            instrument=instrument,
            side=side,
            order_type=order_type,
            quantity=quantity,
            filled_qty=quantity,
            price=price or Decimal(str(base_price)),
            avg_fill_price=Decimal(str(fill_price)),
            status="FILLED",
            timestamp=time.time(),
        )
        self._orders.append(order)

        # Update position
        existing = self._positions.get(instrument)
        if existing:
            if side == "BUY":
                new_qty = existing.quantity + quantity
            else:
                new_qty = existing.quantity - quantity

            if new_qty == 0:
                del self._positions[instrument]
            else:
                existing.quantity = new_qty
                existing.avg_price = Decimal(str(fill_price))
        else:
            qty = quantity if side == "BUY" else -quantity
            self._positions[instrument] = Position(
                instrument=instrument,
                quantity=qty,
                avg_price=Decimal(str(fill_price)),
                pnl=Decimal("0"),
            )

        logger.info(
            "mock_order_filled",
            order_id=oid,
            instrument=instrument,
            side=side,
            quantity=quantity,
            fill_price=fill_price,
        )

        return OrderResponse(broker_order_id=oid, status="FILLED")

    async def cancel_order(self, broker_order_id: str) -> OrderResponse:
        for order in self._orders:
            if order.broker_order_id == broker_order_id and order.status == "OPEN":
                order.status = "CANCELLED"
                return OrderResponse(broker_order_id=broker_order_id, status="CANCELLED")
        return OrderResponse(
            broker_order_id=broker_order_id,
            status="REJECTED",
            message="Order not found or not cancellable",
        )

    async def get_orders(self) -> list[OrderBook]:
        return list(self._orders)

    async def get_positions(self) -> list[Position]:
        return list(self._positions.values())

    async def get_ltp(self, instruments: list[str]) -> dict[str, Decimal]:
        return {
            inst: Decimal(str(self._prices.get(inst, 0)))
            for inst in instruments
            if inst in self._prices
        }
