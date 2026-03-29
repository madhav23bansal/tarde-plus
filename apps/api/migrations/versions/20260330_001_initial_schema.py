"""Initial schema — ticks, signals, predictions, pipeline runs.

Revision ID: 001
Revises:
Create Date: 2026-03-30
"""

from alembic import op

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # TimescaleDB extension
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE")

    # ── Raw tick data ────────────────────────────────────────────

    op.execute("""
        CREATE TABLE IF NOT EXISTS ticks (
            time        TIMESTAMPTZ NOT NULL,
            instrument  TEXT NOT NULL,
            ltp         DECIMAL(12,2) NOT NULL,
            bid         DECIMAL(12,2),
            ask         DECIMAL(12,2),
            volume      BIGINT,
            oi          BIGINT,
            exchange    TEXT NOT NULL DEFAULT 'NSE'
        )
    """)
    op.execute("SELECT create_hypertable('ticks', 'time', chunk_time_interval => INTERVAL '1 day', if_not_exists => TRUE)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_ticks_instrument_time ON ticks (instrument, time DESC)")

    # Compression
    op.execute("""
        ALTER TABLE ticks SET (
            timescaledb.compress,
            timescaledb.compress_segmentby = 'instrument',
            timescaledb.compress_orderby = 'time DESC'
        )
    """)
    op.execute("SELECT add_compression_policy('ticks', INTERVAL '3 days', if_not_exists => TRUE)")

    # OHLCV 1-minute
    op.execute("""
        CREATE MATERIALIZED VIEW IF NOT EXISTS ohlcv_1m
        WITH (timescaledb.continuous) AS
        SELECT
            time_bucket('1 minute', time) AS bucket,
            instrument,
            FIRST(ltp, time) AS open,
            MAX(ltp) AS high,
            MIN(ltp) AS low,
            LAST(ltp, time) AS close,
            SUM(volume) AS volume
        FROM ticks
        GROUP BY bucket, instrument
        WITH NO DATA
    """)
    op.execute("""
        SELECT add_continuous_aggregate_policy('ohlcv_1m',
            start_offset => INTERVAL '1 hour',
            end_offset => INTERVAL '1 minute',
            schedule_interval => INTERVAL '1 minute',
            if_not_exists => TRUE
        )
    """)

    # OHLCV 5-minute
    op.execute("""
        CREATE MATERIALIZED VIEW IF NOT EXISTS ohlcv_5m
        WITH (timescaledb.continuous) AS
        SELECT
            time_bucket('5 minutes', time) AS bucket,
            instrument,
            FIRST(ltp, time) AS open,
            MAX(ltp) AS high,
            MIN(ltp) AS low,
            LAST(ltp, time) AS close,
            SUM(volume) AS volume
        FROM ticks
        GROUP BY bucket, instrument
        WITH NO DATA
    """)
    op.execute("""
        SELECT add_continuous_aggregate_policy('ohlcv_5m',
            start_offset => INTERVAL '2 hours',
            end_offset => INTERVAL '5 minutes',
            schedule_interval => INTERVAL '5 minutes',
            if_not_exists => TRUE
        )
    """)

    op.execute("SELECT add_retention_policy('ticks', INTERVAL '30 days', if_not_exists => TRUE)")

    # ── Signal snapshots ─────────────────────────────────────────

    op.execute("""
        CREATE TABLE IF NOT EXISTS signal_snapshots (
            time            TIMESTAMPTZ NOT NULL,
            cycle           INTEGER NOT NULL,
            session         TEXT NOT NULL,
            instrument      TEXT NOT NULL,
            sector          TEXT NOT NULL,
            price           DECIMAL(12,2),
            prev_close      DECIMAL(12,2),
            change_pct      DECIMAL(8,4),
            day_high        DECIMAL(12,2),
            day_low         DECIMAL(12,2),
            volume          BIGINT,
            volume_ratio    DECIMAL(8,4),
            rsi_14          DECIMAL(8,4),
            macd_histogram  DECIMAL(12,4),
            bb_position     DECIMAL(8,4),
            ema_9           DECIMAL(12,2),
            ema_21          DECIMAL(12,2),
            atr_14          DECIMAL(12,4),
            returns_1d      DECIMAL(8,4),
            returns_5d      DECIMAL(8,4),
            returns_10d     DECIMAL(8,4),
            news_sentiment  DECIMAL(8,4),
            news_count      INTEGER,
            fii_net         DECIMAL(12,2),
            dii_net         DECIMAL(12,2),
            india_vix       DECIMAL(8,2),
            india_vix_change DECIMAL(8,4),
            pcr_oi          DECIMAL(8,4),
            ad_ratio        DECIMAL(8,4),
            features        JSONB,
            global_signals  JSONB,
            sector_signals  JSONB,
            data_staleness  TEXT,
            errors          TEXT[]
        )
    """)
    op.execute("SELECT create_hypertable('signal_snapshots', 'time', chunk_time_interval => INTERVAL '7 days', if_not_exists => TRUE)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_signals_instrument ON signal_snapshots (instrument, time DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_signals_cycle ON signal_snapshots (cycle)")

    # ── Predictions ──────────────────────────────────────────────

    op.execute("""
        CREATE TABLE IF NOT EXISTS predictions (
            time            TIMESTAMPTZ NOT NULL,
            cycle           INTEGER NOT NULL,
            session         TEXT NOT NULL,
            instrument      TEXT NOT NULL,
            direction       TEXT NOT NULL,
            score           DECIMAL(8,4) NOT NULL,
            confidence      DECIMAL(8,4) NOT NULL,
            features_used   INTEGER,
            reasons         TEXT[],
            actual_change_1h  DECIMAL(8,4),
            actual_change_eod DECIMAL(8,4),
            was_correct       BOOLEAN
        )
    """)
    op.execute("SELECT create_hypertable('predictions', 'time', chunk_time_interval => INTERVAL '7 days', if_not_exists => TRUE)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_predictions_instrument ON predictions (instrument, time DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_predictions_cycle ON predictions (cycle)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_predictions_direction ON predictions (direction, time DESC)")

    # ── Pipeline runs ────────────────────────────────────────────

    op.execute("""
        CREATE TABLE IF NOT EXISTS pipeline_runs (
            time            TIMESTAMPTZ NOT NULL,
            cycle           INTEGER NOT NULL,
            session         TEXT NOT NULL,
            duration_sec    DECIMAL(8,2),
            instruments     INTEGER,
            status          TEXT NOT NULL DEFAULT 'ok',
            error           TEXT
        )
    """)
    op.execute("SELECT create_hypertable('pipeline_runs', 'time', chunk_time_interval => INTERVAL '30 days', if_not_exists => TRUE)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS pipeline_runs CASCADE")
    op.execute("DROP TABLE IF EXISTS predictions CASCADE")
    op.execute("DROP TABLE IF EXISTS signal_snapshots CASCADE")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS ohlcv_5m CASCADE")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS ohlcv_1m CASCADE")
    op.execute("DROP TABLE IF EXISTS ticks CASCADE")
