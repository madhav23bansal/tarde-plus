"""In-process message bus for zero-latency event routing on the hot path."""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from typing import Callable, Coroutine

import structlog

from trade_plus.core.events import Event, EventType

logger = structlog.get_logger()

# Type alias for event handlers
EventHandler = Callable[[Event], Coroutine]


class MessageBus:
    """Publish/subscribe message bus using direct Python object passing.

    No serialization, no network hops. Handlers are invoked sequentially
    on the same event loop to maintain deterministic ordering.
    """

    def __init__(self) -> None:
        self._handlers: dict[EventType, list[EventHandler]] = defaultdict(list)
        self._latency_samples: list[float] = []

    def subscribe(self, event_type: EventType, handler: EventHandler) -> None:
        self._handlers[event_type].append(handler)
        logger.info("handler_subscribed", event_type=event_type.name, handler=handler.__qualname__)

    def unsubscribe(self, event_type: EventType, handler: EventHandler) -> None:
        self._handlers[event_type].remove(handler)

    async def publish(self, event: Event) -> None:
        handlers = self._handlers.get(event.event_type, [])
        if not handlers:
            return

        start = time.perf_counter_ns()
        for handler in handlers:
            try:
                await handler(event)
            except Exception:
                logger.exception(
                    "handler_error",
                    event_type=event.event_type.name,
                    handler=handler.__qualname__,
                )

        elapsed_us = (time.perf_counter_ns() - start) / 1000
        self._latency_samples.append(elapsed_us)

        # Keep last 1000 samples
        if len(self._latency_samples) > 1000:
            self._latency_samples = self._latency_samples[-1000:]

    @property
    def avg_latency_us(self) -> float:
        if not self._latency_samples:
            return 0.0
        return sum(self._latency_samples) / len(self._latency_samples)

    @property
    def handler_count(self) -> int:
        return sum(len(h) for h in self._handlers.values())

    def stats(self) -> dict:
        samples = self._latency_samples
        if not samples:
            return {"avg_us": 0, "p99_us": 0, "handler_count": 0}
        sorted_s = sorted(samples)
        p99_idx = int(len(sorted_s) * 0.99)
        return {
            "avg_us": sum(samples) / len(samples),
            "p99_us": sorted_s[p99_idx] if sorted_s else 0,
            "handler_count": self.handler_count,
            "sample_count": len(samples),
        }
