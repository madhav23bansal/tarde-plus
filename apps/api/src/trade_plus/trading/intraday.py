"""Smart Intraday Trader — holds positions for hours, not seconds.

Lifecycle:
  9:15-10:00 AM:  Collect data, build conviction (don't trade yet)
  10:00-10:30 AM: Enter if confidence >= threshold (morning breakout)
  10:30-2:30 PM:  Monitor, check stop/target, may reverse on strong signal flip
  2:30-2:45 PM:   No new positions
  2:45-3:15 PM:   Square off everything

Entry rules:
  - Ensemble prediction confidence >= 25%
  - At least 2 of: ML agrees, rules agree, intraday trend confirms
  - Not oversold for SHORT / not overbought for LONG (intraday RSI)

Exit rules:
  - Take profit at 0.8-1.2% (dynamic based on today's volatility)
  - Stop loss at 0.4-0.6% (dynamic)
  - Signal reversal with strong confidence → close and reverse
  - EOD square-off at 3:15 PM

Position sizing:
  - Risk 2% of capital per trade
  - Max 2 simultaneous positions
  - Max 4 total round-trips per day
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, time as dt_time
from zoneinfo import ZoneInfo

import structlog

from trade_plus.instruments import Direction
from trade_plus.prediction import Prediction
from trade_plus.trading.paper_trader import PaperTrader, Order

logger = structlog.get_logger()
IST = ZoneInfo("Asia/Kolkata")

# Trading windows (IST)
OBSERVATION_END = dt_time(10, 0)    # don't trade before 10:00 AM
ENTRY_WINDOW_END = dt_time(14, 30)  # no new positions after 2:30 PM
SQUAREOFF_TIME = dt_time(15, 15)    # close everything by 3:15 PM


@dataclass
class TradeDecision:
    instrument: str
    action: str       # "ENTER_LONG", "ENTER_SHORT", "EXIT", "REVERSE", "HOLD", "SKIP"
    confidence: float
    reasons: list[str]
    score: float = 0.0


class IntradayTrader:
    """Smart intraday engine — 1-4 trades per day, holds for hours."""

    def __init__(
        self,
        trader: PaperTrader,
        min_confidence: float = 0.25,        # 25% minimum to enter
        take_profit_pct: float = 0.010,      # 1.0% take profit
        stop_loss_pct: float = 0.005,        # 0.5% stop loss
        reversal_confidence: float = 0.35,   # need 35% to reverse a position
        max_positions: int = 2,
        max_round_trips: int = 4,
    ) -> None:
        self.trader = trader
        self.min_confidence = min_confidence
        self.take_profit_pct = take_profit_pct
        self.stop_loss_pct = stop_loss_pct
        self.reversal_confidence = reversal_confidence
        self.max_positions = max_positions
        self.max_round_trips = max_round_trips

        self.round_trips: dict[str, int] = {}
        self.last_prediction: dict[str, Prediction] = {}
        self.intraday: dict[str, dict] = {}
        self.day_volatility: dict[str, float] = {}  # today's range %

    def set_intraday_indicators(self, instrument: str, indicators: dict) -> None:
        self.intraday[instrument] = indicators
        # Track today's volatility for dynamic targets
        if indicators.get("current_price", 0) > 0:
            today_range = indicators.get("range_pct", 0)
            if today_range:
                self.day_volatility[instrument] = today_range

    def _now_ist(self) -> datetime:
        return datetime.now(IST)

    def _in_observation(self) -> bool:
        """Before 10:00 AM — just observe, don't trade."""
        return self._now_ist().time() < OBSERVATION_END

    def _can_open(self) -> bool:
        """Within entry window (10:00 AM - 2:30 PM)."""
        t = self._now_ist().time()
        return OBSERVATION_END <= t < ENTRY_WINDOW_END

    def _should_squareoff(self) -> bool:
        return self._now_ist().time() >= SQUAREOFF_TIME

    def _get_dynamic_targets(self, instrument: str) -> tuple[float, float]:
        """Adjust take profit / stop loss based on today's volatility."""
        vol = self.day_volatility.get(instrument, 0)
        if vol > 2.0:
            # High volatility day — wider targets
            return 0.012, 0.006   # 1.2% TP, 0.6% SL
        elif vol > 1.0:
            return 0.010, 0.005   # 1.0% TP, 0.5% SL
        else:
            # Low volatility — tighter targets
            return 0.007, 0.004   # 0.7% TP, 0.4% SL

    def decide(self, instrument: str, prediction: Prediction, price: float) -> TradeDecision:
        """Make a trading decision for one instrument."""
        self.last_prediction[instrument] = prediction
        ind = self.intraday.get(instrument, {})
        pos = self.trader.positions.get(instrument)
        tp, sl = self._get_dynamic_targets(instrument)

        # ── Square-off time ──
        if self._should_squareoff() and pos:
            return TradeDecision(instrument, "EXIT", 1.0, ["EOD square-off at 3:15 PM"])

        # ── Observation period ──
        if self._in_observation():
            return TradeDecision(instrument, "SKIP", 0, ["Observation period (before 10:00 AM) — building conviction"])

        # ── Check existing position ──
        if pos:
            if pos.side == "LONG":
                pnl_pct = (price - pos.entry_price) / pos.entry_price
            else:
                pnl_pct = (pos.entry_price - price) / pos.entry_price

            # Take profit
            if pnl_pct >= tp:
                return TradeDecision(instrument, "EXIT", 1.0,
                    [f"Take profit hit: {pnl_pct:.2%} >= {tp:.1%}"],
                    score=pnl_pct)

            # Stop loss
            if pnl_pct <= -sl:
                return TradeDecision(instrument, "EXIT", 1.0,
                    [f"Stop loss hit: {pnl_pct:.2%} <= -{sl:.1%}"],
                    score=pnl_pct)

            # Signal reversal — need higher confidence to reverse than to enter
            opposite = (pos.side == "LONG" and prediction.direction == Direction.SHORT) or \
                       (pos.side == "SHORT" and prediction.direction == Direction.LONG)
            if opposite and prediction.confidence >= self.reversal_confidence:
                return TradeDecision(instrument, "REVERSE", prediction.confidence,
                    [f"Signal reversed to {prediction.direction.value} with {prediction.confidence:.0%} conf",
                     f"Current P&L: {pnl_pct:+.2%}"] + prediction.reasons[:2],
                    score=prediction.score)

            # Hold
            return TradeDecision(instrument, "HOLD", prediction.confidence,
                [f"Holding {pos.side} — P&L: {pnl_pct:+.2%}",
                 f"TP at {tp:.1%}, SL at {sl:.1%}"])

        # ── No position — should we enter? ──

        if not self._can_open():
            return TradeDecision(instrument, "SKIP", 0, ["Past 2:30 PM — no new positions"])

        if prediction.direction == Direction.FLAT:
            return TradeDecision(instrument, "SKIP", 0, ["Prediction is FLAT — no trade"])

        if prediction.confidence < self.min_confidence:
            return TradeDecision(instrument, "SKIP", prediction.confidence,
                [f"Confidence {prediction.confidence:.0%} below {self.min_confidence:.0%} threshold"])

        if self.round_trips.get(instrument, 0) >= self.max_round_trips:
            return TradeDecision(instrument, "SKIP", 0,
                [f"Max round-trips ({self.max_round_trips}) reached for {instrument}"])

        if len(self.trader.positions) >= self.max_positions:
            return TradeDecision(instrument, "SKIP", 0,
                [f"Max {self.max_positions} positions already open"])

        # ── Confirmation checks ──
        confirmations = 0
        confirm_reasons = []

        # ML agrees?
        if prediction.ml_score != 0:
            if (prediction.direction == Direction.LONG and prediction.ml_score > 0) or \
               (prediction.direction == Direction.SHORT and prediction.ml_score < 0):
                confirmations += 1
                confirm_reasons.append(f"ML agrees ({prediction.ml_score:+.2f})")

        # Rules agree?
        if prediction.rules_score != 0:
            if (prediction.direction == Direction.LONG and prediction.rules_score > 0) or \
               (prediction.direction == Direction.SHORT and prediction.rules_score < 0):
                confirmations += 1
                confirm_reasons.append(f"Rules agree ({prediction.rules_score:+.2f})")

        # Intraday trend confirms?
        if ind:
            intra_ema = ind.get("intraday_ema_trend", "")
            if (prediction.direction == Direction.LONG and intra_ema == "BULL") or \
               (prediction.direction == Direction.SHORT and intra_ema == "BEAR"):
                confirmations += 1
                confirm_reasons.append(f"Intraday EMA={intra_ema}")

            # RSI sanity check
            intra_rsi = ind.get("intraday_rsi", 50)
            if prediction.direction == Direction.LONG and intra_rsi > 75:
                return TradeDecision(instrument, "SKIP", prediction.confidence,
                    [f"Intraday RSI={intra_rsi:.0f} — overbought, skip LONG"])
            if prediction.direction == Direction.SHORT and intra_rsi < 25:
                return TradeDecision(instrument, "SKIP", prediction.confidence,
                    [f"Intraday RSI={intra_rsi:.0f} — oversold, skip SHORT"])

        if confirmations < 2:
            return TradeDecision(instrument, "SKIP", prediction.confidence,
                [f"Only {confirmations}/3 confirmations — need 2",
                 f"Checked: ML, Rules, Intraday EMA"] + confirm_reasons)

        # ── Enter ──
        action = "ENTER_LONG" if prediction.direction == Direction.LONG else "ENTER_SHORT"
        reasons = [
            f"{confirmations}/3 confirmations: {', '.join(confirm_reasons)}",
            f"Ensemble: {prediction.score:+.3f} ({prediction.confidence:.0%})",
            f"Targets: TP={tp:.1%} SL={sl:.1%} (vol={self.day_volatility.get(instrument, 0):.1f}%)",
        ] + prediction.reasons[:2]

        return TradeDecision(instrument, action, prediction.confidence, reasons, prediction.score)

    def execute(self, decision: TradeDecision, price: float, run_id: str) -> Order | None:
        """Execute a trading decision."""
        if decision.action == "SKIP" or decision.action == "HOLD":
            return None

        if decision.action == "EXIT":
            order = self.trader._close_position(decision.instrument, price, decision.reasons[0])
            if order:
                self.round_trips[decision.instrument] = self.round_trips.get(decision.instrument, 0) + 1
            return order

        if decision.action == "REVERSE":
            # Close existing + open opposite
            self.trader._close_position(decision.instrument, price, f"Reversal: {decision.reasons[0]}")
            self.round_trips[decision.instrument] = self.round_trips.get(decision.instrument, 0) + 1
            direction = Direction.LONG if "LONG" in decision.reasons[0] else Direction.SHORT
            return self.trader.execute_entry(
                decision.instrument, direction, price,
                decision.score, run_id, f"Reversal entry: {decision.reasons[0]}",
            )

        if decision.action in ("ENTER_LONG", "ENTER_SHORT"):
            direction = Direction.LONG if "LONG" in decision.action else Direction.SHORT
            order = self.trader.execute_entry(
                decision.instrument, direction, price,
                decision.score, run_id, " | ".join(decision.reasons[:2]),
            )
            return order

        return None

    def get_status(self) -> dict:
        """Full status for dashboard."""
        decisions = {}
        for inst, pred in self.last_prediction.items():
            ind = self.intraday.get(inst, {})
            pos = self.trader.positions.get(inst)
            price = ind.get("current_price", 0)
            if price > 0:
                d = self.decide(inst, pred, price)
                decisions[inst] = {
                    "action": d.action,
                    "confidence": round(d.confidence, 3),
                    "reasons": d.reasons,
                    "round_trips": self.round_trips.get(inst, 0),
                    "intraday": ind,
                }

        return {
            "mode": "intraday_swing",
            "observation_period": self._in_observation(),
            "can_open": self._can_open(),
            "should_squareoff": self._should_squareoff(),
            "decisions": decisions,
            "volatility": {k: round(v, 2) for k, v in self.day_volatility.items()},
        }
