"""Level-Based Intraday Trader.

Trades at key S/R levels with direction + VWAP + OI confirmation.
NOT a direction-only predictor — waits for price to reach a level,
then enters if multiple factors align.

Lifecycle:
  8:45 AM:  Compute levels (Pivots, CPR, Camarilla, PDH/PDL)
  9:15 AM:  Note opening price, start marking 15-min ORB
  9:30 AM:  ORB set — first trade opportunity
  9:30-11:30: Prime window — trade at levels with full confirmation
  11:30-2:30: Reduced — only major levels (R2/S2, H4/L4, OI walls)
  2:30-3:15:  No new positions, tighten stops, square off
"""

from __future__ import annotations

import time
from datetime import datetime, time as dt_time
from zoneinfo import ZoneInfo

import structlog

from trade_plus.instruments import Direction
from trade_plus.prediction import Prediction
from trade_plus.trading.levels import DayLevels, Level, compute_levels, set_opening_range, set_oi_levels
from trade_plus.trading.paper_trader import PaperTrader, Order

logger = structlog.get_logger()
IST = ZoneInfo("Asia/Kolkata")

ORB_END = dt_time(9, 30)
PRIME_END = dt_time(11, 30)
ENTRY_END = dt_time(14, 30)
SQUAREOFF = dt_time(15, 15)


