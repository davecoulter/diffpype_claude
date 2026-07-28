"""add project scoping, base_filename unique, moc multirange footprints

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-27

Scopes Level2Calibration to a Project (so one raw image can have per-project
calibrations), enforces base_filename uniqueness on Level2Image, and replaces the
Text `moc_str` footprint columns on tiles/level2_calibrations/level3_mosaics with
native `int8multirange` columns (see src/db/spatial_types.py, GitHub issue #26).

All four affected tables are empty in every environment (nothing seeds or
populates them yet), so the new NOT NULL `project_id` and the Text->multirange
column swaps are done as plain add/drop with no data backfill or conversion.
"""

import sqlalchemy as sa
from alembic import op

from src.db.spatial_types import MOCType

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- Level2Calibration: scope to Project, swap unique to composite ---
    op.add_column(
        "level2_calibrations",
        sa.Column("project_id", sa.Integer(), nullable=False),
    )
    op.create_foreign_key(
        "level2_calibrations_project_id_fkey",
        "level2_calibrations",
        "projects",
        ["project_id"],
        ["id"],
    )
    op.drop_constraint(
        "level2_calibrations_level2_image_id_key",
        "level2_calibrations",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_level2_calibration_image_project",
        "level2_calibrations",
        ["level2_image_id", "project_id"],
    )

    # --- Level2Image: enforce base_filename uniqueness ---
    op.create_unique_constraint(
        "level2_images_base_filename_key", "level2_images", ["base_filename"]
    )

    # --- moc_str (Text) -> footprint (int8multirange) on all footprint tables ---
    op.add_column(
        "level2_calibrations", sa.Column("footprint", MOCType(), nullable=True)
    )
    op.drop_column("level2_calibrations", "moc_str")
    op.add_column("tiles", sa.Column("footprint", MOCType(), nullable=True))
    op.drop_column("tiles", "moc_str")
    op.add_column("level3_mosaics", sa.Column("footprint", MOCType(), nullable=True))
    op.drop_column("level3_mosaics", "moc_str")

    # --- GiST indexes for native multirange overlap (&&) queries ---
    # Paves the way for the doc-28 ingest/spatial-match tooling; multirange types
    # use the built-in GiST operator class for range overlap.
    op.create_index(
        "ix_tile_footprint_gist", "tiles", ["footprint"], postgresql_using="gist"
    )
    op.create_index(
        "ix_level2_calibration_footprint_gist",
        "level2_calibrations",
        ["footprint"],
        postgresql_using="gist",
    )
    op.create_index(
        "ix_level3_mosaic_footprint_gist",
        "level3_mosaics",
        ["footprint"],
        postgresql_using="gist",
    )


def downgrade() -> None:
    op.drop_index("ix_level3_mosaic_footprint_gist", table_name="level3_mosaics")
    op.drop_index(
        "ix_level2_calibration_footprint_gist", table_name="level2_calibrations"
    )
    op.drop_index("ix_tile_footprint_gist", table_name="tiles")

    # --- footprint (int8multirange) -> moc_str (Text) ---
    op.add_column("level3_mosaics", sa.Column("moc_str", sa.Text(), nullable=True))
    op.drop_column("level3_mosaics", "footprint")
    op.add_column("tiles", sa.Column("moc_str", sa.Text(), nullable=True))
    op.drop_column("tiles", "footprint")
    op.add_column("level2_calibrations", sa.Column("moc_str", sa.Text(), nullable=True))
    op.drop_column("level2_calibrations", "footprint")

    # --- Level2Image: drop base_filename uniqueness ---
    op.drop_constraint(
        "level2_images_base_filename_key", "level2_images", type_="unique"
    )

    # --- Level2Calibration: restore single-column unique, drop Project scoping ---
    op.drop_constraint(
        "uq_level2_calibration_image_project",
        "level2_calibrations",
        type_="unique",
    )
    op.create_unique_constraint(
        "level2_calibrations_level2_image_id_key",
        "level2_calibrations",
        ["level2_image_id"],
    )
    op.drop_constraint(
        "level2_calibrations_project_id_fkey",
        "level2_calibrations",
        type_="foreignkey",
    )
    op.drop_column("level2_calibrations", "project_id")
