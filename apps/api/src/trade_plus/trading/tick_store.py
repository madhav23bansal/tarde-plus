"""Tick storage — backfill historical + store live ticks in TimescaleDB.

Provides intraday candle queries for the scalper's technical analysis.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import structlog

logger = structlog.get_logger()
_executor = ThreadPoolExecutor(max_workers=2)


async def backfill_ticks(pool, instruments: dict[str, str]) -> int:
    """Download and store 7 days of 1-min + 60 days of 5-min candles.

    Args:
        pool: asyncpg connection pool
        instruments: {ticker: yahoo_symbol}
    Returns:
        total rows inserted
    """
    loop = asyncio.get_event_loop()
    total = 0

    def _download(yahoo_sym: str, period: str, interval: str):
        import yfinance as yf
        t = yf.Ticker(yahoo_sym)
        df = t.history(period=period, interval=interval)
        if df.empty:
            return []
        rows = []
        for ts, row in df.iterrows():
            # Normalize timezone
            if ts.tzinfo is not None:
                ts = ts.tz_localize(None)
            rows.append((
                ts.to_pydatetime(),
                float(row["Close"]),
                float(row.get("Open", row["Close"])),
                float(row.get("High", row["Close"])),
                float(row.get("Low", row["Close"])),
                int(row.get("Volume", 0)),
            ))
        return rows

    for ticker, yahoo_sym in instruments.items():
        # 1-minute candles (7 days)
        rows_1m = await loop.run_in_executor(_executor, _download, yahoo_sym, "7d", "1m")
        if rows_1m:
            await pool.executemany(
                """INSERT INTO ticks (time, instrument, ltp, bid, ask, volume, oi, exchange)
                   VALUES ($1, $2, $3, $3, $3, $4, 0, 'NSE')
                   ON CONFLICT DO NOTHING""",
                [(r[0], ticker, r[1], r[5]) for r in rows_1m],
            )
            total += len(rows_1m)
            logger.info("backfill_1m", instrument=ticker, rows=len(rows_1m))

        # 5-minute candles (60 days) — fill gaps where 1m data doesn't reach
        rows_5m = await loop.run_in_executor(_executor, _download, yahoo_sym, "60d", "5m")
        if rows_5m:
            await pool.executemany(
                """INSERT INTO ticks (time, instrument, ltp, bid, ask, volume, oi, exchange)
                   VALUES ($1, $2, $3, $3, $3, $4, 0, 'NSE')
                   ON CONFLICT DO NOTHING""",
                [(r[0], ticker, r[1], r[5]) for r in rows_5m],
            )
            total += len(rows_5m)
            logger.info("backfill_5m", instrument=ticker, rows=len(rows_5m))

    logger.info("backfill_complete", total_rows=total)
    return total


async def store_tick(pool, instrument: str, price: float, volume: int = 0) -> None:
    """Store a single live price tick."""
    await pool.execute(
        """INSERT INTO ticks (time, instrument, ltp, bid, ask, volume, oi, exchange)
           VALUES (NOW(), $1, $2, $2, $2, $3, 0, 'NSE')""",
        instrument, price, volume,
    )


async def store_ticks_batch(pool, ticks: list[tuple]) -> None:
    """Store multiple live ticks. Each tuple: (instrument, price, volume)."""
    await pool.executemany(
        """INSERT INTO ticks (time, instrument, ltp, bid, ask, volume, oi, exchange)
           VALUES (NOW(), $1, $2, $2, $2, $3, 0, 'NSE')""",
        ticks,
    )


async def get_intraday_candles(pool, instrument: str, interval_min: int = 5, limit: int = 100) -> list[dict]:
    """Get recent intraday candles from stored ticks.

    Uses TimescaleDB time_bucket for efficient aggregation.
    """
    rows = await pool.fetch(
        f"""SELECT
            time_bucket('{interval_min} minutes', time) AS bucket,
            FIRST(ltp, time) AS open,
            MAX(ltp) AS high,
            MIN(ltp) AS low,
            LAST(ltp, time) AS close,
            SUM(volume) AS volume,
            COUNT(*) AS tick_count
        FROM ticks
        WHERE instrument = $1 AND time > NOW() - INTERVAL '{limit * interval_min} minutes'
        GROUP BY bucket
        ORDER BY bucket DESC
        LIMIT $2""",
        instrument, limit,
    )
    return [dict(r) for r in rows]


async def get_today_stats(pool, instrument: str) -> dict:
    """Get today's OHLCV stats from ticks."""
    row = await pool.fetchrow(
        """SELECT
            FIRST(ltp, time) AS day_open,
            MAX(ltp) AS day_high,
            MIN(ltp) AS day_low,
            LAST(ltp, time) AS day_close,
            SUM(volume) AS day_volume,
            COUNT(*) AS tick_count,
            MIN(time) AS first_tick,
            MAX(time) AS last_tick
        FROM ticks
        WHERE instrument = $1 AND time >= CURRENT_DATE
        """,
        instrument,
    )
    if not row or not row["day_close"]:
        return {}
    return {
        "open": float(row["day_open"]),
        "high": float(row["day_high"]),
        "low": float(row["day_low"]),
        "close": float(row["day_close"]),
        "volume": int(row["day_volume"] or 0),
        "tick_count": row["tick_count"],
        "range_pct": round((float(row["day_high"]) - float(row["day_low"])) / float(row["day_open"]) * 100, 3) if row["day_open"] else 0,
    }


