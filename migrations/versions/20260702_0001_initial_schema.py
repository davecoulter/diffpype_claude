"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-07-02

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE TYPE celery_queue AS ENUM ('light', 'heavy_memory', 'gpu')"
    )
    op.execute(
        "CREATE TYPE job_status AS ENUM ('pending', 'in_process', 'complete', 'failed')"
    )

    op.create_table(
        "step_definitions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("task_name", sa.String(), nullable=False),
        sa.Column(
            "queue",
            postgresql.ENUM(
                "light", "heavy_memory", "gpu",
                name="celery_queue",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "dummy_images",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "pending", "in_process", "complete", "failed",
                name="job_status",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("latest_job_id", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("dummy_images")
    op.drop_table("step_definitions")
    op.execute("DROP TYPE job_status")
    op.execute("DROP TYPE celery_queue")
