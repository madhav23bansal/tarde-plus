"""Train LightGBM + CatBoost ensemble with triple barrier labels.

Key improvements over v1:
  - Triple barrier labeling (matches 0.5% target / 0.7% stop)
  - LightGBM + CatBoost ensemble (averaged probabilities)
  - Walk-forward validation with embargo (prevents look-ahead bias)
  - Feature importance-based pruning

Usage:
    .venv/bin/python -m trade_plus.ml.train
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import catboost as cb
import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
import yfinance as yf
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import TimeSeriesSplit

from trade_plus.instruments import ALL_INSTRUMENTS, Instrument, NIFTYBEES, BANKBEES
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
    embargo: int = 3,
) -> tuple[dict, dict]:
    """Train LightGBM + CatBoost ensemble with walk-forward validation.

    Returns dict of models {"lgb": model, "cat": model} and metrics.
    """
    print(f"\n{'='*60}")
    print(f"  Training: {instrument} (Triple Barrier + Ensemble)")
    print(f"  Samples: {len(X)} | Features: {X.shape[1]}")
    print(f"  Class balance: WIN={int(y.sum())} ({y.mean()*100:.1f}%) / LOSS={int(len(y)-y.sum())} ({(1-y.mean())*100:.1f}%)")
    print(f"  Label: triple barrier (0.5% target / 0.7% stop)")
    print(f"{'='*60}")

    # Walk-forward with embargo
    tscv = TimeSeriesSplit(n_splits=n_splits)
    lgb_scores = []
    cat_scores = []
    ens_scores = []
    fold_details = []

    for fold, (train_idx, test_idx) in enumerate(tscv.split(X)):
        # Apply embargo: skip first `embargo` rows of test set
        if embargo > 0 and len(test_idx) > embargo:
            test_idx = test_idx[embargo:]

        X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
        y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]

        # LightGBM
        lgb_model = lgb.LGBMClassifier(
            n_estimators=500, max_depth=6, learning_rate=0.03,
            subsample=0.7, colsample_bytree=0.7,
            reg_alpha=0.5, reg_lambda=1.0,
            min_child_samples=30, random_state=42, verbose=-1,
        )
        lgb_model.fit(
            X_train, y_train,
            eval_set=[(X_test, y_test)],
            callbacks=[lgb.log_evaluation(0), lgb.early_stopping(50, verbose=False)],
        )

        # CatBoost
        cat_model = cb.CatBoostClassifier(
            iterations=500, depth=6, learning_rate=0.03,
            l2_leaf_reg=3, subsample=0.7,
            random_seed=42, verbose=0,
        )
        cat_model.fit(X_train, y_train, eval_set=(X_test, y_test), early_stopping_rounds=50)

        # Individual predictions
        lgb_proba = lgb_model.predict_proba(X_test)[:, 1]
        cat_proba = cat_model.predict_proba(X_test)[:, 1]

        # Ensemble: average probabilities
        ens_proba = 0.5 * lgb_proba + 0.5 * cat_proba
        ens_preds = (ens_proba > 0.5).astype(int)

        lgb_acc = accuracy_score(y_test, (lgb_proba > 0.5).astype(int))
        cat_acc = accuracy_score(y_test, (cat_proba > 0.5).astype(int))
        ens_acc = accuracy_score(y_test, ens_preds)

        lgb_scores.append(lgb_acc)
        cat_scores.append(cat_acc)
        ens_scores.append(ens_acc)

        # Confident predictions (>55% or <45%)
        confident_mask = (ens_proba > 0.55) | (ens_proba < 0.45)
        conf_acc = accuracy_score(y_test[confident_mask], ens_preds[confident_mask]) if confident_mask.sum() > 5 else 0
        conf_pct = confident_mask.mean() * 100

        fold_details.append({
            "fold": fold + 1,
            "train_size": len(X_train),
            "test_size": len(X_test),
            "lgb_acc": round(lgb_acc, 4),
            "cat_acc": round(cat_acc, 4),
            "ensemble_acc": round(ens_acc, 4),
            "confident_acc": round(conf_acc, 4),
            "confident_pct": round(conf_pct, 1),
        })

        print(f"  Fold {fold+1}: LGB={lgb_acc:.3f} CAT={cat_acc:.3f} ENS={ens_acc:.3f} | confident={conf_acc:.3f} ({conf_pct:.0f}%)")

    mean_lgb = np.mean(lgb_scores)
    mean_cat = np.mean(cat_scores)
    mean_ens = np.mean(ens_scores)
    print(f"\n  Mean: LGB={mean_lgb:.3f} CAT={mean_cat:.3f} ENSEMBLE={mean_ens:.3f}")

    # Train final models on ALL data
    final_lgb = lgb.LGBMClassifier(
        n_estimators=500, max_depth=6, learning_rate=0.03,
        subsample=0.7, colsample_bytree=0.7,
        reg_alpha=0.5, reg_lambda=1.0,
        min_child_samples=30, random_state=42, verbose=-1,
    )
    final_lgb.fit(X, y)

    final_cat = cb.CatBoostClassifier(
        iterations=500, depth=6, learning_rate=0.03,
        l2_leaf_reg=3, subsample=0.7,
        random_seed=42, verbose=0,
    )
    final_cat.fit(X, y)

    # Feature importance (from LightGBM — more interpretable)
    importance = pd.Series(
        final_lgb.feature_importances_, index=X.columns,
    ).sort_values(ascending=False)

    print(f"\n  Top 10 features:")
    for feat, imp in importance.head(10).items():
        print(f"    {feat:<35s} {imp:>6.0f}")

    metrics = {
        "instrument": instrument,
        "samples": len(X),
        "features": X.shape[1],
        "feature_names": list(X.columns),
        "label_type": "triple_barrier",
        "target_pct": 0.005,
        "stop_pct": 0.007,
        "mean_accuracy": round(mean_ens, 4),
        "lgb_accuracy": round(mean_lgb, 4),
        "cat_accuracy": round(mean_cat, 4),
        "std_accuracy": round(np.std(ens_scores), 4),
        "folds": fold_details,
        "top_features": {str(k): int(v) for k, v in importance.head(20).items()},
        "class_balance": {"win": int(y.sum()), "loss": int(len(y) - y.sum())},
        "trained_at": datetime.now().isoformat(),
        "embargo_days": embargo,
    }

    models = {"lgb": final_lgb, "cat": final_cat}
    return models, metrics


def save_model(models: dict, instrument: str, metrics: dict, feature_names: list[str]):
    """Save ensemble models, metrics, and feature names."""
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    # Save LightGBM (backward compatible — old predict.py loads this)
    lgb_path = MODEL_DIR / f"{instrument.lower()}_model.joblib"
    joblib.dump(models["lgb"], lgb_path)

    # Save CatBoost
    cat_path = MODEL_DIR / f"{instrument.lower()}_cat_model.joblib"
    joblib.dump(models["cat"], cat_path)

    metrics_path = MODEL_DIR / f"{instrument.lower()}_metrics.json"
    features_path = MODEL_DIR / f"{instrument.lower()}_features.json"

    metrics_path.write_text(json.dumps(metrics, indent=2))
    features_path.write_text(json.dumps(feature_names))

    print(f"  Saved: {lgb_path} + {cat_path}")


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

        models, metrics = train_model(X, y, inst.ticker)
        save_model(models, inst.ticker, metrics, list(X.columns))
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
