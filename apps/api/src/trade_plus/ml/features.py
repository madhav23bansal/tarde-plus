"""Feature engineering — reconstruct signal_collector features from historical data.

Takes raw OHLCV DataFrames for instruments + global markets and produces
the same feature set that the live pipeline generates, so the model
trained on history works identically in production.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(period).mean()
    rs = gain / (loss + 1e-10)
    return 100 - (100 / (1 + rs))


def macd_histogram(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.Series:
    macd_line = ema(close, fast) - ema(close, slow)
    signal_line = ema(macd_line, signal)
    return macd_line - signal_line


def bollinger_position(close: pd.Series, period: int = 20, std_dev: float = 2.0) -> pd.Series:
    sma = close.rolling(period).mean()
    std = close.rolling(period).std()
    upper = sma + std_dev * std
    lower = sma - std_dev * std
    band_range = upper - lower
    return ((close - lower) / band_range).clip(0, 1)


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def build_instrument_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute technical features for one instrument.

    Input: DataFrame with columns [Open, High, Low, Close, Volume]
    Output: DataFrame with all technical indicator columns added.
    """
    out = pd.DataFrame(index=df.index)

    c = df["Close"]
    h = df["High"]
    l = df["Low"]
    v = df["Volume"]

    # Returns
    out["returns_1d"] = c.pct_change() * 100
    out["returns_5d"] = c.pct_change(5) * 100
    out["returns_10d"] = c.pct_change(10) * 100

    # Momentum indicators
    out["rsi_14"] = rsi(c, 14)
    out["macd_histogram"] = macd_histogram(c)
    out["bb_position"] = bollinger_position(c)
    out["atr_14"] = atr(h, l, c, 14)

    # EMA crossover
    out["ema_9"] = ema(c, 9)
    out["ema_21"] = ema(c, 21)
    out["ema_crossover"] = (out["ema_9"] > out["ema_21"]).astype(float) * 2 - 1  # +1 or -1

    # Volume
    vol_avg = v.rolling(20).mean()
    out["volume_ratio"] = v / (vol_avg + 1)

    # Price change
    out["price_change_pct"] = c.pct_change() * 100

    return out


def build_global_features(globals_df: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Build features from global market DataFrames.

    Input: dict of {name: DataFrame with Close column}
    Output: DataFrame with global change% features, indexed by date.
    """
    features = pd.DataFrame()

    for name, df in globals_df.items():
        if df.empty:
            continue
        close = df["Close"]
        features[f"global_{name}_change"] = close.pct_change() * 100
        features[f"global_{name}_5d"] = close.pct_change(5) * 100

    # India VIX derived features (critical for Nifty prediction)
    if "india_vix" in globals_df and not globals_df["india_vix"].empty:
        vix = globals_df["india_vix"]["Close"]
        features["vix_level"] = vix
        features["vix_above_20"] = (vix > 20).astype(float)      # fear regime
        features["vix_below_14"] = (vix < 14).astype(float)      # complacency
        features["vix_percentile"] = vix.rolling(120).rank(pct=True)  # 6-month percentile
        features["vix_10d_change"] = vix.pct_change(10) * 100
        # VIX spike: single-day move > 10%
        features["vix_spike"] = (vix.pct_change().abs() > 0.10).astype(float)
        # VIX mean reversion signal: high VIX + falling = bullish
        features["vix_mean_revert"] = ((vix > 20) & (vix.pct_change() < -0.03)).astype(float)

    # Derived
    if "gold" in globals_df and "silver" in globals_df:
        gc = globals_df["gold"]["Close"]
        sc = globals_df["silver"]["Close"]
        aligned = pd.concat([gc, sc], axis=1, keys=["gold", "silver"]).dropna()
        if not aligned.empty:
            gs_ratio = aligned["gold"] / aligned["silver"]
            features["global_gold_silver_ratio"] = gs_ratio
            features["global_gs_ratio_signal"] = (gs_ratio > 85).astype(float) - (gs_ratio < 70).astype(float)

    return features


def build_calendar_features(index: pd.DatetimeIndex) -> pd.DataFrame:
    """Calendar-based features."""
    out = pd.DataFrame(index=index)
    out["day_of_week"] = index.dayofweek

    # Days to monthly expiry (last Thursday)
    def days_to_expiry(dt):
        import calendar
        year, month = dt.year, dt.month
        cal = calendar.monthcalendar(year, month)
        last_thu = max(week[3] for week in cal if week[3] != 0)
        expiry = pd.Timestamp(year, month, last_thu)
        if dt.date() > expiry.date():
            # next month
            month = month + 1 if month < 12 else 1
            year = year if month > 1 else year + 1
            cal = calendar.monthcalendar(year, month)
            last_thu = max(week[3] for week in cal if week[3] != 0)
            expiry = pd.Timestamp(year, month, last_thu)
        return (expiry.date() - dt.date()).days

    out["days_to_expiry"] = [days_to_expiry(dt) for dt in index]
    out["is_expiry_week"] = (out["days_to_expiry"] <= 5).astype(float)

    return out


def _normalize_index(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize index to tz-naive date for consistent joining."""
    df = df.copy()
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    df.index = df.index.normalize()  # strip time, keep date
    # Remove duplicate dates (keep last)
    df = df[~df.index.duplicated(keep="last")]
    return df


def build_training_dataset(
    instrument_df: pd.DataFrame,
    globals_df: dict[str, pd.DataFrame],
    lookahead: int = 1,
) -> tuple[pd.DataFrame, pd.Series]:
    """Build complete feature matrix + target for one instrument.

    Args:
        instrument_df: OHLCV data for the instrument
        globals_df: dict of global market OHLCV DataFrames
        lookahead: number of days to look ahead for the target (1 = next day)

    Returns:
        X: feature DataFrame
        y: target Series (1 = price went up, 0 = price went down)
    """
    # Normalize all indexes to tz-naive dates
    instrument_df = _normalize_index(instrument_df)
    normalized_globals = {k: _normalize_index(v) for k, v in globals_df.items()}

    # Instrument features
    inst_feat = build_instrument_features(instrument_df)

    # Global features
    global_feat = build_global_features(normalized_globals)

    # Calendar
    cal_feat = build_calendar_features(instrument_df.index)

    # Merge all on date index
    X = pd.concat([inst_feat, global_feat, cal_feat], axis=1)

    # Align all to the instrument's index
    X = X.reindex(instrument_df.index)

    # Forward-fill global data (different trading calendars)
    X = X.ffill()

    # Target: did price go UP in the next N days?
    future_return = instrument_df["Close"].shift(-lookahead) / instrument_df["Close"] - 1
    y = (future_return > 0).astype(int)

    # Drop rows with NaN (warmup period + last N rows without future data)
    valid = X.notna().all(axis=1) & y.notna()
    X = X[valid]
    y = y[valid]

    return X, y
