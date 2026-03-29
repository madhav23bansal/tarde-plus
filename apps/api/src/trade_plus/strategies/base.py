"""Base strategy interface. All strategies implement this ABC."""

from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal

from trade_plus.core.events import BarEvent, FillEvent, SignalEvent, TickEvent


class Strategy(ABC):
    """Abstract base class for trading strategies.

    The engine calls lifecycle methods in order:
    on_start() -> on_tick()/on_bar() [repeated] -> on_stop()
    """

    def __init__(self, strategy_id: str, params: dict | None = None) -> None:
        self.strategy_id = strategy_id
        self.params = params or {}
        self._is_warmed_up = False

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    def is_warmed_up(self) -> bool:
        return self._is_warmed_up

    def on_start(self) -> None:
        """Called once when strategy is activated."""
        pass

    @abstractmethod
    def on_tick(self, tick: TickEvent) -> SignalEvent | None:
        """Called on every tick. Return a signal or None."""
        ...

    def on_bar(self, bar: BarEvent) -> SignalEvent | None:
        """Called on bar close. Override if strategy uses bars."""
        return None

    def on_fill(self, fill: FillEvent) -> None:
        """Called when an order is filled."""
        pass

    def on_stop(self) -> None:
        """Called when strategy is deactivated."""
        pass
