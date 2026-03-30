"""Scalping engine — fast-loop trader for multiple small profits per day.

Two-tier architecture:
  FAST LOOP (30s): Price feed → momentum check → trade → P&L
  SLOW LOOP (10min): Full signal collection → directional bias update

Trading logic:
  1. Slow loop sets BIAS per instrument: LONG, SHORT, or FLAT
  2. Fast loop enters when price momentum aligns with bias
  3. Take profit at target_pct (0.3-0.5%)
  4. Cut loss at stop_pct (0.2%)
  5. Re-enter on next momentum signal
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field

import structlog

from trade_plus.instruments import Direction
from trade_plus.trading.paper_trader import PaperTrader, Order

logger = structlog.get_logger()


@dataclass
class MomentumState:
    """Price momentum tracker for one instrument."""
    prices: deque = field(default_factory=lambda: deque(maxlen=20))  # last 20 ticks
    vwap: float = 0.0
    cum_volume: float = 0.0
    cum_pv: float = 0.0        # price × volume
    trend: float = 0.0         # -1 to +1, short-term trend
    momentum: float = 0.0      # rate of change
    above_vwap: bool = False

    def update(self, price: float, volume: int) -> None:
        self.prices.append(price)

        # VWAP
        self.cum_volume += volume
        self.cum_pv += price * volume
        if self.cum_volume > 0:
            self.vwap = self.cum_pv / self.cum_volume

        self.above_vwap = price > self.vwap

        # Short-term trend: compare last 3 vs last 10
        if len(self.prices) >= 10:
            recent_avg = sum(list(self.prices)[-3:]) / 3
            older_avg = sum(list(self.prices)[-10:-3]) / 7
            if older_avg > 0:
                self.trend = (recent_avg - older_avg) / older_avg * 100
            self.momentum = (price - list(self.prices)[-5]) / list(self.prices)[-5] * 100 if len(self.prices) >= 5 and list(self.prices)[-5] > 0 else 0

    def reset_vwap(self) -> None:
        """Reset VWAP at start of day."""
        self.cum_volume = 0
        self.cum_pv = 0
        self.vwap = 0
        self.prices.clear()


class Scalper:
    """Fast-loop scalping engine that works with PaperTrader."""

    def __init__(
        self,
        trader: PaperTrader,
        take_profit_pct: float = 0.004,   # 0.4% take profit
        stop_loss_pct: float = 0.002,     # 0.2% stop loss
        min_momentum: float = 0.05,       # minimum price momentum to enter (0.05%)
        cooldown_ticks: int = 3,          # wait 3 ticks after closing before re-entering
        max_positions: int = 2,           # max simultaneous positions
    ) -> None:
        self.trader = trader
        self.take_profit_pct = take_profit_pct
        self.stop_loss_pct = stop_loss_pct
        self.min_momentum = min_momentum
        self.cooldown_ticks = cooldown_ticks
        self.max_positions = max_positions

        # Per-instrument state
        self.momentum: dict[str, MomentumState] = {}
        self.bias: dict[str, Direction] = {}     # from slow loop
        self.bias_score: dict[str, float] = {}
        self.cooldowns: dict[str, int] = {}      # ticks remaining before can trade
        self.tick_count: int = 0

    def set_bias(self, instrument: str, direction: Direction, score: float) -> None:
        """Set directional bias from the slow loop (prediction engine)."""
        self.bias[instrument] = direction
        self.bias_score[instrument] = score

    def tick(self, prices: dict[str, "PriceTick"], run_id: str = "") -> list[Order]:
        """Process one fast-loop tick. Returns list of orders executed."""
        from trade_plus.trading.price_feed import PriceTick
        self.tick_count += 1
        orders: list[Order] = []

        # Update momentum for each instrument
        for ticker, tick in prices.items():
            if tick.price <= 0:
                continue

            if ticker not in self.momentum:
                self.momentum[ticker] = MomentumState()
            self.momentum[ticker].update(tick.price, tick.volume)

        # Decrement cooldowns
        for inst in list(self.cooldowns.keys()):
            self.cooldowns[inst] -= 1
            if self.cooldowns[inst] <= 0:
                del self.cooldowns[inst]

        # Update prices in trader
        price_map = {t: p.price for t, p in prices.items() if p.price > 0}
        self.trader.update_prices(price_map)

        # Check take-profit and stop-loss on open positions
        for inst in list(self.trader.positions.keys()):
            pos = self.trader.positions[inst]
            price = price_map.get(inst, pos.current_price)
            if price <= 0:
                continue

            if pos.side == "LONG":
                pnl_pct = (price - pos.entry_price) / pos.entry_price
            else:
                pnl_pct = (pos.entry_price - price) / pos.entry_price

            # Take profit
            if pnl_pct >= self.take_profit_pct:
                order = self.trader._close_position(inst, price, f"Take profit ({pnl_pct:.2%})")
                if order:
                    orders.append(order)
                    self.cooldowns[inst] = self.cooldown_ticks
                    logger.info("scalp_take_profit", instrument=inst, pnl_pct=f"{pnl_pct:.2%}")

            # Stop loss
            elif pnl_pct <= -self.stop_loss_pct:
                order = self.trader._close_position(inst, price, f"Stop loss ({pnl_pct:.2%})")
                if order:
                    orders.append(order)
                    self.cooldowns[inst] = self.cooldown_ticks
                    logger.info("scalp_stop_loss", instrument=inst, pnl_pct=f"{pnl_pct:.2%}")

        # Look for entry signals
        if len(self.trader.positions) < self.max_positions:
            for ticker, tick in prices.items():
                if tick.price <= 0 or ticker in self.trader.positions or ticker in self.cooldowns:
                    continue

                bias = self.bias.get(ticker, Direction.FLAT)
                if bias == Direction.FLAT:
                    continue

                mom = self.momentum.get(ticker)
                if not mom or len(mom.prices) < 5:
                    continue

                # Entry conditions: momentum aligns with bias
                if bias == Direction.LONG and mom.momentum > self.min_momentum and mom.above_vwap:
                    reason = f"Scalp LONG: momentum={mom.momentum:.3f}%, above VWAP, bias=LONG({self.bias_score.get(ticker, 0):+.2f})"
                    order = self.trader.execute_entry(
                        ticker, Direction.LONG, tick.price,
                        self.bias_score.get(ticker, 0), run_id, reason,
                    )
                    if order:
                        orders.append(order)

                elif bias == Direction.SHORT and mom.momentum < -self.min_momentum and not mom.above_vwap:
                    reason = f"Scalp SHORT: momentum={mom.momentum:.3f}%, below VWAP, bias=SHORT({self.bias_score.get(ticker, 0):+.2f})"
                    order = self.trader.execute_entry(
                        ticker, Direction.SHORT, tick.price,
                        self.bias_score.get(ticker, 0), run_id, reason,
                    )
                    if order:
                        orders.append(order)

        return orders

    def get_momentum_status(self) -> dict:
        """Momentum state for all instruments — for dashboard."""
        result = {}
        for inst, mom in self.momentum.items():
            result[inst] = {
                "vwap": round(mom.vwap, 2),
                "trend": round(mom.trend, 4),
                "momentum": round(mom.momentum, 4),
                "above_vwap": mom.above_vwap,
                "ticks": len(mom.prices),
                "bias": self.bias.get(inst, Direction.FLAT).value,
                "bias_score": round(self.bias_score.get(inst, 0), 3),
                "cooldown": self.cooldowns.get(inst, 0),
            }
        return result
