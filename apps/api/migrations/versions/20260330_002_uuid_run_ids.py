"""Replace integer cycle IDs with UUIDs (run_id).

Revision ID: 002
Revises: 001
Create Date: 2026-03-30
"""

from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    # ── signal_snapshots: cycle INTEGER → run_id UUID ─────────
    op.execute("ALTER TABLE signal_snapshots ADD COLUMN IF NOT EXISTS run_id UUID")
    op.execute("UPDATE signal_snapshots SET run_id = uuid_generate_v4() WHERE run_id IS NULL")
    op.execute("ALTER TABLE signal_snapshots ALTER COLUMN run_id SET NOT NULL")
    op.execute("ALTER TABLE signal_snapshots ALTER COLUMN run_id SET DEFAULT uuid_generate_v4()")
    op.execute("DROP INDEX IF EXISTS idx_signals_cycle")
    op.execute("CREATE INDEX IF NOT EXISTS idx_signals_run_id ON signal_snapshots (run_id)")
    op.execute("ALTER TABLE signal_snapshots DROP COLUMN IF EXISTS cycle")

    # ── predictions: cycle INTEGER → run_id UUID ──────────────
    op.execute("ALTER TABLE predictions ADD COLUMN IF NOT EXISTS run_id UUID")
    op.execute("UPDATE predictions SET run_id = uuid_generate_v4() WHERE run_id IS NULL")
    op.execute("ALTER TABLE predictions ALTER COLUMN run_id SET NOT NULL")
    op.execute("ALTER TABLE predictions ALTER COLUMN run_id SET DEFAULT uuid_generate_v4()")
    op.execute("DROP INDEX IF EXISTS idx_predictions_cycle")
    op.execute("CREATE INDEX IF NOT EXISTS idx_predictions_run_id ON predictions (run_id)")
    op.execute("ALTER TABLE predictions DROP COLUMN IF EXISTS cycle")

    # ── pipeline_runs: cycle INTEGER → run_id UUID (PK-like) ──
    op.execute("ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS run_id UUID")
    op.execute("UPDATE pipeline_runs SET run_id = uuid_generate_v4() WHERE run_id IS NULL")
    op.execute("ALTER TABLE pipeline_runs ALTER COLUMN run_id SET NOT NULL")
    op.execute("ALTER TABLE pipeline_runs ALTER COLUMN run_id SET DEFAULT uuid_generate_v4()")
    op.execute("CREATE INDEX IF NOT EXISTS idx_pipeline_runs_run_id ON pipeline_runs (run_id)")
    op.execute("ALTER TABLE pipeline_runs DROP COLUMN IF EXISTS cycle")


def downgrade() -> None:
    for table in ("signal_snapshots", "predictions", "pipeline_runs"):
        op.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS cycle INTEGER DEFAULT 0")
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS run_id")
