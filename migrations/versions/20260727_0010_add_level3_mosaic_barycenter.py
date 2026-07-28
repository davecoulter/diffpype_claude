"""add ra/decl barycenter columns and Q3C index to level3_mosaics

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-27

Addresses GitHub issue #27: Level3Mosaic gains its own ra/decl columns,
computed as the barycenter of its footprint at write time (see
src/services/mosaic_service.py), Q3C-indexed like Tile/Level2Image. Nullable
because a mosaic with zero constituent calibrations has no footprint to
derive a barycenter from yet. The table is empty in every environment (doc 28
is the first thing that ever writes a Level3Mosaic row), so this is a plain
additive migration with no backfill.
"""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("level3_mosaics", sa.Column("ra", sa.Float(), nullable=True))
    op.add_column("level3_mosaics", sa.Column("decl", sa.Float(), nullable=True))
    op.create_index(
        "ix_level3_mosaic_q3c",
        "level3_mosaics",
        [sa.text("q3c_ang2ipix(ra, decl)")],
    )


def downgrade() -> None:
    op.drop_index("ix_level3_mosaic_q3c", table_name="level3_mosaics")
    op.drop_column("level3_mosaics", "decl")
    op.drop_column("level3_mosaics", "ra")
