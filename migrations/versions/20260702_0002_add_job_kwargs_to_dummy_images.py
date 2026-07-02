"""add job_kwargs to dummy_images

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-02

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "dummy_images",
        sa.Column("job_kwargs", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("dummy_images", "job_kwargs")
