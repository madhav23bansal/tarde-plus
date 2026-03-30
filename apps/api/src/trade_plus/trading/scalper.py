"""Scalping engine v2 — uses stored intraday ticks + circuit breakers.

Two-tier architecture:
  SLOW LOOP (2min): Full signal collection → directional bias update
  FAST LOOP (30s): Store tick → compute intraday technicals → trade

Key improvements over v1:
  - Intraday RSI/EMA/BB from stored 5-min candles (not just 30s snapshots)
  - Trade circuit breakers (consecutive losses, daily loss limit)
  - Today's trade history factors into entry decisions
  - Wider stops (0.5%) and larger targets (0.7%) for ETF noise
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import structlog

from trade_plus.instruments import Direction
from trade_plus.trading.paper_trader import PaperTrader, Order

logger = structlog.get_logger()


class Scalper:
    """Fast-loop scalping engine with intraday technicals and circuit breakers."""

    def __init__(
        self,
        trader: PaperTrader,
        take_profit_pct: float = 0.007,   # 0.7% take profit (wider for ETFs)
        stop_loss_pct: float = 0.005,     # 0.5% stop loss (room for noise)
        min_momentum: float = 0.15,       # 0.15% min momentum to enter
        cooldown_after_loss: int = 10,    # 10 ticks (5 min) cooldown after loss
        cooldown_after_win: int = 5,      # 5 ticks after win
        max_positions: int = 2,
        max_trades_per_instrument: int = 4,  # max round-trips per instrument per day
        max_consecutive_losses: int = 3,     # pause after 3 losses in a row
        daily_loss_limit_pct: float = 0.02,  # stop trading if day loss > 2%
    ) -> None:
        self.trader = trader
        self.take_profit_pct = take_profit_pct
        self.stop_loss_pct = stop_loss_pct
        self.min_momentum = min_momentum
        self.cooldown_after_loss = cooldown_after_loss
        self.cooldown_after_win = cooldown_after_win
        self.max_positions = max_positions
        self.max_trades_per_instrument = max_trades_per_instrument
        self.max_consecutive_losses = max_consecutive_losses
        self.daily_loss_limit_pct = daily_loss_limit_pct

        # Per-instrument state
        self.bias: dict[str, Direction] = {}
        self.bias_score: dict[str, float] = {}
        self.cooldowns: dict[str, int] = {}
        self.trade_count: dict[str, int] = {}  # per instrument today
        self.consecutive_losses: int = 0
        self.paused_until: float = 0  # unix timestamp
        self.tick_count: int = 0

        # Intraday indicators (populated from tick_store)
        self.intraday: dict[str, dict] = {}

    def set_bias(self, instrument: str, direction: Direction, score: float) -> None:
        self.bias[instrument] = direction
        self.bias_score[instrument] = score

    def set_intraday_indicators(self, instrument: str, indicators: dict) -> None:
        """Set intraday technical indicators computed from stored ticks."""
        self.intraday[instrument] = indicators

    def _is_circuit_broken(self) -> tuple[bool, str]:
        """Check circuit breakers."""
        # Daily loss limit
        loss_pct = abs(self.trader.day_pnl) / self.trader.starting_capital
        if self.trader.day_pnl < 0 and loss_pct >= self.daily_loss_limit_pct:
            return True, f"Daily loss limit ({loss_pct:.1%} >= {self.daily_loss_limit_pct:.1%})"

        # Consecutive losses
        if self.consecutive_losses >= self.max_consecutive_losses:
            if time.time() < self.paused_until:
                remaining = int(self.paused_until - time.time())
                return True, f"Paused after {self.consecutive_losses} consecutive losses ({remaining}s remaining)"
            else:
                # Cooldown expired, reset
                self.consecutive_losses = 0

        return False, ""

    def tick(self, prices: dict[str, "PriceTick"], run_id: str = "") -> list[Order]:
        """Process one fast-loop tick."""
        from trade_plus.trading.price_feed import PriceTick
        self.tick_count += 1
        orders: list[Order] = []

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
                    self.cooldowns[inst] = self.cooldown_after_win
                    self.consecutive_losses = 0  # reset on win
                    logger.info("scalp_take_profit", instrument=inst, pnl_pct=f"{pnl_pct:.2%}")

            # Stop loss
            elif pnl_pct <= -self.stop_loss_pct:
                order = self.trader._close_position(inst, price, f"Stop loss ({pnl_pct:.2%})")
                if order:
                    orders.append(order)
                    self.cooldowns[inst] = self.cooldown_after_loss
                    self.consecutive_losses += 1
                    if self.consecutive_losses >= self.max_consecutive_losses:
                        self.paused_until = time.time() + 1800  # 30 min pause
                        logger.warning("scalp_circuit_breaker", losses=self.consecutive_losses, paused_min=30)
                    logger.info("scalp_stop_loss", instrument=inst, pnl_pct=f"{pnl_pct:.2%}")

        # Check circuit breakers before new entries
        broken, reason = self._is_circuit_broken()
        if broken:
            return orders

        # Look for entry signals
        if len(self.trader.positions) >= self.max_positions:
            return orders

        for ticker, tick in prices.items():
            if tick.price <= 0 or ticker in self.trader.positions or ticker in self.cooldowns:
                continue

            # Max trades per instrument per day
            if self.trade_count.get(ticker, 0) >= self.max_trades_per_instrument:
                continue

            bias = self.bias.get(ticker, Direction.FLAT)
            if bias == Direction.FLAT:
                continue

            # Get intraday indicators
            ind = self.intraday.get(ticker, {})
            if not ind:
                continue

            intra_rsi = ind.get("intraday_rsi", 50)
            intra_ema_trend = ind.get("intraday_ema_trend", "")
            above_vwap = ind.get("above_vwap", False)
            momentum = ind.get("momentum_25m", 0)
            bb_pos = ind.get("intraday_bb_position", 0.5)

            # LONG entry conditions
            if bias == Direction.LONG:
                conditions_met = 0
                reasons = []

                if momentum > self.min_momentum:
                    conditions_met += 1
                    reasons.append(f"mom={momentum:+.3f}%")
                if above_vwap:
                    conditions_met += 1
                    reasons.append("above VWAP")
                if intra_rsi < 65:  # not overbought
                    conditions_met += 1
                    reasons.append(f"RSI={intra_rsi:.0f}")
                if intra_ema_trend == "BULL":
                    conditions_met += 1
                    reasons.append("EMA bull")
                if bb_pos < 0.7:  # not at upper band
                    conditions_met += 1
                    reasons.append(f"BB={bb_pos:.2f}")

                if conditions_met >= 3:  # need 3 of 5 conditions
                    reason = f"Scalp LONG ({conditions_met}/5): {', '.join(reasons)} | bias={self.bias_score.get(ticker, 0):+.2f}"
                    order = self.trader.execute_entry(
                        ticker, Direction.LONG, tick.price,
                        self.bias_score.get(ticker, 0), run_id, reason,
                    )
                    if order:
                        orders.append(order)
                        self.trade_count[ticker] = self.trade_count.get(ticker, 0) + 1

            # SHORT entry conditions
            elif bias == Direction.SHORT:
                conditions_met = 0
                reasons = []

                if momentum < -self.min_momentum:
                    conditions_met += 1
                    reasons.append(f"mom={momentum:+.3f}%")
                if not above_vwap:
                    conditions_met += 1
                    reasons.append("below VWAP")
                if intra_rsi > 35:  # not oversold
                    conditions_met += 1
                    reasons.append(f"RSI={intra_rsi:.0f}")
                if intra_ema_trend == "BEAR":
                    conditions_met += 1
                    reasons.append("EMA bear")
                if bb_pos > 0.3:  # not at lower band
                    conditions_met += 1
                    reasons.append(f"BB={bb_pos:.2f}")

                if conditions_met >= 3:
                    reason = f"Scalp SHORT ({conditions_met}/5): {', '.join(reasons)} | bias={self.bias_score.get(ticker, 0):+.2f}"
                    order = self.trader.execute_entry(
                        ticker, Direction.SHORT, tick.price,
                        self.bias_score.get(ticker, 0), run_id, reason,
                    )
                    if order:
                        orders.append(order)
                        self.trade_count[ticker] = self.trade_count.get(ticker, 0) + 1

        return orders

    def get_momentum_status(self) -> dict:
        result = {}
        for inst, ind in self.intraday.items():
            result[inst] = {
                **ind,
                "bias": self.bias.get(inst, Direction.FLAT).value,
                "bias_score": round(self.bias_score.get(inst, 0), 3),
                "cooldown": self.cooldowns.get(inst, 0),
                "trades_today": self.trade_count.get(inst, 0),
            }
        result["_circuit"] = {
            "broken": self._is_circuit_broken()[0],
            "reason": self._is_circuit_broken()[1],
            "consecutive_losses": self.consecutive_losses,
            "day_pnl": round(self.trader.day_pnl, 2),
        }
        return result
