"""Paper trading engine — executes mock trades using live prices.

Mirrors Shoonya's order flow exactly:
  1. Place order → get order_id
  2. Order fills at market price + simulated slippage
  3. Track positions, P&L, charges in real-time
  4. Square off all positions at 3:15 PM

Everything is persisted to PostgreSQL for later verification.
When switching to real Shoonya, only the execution layer changes.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

import structlog

from trade_plus.instruments import Direction, Instrument
from trade_plus.trading.charges import calculate_round_trip, calculate_leg, D

logger = structlog.get_logger()

# Simulated slippage: 0.02% for liquid ETFs (1-2 paise on Rs 260)
SLIPPAGE_PCT = 0.0002


@dataclass
class Order:
    order_id: str
    instrument: str
    side: str               # "BUY" or "SELL"
    quantity: int
    order_type: str         # "MARKET" or "LIMIT"
    product: str            # "MIS" (intraday)
    status: str             # PENDING → COMPLETE / REJECTED
    signal_price: float     # price when signal was generated
    fill_price: float = 0.0 # actual fill price (with slippage)
    placed_at: float = 0.0  # unix timestamp ms
    filled_at: float = 0.0
    charges: float = 0.0
    pnl: float = 0.0       # only for closing orders
    run_id: str = ""        # which pipeline run triggered this
    prediction_score: float = 0.0
    prediction_direction: str = ""
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "order_id": self.order_id,
            "instrument": self.instrument,
            "side": self.side,
            "quantity": self.quantity,
            "order_type": self.order_type,
            "product": self.product,
            "status": self.status,
            "signal_price": self.signal_price,
            "fill_price": self.fill_price,
            "placed_at": self.placed_at,
            "filled_at": self.filled_at,
            "charges": self.charges,
            "pnl": self.pnl,
            "run_id": self.run_id,
            "prediction_score": self.prediction_score,
            "prediction_direction": self.prediction_direction,
            "reason": self.reason,
        }


@dataclass
class Position:
    instrument: str
    side: str               # "LONG" or "SHORT"
    quantity: int
    entry_price: float
    entry_time: float
    entry_order_id: str
    current_price: float = 0.0
    unrealized_pnl: float = 0.0
    charges_entry: float = 0.0
    high_water_pnl_pct: float = 0.0  # best P&L % reached, for trailing stop

    def to_dict(self) -> dict:
        return {
            "instrument": self.instrument,
            "side": self.side,
            "quantity": self.quantity,
            "entry_price": self.entry_price,
            "entry_time": self.entry_time,
            "entry_order_id": self.entry_order_id,
            "current_price": self.current_price,
            "unrealized_pnl": self.unrealized_pnl,
            "charges_entry": self.charges_entry,
        }


@dataclass
class DayResult:
    date: str
    starting_capital: float
    ending_capital: float
    gross_pnl: float
    total_charges: float
    net_pnl: float
    trades_count: int
    wins: int
    losses: int
    win_rate: float
    max_drawdown: float
    instruments_traded: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return self.__dict__.copy()


class PaperTrader:
    """Mock trading engine with realistic execution simulation."""

    def __init__(
        self,
        capital: float = 50_000.0,
        leverage: float = 5.0,
        max_risk_pct: float = 0.02,      # 2% of capital per trade
        min_confidence: float = 0.35,     # minimum prediction confidence to trade
        stop_loss_pct: float = 0.01,      # 1% stop loss
        max_daily_loss: float = 5000.0,   # stop trading after this loss
        broker: str = "shoonya",
    ) -> None:
        self.starting_capital = capital
        self.capital = capital
        self.leverage = leverage
        self.max_risk_pct = max_risk_pct
        self.min_confidence = min_confidence
        self.stop_loss_pct = stop_loss_pct
        self.max_daily_loss = max_daily_loss
        self.broker = broker

        self.positions: dict[str, Position] = {}
        self.orders: list[Order] = []
        self.closed_trades: list[dict] = []
        self.day_pnl: float = 0.0
        self.day_charges: float = 0.0
        self.day_trades: int = 0
        self.day_wins: int = 0
        self.day_losses: int = 0
        self.peak_capital: float = capital
        self.max_drawdown: float = 0.0

    @property
    def buying_power(self) -> float:
        return self.capital * self.leverage

    @property
    def total_unrealized_pnl(self) -> float:
        return sum(p.unrealized_pnl for p in self.positions.values())

    @property
    def net_equity(self) -> float:
        return self.capital + self.total_unrealized_pnl

    def should_trade(self, instrument: str, direction: Direction, confidence: float, score: float) -> tuple[bool, str]:
        """Decide whether to enter a trade."""
        if direction == Direction.FLAT:
            return False, "Signal is FLAT"

        if self.day_pnl <= -self.max_daily_loss:
            return False, f"Daily loss limit hit: Rs {self.day_pnl:.0f}"

        if confidence < self.min_confidence:
            return False, f"Confidence {confidence:.0%} below threshold {self.min_confidence:.0%}"

        if instrument in self.positions:
            pos = self.positions[instrument]
            # If same direction, skip (already in position)
            if (pos.side == "LONG" and direction == Direction.LONG) or \
               (pos.side == "SHORT" and direction == Direction.SHORT):
                return False, f"Already {pos.side} on {instrument}"
            # If opposite direction, we'll close and reverse
            return True, f"Reversing from {pos.side} to {direction.value}"

        # Check capital
        if self.capital < self.starting_capital * 0.05:
            return False, "Capital too low (< 5% of starting)"

        return True, "Signal accepted"

    def execute_entry(
        self,
        instrument: str,
        direction: Direction,
        current_price: float,
        prediction_score: float,
        run_id: str,
        reason: str,
    ) -> Order | None:
        """Enter a new position or reverse an existing one."""
        now = time.time()

        # Close existing opposite position first
        if instrument in self.positions:
            self._close_position(instrument, current_price, "Signal reversal")

        # Calculate position size
        risk_amount = self.capital * self.max_risk_pct
        quantity = max(1, int(risk_amount / current_price))

        # Ensure we don't exceed buying power
        trade_value = quantity * current_price
        if trade_value > self.buying_power:
            quantity = max(1, int(self.buying_power / current_price))
            trade_value = quantity * current_price

        # Simulate slippage
        if direction == Direction.LONG:
            fill_price = current_price * (1 + SLIPPAGE_PCT)  # buy slightly higher
            side = "BUY"
        else:
            fill_price = current_price * (1 - SLIPPAGE_PCT)  # sell slightly lower
            side = "SELL"

        fill_price = round(fill_price, 2)

        # Calculate entry charges
        charges_obj = calculate_leg(D(str(trade_value)), side, self.broker)
        charges = float(charges_obj.total)

        # Create order
        order = Order(
            order_id=str(uuid.uuid4()),
            instrument=instrument,
            side=side,
            quantity=quantity,
            order_type="MARKET",
            product="MIS",
            status="COMPLETE",
            signal_price=current_price,
            fill_price=fill_price,
            placed_at=now,
            filled_at=now,
            charges=charges,
            run_id=run_id,
            prediction_score=prediction_score,
            prediction_direction=direction.value,
            reason=reason,
        )
        self.orders.append(order)

        # Create position
        self.positions[instrument] = Position(
            instrument=instrument,
            side="LONG" if direction == Direction.LONG else "SHORT",
            quantity=quantity,
            entry_price=fill_price,
            entry_time=now,
            entry_order_id=order.order_id,
            current_price=current_price,
            charges_entry=charges,
        )

        self.capital -= charges
        self.day_charges += charges
        self.day_trades += 1

        logger.info(
            "paper_trade_entry",
            instrument=instrument,
            side=side,
            quantity=quantity,
            signal_price=current_price,
            fill_price=fill_price,
            charges=round(charges, 2),
            capital=round(self.capital, 2),
        )

        return order

    def _close_position(self, instrument: str, current_price: float, reason: str) -> Order | None:
        """Close an existing position."""
        pos = self.positions.get(instrument)
        if not pos:
            return None

        now = time.time()

        # Determine close side
        if pos.side == "LONG":
            close_side = "SELL"
            fill_price = current_price * (1 - SLIPPAGE_PCT)  # sell slightly lower
            gross_pnl = (fill_price - pos.entry_price) * pos.quantity
        else:
            close_side = "BUY"
            fill_price = current_price * (1 + SLIPPAGE_PCT)  # buy slightly higher
            gross_pnl = (pos.entry_price - fill_price) * pos.quantity

        fill_price = round(fill_price, 2)
        trade_value = pos.quantity * fill_price

        # Calculate exit charges
        charges_obj = calculate_leg(D(str(trade_value)), close_side, self.broker)
        exit_charges = float(charges_obj.total)
        total_charges = pos.charges_entry + exit_charges

        # Round trip charge calculation
        net_pnl = gross_pnl - total_charges

        # Create close order
        order = Order(
            order_id=str(uuid.uuid4()),
            instrument=instrument,
            side=close_side,
            quantity=pos.quantity,
            order_type="MARKET",
            product="MIS",
            status="COMPLETE",
            signal_price=current_price,
            fill_price=fill_price,
            placed_at=now,
            filled_at=now,
            charges=exit_charges,
            pnl=round(net_pnl, 2),
            reason=reason,
        )
        self.orders.append(order)

        # Record closed trade
        self.closed_trades.append({
            "instrument": instrument,
            "side": pos.side,
            "quantity": pos.quantity,
            "entry_price": pos.entry_price,
            "exit_price": fill_price,
            "entry_time": pos.entry_time,
            "exit_time": now,
            "gross_pnl": round(gross_pnl, 2),
            "charges": round(total_charges, 2),
            "net_pnl": round(net_pnl, 2),
            "entry_order_id": pos.entry_order_id,
            "exit_order_id": order.order_id,
            "reason": reason,
        })

        # Update stats
        self.capital += net_pnl - exit_charges  # PnL goes to capital, charges deducted
        self.day_pnl += net_pnl
        self.day_charges += exit_charges

        if net_pnl > 0:
            self.day_wins += 1
        else:
            self.day_losses += 1

        # Track drawdown
        if self.capital > self.peak_capital:
            self.peak_capital = self.capital
        dd = (self.peak_capital - self.capital) / self.peak_capital
        if dd > self.max_drawdown:
            self.max_drawdown = dd

        del self.positions[instrument]

        logger.info(
            "paper_trade_exit",
            instrument=instrument,
            side=close_side,
            entry=pos.entry_price,
            exit=fill_price,
            gross_pnl=round(gross_pnl, 2),
            charges=round(total_charges, 2),
            net_pnl=round(net_pnl, 2),
            capital=round(self.capital, 2),
            reason=reason,
        )

        return order

    def update_prices(self, prices: dict[str, float]) -> None:
        """Update current prices and unrealized P&L for all positions."""
        for inst, price in prices.items():
            if inst in self.positions:
                pos = self.positions[inst]
                pos.current_price = price
                if pos.side == "LONG":
                    pos.unrealized_pnl = round((price - pos.entry_price) * pos.quantity, 2)
                    pnl_pct = (price - pos.entry_price) / pos.entry_price
                else:
                    pos.unrealized_pnl = round((pos.entry_price - price) * pos.quantity, 2)
                    pnl_pct = (pos.entry_price - price) / pos.entry_price
                pos.high_water_pnl_pct = max(pos.high_water_pnl_pct, pnl_pct)

    def check_stop_losses(self, prices: dict[str, float]) -> list[Order]:
        """Check and execute stop losses."""
        closed = []
        for inst in list(self.positions.keys()):
            pos = self.positions[inst]
            price = prices.get(inst, pos.current_price)

            if pos.side == "LONG":
                loss_pct = (pos.entry_price - price) / pos.entry_price
            else:
                loss_pct = (price - pos.entry_price) / pos.entry_price

            if loss_pct >= self.stop_loss_pct:
                order = self._close_position(inst, price, f"Stop loss hit ({loss_pct:.1%})")
                if order:
                    closed.append(order)

        return closed

    def square_off_all(self, prices: dict[str, float]) -> list[Order]:
        """Close all positions — called at 3:15 PM."""
        closed = []
        for inst in list(self.positions.keys()):
            price = prices.get(inst, self.positions[inst].current_price)
            order = self._close_position(inst, price, "EOD square-off")
            if order:
                closed.append(order)
        return closed

    def get_day_result(self) -> DayResult:
        """Generate end-of-day summary."""
        from datetime import date
        win_rate = self.day_wins / self.day_trades if self.day_trades > 0 else 0

        return DayResult(
            date=date.today().isoformat(),
            starting_capital=self.starting_capital,
            ending_capital=round(self.capital, 2),
            gross_pnl=round(self.day_pnl + self.day_charges, 2),
            total_charges=round(self.day_charges, 2),
            net_pnl=round(self.day_pnl, 2),
            trades_count=self.day_trades,
            wins=self.day_wins,
            losses=self.day_losses,
            win_rate=round(win_rate, 4),
            max_drawdown=round(self.max_drawdown, 4),
            instruments_traded=list(set(t["instrument"] for t in self.closed_trades)),
        )

    def get_status(self) -> dict:
        """Full status for API/dashboard."""
        return {
            "capital": round(self.capital, 2),
            "starting_capital": self.starting_capital,
            "buying_power": round(self.buying_power, 2),
            "leverage": self.leverage,
            "net_equity": round(self.net_equity, 2),
            "day_pnl": round(self.day_pnl, 2),
            "day_charges": round(self.day_charges, 2),
            "day_trades": self.day_trades,
            "day_wins": self.day_wins,
            "day_losses": self.day_losses,
            "win_rate": round(self.day_wins / max(self.day_trades, 1), 2),
            "max_drawdown": round(self.max_drawdown, 4),
            "positions": {k: v.to_dict() for k, v in self.positions.items()},
            "open_position_count": len(self.positions),
            "total_unrealized_pnl": round(self.total_unrealized_pnl, 2),
            "recent_orders": [o.to_dict() for o in self.orders[-20:]],
            "closed_trades": self.closed_trades[-20:],
            "broker": self.broker,
        }
