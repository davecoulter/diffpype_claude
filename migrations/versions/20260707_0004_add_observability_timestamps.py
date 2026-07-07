"""add observability timestamps to dummy_images and job_configurations

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-07

Adds row-level provenance (created_at, updated_at) to both dummy_images and
job_configurations via the TimestampMixin, plus explicit job-timing columns
(job_started_at, job_finished_at) on dummy_images. The created_at/updated_at
columns carry a ``now()`` server default so existing rows are backfilled and the
NOT NULL constraints hold.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for table in ("dummy_images", "job_configurations"):
        op.add_column(
            table,
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
        )
        op.add_column(
            table,
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
        )

    op.add_column(
        "dummy_images",
        sa.Column("job_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "dummy_images",
        sa.Column("job_finished_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("dummy_images", "job_finished_at")
    op.drop_column("dummy_images", "job_started_at")
    for table in ("dummy_images", "job_configurations"):
        op.drop_column(table, "updated_at")
        op.drop_column(table, "created_at")