class IntradayTrader:
    """Level-based intraday engine."""

    def __init__(
        self,
        trader: PaperTrader,
        max_positions: int = 2,
        max_round_trips: int = 4,
        level_proximity_pct: float = 0.20,  # must be within 0.20% of a level to enter
    ) -> None:
        self.trader = trader
        self.max_positions = max_positions
        self.max_round_trips = max_round_trips
        self.level_proximity_pct = level_proximity_pct

        self.levels: dict[str, DayLevels] = {}
        self.bias: dict[str, Direction] = {}
        self.bias_score: dict[str, float] = {}
        self.last_prediction: dict[str, Prediction] = {}
        self.intraday: dict[str, dict] = {}
        self.round_trips: dict[str, int] = {}
        self.oi_data: dict = {}

        # ORB tracking
        self._orb_prices: dict[str, list] = {}  # prices collected 9:15-9:30

        self._levels_computed = False
        self._orb_computed = False

    def _now(self) -> datetime:
        return datetime.now(IST)

    def _time(self) -> dt_time:
        return self._now().time()

    # ── Level setup ──────────────────────────────────────────────

    def compute_morning_levels(self, instruments_ohlc: dict[str, dict]) -> None:
        """Compute all S/R levels from previous day's OHLC.
        Call this once before market open.
        instruments_ohlc: {ticker: {"high": x, "low": x, "close": x, "open_today": x}}
        """
        for ticker, ohlc in instruments_ohlc.items():
            dl = compute_levels(
                ticker,
                ohlc["high"], ohlc["low"], ohlc["close"],
                ohlc.get("open_today", 0),
            )
            self.levels[ticker] = dl
            logger.info("levels_computed", instrument=ticker, day_type=dl.day_type,
                       pivot=dl.pivot, pdh=dl.pdh, pdl=dl.pdl,
                       gap=f"{dl.gap_pct:+.2f}%" if dl.gap_pct else "n/a")

        self._levels_computed = True

    def update_oi(self, oi_data: dict) -> None:
        """Update OI-based levels from NSE option chain."""
        self.oi_data = oi_data
        if not oi_data or oi_data.get("empty"):
            return

        # Set OI levels on NIFTYBEES and BANKBEES (they track Nifty/BankNifty)
        for ticker, ratio in [("NIFTYBEES", 100), ("BANKBEES", 100)]:
            if ticker in self.levels:
                set_oi_levels(
                    self.levels[ticker],
                    oi_data.get("oi_resistance", 0),
                    oi_data.get("oi_support", 0),
                    oi_data.get("max_pain", 0),
                    oi_data.get("pcr", 0),
                    nifty_to_etf_ratio=ratio,
                )

    def collect_orb_price(self, ticker: str, price: float) -> None:
        """Collect prices during 9:15-9:30 for ORB computation."""
        if ticker not in self._orb_prices:
            self._orb_prices[ticker] = []
        self._orb_prices[ticker].append(price)

    def finalize_orb(self) -> None:
        """Set the opening range from collected prices."""
        for ticker, prices in self._orb_prices.items():
            if prices and ticker in self.levels:
                set_opening_range(self.levels[ticker], max(prices), min(prices))
                logger.info("orb_set", instrument=ticker, high=max(prices), low=min(prices),
                           range_pct=f"{(max(prices)-min(prices))/min(prices)*100:.2f}%")
        self._orb_computed = True

    def set_bias(self, instrument: str, direction: Direction, score: float) -> None:
        self.bias[instrument] = direction
        self.bias_score[instrument] = score

    def set_intraday_indicators(self, instrument: str, indicators: dict) -> None:
        self.intraday[instrument] = indicators

    # ── Trading decisions ────────────────────────────────────────

    def decide(self, instrument: str, prediction: Prediction, price: float) -> dict:
        """Make a trading decision. Returns decision dict for dashboard + execution."""
        self.last_prediction[instrument] = prediction
        t = self._time()
        dl = self.levels.get(instrument)
        ind = self.intraday.get(instrument, {})
        pos = self.trader.positions.get(instrument)

        decision = {
            "instrument": instrument,
            "action": "SKIP",
            "reasons": [],
            "level": None,
            "confidence": prediction.confidence,
            "score": prediction.score,
        }

        # Square-off time
        if t >= SQUAREOFF and pos:
            decision["action"] = "EXIT"
            decision["reasons"] = ["EOD square-off at 3:15 PM"]
            return decision

        # Check open position for stop/target
        if pos:
            return self._check_position(instrument, price, prediction, dl, ind)

        # No levels computed yet
        if not dl:
            decision["reasons"] = ["Levels not computed yet"]
            return decision

        # ORB period — just collect prices
        if t < ORB_END:
            self.collect_orb_price(instrument, price)
            decision["reasons"] = [f"ORB collection ({len(self._orb_prices.get(instrument, []))} ticks)"]
            return decision

        # Finalize ORB if just passed 9:30
        if not self._orb_computed and t >= ORB_END:
            self.finalize_orb()

        # No new positions after 2:30
        if t >= ENTRY_END:
            decision["reasons"] = ["Past 2:30 PM — no new entries"]
            return decision

        # Max positions / round trips
        if len(self.trader.positions) >= self.max_positions:
            decision["reasons"] = [f"Max {self.max_positions} positions open"]
            return decision
        if self.round_trips.get(instrument, 0) >= self.max_round_trips:
            decision["reasons"] = [f"Max {self.max_round_trips} round-trips for {instrument}"]
            return decision

        # Direction bias
        bias = self.bias.get(instrument, Direction.FLAT)
        if bias == Direction.FLAT:
            decision["reasons"] = ["Bias is FLAT — no trade"]
            return decision

        # ── THE KEY: Is price at a level? ──
        level = dl.at_level(price, self.level_proximity_pct)
        if not level:
            nearest_s = dl.nearest_support(price)
            nearest_r = dl.nearest_resistance(price)
            s_dist = f"{((price - nearest_s.price) / price * 100):.2f}%" if nearest_s else "?"
            r_dist = f"{((nearest_r.price - price) / price * 100):.2f}%" if nearest_r else "?"
            decision["reasons"] = [
                f"Not at any level (proximity: {self.level_proximity_pct}%)",
                f"Nearest support: {nearest_s.name}={nearest_s.price:.2f} ({s_dist} away)" if nearest_s else "No support below",
                f"Nearest resistance: {nearest_r.name}={nearest_r.price:.2f} ({r_dist} away)" if nearest_r else "No resistance above",
            ]
            return decision

        decision["level"] = {"price": level.price, "name": level.name, "type": level.type, "source": level.source}

        # ── Confirmation checks ──
        confirmations = 0
        confirm_reasons = []

        # 1. VWAP position
        vwap = ind.get("intraday_vwap", 0)
        above_vwap = ind.get("above_vwap", False)
        if bias == Direction.LONG and above_vwap:
            confirmations += 1
            confirm_reasons.append(f"Above VWAP ({vwap:.2f})")
        elif bias == Direction.SHORT and not above_vwap:
            confirmations += 1
            confirm_reasons.append(f"Below VWAP ({vwap:.2f})")

        # 2. Intraday RSI sanity
        rsi = ind.get("intraday_rsi", 50)
        if bias == Direction.LONG and 25 < rsi < 70:
            confirmations += 1
            confirm_reasons.append(f"RSI={rsi:.0f} (not overbought)")
        elif bias == Direction.SHORT and 30 < rsi < 75:
            confirmations += 1
            confirm_reasons.append(f"RSI={rsi:.0f} (not oversold)")

        # 3. Level type matches trade direction
        if bias == Direction.LONG and level.type == "support":
            confirmations += 1
            confirm_reasons.append(f"At SUPPORT level: {level.name}")
        elif bias == Direction.SHORT and level.type == "resistance":
            confirmations += 1
            confirm_reasons.append(f"At RESISTANCE level: {level.name}")
        elif level.type == "pivot":
            confirmations += 1
            confirm_reasons.append(f"At PIVOT: {level.name}")

        # 4. OI confirmation (for Nifty-based ETFs)
        pcr = dl.pcr
        if pcr > 0:
            if bias == Direction.LONG and pcr > 1.0:
                confirmations += 1
                confirm_reasons.append(f"PCR={pcr:.2f} (bullish)")
            elif bias == Direction.SHORT and pcr < 0.8:
                confirmations += 1
                confirm_reasons.append(f"PCR={pcr:.2f} (bearish)")

        # 5. Day type alignment
        if dl.day_type == "trending" and level.source == "orb":
            confirmations += 1
            confirm_reasons.append("Trending day + ORB level")
        elif dl.day_type == "range" and level.source in ("camarilla", "pivot"):
            confirmations += 1
            confirm_reasons.append("Range day + Camarilla/Pivot level")

        # Prime vs reduced window
        min_confirmations = 2 if t < PRIME_END else 3

        if confirmations < min_confirmations:
            decision["reasons"] = [
                f"Only {confirmations}/{min_confirmations} confirmations at {level.name}={level.price:.2f}",
                f"Checked: {', '.join(confirm_reasons) if confirm_reasons else 'none passed'}",
            ]
            return decision

        # ── Compute stop and target ──
        if bias == Direction.LONG:
            # Stop below the level
            stop = level.price * 0.995  # 0.5% below level
            # Target = next resistance
            next_r = dl.nearest_resistance(price)
            target = next_r.price if next_r else price * 1.01

            decision["action"] = "ENTER_LONG"
        else:
            # Stop above the level
            stop = level.price * 1.005
            next_s = dl.nearest_support(price)
            target = next_s.price if next_s else price * 0.99

            decision["action"] = "ENTER_SHORT"

        rr = abs(target - price) / abs(price - stop) if abs(price - stop) > 0 else 0
        decision["reasons"] = [
            f"{confirmations}/{min_confirmations} confirmations at {level.name}={level.price:.2f}",
            f"{', '.join(confirm_reasons)}",
            f"Stop={stop:.2f} Target={target:.2f} R:R={rr:.1f}",
            f"Bias={bias.value}({self.bias_score.get(instrument, 0):+.2f}) Day={dl.day_type}",
        ]
        decision["stop"] = stop
        decision["target"] = target

        return decision

    def _check_position(self, instrument: str, price: float, prediction: Prediction, dl: DayLevels | None, ind: dict) -> dict:
        """Check stop/target for an open position."""
        pos = self.trader.positions[instrument]
        decision = {"instrument": instrument, "action": "HOLD", "reasons": [], "confidence": prediction.confidence, "score": prediction.score, "level": None}

        if pos.side == "LONG":
            pnl_pct = (price - pos.entry_price) / pos.entry_price
        else:
            pnl_pct = (pos.entry_price - price) / pos.entry_price

        # Dynamic stop/target based on day volatility
        stop_pct = 0.005  # default 0.5%
        target_pct = 0.008  # default 0.8%

        # Check against next S/R level for target
        if dl:
            if pos.side == "LONG":
                next_level = dl.nearest_resistance(price)
            else:
                next_level = dl.nearest_support(price)
            if next_level:
                level_target = abs(next_level.price - pos.entry_price) / pos.entry_price
                if level_target > 0.003:  # at least 0.3%
                    target_pct = min(target_pct, level_target)

        # Take profit
        if pnl_pct >= target_pct:
            decision["action"] = "EXIT"
            decision["reasons"] = [f"Take profit: {pnl_pct:.2%} >= {target_pct:.1%}"]
            return decision

        # Stop loss
        if pnl_pct <= -stop_pct:
            decision["action"] = "EXIT"
            decision["reasons"] = [f"Stop loss: {pnl_pct:.2%} <= -{stop_pct:.1%}"]
            return decision

        # Time-based tightening after 2:30 PM
        if self._time() >= ENTRY_END and pnl_pct > 0:
            decision["action"] = "EXIT"
            decision["reasons"] = [f"Time exit (after 2:30): locking profit {pnl_pct:.2%}"]
            return decision

        decision["reasons"] = [
            f"Holding {pos.side} — P&L: {pnl_pct:+.2%}",
            f"Stop: {stop_pct:.1%} | Target: {target_pct:.1%}",
        ]
        return decision

    def execute(self, decision: dict, price: float, run_id: str) -> Order | None:
        """Execute a trading decision."""
        action = decision["action"]
        instrument = decision["instrument"]

        if action in ("SKIP", "HOLD"):
            return None

        if action == "EXIT":
            order = self.trader._close_position(instrument, price, decision["reasons"][0])
            if order:
                self.round_trips[instrument] = self.round_trips.get(instrument, 0) + 1
            return order

        if action == "ENTER_LONG":
            return self.trader.execute_entry(
                instrument, Direction.LONG, price,
                decision["score"], run_id,
                " | ".join(decision["reasons"][:2]),
            )

        if action == "ENTER_SHORT":
            return self.trader.execute_entry(
                instrument, Direction.SHORT, price,
                decision["score"], run_id,
                " | ".join(decision["reasons"][:2]),
            )

        return None

    def get_status(self) -> dict:
        """Full status for dashboard."""
        decisions = {}
        for inst, pred in self.last_prediction.items():
            ind = self.intraday.get(inst, {})
            price = ind.get("current_price", 0)
            if price > 0:
                d = self.decide(inst, pred, price)
                decisions[inst] = d

        return {
            "mode": "level_based",
            "levels_computed": self._levels_computed,
            "orb_set": self._orb_computed,
            "time_window": "orb" if self._time() < ORB_END else "prime" if self._time() < PRIME_END else "reduced" if self._time() < ENTRY_END else "wind_down",
            "decisions": decisions,
            "levels": {t: dl.to_dict() for t, dl in self.levels.items()},
            "oi": self.oi_data,
        }
