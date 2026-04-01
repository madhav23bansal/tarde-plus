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

    def predict(self, signals: dict, full_snapshot=None) -> DailyBias:
        """Generate daily bias from global signals.

        Args:
            signals: dict with keys like sp500_change, india_vix, crude_oil_change, etc.
            full_snapshot: optional SignalSnapshot for ML — avoids creating an empty one.
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
        vix_change = signals.get("india_vix_change", 0)
        if vix > 20:
            # High VIX = fear = intraday momentum continues down
            bear += 2
            reasons_bear.append(f"High VIX {vix:.0f} (fear = sell momentum)")
            # But if VIX is falling sharply from high, recovery underway
            if vix_change < -5:
                bull += 1
                reasons_bull.append(f"VIX falling {vix_change:.1f}% (recovery)")
        elif vix < 14:
            # Low VIX = complacency = slow grind up
            bull += 1
            reasons_bull.append(f"Low VIX {vix:.0f} (calm, grind up)")

        # 3. Crude oil (weight: 2)
        crude = signals.get("crude_oil_change", 0)
        if crude > 2:
            bear += 2
            reasons_bear.append(f"Crude +{crude:.1f}% (bearish for India)")
        elif crude < -2:
            bull += 2
            reasons_bull.append(f"Crude {crude:.1f}% (bullish for India)")

        # 4. FII/DII (weight: up to 4) — proportional to flow magnitude
        fii = signals.get("fii_net", 0)
        if abs(fii) > 500:
            # Scale: 1000 Cr = 1 point. Cap at ±4.
            fii_score = max(-4, min(4, fii / 1000))
            if fii_score > 0:
                bull += abs(fii_score)
                reasons_bull.append(f"FII +{fii:.0f}Cr (w={abs(fii_score):.1f})")
            else:
                bear += abs(fii_score)
                reasons_bear.append(f"FII {fii:.0f}Cr (w={abs(fii_score):.1f})")

        # 5. USD/INR (weight: 1)
        usdinr = signals.get("usd_inr_change", 0)
        if usdinr > 0.3:
            bear += 1
            reasons_bear.append(f"INR weakening +{usdinr:.1f}%")
        elif usdinr < -0.3:
            bull += 1
            reasons_bull.append(f"INR strengthening {usdinr:.1f}%")

        # 6. Advance/Decline breadth (weight: 2) — NEW
        ad_ratio = signals.get("ad_ratio", 0)
        breadth = signals.get("ad_breadth_pct", 0)
        if ad_ratio > 0:
            if breadth > 65:
                # Strong breadth: >65% of Nifty 50 advancing
                bull += 2
                reasons_bull.append(f"Breadth {breadth:.0f}% advancing (A:D={ad_ratio:.1f})")
            elif breadth < 35:
                # Weak breadth: <35% advancing
                bear += 2
                reasons_bear.append(f"Breadth {breadth:.0f}% advancing (A:D={ad_ratio:.1f})")

        # 7. News sentiment from RSS feeds (weight: 1.5)
        news_score = signals.get("news_score", 0)
        news_total = signals.get("news_total", 0)
        if news_total >= 5 and abs(news_score) > 0.1:
            news_weight = min(1.5, abs(news_score) * 3)  # scale 0-1.5
            if news_score > 0.1:
                bull += news_weight
                reasons_bull.append(f"News sentiment +{news_score:.2f} ({news_total} articles)")
            elif news_score < -0.1:
                bear += news_weight
                reasons_bear.append(f"News sentiment {news_score:.2f} ({news_total} articles)")

        # 8. FII cumulative momentum (weight: up to 2)
        fii_5d = signals.get("fii_5d", 0)
        fii_momentum = signals.get("fii_momentum_score", 0)
        fii_consec = signals.get("fii_consecutive", 0)
        if abs(fii_momentum) > 0.05:
            mom_weight = min(2, abs(fii_momentum) * 4)
            if fii_momentum > 0:
                bull += mom_weight
                reasons_bull.append(f"FII momentum +{fii_5d:.0f}Cr/5d (streak {fii_consec}d)")
            else:
                bear += mom_weight
                reasons_bear.append(f"FII momentum {fii_5d:.0f}Cr/5d (streak {fii_consec}d)")

        # 9. Gap prediction from pre-market signals (weight: 2)
        gap_pct = signals.get("predicted_gap_pct", 0)
        gap_conf = signals.get("gap_confidence", 0)
        if abs(gap_pct) > 0.3 and gap_conf > 0.2:
            gap_weight = min(2, abs(gap_pct))  # cap at 2
            if gap_pct > 0:
                bull += gap_weight
                reasons_bull.append(f"Gap prediction +{gap_pct:.2f}% ({gap_conf:.0%} conf)")
            else:
                bear += gap_weight
                reasons_bear.append(f"Gap prediction {gap_pct:.2f}% ({gap_conf:.0%} conf)")

        # Compute rules score
        total = bull + bear
        rules_score = (bull - bear) / total if total > 0 else 0

        # ML bias (if available)
        ml_score = 0.0
        if self._ml and self._ml.has_model("NIFTYBEES"):
            try:
                if full_snapshot:
                    # Use the real snapshot with all 52 features
                    snap = full_snapshot
                else:
                    from trade_plus.market_data.signal_collector import SignalSnapshot
                    snap = SignalSnapshot(instrument="NIFTYBEES", sector="index")
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
