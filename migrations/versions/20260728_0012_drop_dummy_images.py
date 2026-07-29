"""drop the Stage-0 dummy_images table

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-28

Doc 29 §3 (resolves issue #33). Removes the last Stage-0 walking-skeleton table
now that IngestBatch/Level3Mosaic are the real async-status-tracking pattern.
The downgrade recreates the table at its final pre-removal shape (job_status
enum reused via create_type=False, since other tables still define it).
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("dummy_images")


def downgrade() -> None:
    op.create_table(
        "dummy_images",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(name="job_status", create_type=False),
            nullable=False,
        ),
        sa.Column("latest_job_id", sa.String(), nullable=True),
        sa.Column("job_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("job_finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("job_configuration_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["job_configuration_id"],
            ["job_configurations.id"],
        ),
    )
