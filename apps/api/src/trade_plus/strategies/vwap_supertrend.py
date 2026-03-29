"""VWAP + SuperTrend intraday strategy.

Entry logic:
- Long: Price crosses above VWAP AND SuperTrend is bullish
- Short: Price crosses below VWAP AND SuperTrend is bearish

Exit logic:
- Trailing stop via SuperTrend flip
- Hard exit at 15:00 IST (flatten all)
"""

from __future__ import annotations

import time
from collections import defaultdict
from decimal import Decimal

import numpy as np
import structlog

from trade_plus.core.events import Side, SignalEvent, TickEvent
from trade_plus.strategies.base import Strategy

logger = structlog.get_logger()

# Default parameters
DEFAULT_PARAMS = {
    "supertrend_period": 10,
    "supertrend_multiplier": 3.0,
    "warmup_ticks": 200,
    "min_signal_strength": 0.3,
}


class VWAPSuperTrendStrategy(Strategy):
    """VWAP + SuperTrend combination strategy."""

    @property
    def name(self) -> str:
        return "vwap_supertrend"

    def __init__(self, strategy_id: str, params: dict | None = None) -> None:
        merged = {**DEFAULT_PARAMS, **(params or {})}
        super().__init__(strategy_id, merged)

        self._warmup = self.params["warmup_ticks"]

        # Per-instrument state
        self._tick_count: dict[str, int] = defaultdict(int)
        self._cum_volume: dict[str, float] = defaultdict(float)
        self._cum_pv: dict[str, float] = defaultdict(float)  # price * volume
        self._highs: dict[str, list[float]] = defaultdict(list)
        self._lows: dict[str, list[float]] = defaultdict(list)
        self._closes: dict[str, list[float]] = defaultdict(list)
        self._vwap: dict[str, float] = defaultdict(float)
        self._prev_above_vwap: dict[str, bool | None] = defaultdict(lambda: None)
        self._supertrend_dir: dict[str, int] = defaultdict(int)  # 1=bull, -1=bear

    def on_start(self) -> None:
        logger.info("strategy_started", strategy=self.name, params=self.params)

    def _update_vwap(self, instrument: str, price: float, volume: int) -> float:
        self._cum_volume[instrument] += volume
        self._cum_pv[instrument] += price * volume
        if self._cum_volume[instrument] > 0:
            vwap = self._cum_pv[instrument] / self._cum_volume[instrument]
            self._vwap[instrument] = vwap
            return vwap
        return price

    def _update_supertrend(self, instrument: str, high: float, low: float, close: float) -> int:
        """Simplified SuperTrend calculation. Returns 1 (bullish) or -1 (bearish)."""
        period = self.params["supertrend_period"]
        mult = self.params["supertrend_multiplier"]

        self._highs[instrument].append(high)
        self._lows[instrument].append(low)
        self._closes[instrument].append(close)

        if len(self._closes[instrument]) < period:
            return 0  # not enough data

        # Keep only what we need
        highs = self._highs[instrument][-period:]
        lows = self._lows[instrument][-period:]
        closes = self._closes[instrument][-period:]

        # ATR calculation (simplified — using range)
        tr_values = [h - l for h, l in zip(highs, lows)]
        atr = sum(tr_values) / len(tr_values)

        hl2 = (highs[-1] + lows[-1]) / 2
        upper_band = hl2 + mult * atr
        lower_band = hl2 - mult * atr

        # Direction
        prev_dir = self._supertrend_dir[instrument]
        if close > upper_band:
            direction = 1
        elif close < lower_band:
            direction = -1
        else:
            direction = prev_dir if prev_dir != 0 else 1

        self._supertrend_dir[instrument] = direction

        # Trim history
        max_keep = period * 3
        if len(self._closes[instrument]) > max_keep:
            self._highs[instrument] = self._highs[instrument][-max_keep:]
            self._lows[instrument] = self._lows[instrument][-max_keep:]
            self._closes[instrument] = self._closes[instrument][-max_keep:]

        return direction

    def on_tick(self, tick: TickEvent) -> SignalEvent | None:
        inst = tick.instrument
        price = float(tick.ltp)
        volume = tick.volume

        self._tick_count[inst] += 1

        # Update VWAP
        vwap = self._update_vwap(inst, price, volume)

        # Update SuperTrend (use tick price as H/L/C approximation)
        spread = float(tick.ask - tick.bid) if tick.ask > tick.bid else price * 0.0002
        high = price + spread / 2
        low = price - spread / 2
        st_dir = self._update_supertrend(inst, high, low, price)

        # Warmup check
        if self._tick_count[inst] < self._warmup:
            if self._tick_count[inst] == self._warmup - 1:
                self._is_warmed_up = True
                logger.info("strategy_warmed_up", strategy=self.name, instrument=inst)
            return None

        # Signal logic: VWAP crossover + SuperTrend confirmation
        above_vwap = price > vwap
        prev_above = self._prev_above_vwap[inst]
        self._prev_above_vwap[inst] = above_vwap

        if prev_above is None or st_dir == 0:
            return None

        signal = None

        # Bullish: price crosses above VWAP + SuperTrend bullish
        if above_vwap and not prev_above and st_dir == 1:
            deviation = (price - vwap) / vwap
            strength = min(abs(deviation) * 100, 1.0)
            if strength >= self.params["min_signal_strength"]:
                signal = SignalEvent(
                    instrument=inst,
                    side=Side.BUY,
                    strength=strength,
                    strategy_id=self.strategy_id,
                    reason=f"VWAP cross up + ST bull | VWAP={vwap:.2f} LTP={price:.2f}",
                )

        # Bearish: price crosses below VWAP + SuperTrend bearish
        elif not above_vwap and prev_above and st_dir == -1:
            deviation = (vwap - price) / vwap
            strength = min(abs(deviation) * 100, 1.0)
            if strength >= self.params["min_signal_strength"]:
                signal = SignalEvent(
                    instrument=inst,
                    side=Side.SELL,
                    strength=strength,
                    strategy_id=self.strategy_id,
                    reason=f"VWAP cross down + ST bear | VWAP={vwap:.2f} LTP={price:.2f}",
                )

        return signal

    def on_stop(self) -> None:
        logger.info("strategy_stopped", strategy=self.name)
