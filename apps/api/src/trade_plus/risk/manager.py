"""Risk management module — sits on the hot path, cannot be bypassed."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from decimal import Decimal

import structlog

from trade_plus.core.config import RiskConfig
from trade_plus.core.events import OrderEvent, SignalEvent, Side

logger = structlog.get_logger()


@dataclass
class RiskState:
    daily_pnl: float = 0.0
    open_positions: int = 0
    order_timestamps: list[float] = field(default_factory=list)
    total_orders_today: int = 0
    is_halted: bool = False
    halt_reason: str = ""


class RiskManager:
    def __init__(self, config: RiskConfig) -> None:
        self._config = config
        self._state = RiskState()

    @property
    def is_halted(self) -> bool:
        return self._state.is_halted

    def check_signal(self, signal: SignalEvent) -> tuple[bool, str]:
        """Pre-trade risk checks. Returns (approved, reason)."""
        if self._state.is_halted:
            return False, f"Trading halted: {self._state.halt_reason}"

        # Daily loss limit
        if self._state.daily_pnl <= -self._config.max_daily_loss:
            self._halt(f"Daily loss limit breached: {self._state.daily_pnl}")
            return False, "Daily loss limit breached"

        # Max open positions
        if self._state.open_positions >= self._config.max_open_positions:
            return False, f"Max open positions ({self._config.max_open_positions}) reached"

        # Rate limiting (orders per second)
        now = time.time()
        self._state.order_timestamps = [
            t for t in self._state.order_timestamps if now - t < 1.0
        ]
        if len(self._state.order_timestamps) >= self._config.max_orders_per_second:
            return False, f"Rate limit: {self._config.max_orders_per_second} OPS"

        return True, "approved"

    def check_order(self, order: OrderEvent) -> tuple[bool, str]:
        """Final check before sending to broker."""
        # Position size
        if order.quantity > self._config.max_position_size:
            return False, f"Position size {order.quantity} > max {self._config.max_position_size}"

        # Order value
        value = float(order.price or Decimal("0")) * order.quantity
        if value > self._config.max_order_value:
            return False, f"Order value {value} > max {self._config.max_order_value}"

        return True, "approved"

    def record_order_sent(self) -> None:
        self._state.order_timestamps.append(time.time())
        self._state.total_orders_today += 1

    def update_pnl(self, pnl_change: float) -> None:
        self._state.daily_pnl += pnl_change
        if self._state.daily_pnl <= -self._config.max_daily_loss:
            self._halt(f"Daily loss limit: {self._state.daily_pnl:.2f}")

    def update_positions(self, count: int) -> None:
        self._state.open_positions = count

    def _halt(self, reason: str) -> None:
        self._state.is_halted = True
        self._state.halt_reason = reason
        logger.critical("risk_halt", reason=reason, state=self._state)

    def kill_switch(self, reason: str = "Manual kill switch") -> None:
        self._halt(reason)

    def resume(self) -> None:
        self._state.is_halted = False
        self._state.halt_reason = ""
        logger.warning("risk_resumed")

    def reset_daily(self) -> None:
        self._state.daily_pnl = 0.0
        self._state.order_timestamps.clear()
        self._state.total_orders_today = 0
        self._state.is_halted = False
        self._state.halt_reason = ""

    def status(self) -> dict:
        return {
            "halted": self._state.is_halted,
            "halt_reason": self._state.halt_reason,
            "daily_pnl": self._state.daily_pnl,
            "open_positions": self._state.open_positions,
            "orders_today": self._state.total_orders_today,
            "orders_last_second": len(self._state.order_timestamps),
        }
