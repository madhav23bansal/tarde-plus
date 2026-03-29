"""Main trading engine — orchestrates the hot path event loop."""

from __future__ import annotations

import asyncio
import time
from decimal import Decimal

import structlog

from trade_plus.brokers.base import BrokerAdapter
from trade_plus.core.config import AppConfig
from trade_plus.core.events import (
    EventType,
    FillEvent,
    OrderEvent,
    OrderStatus,
    OrderType,
    Side,
    SignalEvent,
    TickEvent,
)
from trade_plus.core.message_bus import MessageBus
from trade_plus.data.redis_store import RedisStore
from trade_plus.risk.manager import RiskManager
from trade_plus.strategies.base import Strategy

logger = structlog.get_logger()


class TradingEngine:
    """Core engine that wires together all components on the hot path."""

    def __init__(
        self,
        config: AppConfig,
        broker: BrokerAdapter,
        strategies: list[Strategy],
    ) -> None:
        self._config = config
        self._broker = broker
        self._strategies = {s.strategy_id: s for s in strategies}
        self._bus = MessageBus()
        self._risk = RiskManager(config.risk)
        self._redis = RedisStore(config.redis)
        self._running = False
        self._tick_count = 0
        self._order_count = 0
        self._start_time = 0.0

    async def start(self, instruments: list[str]) -> None:
        """Start the engine: connect services, wire handlers, stream ticks."""
        logger.info("engine_starting", broker=self._broker.name, instruments=instruments)

        # Connect infrastructure
        await self._broker.connect()
        await self._redis.connect()

        # Wire message bus handlers
        self._bus.subscribe(EventType.TICK, self._on_tick)
        self._bus.subscribe(EventType.SIGNAL, self._on_signal)
        self._bus.subscribe(EventType.FILL, self._on_fill)

        # Start strategies
        for strategy in self._strategies.values():
            strategy.on_start()

        self._running = True
        self._start_time = time.time()

        logger.info(
            "engine_started",
            strategies=list(self._strategies.keys()),
            risk_status=self._risk.status(),
        )

        # Main tick loop
        try:
            async for quote in self._broker.subscribe_ticks(instruments):
                if not self._running:
                    break

                tick = TickEvent(
                    instrument=quote.instrument,
                    ltp=quote.ltp,
                    bid=quote.bid,
                    ask=quote.ask,
                    volume=quote.volume,
                    oi=quote.oi,
                    exchange=quote.exchange,
                    exchange_timestamp=quote.timestamp,
                )
                await self._bus.publish(tick)
                self._tick_count += 1

                # Periodic status log
                if self._tick_count % 100 == 0:
                    elapsed = time.time() - self._start_time
                    bus_stats = self._bus.stats()
                    logger.info(
                        "engine_heartbeat",
                        ticks=self._tick_count,
                        orders=self._order_count,
                        elapsed_s=round(elapsed, 1),
                        bus_avg_us=round(bus_stats["avg_us"], 1),
                        bus_p99_us=round(bus_stats["p99_us"], 1),
                        risk=self._risk.status(),
                    )

        except asyncio.CancelledError:
            logger.info("engine_cancelled")
        finally:
            await self.stop()

    async def stop(self) -> None:
        """Graceful shutdown."""
        self._running = False
        for strategy in self._strategies.values():
            strategy.on_stop()
        await self._broker.disconnect()
        await self._redis.disconnect()
        logger.info(
            "engine_stopped",
            total_ticks=self._tick_count,
            total_orders=self._order_count,
        )

    async def _on_tick(self, event: TickEvent) -> None:
        """Route tick to all strategies."""
        # Cache in Redis (fire-and-forget for cold path)
        asyncio.create_task(
            self._redis.set_tick(event.instrument, {
                "ltp": str(event.ltp),
                "bid": str(event.bid),
                "ask": str(event.ask),
                "volume": event.volume,
                "ts": event.timestamp,
            })
        )

        # Hot path: evaluate strategies
        for strategy in self._strategies.values():
            signal = strategy.on_tick(event)
            if signal:
                await self._bus.publish(signal)

    async def _on_signal(self, event: SignalEvent) -> None:
        """Risk check and convert signal to order."""
        approved, reason = self._risk.check_signal(event)
        if not approved:
            logger.warning("signal_rejected", reason=reason, signal=event)
            return

        # Create order from signal
        order = OrderEvent(
            instrument=event.instrument,
            side=event.side,
            order_type=OrderType.MARKET,
            quantity=1,  # TODO: position sizing
            strategy_id=event.strategy_id,
        )

        approved, reason = self._risk.check_order(order)
        if not approved:
            logger.warning("order_rejected", reason=reason, order=order)
            return

        # Execute
        self._risk.record_order_sent()
        response = await self._broker.place_order(
            instrument=order.instrument,
            side=order.side.value,
            order_type=order.order_type.value,
            quantity=order.quantity,
        )

        self._order_count += 1
        logger.info(
            "order_placed",
            broker_id=response.broker_order_id,
            status=response.status,
            instrument=order.instrument,
            side=order.side.value,
            strategy=order.strategy_id,
        )

        if response.status == "FILLED":
            fill = FillEvent(
                order_id=order.order_id,
                instrument=order.instrument,
                side=order.side,
                quantity=order.quantity,
                broker_order_id=response.broker_order_id,
            )
            await self._bus.publish(fill)

    async def _on_fill(self, event: FillEvent) -> None:
        """Notify strategies of fills."""
        for strategy in self._strategies.values():
            strategy.on_fill(event)
