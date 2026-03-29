"""ML prediction — loads trained LightGBM models and generates predictions.

Used by the live prediction engine as an upgrade from the rule-based scorer.
Falls back to rule-based if no trained model is available.
"""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import structlog

from trade_plus.instruments import Direction, Instrument, INSTRUMENT_MAP
from trade_plus.market_data.signal_collector import SignalSnapshot
from trade_plus.ml.features import (
    build_instrument_features,
    build_global_features,
    build_calendar_features,
)

logger = structlog.get_logger()

MODEL_DIR = Path(__file__).resolve().parents[3] / "models"


class MLPredictor:
    """Loads trained models and generates ML-based predictions."""

    def __init__(self) -> None:
        self._models: dict[str, object] = {}
        self._feature_names: dict[str, list[str]] = {}
        self._metrics: dict[str, dict] = {}
        self._loaded = False

    def load_models(self) -> None:
        """Load all available trained models from disk."""
        if not MODEL_DIR.exists():
            logger.warning("ml_no_model_dir", path=str(MODEL_DIR))
            return

        for model_file in MODEL_DIR.glob("*_model.joblib"):
            ticker = model_file.stem.replace("_model", "").upper()
            features_file = MODEL_DIR / f"{ticker.lower()}_features.json"
            metrics_file = MODEL_DIR / f"{ticker.lower()}_metrics.json"

            try:
                self._models[ticker] = joblib.load(model_file)

                if features_file.exists():
                    self._feature_names[ticker] = json.loads(features_file.read_text())

                if metrics_file.exists():
                    self._metrics[ticker] = json.loads(metrics_file.read_text())

                acc = self._metrics.get(ticker, {}).get("mean_accuracy", "?")
                logger.info("ml_model_loaded", instrument=ticker, accuracy=acc,
                           features=len(self._feature_names.get(ticker, [])))
            except Exception as e:
                logger.warning("ml_model_load_failed", instrument=ticker, error=str(e))

        self._loaded = True
        logger.info("ml_models_ready", count=len(self._models),
                   instruments=list(self._models.keys()))

    def has_model(self, ticker: str) -> bool:
        return ticker in self._models

    def predict(self, snap: SignalSnapshot) -> tuple[Direction, float, float, list[str]]:
        """Generate ML prediction for an instrument.

        Returns: (direction, score, confidence, reasons)
        """
        ticker = snap.instrument
        model = self._models.get(ticker)
        feature_names = self._feature_names.get(ticker, [])

        if model is None or not feature_names:
            raise ValueError(f"No model for {ticker}")

        # Build feature vector from the live snapshot
        features = snap.to_feature_dict()

        # Map snapshot features to the model's expected feature names
        feature_vector = []
        missing = []
        for fname in feature_names:
            val = features.get(fname)
            if val is None:
                # Try partial match (signal_collector prefixes differ from historical)
                matched = False
                for k, v in features.items():
                    if k.endswith(fname) or fname.endswith(k):
                        feature_vector.append(float(v) if v is not None else 0.0)
                        matched = True
                        break
                if not matched:
                    feature_vector.append(0.0)
                    missing.append(fname)
            else:
                feature_vector.append(float(val) if val is not None else 0.0)

        if missing:
            logger.debug("ml_features_missing", instrument=ticker, count=len(missing))

        # Predict
        X = np.array([feature_vector])
        proba = model.predict_proba(X)[0]  # [prob_down, prob_up]
        prob_up = proba[1]
        prob_down = proba[0]

        # Convert to direction + score
        score = (prob_up - 0.5) * 2  # -1 to +1

        if prob_up > 0.55:
            direction = Direction.LONG
        elif prob_down > 0.55:
            direction = Direction.SHORT
        else:
            direction = Direction.FLAT

        confidence = abs(prob_up - 0.5) * 2  # 0 to 1

        # Reasons from feature importance
        metrics = self._metrics.get(ticker, {})
        top_features = metrics.get("top_features", {})
        reasons = []

        if direction == Direction.LONG:
            reasons.append(f"ML model: {prob_up:.0%} probability UP")
        elif direction == Direction.SHORT:
            reasons.append(f"ML model: {prob_down:.0%} probability DOWN")
        else:
            reasons.append(f"ML model: low confidence ({max(prob_up, prob_down):.0%})")

        # Add top contributing features
        for fname in list(top_features.keys())[:3]:
            val = features.get(fname, 0)
            if isinstance(val, (int, float)) and abs(val) > 0.01:
                reasons.append(f"{fname.replace('_', ' ')}: {val:+.2f}")

        acc = metrics.get("mean_accuracy", 0)
        reasons.append(f"Model accuracy: {acc:.1%} (CV)")

        return direction, round(score, 4), round(confidence, 4), reasons


# Global singleton
_predictor: MLPredictor | None = None


def get_ml_predictor() -> MLPredictor:
    global _predictor
    if _predictor is None:
        _predictor = MLPredictor()
        _predictor.load_models()
    return _predictor
