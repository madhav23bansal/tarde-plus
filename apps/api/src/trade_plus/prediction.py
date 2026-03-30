"""Daily direction bias predictor.

PURPOSE: Sets the daily lean (LONG/SHORT/FLAT) for the trading day.
This is NOT used for trade timing — S/R levels + OI handle that.
This only answers: "Should we be looking for longs or shorts today?"

CURRENT: Rule-based with ML ensemble (53% accuracy on NIFTYBEES).
FUTURE: When we have 300+ trades of level-based data, retrain ML
        with features like: S/R bounce rate, OI wall strength,
        VWAP slope, time-of-day effects.

ML DATA RECORDING: The signal_collector stores all raw features in
TimescaleDB on every cycle. The intraday trader records every decision
with the bias that was active. This gives us labeled training data:
  input: (global signals, OI state, levels, time)
  output: (was the bias correct for this trade?)
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog

from trade_plus.instruments import Direction

logger = structlog.get_logger()


@dataclass
class DailyBias:
    direction: Direction
    confidence: float       # 0-1
    score: float           # -1 to +1
    reasons: list[str]
    method: str = "rules"  # "rules", "ml", "ensemble"

    # ML breakdown (for future training)
    ml_score: float = 0.0
    rules_score: float = 0.0


class BiasPredictor:
    """Predicts daily direction bias from overnight/pre-market data.

    Uses 5 simple signals:
      1. S&P 500 overnight change (strongest global signal)
      2. India VIX level (regime: trending vs range)
      3. Crude oil change (India is net importer)
      4. FII/DII net flow (institutional direction)
      5. USD/INR change (FII flow proxy)

    ML layer can be added later — all inputs are recorded in DB.
    """

    def __init__(self) -> None:
        self._ml = None
        try:
            from trade_plus.ml.predict import get_ml_predictor
            self._ml = get_ml_predictor()
            if self._ml and self._ml.has_model("NIFTYBEES"):
                logger.info("bias_predictor", mode="ml+rules")
            else:
                logger.info("bias_predictor", mode="rules_only")
        except Exception:
            logger.info("bias_predictor", mode="rules_only")

    def predict(self, signals: dict) -> DailyBias:
        """Generate daily bias from global signals.

        Args:
            signals: dict with keys like sp500_change, india_vix, crude_oil_change, etc.
        """
        bull = 0.0
        bear = 0.0
        reasons_bull = []
        reasons_bear = []

        # 1. S&P 500 (weight: 3)
        sp = signals.get("sp500_change", 0)
        if sp > 0.3:
            bull += 3
            reasons_bull.append(f"S&P +{sp:.1f}%")
        elif sp < -0.3:
            bear += 3
            reasons_bear.append(f"S&P {sp:.1f}%")

        # 2. India VIX regime (weight: 2)
        vix = signals.get("india_vix", 15)
        if vix > 22:
            # High fear — contrarian bullish (mean reversion)
            bull += 2
            reasons_bull.append(f"High VIX {vix:.0f} (contrarian)")
        elif vix < 12:
            # Low fear — complacency warning
            bear += 1
            reasons_bear.append(f"Low VIX {vix:.0f} (complacent)")

        # 3. Crude oil (weight: 2)
        crude = signals.get("crude_oil_change", 0)
        if crude > 2:
            bear += 2
            reasons_bear.append(f"Crude +{crude:.1f}% (bearish for India)")
        elif crude < -2:
            bull += 2
            reasons_bull.append(f"Crude {crude:.1f}% (bullish for India)")

        # 4. FII/DII (weight: 3) — strongest Indian-specific signal
        fii = signals.get("fii_net", 0)
        if fii > 1000:
            bull += 3
            reasons_bull.append(f"FII +{fii:.0f}Cr")
        elif fii < -1000:
            bear += 3
            reasons_bear.append(f"FII {fii:.0f}Cr")

        # 5. USD/INR (weight: 1)
        usdinr = signals.get("usd_inr_change", 0)
        if usdinr > 0.3:
            bear += 1
            reasons_bear.append(f"INR weakening +{usdinr:.1f}%")
        elif usdinr < -0.3:
            bull += 1
            reasons_bull.append(f"INR strengthening {usdinr:.1f}%")

        # Compute rules score
        total = bull + bear
        rules_score = (bull - bear) / total if total > 0 else 0

        # ML bias (if available)
        ml_score = 0.0
        if self._ml and self._ml.has_model("NIFTYBEES"):
            try:
                # Build a minimal snapshot for ML
                # NOTE: This is a simplified call — ML uses stored features
                from trade_plus.market_data.signal_collector import SignalSnapshot
                snap = SignalSnapshot(instrument="NIFTYBEES", sector="index")
                # Copy available signals to snapshot fields
                snap.rsi_14 = signals.get("rsi_14", 50)
                snap.returns_1d = signals.get("returns_1d", 0)
                snap.returns_5d = signals.get("returns_5d", 0)
                snap.volume_ratio = signals.get("volume_ratio", 1)
                _, ml_score, _, _ = self._ml.predict(snap)
            except Exception:
                ml_score = 0

        # Blend: 80% rules, 20% ML (ML accuracy is low)
        final_score = 0.8 * rules_score + 0.2 * ml_score

        if final_score > 0.1:
            direction = Direction.LONG
            reasons = reasons_bull[:3]
        elif final_score < -0.1:
            direction = Direction.SHORT
            reasons = reasons_bear[:3]
        else:
            direction = Direction.FLAT
            reasons = ["No clear direction — mixed signals"]

        confidence = abs(final_score)

        return DailyBias(
            direction=direction,
            confidence=round(confidence, 3),
            score=round(final_score, 3),
            reasons=reasons,
            method="ensemble" if ml_score != 0 else "rules",
            ml_score=round(ml_score, 3),
            rules_score=round(rules_score, 3),
        )
