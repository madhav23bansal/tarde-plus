"""Add AI sentiment columns to signal_snapshots.

Revision ID: 004
Revises: 003
Create Date: 2026-03-30
"""

from alembic import op

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for col, typ in [
        ("social_sentiment", "DECIMAL(8,4)"),
        ("social_positive_pct", "DECIMAL(8,4)"),
        ("social_negative_pct", "DECIMAL(8,4)"),
        ("social_post_count", "INTEGER"),
        ("social_trending", "TEXT[]"),
        ("ai_news_sentiment", "DECIMAL(8,4)"),
        ("ai_news_count", "INTEGER"),
        ("ai_news_positive", "INTEGER"),
        ("ai_news_negative", "INTEGER"),
    ]:
        op.execute(f"ALTER TABLE signal_snapshots ADD COLUMN IF NOT EXISTS {col} {typ}")


def downgrade() -> None:
    for col in [
        "social_sentiment", "social_positive_pct", "social_negative_pct",
        "social_post_count", "social_trending",
        "ai_news_sentiment", "ai_news_count", "ai_news_positive", "ai_news_negative",
    ]:
        op.execute(f"ALTER TABLE signal_snapshots DROP COLUMN IF EXISTS {col}")
