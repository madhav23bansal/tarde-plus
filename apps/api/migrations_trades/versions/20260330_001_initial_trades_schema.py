"""Initial trades schema — orders, trades, positions, daily P&L.

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
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    op.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            strategy_id     TEXT NOT NULL,
            instrument      TEXT NOT NULL,
            exchange        TEXT NOT NULL DEFAULT 'NSE',
            side            TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
            order_type      TEXT NOT NULL CHECK (order_type IN ('MARKET', 'LIMIT', 'SL', 'SL-M')),
            quantity        INTEGER NOT NULL,
            price           DECIMAL(12,2),
            trigger_price   DECIMAL(12,2),
            status          TEXT NOT NULL DEFAULT 'PENDING',
            broker_order_id TEXT,
            broker          TEXT NOT NULL DEFAULT 'mock',
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            filled_qty      INTEGER DEFAULT 0,
            avg_fill_price  DECIMAL(12,2),
            metadata        JSONB DEFAULT '{}'
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON orders (status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_orders_strategy ON orders (strategy_id, created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_orders_instrument ON orders (instrument, created_at DESC)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            order_id        UUID REFERENCES orders(id),
            instrument      TEXT NOT NULL,
            exchange        TEXT NOT NULL DEFAULT 'NSE',
            side            TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
            quantity        INTEGER NOT NULL,
            price           DECIMAL(12,2) NOT NULL,
            fees            DECIMAL(12,2) DEFAULT 0,
            executed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            metadata        JSONB DEFAULT '{}'
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_trades_order ON trades (order_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_trades_instrument ON trades (instrument, executed_at DESC)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS positions (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            strategy_id     TEXT NOT NULL,
            instrument      TEXT NOT NULL,
            exchange        TEXT NOT NULL DEFAULT 'NSE',
            quantity        INTEGER NOT NULL,
            avg_price       DECIMAL(12,2) NOT NULL,
            realized_pnl    DECIMAL(12,2) DEFAULT 0,
            unrealized_pnl  DECIMAL(12,2) DEFAULT 0,
            recorded_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_positions_strategy ON positions (strategy_id, recorded_at DESC)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS strategy_configs (
            id              TEXT PRIMARY KEY,
            name            TEXT NOT NULL,
            class_name      TEXT NOT NULL,
            parameters      JSONB NOT NULL DEFAULT '{}',
            enabled         BOOLEAN DEFAULT true,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS daily_pnl (
            date            DATE NOT NULL,
            strategy_id     TEXT NOT NULL,
            realized_pnl    DECIMAL(12,2) NOT NULL DEFAULT 0,
            fees_total      DECIMAL(12,2) NOT NULL DEFAULT 0,
            trades_count    INTEGER NOT NULL DEFAULT 0,
            win_count       INTEGER NOT NULL DEFAULT 0,
            loss_count      INTEGER NOT NULL DEFAULT 0,
            max_drawdown    DECIMAL(12,2) DEFAULT 0,
            PRIMARY KEY (date, strategy_id)
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS daily_pnl CASCADE")
    op.execute("DROP TABLE IF EXISTS strategy_configs CASCADE")
    op.execute("DROP TABLE IF EXISTS positions CASCADE")
    op.execute("DROP TABLE IF EXISTS trades CASCADE")
    op.execute("DROP TABLE IF EXISTS orders CASCADE")
