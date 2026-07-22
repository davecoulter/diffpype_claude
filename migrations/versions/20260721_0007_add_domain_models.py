"""add domain models: reference data, tiles/epochs, level2/level3 products

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-21
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def _timestamp_columns() -> list:
    """Server-managed created_at/updated_at columns matching TimestampMixin."""
    return [
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
    ]


def _job_status_enum() -> postgresql.ENUM:
    """Reference the job_status enum type created in migration 0001 (never re-create it)."""
    return postgresql.ENUM(
        "pending",
        "in_process",
        "complete",
        "failed",
        name="job_status",
        create_type=False,
    )


def upgrade() -> None:
    # --- §1 Reference data ---
    op.create_table(
        "instruments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        *_timestamp_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "bands",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("central_lambda", sa.Float(), nullable=False),
        *_timestamp_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    # --- §2 Organizational framework & spatial footprints ---
    op.create_table(
        "tiles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("ra", sa.Float(), nullable=False),
        sa.Column("decl", sa.Float(), nullable=False),
        sa.Column("delta_ra", sa.Float(), nullable=False),
        sa.Column("delta_decl", sa.Float(), nullable=False),
        sa.Column("moc_str", sa.Text(), nullable=True),
        sa.Column("healpix_index", sa.Integer(), nullable=True),
        sa.Column("coord_sys", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        *_timestamp_columns(),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "epochs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("start_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("start_mjd", sa.Float(), nullable=True),
        sa.Column("end_mjd", sa.Float(), nullable=True),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("tile_id", sa.Integer(), nullable=False),
        sa.Column("band_id", sa.Integer(), nullable=False),
        *_timestamp_columns(),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["tile_id"], ["tiles.id"]),
        sa.ForeignKeyConstraint(["band_id"], ["bands.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # --- §3 Data products & many-to-many associations ---
    op.create_table(
        "level2_images",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("base_filename", sa.String(), nullable=False),
        sa.Column("ra", sa.Float(), nullable=False),
        sa.Column("decl", sa.Float(), nullable=False),
        sa.Column("exp_time", sa.Float(), nullable=False),
        sa.Column("mjd_avg", sa.Float(), nullable=True),
        sa.Column("target_name", sa.String(), nullable=False),
        sa.Column("obs_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("instrument_id", sa.Integer(), nullable=False),
        sa.Column("band_id", sa.Integer(), nullable=False),
        *_timestamp_columns(),
        sa.ForeignKeyConstraint(["instrument_id"], ["instruments.id"]),
        sa.ForeignKeyConstraint(["band_id"], ["bands.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "level2_calibrations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("level2_image_id", sa.Integer(), nullable=False),
        sa.Column("moc_str", sa.Text(), nullable=True),
        sa.Column("current_file_ext", sa.String(), nullable=False),
        sa.Column("plate_scale", sa.Float(), nullable=False),
        sa.Column("status", _job_status_enum(), nullable=False),
        *_timestamp_columns(),
        sa.ForeignKeyConstraint(["level2_image_id"], ["level2_images.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("level2_image_id"),
    )
    op.create_table(
        "level3_mosaics",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("target_plate_scale", sa.Float(), nullable=False),
        sa.Column("moc_str", sa.Text(), nullable=True),
        sa.Column("instrument_id", sa.Integer(), nullable=False),
        sa.Column("band_id", sa.Integer(), nullable=False),
        sa.Column("epoch_id", sa.Integer(), nullable=False),
        sa.Column("tile_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("job_configuration_id", sa.Integer(), nullable=True),
        sa.Column("status", _job_status_enum(), nullable=False),
        *_timestamp_columns(),
        sa.ForeignKeyConstraint(["instrument_id"], ["instruments.id"]),
        sa.ForeignKeyConstraint(["band_id"], ["bands.id"]),
        sa.ForeignKeyConstraint(["epoch_id"], ["epochs.id"]),
        sa.ForeignKeyConstraint(["tile_id"], ["tiles.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["job_configuration_id"], ["job_configurations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "instrument_id",
            "tile_id",
            "epoch_id",
            "band_id",
            "project_id",
            name="uq_level3_mosaic_identity",
        ),
    )
    op.create_table(
        "tile_level2_calibration_association",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tile_id", sa.Integer(), nullable=False),
        sa.Column("level2_calibration_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["tile_id"], ["tiles.id"]),
        sa.ForeignKeyConstraint(["level2_calibration_id"], ["level2_calibrations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tile_id", "level2_calibration_id", name="uq_tile_level2_calibration"
        ),
    )
    op.create_table(
        "epoch_level2_calibration_association",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("epoch_id", sa.Integer(), nullable=False),
        sa.Column("level2_calibration_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["epoch_id"], ["epochs.id"]),
        sa.ForeignKeyConstraint(["level2_calibration_id"], ["level2_calibrations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "epoch_id", "level2_calibration_id", name="uq_epoch_level2_calibration"
        ),
    )

    # --- Q3C spatial indexes ---
    # Enabling the extension itself has no ORM equivalent — it ships only in the
    # project's custom db image (docker/db.Dockerfile) and must be created before
    # either functional index below. The indexes themselves are declared for real
    # on Tile/Level2Image (see __table_args__), matching what's created here.
    op.execute("CREATE EXTENSION IF NOT EXISTS q3c")
    op.create_index("ix_tile_q3c", "tiles", [sa.text("q3c_ang2ipix(ra, decl)")])
    op.create_index(
        "ix_level2_image_q3c", "level2_images", [sa.text("q3c_ang2ipix(ra, decl)")]
    )


def downgrade() -> None:
    # Drop only the indexes, not the extension — other objects may depend on it.
    op.drop_index("ix_level2_image_q3c", table_name="level2_images")
    op.drop_index("ix_tile_q3c", table_name="tiles")
    op.drop_table("epoch_level2_calibration_association")
    op.drop_table("tile_level2_calibration_association")
    op.drop_table("level3_mosaics")
    op.drop_table("level2_calibrations")
    op.drop_table("level2_images")
    op.drop_table("epochs")
    op.drop_table("tiles")
    op.drop_table("bands")
    op.drop_table("instruments")
