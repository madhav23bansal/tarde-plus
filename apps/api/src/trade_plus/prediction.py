"""Prediction engine for Nifty/Gold/Silver/Bank direction.

Uses LightGBM ML model when available, falls back to rule-based scoring.
Each instrument gets a score from -1.0 (strong SHORT) to +1.0 (strong LONG).
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog

from trade_plus.instruments import Direction, Instrument, Sector
from trade_plus.market_data.signal_collector import SignalSnapshot

logger = structlog.get_logger()


@dataclass
class Prediction:
    instrument: str
    direction: Direction
    confidence: float           # 0.0 to 1.0
    score: float                # -1.0 (short) to +1.0 (long)
    reasons: list[str]
    features_used: int = 0
    method: str = "ensemble"    # "ensemble", "ml", "rules"
    ml_score: float = 0.0      # raw ML score before blending
    rules_score: float = 0.0   # raw rules score before blending
    ml_confidence: float = 0.0
    rules_confidence: float = 0.0


# ML weight by model accuracy — better models get more influence
ML_WEIGHT_BY_ACCURACY = {
    # accuracy -> ml_weight (rules_weight = 1 - ml_weight)
    # Below 52%: don't trust ML, mostly rules
    # 52-55%: slight ML edge
    # 55-60%: ML is genuinely useful
    # 60%+: ML dominant
}

def _ml_weight(accuracy: float) -> float:
    """How much to trust the ML model based on its CV accuracy."""
    if accuracy < 0.52:
        return 0.2   # barely trust it
    elif accuracy < 0.55:
        return 0.4   # slight ML lean
    elif accuracy < 0.60:
        return 0.6   # ML is genuinely useful
    else:
        return 0.75  # ML dominant


class PredictionEngine:
    """Generates ensemble predictions by blending ML + rule-based scores.

    For each instrument:
    1. Compute ML score (LightGBM probability → -1 to +1)
    2. Compute rule-based score (weighted factors → -1 to +1)
    3. Blend: final_score = ml_weight * ml_score + rules_weight * rules_score
       where ml_weight depends on that model's CV accuracy

    If no ML model exists, falls back to rules-only.
    """

    def __init__(self) -> None:
        self._ml = None
        self._ml_accuracies: dict[str, float] = {}
        try:
            from trade_plus.ml.predict import get_ml_predictor
            self._ml = get_ml_predictor()
            for ticker in list(self._ml._metrics.keys()):
                self._ml_accuracies[ticker] = self._ml._metrics[ticker].get("mean_accuracy", 0.5)
            if self._ml_accuracies:
                logger.info("prediction_engine_mode", mode="ensemble",
                           weights={t: f"ml={_ml_weight(a):.0%}" for t, a in self._ml_accuracies.items()})
            else:
                logger.info("prediction_engine_mode", mode="rules_only")
        except Exception as e:
            logger.info("prediction_engine_mode", mode="rules_only", reason=str(e))

    # Factor weights (higher = more influential)
    WEIGHTS = {
        "fii_flow": 3.0,
        "vix_regime": 2.5,
        "global_risk": 2.0,
        "pcr": 2.0,
        "rsi_extreme": 2.0,
        "trend": 1.5,
        "momentum": 1.5,
        "bollinger": 1.0,
        "volume": 1.0,
        "sentiment": 1.0,
        "social_sentiment": 1.5,   # X/Twitter via Grok
        "ai_news": 1.5,           # Parallel AI news
        "sector_driver": 2.0,
        "breadth": 1.0,
    }

    def predict(self, snap: SignalSnapshot) -> Prediction:
        # Always compute rule-based
        rules_pred = self._predict_rules(snap)

        # Try ML
        ml_score = 0.0
        ml_conf = 0.0
        ml_reasons: list[str] = []
        has_ml = False

        if self._ml and self._ml.has_model(snap.instrument):
            try:
                ml_dir, ml_score, ml_conf, ml_reasons = self._ml.predict(snap)
                has_ml = True
            except Exception as e:
                logger.warning("ml_predict_failed", instrument=snap.instrument, error=str(e))

        if not has_ml:
            rules_pred.method = "rules"
            rules_pred.rules_score = rules_pred.score
            rules_pred.rules_confidence = rules_pred.confidence
            return rules_pred

        # Ensemble: blend based on model accuracy
        accuracy = self._ml_accuracies.get(snap.instrument, 0.5)
        w_ml = _ml_weight(accuracy)
        w_rules = 1.0 - w_ml

        blended_score = w_ml * ml_score + w_rules * rules_pred.score
        blended_conf = w_ml * ml_conf + w_rules * rules_pred.confidence

        # Direction from blended score
        if blended_score > 0.05:
            direction = Direction.LONG
        elif blended_score < -0.05:
            direction = Direction.SHORT
        else:
            direction = Direction.FLAT

        # Combine reasons: ML first (if confident), then rules
        reasons = []
        if ml_conf > 0.3:
            reasons.extend(ml_reasons[:2])
        reasons.extend(rules_pred.reasons[:3])
        reasons.append(f"Ensemble: ML({w_ml:.0%}) + Rules({w_rules:.0%}) | ML acc: {accuracy:.1%}")

        return Prediction(
            instrument=snap.instrument,
            direction=direction,
            confidence=round(blended_conf, 4),
            score=round(blended_score, 4),
            reasons=reasons,
            features_used=snap.feature_count,
            method="ensemble",
            ml_score=round(ml_score, 4),
            rules_score=round(rules_pred.score, 4),
            ml_confidence=round(ml_conf, 4),
            rules_confidence=round(rules_pred.confidence, 4),
        )

    def _predict_rules(self, snap: SignalSnapshot) -> Prediction:
        bull = 0.0
        bear = 0.0
        reasons_bull: list[str] = []
        reasons_bear: list[str] = []

        W = self.WEIGHTS

        # ── RSI extremes (mean reversion) ──
        if snap.rsi_14 < 30:
            bull += W["rsi_extreme"]
            reasons_bull.append(f"RSI oversold ({snap.rsi_14:.0f})")
        elif snap.rsi_14 < 40:
            bull += W["rsi_extreme"] * 0.5
        elif snap.rsi_14 > 70:
            bear += W["rsi_extreme"]
            reasons_bear.append(f"RSI overbought ({snap.rsi_14:.0f})")
        elif snap.rsi_14 > 60:
            bear += W["rsi_extreme"] * 0.5

        # ── Trend (EMA crossover + MACD) ──
        if snap.ema_9 > snap.ema_21 and snap.macd_histogram > 0:
            bull += W["trend"]
            reasons_bull.append("Bullish trend (EMA+MACD)")
        elif snap.ema_9 < snap.ema_21 and snap.macd_histogram < 0:
            bear += W["trend"]
            reasons_bear.append("Bearish trend (EMA+MACD)")
        elif snap.ema_9 > snap.ema_21:
            bull += W["trend"] * 0.3
        elif snap.ema_9 < snap.ema_21:
            bear += W["trend"] * 0.3

        # ── Bollinger Band position ──
        if snap.bb_position < 0.15:
            bull += W["bollinger"]
            reasons_bull.append(f"Near lower BB ({snap.bb_position:.2f})")
        elif snap.bb_position > 0.85:
            bear += W["bollinger"]
            reasons_bear.append(f"Near upper BB ({snap.bb_position:.2f})")

        # ── Momentum ──
        if snap.returns_5d > 3:
            bull += W["momentum"]
        elif snap.returns_5d < -3:
            bear += W["momentum"]
            reasons_bear.append(f"5d down {snap.returns_5d:.1f}%")
        if snap.returns_10d > 5:
            bull += W["momentum"] * 0.5
        elif snap.returns_10d < -5:
            bear += W["momentum"] * 0.5

        # ── Volume confirmation ──
        if snap.volume_ratio > 1.5:
            if snap.change_pct > 0:
                bull += W["volume"]
            elif snap.change_pct < 0:
                bear += W["volume"]

        # ── RSS News sentiment ──
        if snap.news_sentiment > 0.15:
            bull += W["sentiment"]
            reasons_bull.append(f"Positive RSS news ({snap.news_sentiment:+.3f})")
        elif snap.news_sentiment < -0.15:
            bear += W["sentiment"]
            reasons_bear.append(f"Negative RSS news ({snap.news_sentiment:+.3f})")

        # ── X/Twitter social sentiment (via Grok) ──
        if snap.social_post_count > 0:
            if snap.social_sentiment > 0.2:
                bull += W["social_sentiment"]
                reasons_bull.append(f"X/Twitter bullish ({snap.social_sentiment:+.2f}, {snap.social_post_count} posts)")
            elif snap.social_sentiment < -0.2:
                bear += W["social_sentiment"]
                reasons_bear.append(f"X/Twitter bearish ({snap.social_sentiment:+.2f}, {snap.social_post_count} posts)")

        # ── AI news search (Parallel AI) ──
        if snap.ai_news_count > 0:
            if snap.ai_news_sentiment > 0.15:
                bull += W["ai_news"]
                reasons_bull.append(f"AI news positive ({snap.ai_news_sentiment:+.3f}, {snap.ai_news_count} articles)")
            elif snap.ai_news_sentiment < -0.15:
                bear += W["ai_news"]
                reasons_bear.append(f"AI news negative ({snap.ai_news_sentiment:+.3f}, {snap.ai_news_count} articles)")

        # ── Global risk (S&P 500 move) ──
        sp_change = snap.sector_signals.get("sp500_change", snap.global_signals.get("global_sp500_change", 0))
        if sp_change > 0.5:
            bull += W["global_risk"]
            reasons_bull.append(f"US markets up ({sp_change:+.1f}%)")
        elif sp_change < -0.5:
            bear += W["global_risk"]
            reasons_bear.append(f"US markets down ({sp_change:+.1f}%)")

        # ── SECTOR-SPECIFIC ──
        self._score_sector(snap, bull, bear, reasons_bull, reasons_bear, W)

        # ── NSE-specific (index/banking only) ──
        if snap.sector in ("index", "banking"):
            # FII/DII flows
            if snap.fii_net > 1000:
                bull += W["fii_flow"]
                reasons_bull.append(f"FII buying +{snap.fii_net:.0f}Cr")
            elif snap.fii_net < -1000:
                bear += W["fii_flow"]
                reasons_bear.append(f"FII selling {snap.fii_net:.0f}Cr")
            elif snap.fii_net > 500:
                bull += W["fii_flow"] * 0.3
            elif snap.fii_net < -500:
                bear += W["fii_flow"] * 0.3

            # VIX regime (contrarian)
            if snap.india_vix > 25:
                bull += W["vix_regime"]
                reasons_bull.append(f"High VIX contrarian ({snap.india_vix:.1f})")
            elif snap.india_vix < 12:
                bear += W["vix_regime"]
                reasons_bear.append(f"Low VIX complacency ({snap.india_vix:.1f})")

            # PCR
            if snap.pcr_oi > 1.3:
                bull += W["pcr"]
                reasons_bull.append(f"High PCR ({snap.pcr_oi:.2f})")
            elif 0 < snap.pcr_oi < 0.7:
                bear += W["pcr"]
                reasons_bear.append(f"Low PCR ({snap.pcr_oi:.2f})")

            # Breadth
            if snap.ad_ratio > 2:
                bull += W["breadth"]
            elif 0 < snap.ad_ratio < 0.5:
                bear += W["breadth"]
                reasons_bear.append(f"Poor breadth (A/D={snap.ad_ratio:.2f})")

        # ── Compute final score ──
        total = bull + bear
        if total == 0:
            return Prediction(
                instrument=snap.instrument, direction=Direction.FLAT,
                confidence=0.0, score=0.0, reasons=["No signals"],
                features_used=snap.feature_count,
            )

        score = (bull - bear) / total  # -1 to +1
        confidence = abs(score)

        # Minimum confidence threshold
        if confidence < 0.1:
            direction = Direction.FLAT
        elif score > 0:
            direction = Direction.LONG
        else:
            direction = Direction.SHORT

        reasons = reasons_bull if direction == Direction.LONG else reasons_bear if direction == Direction.SHORT else ["Low confidence"]

        return Prediction(
            instrument=snap.instrument,
            direction=direction,
            confidence=round(confidence, 3),
            score=round(score, 3),
            reasons=reasons[:5],
            features_used=snap.feature_count,
        )

    def _score_sector(self, snap, bull, bear, reasons_bull, reasons_bear, W):
        """Sector-specific scoring."""
        if snap.sector == "gold":
            # Gold: DXY inverse, real yields inverse
            dxy_change = snap.sector_signals.get("dxy_change", 0)
            if dxy_change < -0.3:
                bull += W["sector_driver"]
                reasons_bull.append(f"USD weakening ({dxy_change:+.2f}%)")
            elif dxy_change > 0.3:
                bear += W["sector_driver"]
                reasons_bear.append(f"USD strengthening ({dxy_change:+.2f}%)")

        elif snap.sector == "silver":
            # Silver: gold correlation + industrial demand
            gs_signal = snap.sector_signals.get("gs_ratio_signal", 0)
            if gs_signal > 0:
                bull += W["sector_driver"]
                reasons_bull.append("Silver cheap vs gold (high G/S ratio)")
            elif gs_signal < 0:
                bear += W["sector_driver"] * 0.3

            copper_change = snap.sector_signals.get("copper_change", 0)
            if copper_change > 1:
                bull += W["sector_driver"] * 0.5
                reasons_bull.append(f"Copper up (industrial demand)")

        elif snap.sector == "banking":
            # Banking: rate sensitivity
            rate_sens = snap.sector_signals.get("rate_sensitivity", 0)
            if rate_sens > 0:
                bull += W["sector_driver"] * 0.5
            elif rate_sens < 0:
                bear += W["sector_driver"] * 0.5
