"""Trade accuracy measurement — tracks every decision and outcome.

Records:
  - Every entry/skip/exit decision with full context
  - Every trade outcome (target hit vs stop hit vs time exit)
  - Daily performance metrics (win rate, R:R, Sharpe, drawdown)
  - Level accuracy (which S/R levels produce winning trades)
  - Running statistics for system validation

Need 300+ trades for statistical confidence that the system works.
Track progress toward this goal on the dashboard.
"""

from __future__ import annotations

import time
import math
from dataclasses import dataclass, field
from datetime import date


@dataclass
class TradeRecord:
    """Complete record of one trade for accuracy analysis."""
    trade_id: str
    instrument: str
    direction: str          # LONG or SHORT
    entry_price: float
    exit_price: float
    entry_time: float
    exit_time: float
    quantity: int

    # What triggered this trade
    entry_level: str        # e.g., "PDL", "Cam H3", "ORB High"
    entry_level_price: float
    entry_confirmations: int
    daily_bias: str         # LONG/SHORT/FLAT
    bias_score: float

    # Outcome
    gross_pnl: float
    charges: float
    net_pnl: float
    exit_reason: str        # "take_profit", "stop_loss", "time_exit", "reversal", "eod_squareoff"
    was_target_hit: bool
    was_stop_hit: bool
    hold_time_minutes: float
    pnl_pct: float          # % return

    def to_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class DailyStats:
    """End-of-day performance summary."""
    date: str
    trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    gross_pnl: float = 0.0
    charges: float = 0.0
    net_pnl: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    avg_rr: float = 0.0     # average risk:reward achieved
    max_drawdown: float = 0.0
    best_trade: float = 0.0
    worst_trade: float = 0.0
    capital_start: float = 0.0
    capital_end: float = 0.0
    return_pct: float = 0.0

    # Level accuracy
    levels_traded: dict = field(default_factory=dict)  # level_name → {wins, losses}

    def to_dict(self) -> dict:
        return self.__dict__.copy()


class AccuracyTracker:
    """Tracks all trades and computes rolling performance metrics."""

    def __init__(self) -> None:
        self.trades: list[TradeRecord] = []
        self.daily_stats: list[DailyStats] = []
        self.skipped_decisions: list[dict] = []  # why we didn't trade

    def record_trade(self, record: TradeRecord) -> None:
        """Record a completed trade."""
        self.trades.append(record)

    def record_skip(self, instrument: str, reasons: list[str], price: float, bias: str) -> None:
        """Record why we skipped a trade opportunity (for analysis)."""
        self.skipped_decisions.append({
            "timestamp": time.time(),
            "instrument": instrument,
            "reasons": reasons[:3],
            "price": price,
            "bias": bias,
        })
        # Keep last 100
        if len(self.skipped_decisions) > 100:
            self.skipped_decisions = self.skipped_decisions[-100:]

    def compute_daily_stats(self, capital_start: float, capital_end: float) -> DailyStats:
        """Compute today's performance stats."""
        today = date.today().isoformat()
        today_trades = [t for t in self.trades if time.strftime("%Y-%m-%d", time.localtime(t.entry_time)) == today]

        stats = DailyStats(
            date=today,
            trades=len(today_trades),
            capital_start=capital_start,
            capital_end=capital_end,
        )

        if not today_trades:
            return stats

        wins = [t for t in today_trades if t.net_pnl > 0]
        losses = [t for t in today_trades if t.net_pnl <= 0]

        stats.wins = len(wins)
        stats.losses = len(losses)
        stats.win_rate = len(wins) / len(today_trades) if today_trades else 0
        stats.gross_pnl = sum(t.gross_pnl for t in today_trades)
        stats.charges = sum(t.charges for t in today_trades)
        stats.net_pnl = sum(t.net_pnl for t in today_trades)
        stats.avg_win = sum(t.net_pnl for t in wins) / len(wins) if wins else 0
        stats.avg_loss = sum(t.net_pnl for t in losses) / len(losses) if losses else 0
        stats.best_trade = max(t.net_pnl for t in today_trades) if today_trades else 0
        stats.worst_trade = min(t.net_pnl for t in today_trades) if today_trades else 0
        stats.return_pct = (capital_end / capital_start - 1) * 100 if capital_start > 0 else 0

        # R:R ratio
        if stats.avg_loss != 0:
            stats.avg_rr = abs(stats.avg_win / stats.avg_loss)

        # Level accuracy
        for t in today_trades:
            level = t.entry_level
            if level not in stats.levels_traded:
                stats.levels_traded[level] = {"wins": 0, "losses": 0}
            if t.net_pnl > 0:
                stats.levels_traded[level]["wins"] += 1
            else:
                stats.levels_traded[level]["losses"] += 1

        return stats

    def get_overall_stats(self) -> dict:
        """Rolling statistics across all recorded trades."""
        if not self.trades:
            return {
                "total_trades": 0,
                "message": "Need 300+ trades for statistical confidence",
                "progress": "0/300",
            }

        total = len(self.trades)
        wins = [t for t in self.trades if t.net_pnl > 0]
        losses = [t for t in self.trades if t.net_pnl <= 0]

        win_rate = len(wins) / total
        avg_win = sum(t.net_pnl for t in wins) / len(wins) if wins else 0
        avg_loss = sum(t.net_pnl for t in losses) / len(losses) if losses else 0

        # Expectancy per trade
        expectancy = (win_rate * avg_win) + ((1 - win_rate) * avg_loss)

        # Sharpe ratio (daily returns)
        daily_returns = {}
        for t in self.trades:
            day = time.strftime("%Y-%m-%d", time.localtime(t.entry_time))
            daily_returns.setdefault(day, 0)
            daily_returns[day] += t.net_pnl

        returns = list(daily_returns.values())
        if len(returns) >= 5:
            mean_r = sum(returns) / len(returns)
            std_r = (sum((r - mean_r) ** 2 for r in returns) / len(returns)) ** 0.5
            sharpe = (mean_r / std_r) * math.sqrt(252) if std_r > 0 else 0
        else:
            sharpe = 0

        # Level accuracy
        level_stats = {}
        for t in self.trades:
            level = t.entry_level
            if level not in level_stats:
                level_stats[level] = {"wins": 0, "losses": 0, "total_pnl": 0}
            if t.net_pnl > 0:
                level_stats[level]["wins"] += 1
            else:
                level_stats[level]["losses"] += 1
            level_stats[level]["total_pnl"] += t.net_pnl

        # Statistical confidence
        # For 55% win rate: need ~1500 trades for 95% confidence
        # For 60% win rate: need ~370 trades
        needed = 300
        confidence = min(total / needed, 1.0)

        return {
            "total_trades": total,
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(win_rate, 3),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "risk_reward": round(abs(avg_win / avg_loss), 2) if avg_loss != 0 else 0,
            "expectancy_per_trade": round(expectancy, 2),
            "total_pnl": round(sum(t.net_pnl for t in self.trades), 2),
            "total_charges": round(sum(t.charges for t in self.trades), 2),
            "sharpe_ratio": round(sharpe, 2),
            "statistical_confidence": f"{confidence:.0%}",
            "progress": f"{total}/{needed}",
            "level_accuracy": level_stats,
            "recent_skips": self.skipped_decisions[-10:],
        }
