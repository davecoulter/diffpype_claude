"""add job_configurations table and link dummy_images

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-06

Normalizes job provenance: introduces the job_configurations table (job_kwargs +
execution_command) and replaces the DummyImage.job_kwargs shortcut with a
job_configuration_id foreign key.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FK_NAME = "fk_dummy_images_job_configuration_id"


def upgrade() -> None:
    op.create_table(
        "job_configurations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_kwargs", sa.JSON(), nullable=True),
        sa.Column("execution_command", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.add_column(
        "dummy_images",
        sa.Column("job_configuration_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        FK_NAME,
        "dummy_images",
        "job_configurations",
        ["job_configuration_id"],
        ["id"],
    )
    op.drop_column("dummy_images", "job_kwargs")


def downgrade() -> None:
    op.add_column(
        "dummy_images",
        sa.Column("job_kwargs", sa.JSON(), nullable=True),
    )
    op.drop_constraint(FK_NAME, "dummy_images", type_="foreignkey")
    op.drop_column("dummy_images", "job_configuration_id")
    op.drop_table("job_configurations")
