"""FII/DII cumulative flow tracker.

Single-day FII data is noisy. Cumulative flows over 5/10 days are the
strongest predictor of multi-day trends in Indian markets.

Signals:
  - fii_5d_cumulative: 5-day total FII net (strongest directional signal)
  - fii_10d_cumulative: 10-day total (trend confirmation)
  - fii_acceleration: is selling/buying speeding up or slowing down?
  - fii_consecutive_days: streak of buying/selling (8+ = extreme)
  - dii_absorption: are DIIs absorbing FII selling? (stabilizing signal)

Data source: NSE /api/fiidiiTradeReact (free, already used)
Storage: Local JSON file for persistence across restarts.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import structlog

logger = structlog.get_logger()

IST = ZoneInfo("Asia/Kolkata")
_DATA_FILE = Path(__file__).resolve().parents[3] / "data" / "fii_history.json"


@dataclass
class FIIMomentum:
    """Cumulative FII/DII flow analysis."""
    fii_today: float = 0.0
    dii_today: float = 0.0
    fii_5d: float = 0.0           # 5-day cumulative FII net
    fii_10d: float = 0.0          # 10-day cumulative FII net
    fii_acceleration: float = 0.0  # recent_5d - prev_5d (positive = buying accelerating)
    fii_consecutive: int = 0       # streak of same-direction days
    fii_streak_direction: str = "" # "buying" or "selling"
    dii_5d: float = 0.0           # 5-day cumulative DII net
    dii_absorption_pct: float = 0.0  # how much DII offsets FII (0-100%)
    data_days: int = 0             # how many days of history we have
    signal: str = "neutral"        # "strong_buy", "buy", "neutral", "sell", "strong_sell"
    signal_score: float = 0.0      # -1 to +1


class FIITracker:
    """Tracks FII/DII flows over time for momentum signals."""

    def __init__(self) -> None:
        self._history: list[dict] = []  # [{date, fii_net, dii_net}, ...]
        self._load()

    def _load(self) -> None:
        """Load history from disk."""
        try:
            if _DATA_FILE.exists():
                self._history = json.loads(_DATA_FILE.read_text())
                logger.info("fii_history_loaded", days=len(self._history))
        except Exception as e:
            logger.warning("fii_history_load_failed", error=str(e))
            self._history = []

    def _save(self) -> None:
        """Persist history to disk."""
        try:
            _DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
            _DATA_FILE.write_text(json.dumps(self._history, indent=2))
        except Exception as e:
            logger.warning("fii_history_save_failed", error=str(e))

    def record(self, fii_net: float, dii_net: float, dt: date | None = None) -> None:
        """Record today's FII/DII data. Deduplicates by date."""
        if dt is None:
            dt = datetime.now(IST).date()
        date_str = dt.isoformat()

        # Deduplicate — update if same date, append if new
        for entry in self._history:
            if entry["date"] == date_str:
                entry["fii_net"] = fii_net
                entry["dii_net"] = dii_net
                self._save()
                return

        self._history.append({
            "date": date_str,
            "fii_net": fii_net,
            "dii_net": dii_net,
        })

        # Keep last 60 days max
        if len(self._history) > 60:
            self._history = self._history[-60:]

        # Sort by date
        self._history.sort(key=lambda x: x["date"])
        self._save()

    def get_momentum(self, fii_today: float = 0, dii_today: float = 0) -> FIIMomentum:
        """Calculate cumulative momentum signals.

        Args:
            fii_today: today's FII net (may not be in history yet)
            dii_today: today's DII net
        """
        m = FIIMomentum()
        m.fii_today = fii_today
        m.dii_today = dii_today

        # Build the flow list (most recent last), including today if provided
        flows = [e["fii_net"] for e in self._history]
        dii_flows = [e["dii_net"] for e in self._history]

        # Add today if not already in history
        today_str = datetime.now(IST).date().isoformat()
        if fii_today != 0 and (not self._history or self._history[-1]["date"] != today_str):
            flows.append(fii_today)
            dii_flows.append(dii_today)

        m.data_days = len(flows)

        if len(flows) < 2:
            return m

        # 5-day cumulative
        last_5 = flows[-5:] if len(flows) >= 5 else flows
        m.fii_5d = round(sum(last_5), 2)

        # 10-day cumulative
        last_10 = flows[-10:] if len(flows) >= 10 else flows
        m.fii_10d = round(sum(last_10), 2)

        # DII 5-day
        dii_last_5 = dii_flows[-5:] if len(dii_flows) >= 5 else dii_flows
        m.dii_5d = round(sum(dii_last_5), 2)

        # FII acceleration (is selling/buying speeding up?)
        if len(flows) >= 10:
            recent_5 = sum(flows[-5:])
            prev_5 = sum(flows[-10:-5])
            m.fii_acceleration = round(recent_5 - prev_5, 2)

        # Consecutive days streak
        streak = 0
        direction = ""
        for f in reversed(flows):
            if f > 0:
                if direction == "" or direction == "buying":
                    direction = "buying"
                    streak += 1
                else:
                    break
            elif f < 0:
                if direction == "" or direction == "selling":
                    direction = "selling"
                    streak += 1
                else:
                    break
            else:
                break
        m.fii_consecutive = streak
        m.fii_streak_direction = direction

        # DII absorption: when FII sells, how much does DII absorb?
        if m.fii_5d < 0 and m.dii_5d > 0:
            m.dii_absorption_pct = round(min(100, abs(m.dii_5d / m.fii_5d) * 100), 1)

        # Generate composite signal
        m.signal, m.signal_score = self._compute_signal(m)

        return m

    def _compute_signal(self, m: FIIMomentum) -> tuple[str, float]:
        """Compute a composite signal from momentum data."""
        score = 0.0

        # 5-day cumulative (primary signal)
        if m.fii_5d > 5000:
            score += 0.4
        elif m.fii_5d > 2000:
            score += 0.2
        elif m.fii_5d < -5000:
            score -= 0.4
        elif m.fii_5d < -2000:
            score -= 0.2

        # Acceleration
        if m.fii_acceleration > 3000:
            score += 0.2  # buying accelerating
        elif m.fii_acceleration < -3000:
            score -= 0.2  # selling accelerating

        # Streak (8+ consecutive days = extreme, likely reversal coming)
        if m.fii_consecutive >= 8:
            # Contrarian at extreme streaks
            if m.fii_streak_direction == "selling":
                score += 0.15  # selling exhaustion
            elif m.fii_streak_direction == "buying":
                score -= 0.15  # buying exhaustion
        elif m.fii_consecutive >= 5:
            # Trend continuation for moderate streaks
            if m.fii_streak_direction == "buying":
                score += 0.1
            elif m.fii_streak_direction == "selling":
                score -= 0.1

        # DII absorption (stabilizing)
        if m.dii_absorption_pct > 80:
            score += 0.1  # DII absorbing most of FII selling = stabilizing

        # Clamp
        score = max(-1, min(1, score))

        if score > 0.3:
            signal = "strong_buy"
        elif score > 0.1:
            signal = "buy"
        elif score < -0.3:
            signal = "strong_sell"
        elif score < -0.1:
            signal = "sell"
        else:
            signal = "neutral"

        return signal, round(score, 3)

    def to_dict(self) -> dict:
        """For API/dashboard."""
        m = self.get_momentum()
        return {
            "fii_5d": m.fii_5d,
            "fii_10d": m.fii_10d,
            "fii_acceleration": m.fii_acceleration,
            "fii_consecutive": m.fii_consecutive,
            "fii_streak_direction": m.fii_streak_direction,
            "dii_5d": m.dii_5d,
            "dii_absorption_pct": m.dii_absorption_pct,
            "signal": m.signal,
            "signal_score": m.signal_score,
            "data_days": m.data_days,
            "history": self._history[-10:],  # last 10 days for chart
        }
