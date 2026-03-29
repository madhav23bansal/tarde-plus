"""Add prediction accuracy tracking table.

Revision ID: 003
Revises: 002
Create Date: 2026-03-30
"""

from alembic import op

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Daily accuracy summary per instrument
    op.execute("""
        CREATE TABLE IF NOT EXISTS prediction_accuracy (
            date            DATE NOT NULL,
            instrument      TEXT NOT NULL,
            total           INTEGER DEFAULT 0,
            correct         INTEGER DEFAULT 0,
            wrong           INTEGER DEFAULT 0,
            accuracy        DECIMAL(6,4),
            avg_score       DECIMAL(6,4),
            avg_confidence  DECIMAL(6,4),
            actual_change   DECIMAL(8,4),
            PRIMARY KEY (date, instrument)
        )
    """)

    # Ensure predictions table has the accuracy columns (already exist from migration 001 but
    # let's make sure they're usable)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_predictions_accuracy
        ON predictions (instrument, time DESC)
        WHERE was_correct IS NULL
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS prediction_accuracy CASCADE")
    op.execute("DROP INDEX IF EXISTS idx_predictions_accuracy")
