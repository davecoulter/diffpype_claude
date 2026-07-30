"""add JobConfiguration.task_name provenance column

Revision ID: 0013
Revises: 0012
Create Date: 2026-07-29

Doc 30 §3. Records which Celery task (or CLI tool) a JobConfiguration row's
kwargs/command correspond to, e.g. "src.worker.tasks.run_ingest_batch". Nullable,
so existing provenance rows need no backfill.
"""

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "job_configurations",
        sa.Column("task_name", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("job_configurations", "task_name")
