"""TimescaleDB store — persists signals, predictions, and pipeline runs.

All records are linked by run_id (UUID), not integer cycle IDs.
"""

from __future__ import annotations

import json
import uuid

import asyncpg
import structlog

from trade_plus.core.config import TimescaleConfig

logger = structlog.get_logger()


class TimescaleStore:
    def __init__(self, config: TimescaleConfig) -> None:
        self._config = config
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        self._pool = await asyncpg.create_pool(dsn=self._config.dsn, min_size=2, max_size=10)
        logger.info("timescaledb_connected")

    async def disconnect(self) -> None:
        if self._pool:
            await self._pool.close()

    @property
    def pool(self) -> asyncpg.Pool:
        if not self._pool:
            raise RuntimeError("TimescaleDB not connected")
        return self._pool

    async def health_check(self) -> bool:
        try:
            await self.pool.fetchval("SELECT 1")
            return True
        except Exception:
            return False

    # ── Signal snapshots ─────────────────────────────────────────

    async def insert_signal(self, run_id: uuid.UUID, session: str, snap) -> None:
        await self.pool.execute(
            """
            INSERT INTO signal_snapshots (
                time, run_id, session, instrument, sector,
                price, prev_close, change_pct, day_high, day_low, volume, volume_ratio,
                rsi_14, macd_histogram, bb_position, ema_9, ema_21, atr_14,
                returns_1d, returns_5d, returns_10d,
                news_sentiment, news_count,
                social_sentiment, social_positive_pct, social_negative_pct, social_post_count, social_trending,
                ai_news_sentiment, ai_news_count, ai_news_positive, ai_news_negative,
                fii_net, dii_net, india_vix, india_vix_change, pcr_oi, ad_ratio,
                features, global_signals, sector_signals,
                data_staleness, errors
            ) VALUES (
                NOW(), $1, $2, $3, $4,
                $5, $6, $7, $8, $9, $10, $11,
                $12, $13, $14, $15, $16, $17,
                $18, $19, $20,
                $21, $22,
                $23, $24, $25, $26, $27,
                $28, $29, $30, $31,
                $32, $33, $34, $35, $36, $37,
                $38, $39, $40,
                $41, $42
            )
            """,
            run_id, session, getattr(snap, 'instrument', 'NIFTYBEES'), getattr(snap, 'sector', 'index'),
            getattr(snap, 'price', 0), getattr(snap, 'prev_close', 0), getattr(snap, 'change_pct', 0),
            getattr(snap, 'day_high', 0), getattr(snap, 'day_low', 0),
            getattr(snap, 'volume', 0), getattr(snap, 'volume_ratio', 0),
            getattr(snap, 'rsi_14', 50), getattr(snap, 'macd_histogram', 0), getattr(snap, 'bb_position', 0.5),
            getattr(snap, 'ema_9', 0), getattr(snap, 'ema_21', 0),
            getattr(snap, 'atr_14', 0), getattr(snap, 'returns_1d', 0),
            getattr(snap, 'returns_5d', 0), getattr(snap, 'returns_10d', 0),
            getattr(snap, 'news_sentiment', 0), getattr(snap, 'news_count', 0),
            getattr(snap, 'social_sentiment', 0), getattr(snap, 'social_positive_pct', 0),
            getattr(snap, 'social_negative_pct', 0), getattr(snap, 'social_post_count', 0),
            getattr(snap, 'social_trending', []) or [],
            getattr(snap, 'ai_news_sentiment', 0), getattr(snap, 'ai_news_count', 0),
            getattr(snap, 'ai_news_positive', 0), getattr(snap, 'ai_news_negative', 0),
            getattr(snap, 'fii_net', 0), getattr(snap, 'dii_net', 0),
            getattr(snap, 'india_vix', 0), getattr(snap, 'india_vix_change', 0),
            getattr(snap, 'pcr_oi', 0), getattr(snap, 'ad_ratio', 0),
            json.dumps(snap.to_feature_dict(), default=str),
            json.dumps(getattr(snap, 'global_signals', {}), default=str),
            json.dumps(getattr(snap, 'sector_signals', {}), default=str),
            getattr(snap, 'data_staleness', 'unknown'), getattr(snap, 'errors', []) or [],
        )

    # ── Predictions ──────────────────────────────────────────────

    async def insert_prediction(self, run_id: uuid.UUID, session: str, pred) -> None:
        await self.pool.execute(
            """
            INSERT INTO predictions (
                time, run_id, session, instrument, direction, score, confidence,
                features_used, reasons
            ) VALUES (NOW(), $1, $2, $3, $4, $5, $6, $7, $8)
            """,
            run_id, session, pred.instrument, pred.direction.value,
            pred.score, pred.confidence, pred.features_used,
            pred.reasons,
        )

    # ── Pipeline runs ────────────────────────────────────────────

    async def insert_pipeline_run(
        self, run_id: uuid.UUID, session: str, duration: float,
        instruments: int, status: str = "ok", error: str | None = None,
    ) -> None:
        await self.pool.execute(
            """
            INSERT INTO pipeline_runs (time, run_id, session, duration_sec, instruments, status, error)
            VALUES (NOW(), $1, $2, $3, $4, $5, $6)
            """,
            run_id, session, duration, instruments, status, error,
        )

    # ── Queries ──────────────────────────────────────────────────

    async def get_pipeline_runs(self, limit: int = 50) -> list[dict]:
        rows = await self.pool.fetch(
            "SELECT * FROM pipeline_runs ORDER BY time DESC LIMIT $1", limit,
        )
        return [dict(r) for r in rows]

    async def get_signals_by_run(self, run_id: uuid.UUID) -> list[dict]:
        rows = await self.pool.fetch(
            "SELECT * FROM signal_snapshots WHERE run_id = $1", run_id,
        )
        return [dict(r) for r in rows]

    async def get_predictions_by_run(self, run_id: uuid.UUID) -> list[dict]:
        rows = await self.pool.fetch(
            "SELECT * FROM predictions WHERE run_id = $1", run_id,
        )
        return [dict(r) for r in rows]

    async def get_recent_predictions(self, instrument: str, limit: int = 50) -> list[dict]:
        rows = await self.pool.fetch(
            """
            SELECT time, run_id, direction, score, confidence, reasons,
                   actual_change_1h, actual_change_eod, was_correct
            FROM predictions WHERE instrument = $1
            ORDER BY time DESC LIMIT $2
            """,
            instrument, limit,
        )
        return [dict(r) for r in rows]

    async def get_prediction_accuracy(self, instrument: str) -> dict:
        row = await self.pool.fetchrow(
            """
            SELECT count(*) as total,
                count(*) FILTER (WHERE was_correct = true) as correct,
                count(*) FILTER (WHERE was_correct = false) as wrong,
                count(*) FILTER (WHERE was_correct IS NULL) as pending,
                round(avg(score)::numeric, 4) as avg_score,
                round(avg(confidence)::numeric, 4) as avg_confidence
            FROM predictions WHERE instrument = $1
            """,
            instrument,
        )
        return dict(row) if row else {}