async def get_recent_days_summary(pool, instrument: str, days: int = 7) -> list[dict]:
    """Get daily OHLCV for the last N days from stored ticks."""
    rows = await pool.fetch(
        """SELECT
            time_bucket('1 day', time) AS day,
            FIRST(ltp, time) AS open,
            MAX(ltp) AS high,
            MIN(ltp) AS low,
            LAST(ltp, time) AS close,
            SUM(volume) AS volume
        FROM ticks
        WHERE instrument = $1 AND time > NOW() - INTERVAL '$2 days'
        GROUP BY day
        ORDER BY day DESC
        LIMIT $2""",
        instrument, days,
    )
    return [dict(r) for r in rows]


async def compute_intraday_indicators(pool, instrument: str) -> dict:
    """Compute real-time intraday technical indicators from stored ticks.

    These are INTRADAY indicators (from today's ticks), not daily.
    Much more responsive than the 6-month daily RSI.
    """
    # Get last 100 5-minute candles
    candles = await get_intraday_candles(pool, instrument, interval_min=5, limit=100)
    if len(candles) < 14:
        return {}

    # Candles are DESC order, reverse for calculations
    candles = list(reversed(candles))
    closes = [float(c["close"]) for c in candles]

    import numpy as np
    c = np.array(closes)

    # Intraday RSI (14-period on 5-min candles)
    delta = np.diff(c)
    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)
    if len(gain) >= 14:
        avg_gain = np.convolve(gain, np.ones(14) / 14, mode='valid')
        avg_loss = np.convolve(loss, np.ones(14) / 14, mode='valid')
        rs = avg_gain[-1] / (avg_loss[-1] + 1e-10)
        rsi = 100 - (100 / (1 + rs))
    else:
        rsi = 50.0

    # Intraday EMA 9/21
    def ema(data, period):
        alpha = 2 / (period + 1)
        e = data[0]
        for d in data[1:]:
            e = alpha * d + (1 - alpha) * e
        return e

    ema9 = ema(closes, 9) if len(closes) >= 9 else closes[-1]
    ema21 = ema(closes, 21) if len(closes) >= 21 else closes[-1]

    # Intraday Bollinger Bands (20-period)
    if len(c) >= 20:
        sma = np.mean(c[-20:])
        std = np.std(c[-20:])
        upper = sma + 2 * std
        lower = sma - 2 * std
        bb_pos = (c[-1] - lower) / (upper - lower) if upper != lower else 0.5
    else:
        bb_pos = 0.5

    # Intraday VWAP (volume-weighted)
    volumes = [float(c.get("volume", 0) or 1) for c in candles]
    vwap_prices = [float(c["close"]) for c in candles]
    cum_pv = sum(p * v for p, v in zip(vwap_prices, volumes))
    cum_v = sum(volumes)
    vwap = cum_pv / cum_v if cum_v > 0 else closes[-1]

    # Recent momentum (last 5 candles = 25 min)
    momentum_25m = (closes[-1] / closes[-6] - 1) * 100 if len(closes) >= 6 else 0
    # Recent momentum (last 12 candles = 1 hour)
    momentum_1h = (closes[-1] / closes[-13] - 1) * 100 if len(closes) >= 13 else 0

    return {
        "intraday_rsi": round(float(rsi), 1),
        "intraday_ema9": round(ema9, 2),
        "intraday_ema21": round(ema21, 2),
        "intraday_ema_trend": "BULL" if ema9 > ema21 else "BEAR",
        "intraday_bb_position": round(float(bb_pos), 3),
        "intraday_vwap": round(vwap, 2),
        "above_vwap": closes[-1] > vwap,
        "momentum_25m": round(momentum_25m, 4),
        "momentum_1h": round(momentum_1h, 4),
        "current_price": closes[-1],
        "candle_count": len(candles),
    }
