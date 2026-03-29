"""Train LightGBM models for each instrument using historical data.

Downloads 2 years of data from Yahoo Finance, engineers features,
trains with time-series cross-validation, and saves models.

Usage:
    .venv/bin/python -m trade_plus.ml.train
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
import yfinance as yf
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import TimeSeriesSplit

from trade_plus.instruments import ALL_INSTRUMENTS, Instrument
from trade_plus.ml.features import build_training_dataset

MODEL_DIR = Path(__file__).resolve().parents[3] / "models"

# Global market tickers to download
GLOBAL_TICKERS = {
    "sp500": "^GSPC",
    "nasdaq": "^IXIC",
    "dow": "^DJI",
    "nikkei": "^N225",
    "hangseng": "^HSI",
    "crude_oil": "CL=F",
    "gold": "GC=F",
    "silver": "SI=F",
    "copper": "HG=F",
    "usd_inr": "USDINR=X",
    "dxy": "DX-Y.NYB",
    "us_10y": "^TNX",
    "india_vix": "^INDIAVIX",
    "us_futures": "ES=F",
}


def download_data(period: str = "2y") -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame]]:
    """Download historical data for all instruments and global markets."""
    print(f"Downloading {period} of historical data...")

    instruments_data = {}
    for inst in ALL_INSTRUMENTS:
        print(f"  {inst.ticker} ({inst.yahoo_symbol})...", end=" ", flush=True)
        t = yf.Ticker(inst.yahoo_symbol)
        df = t.history(period=period, interval="1d")
        if not df.empty:
            instruments_data[inst.ticker] = df
            print(f"{len(df)} days")
        else:
            print("NO DATA")

    globals_data = {}
    for name, ticker in GLOBAL_TICKERS.items():
        print(f"  {name} ({ticker})...", end=" ", flush=True)
        t = yf.Ticker(ticker)
        df = t.history(period=period, interval="1d")
        if not df.empty:
            globals_data[name] = df
            print(f"{len(df)} days")
        else:
            print("NO DATA")

    return instruments_data, globals_data


def train_model(
    X: pd.DataFrame,
    y: pd.Series,
    instrument: str,
    n_splits: int = 5,
) -> tuple[lgb.LGBMClassifier, dict]:
    """Train LightGBM with time-series cross-validation.

    Returns the final trained model and a metrics dict.
    """
    print(f"\n{'='*60}")
    print(f"  Training: {instrument}")
    print(f"  Samples: {len(X)} | Features: {X.shape[1]}")
    print(f"  Class balance: UP={y.sum()} ({y.mean()*100:.1f}%) / DOWN={len(y)-y.sum()} ({(1-y.mean())*100:.1f}%)")
    print(f"{'='*60}")

    tscv = TimeSeriesSplit(n_splits=n_splits)
    fold_scores = []
    fold_details = []

    for fold, (train_idx, test_idx) in enumerate(tscv.split(X)):
        X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
        y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]

        model = lgb.LGBMClassifier(
            n_estimators=300,
            max_depth=5,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            reg_alpha=0.1,
            reg_lambda=0.1,
            min_child_samples=20,
            random_state=42,
            verbose=-1,
        )

        model.fit(
            X_train, y_train,
            eval_set=[(X_test, y_test)],
            callbacks=[lgb.log_evaluation(0)],
        )

        preds = model.predict(X_test)
        acc = accuracy_score(y_test, preds)
        fold_scores.append(acc)

        # Detailed metrics
        proba = model.predict_proba(X_test)[:, 1]
        # Only count predictions with confidence > threshold
        confident_mask = (proba > 0.55) | (proba < 0.45)
        if confident_mask.sum() > 0:
            confident_acc = accuracy_score(y_test[confident_mask], preds[confident_mask])
            confident_pct = confident_mask.mean() * 100
        else:
            confident_acc = 0
            confident_pct = 0

        fold_details.append({
            "fold": fold + 1,
            "train_size": len(X_train),
            "test_size": len(X_test),
            "accuracy": round(acc, 4),
            "confident_accuracy": round(confident_acc, 4),
            "confident_pct": round(confident_pct, 1),
        })

        print(f"  Fold {fold+1}: acc={acc:.3f} | confident_acc={confident_acc:.3f} ({confident_pct:.0f}% of trades)")

    mean_acc = np.mean(fold_scores)
    std_acc = np.std(fold_scores)
    print(f"\n  Mean accuracy: {mean_acc:.3f} ± {std_acc:.3f}")

    # Train final model on ALL data
    final_model = lgb.LGBMClassifier(
        n_estimators=300,
        max_depth=5,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_alpha=0.1,
        reg_lambda=0.1,
        min_child_samples=20,
        random_state=42,
        verbose=-1,
    )
    final_model.fit(X, y)

    # Feature importance
    importance = pd.Series(
        final_model.feature_importances_,
        index=X.columns,
    ).sort_values(ascending=False)

    print(f"\n  Top 10 features:")
    for feat, imp in importance.head(10).items():
        print(f"    {feat:<35s} {imp:>6.0f}")

    metrics = {
        "instrument": instrument,
        "samples": len(X),
        "features": X.shape[1],
        "feature_names": list(X.columns),
        "mean_accuracy": round(mean_acc, 4),
        "std_accuracy": round(std_acc, 4),
        "folds": fold_details,
        "top_features": {str(k): int(v) for k, v in importance.head(20).items()},
        "class_balance": {"up": int(y.sum()), "down": int(len(y) - y.sum())},
        "trained_at": datetime.now().isoformat(),
    }

    return final_model, metrics


def save_model(model: lgb.LGBMClassifier, instrument: str, metrics: dict, feature_names: list[str]):
    """Save model, metrics, and feature names."""
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    model_path = MODEL_DIR / f"{instrument.lower()}_model.joblib"
    metrics_path = MODEL_DIR / f"{instrument.lower()}_metrics.json"
    features_path = MODEL_DIR / f"{instrument.lower()}_features.json"

    joblib.dump(model, model_path)
    metrics_path.write_text(json.dumps(metrics, indent=2))
    features_path.write_text(json.dumps(feature_names))

    print(f"  Saved: {model_path}")


def main():
    print("="*60)
    print("  Trade-Plus ML Model Training")
    print("="*60)

    instruments_data, globals_data = download_data(period="2y")

    all_metrics = {}

    for inst in ALL_INSTRUMENTS:
        if inst.ticker not in instruments_data:
            print(f"\nSkipping {inst.ticker} — no data")
            continue

        inst_df = instruments_data[inst.ticker]
        X, y = build_training_dataset(inst_df, globals_data, lookahead=1)

        if len(X) < 100:
            print(f"\nSkipping {inst.ticker} — only {len(X)} samples (need 100+)")
            continue

        model, metrics = train_model(X, y, inst.ticker)
        save_model(model, inst.ticker, metrics, list(X.columns))
        all_metrics[inst.ticker] = metrics

    # Summary
    print("\n" + "="*60)
    print("  TRAINING SUMMARY")
    print("="*60)
    for ticker, m in all_metrics.items():
        print(f"  {ticker:<14s} acc={m['mean_accuracy']:.3f}±{m['std_accuracy']:.3f}  samples={m['samples']}  features={m['features']}")

    summary_path = MODEL_DIR / "training_summary.json"
    summary_path.write_text(json.dumps(all_metrics, indent=2))
    print(f"\nSummary saved to {summary_path}")


if __name__ == "__main__":
    main()
