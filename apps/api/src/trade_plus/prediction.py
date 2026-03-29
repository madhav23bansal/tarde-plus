"""Prediction engine for Nifty/Gold/Silver/Bank direction.

Currently: Rule-based scoring with weighted factors.
Future: LightGBM trained on historical signal data.

Each instrument gets a score from -1.0 (strong SHORT) to +1.0 (strong LONG).
"""

from __future__ import annotations

from dataclasses import dataclass

from trade_plus.instruments import Direction, Instrument, Sector
from trade_plus.market_data.signal_collector import SignalSnapshot


@dataclass
class Prediction:
    instrument: str
    direction: Direction
    confidence: float           # 0.0 to 1.0
    score: float                # -1.0 (short) to +1.0 (long)
    reasons: list[str]
    features_used: int = 0


class PredictionEngine:
    """Generates directional predictions from signal snapshots.

    Scoring approach: weighted factor model.
    Each factor adds to bull_score or bear_score.
    Weights reflect empirically observed predictive power.
    """

    # Factor weights (higher = more influential)
    WEIGHTS = {
        "fii_flow": 3.0,       # Strongest predictor for Indian equities
        "vix_regime": 2.5,     # Contrarian at extremes
        "global_risk": 2.0,    # US markets drive opening
        "pcr": 2.0,            # Options market sentiment
        "rsi_extreme": 2.0,    # Mean reversion at extremes
        "trend": 1.5,          # EMA crossover + MACD
        "momentum": 1.5,       # 5d/10d returns
        "bollinger": 1.0,      # Band position
        "volume": 1.0,         # Volume confirmation
        "sentiment": 1.0,      # News sentiment
        "sector_driver": 2.0,  # Sector-specific (gold->DXY, etc.)
        "breadth": 1.0,        # Advance/decline
    }

    def predict(self, snap: SignalSnapshot) -> Prediction:
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

        # ── News sentiment ──
        if snap.news_sentiment > 0.15:
            bull += W["sentiment"]
            reasons_bull.append(f"Positive news ({snap.news_sentiment:+.3f})")
        elif snap.news_sentiment < -0.15:
            bear += W["sentiment"]
            reasons_bear.append(f"Negative news ({snap.news_sentiment:+.3f})")

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
