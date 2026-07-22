"""SQLAlchemy ORM models for Diffpype domain entities and job provenance."""

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from src.db.enums import CeleryQueue, JobStatus


# Declared explicitly (rather than relying on DeclarativeBase's implicit default)
# so module-level Table objects can reference a real MetaData instance even
# under Sphinx's mocked `sqlalchemy` import, where DeclarativeBase's own
# metaclass machinery never runs and `Base.metadata` would otherwise not exist.
_metadata = sa.MetaData()


class Base(DeclarativeBase):
    """Declarative base class for all Diffpype ORM models."""

    metadata = _metadata


class TimestampMixin:
    """Mixin adding server-managed created_at and updated_at provenance columns."""

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
        nullable=False,
    )


class User(TimestampMixin, Base):
    """Authenticated principal who owns Projects, StepDefinitions, and JobConfigurations."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True)
    username: Mapped[str] = mapped_column(sa.String, unique=True, nullable=False)
    email: Mapped[str] = mapped_column(sa.String, unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(sa.String, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.text("true")
    )

    projects: Mapped[list["Project"]] = relationship(back_populates="user")
    step_definitions: Mapped[list["StepDefinition"]] = relationship(
        back_populates="user"
    )
    job_configurations: Mapped[list["JobConfiguration"]] = relationship(
        back_populates="user"
    )


class Project(TimestampMixin, Base):
    """Logical grouping of related pipeline runs under a single User."""

    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True)
    name: Mapped[str] = mapped_column(sa.String, nullable=False)
    description: Mapped[str | None] = mapped_column(sa.String, nullable=True)
    user_id: Mapped[int] = mapped_column(sa.ForeignKey("users.id"), nullable=False)

    user: Mapped["User"] = relationship(back_populates="projects")


class StepDefinition(TimestampMixin, Base):
    """Maps a pipeline action to its Celery task name and execution queue."""

    __tablename__ = "step_definitions"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True)
    name: Mapped[str] = mapped_column(sa.String, unique=True, nullable=False)
    task_name: Mapped[str] = mapped_column(sa.String, nullable=False)
    queue: Mapped[CeleryQueue] = mapped_column(
        sa.Enum(
            CeleryQueue,
            name="celery_queue",
            create_type=False,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=CeleryQueue.LIGHT,
    )
    user_id: Mapped[int] = mapped_column(sa.ForeignKey("users.id"), nullable=False)

    user: Mapped["User"] = relationship(back_populates="step_definitions")


class JobConfiguration(TimestampMixin, Base):
    """Normalized job provenance: the exact kwargs and shell command for a run."""

    __tablename__ = "job_configurations"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True)
    job_kwargs: Mapped[dict | None] = mapped_column(sa.JSON, nullable=True)
    execution_command: Mapped[str | None] = mapped_column(sa.String, nullable=True)
    user_id: Mapped[int] = mapped_column(sa.ForeignKey("users.id"), nullable=False)

    user: Mapped["User"] = relationship(back_populates="job_configurations")
    dummy_images: Mapped[list["DummyImage"]] = relationship(
        back_populates="job_configuration"
    )


class DummyImage(TimestampMixin, Base):
    """Stage 0 domain entity used only to prove status tracking end-to-end."""

    __tablename__ = "dummy_images"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True)
    status: Mapped[JobStatus] = mapped_column(
        sa.Enum(
            JobStatus,
            name="job_status",
            create_type=False,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=JobStatus.PENDING,
    )
    latest_job_id: Mapped[str | None] = mapped_column(sa.String, nullable=True)
    job_started_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    job_finished_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    job_configuration_id: Mapped[int | None] = mapped_column(
        sa.ForeignKey("job_configurations.id"), nullable=True
    )

    job_configuration: Mapped["JobConfiguration | None"] = relationship(
        back_populates="dummy_images"
    )


class Instrument(TimestampMixin, Base):
    """Table-driven reference entry for an observing instrument (e.g. NIRCam, MIRI)."""

    __tablename__ = "instruments"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True)
    name: Mapped[str] = mapped_column(sa.String, unique=True, nullable=False)


class Band(TimestampMixin, Base):
    """Table-driven reference entry for a photometric filter/band and its central wavelength (microns)."""

    __tablename__ = "bands"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True)
    name: Mapped[str] = mapped_column(sa.String, unique=True, nullable=False)
    central_lambda: Mapped[float] = mapped_column(sa.Float, nullable=False)


# Association tables linking derived Level 2 calibrations to their spatial Tiles
# and temporal Epochs. Each has its own surrogate id (consistent with every
# other table in this schema) plus a UniqueConstraint on the FK pair, so a
# duplicate association attempt raises an IntegrityError at the database level.
tile_level2_calibration_association = sa.Table(
    "tile_level2_calibration_association",
    _metadata,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("tile_id", sa.ForeignKey("tiles.id"), nullable=False),
    sa.Column(
        "level2_calibration_id",
        sa.ForeignKey("level2_calibrations.id"),
        nullable=False,
    ),
    sa.UniqueConstraint(
        "tile_id", "level2_calibration_id", name="uq_tile_level2_calibration"
    ),
)

epoch_level2_calibration_association = sa.Table(
    "epoch_level2_calibration_association",
    _metadata,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("epoch_id", sa.ForeignKey("epochs.id"), nullable=False),
    sa.Column(
        "level2_calibration_id",
        sa.ForeignKey("level2_calibrations.id"),
        nullable=False,
    ),
    sa.UniqueConstraint(
        "epoch_id", "level2_calibration_id", name="uq_epoch_level2_calibration"
    ),
)


class Tile(TimestampMixin, Base):
    """User-defined sky square (tangent plane) that calibrated Level 2 images are associated with spatially."""

    __tablename__ = "tiles"
    __table_args__ = (sa.Index("ix_tile_q3c", sa.text("q3c_ang2ipix(ra, decl)")),)

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True)
    name: Mapped[str] = mapped_column(sa.String, nullable=False)
    ra: Mapped[float] = mapped_column(sa.Float, nullable=False)
    decl: Mapped[float] = mapped_column(sa.Float, nullable=False)
    delta_ra: Mapped[float] = mapped_column(sa.Float, nullable=False)
    delta_decl: Mapped[float] = mapped_column(sa.Float, nullable=False)
    moc_str: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    healpix_index: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    coord_sys: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=2000)
    project_id: Mapped[int] = mapped_column(
        sa.ForeignKey("projects.id"), nullable=False
    )

    project: Mapped["Project"] = relationship()
    level2_calibrations: Mapped[list["Level2Calibration"]] = relationship(
        secondary=tile_level2_calibration_association, back_populates="tiles"
    )


class Epoch(TimestampMixin, Base):
    """Temporal grouping (MJD range) of observations for a given Tile and Band."""

    __tablename__ = "epochs"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True)
    start_date: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False
    )
    end_date: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False
    )
    start_mjd: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    end_mjd: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    project_id: Mapped[int] = mapped_column(
        sa.ForeignKey("projects.id"), nullable=False
    )
    tile_id: Mapped[int] = mapped_column(sa.ForeignKey("tiles.id"), nullable=False)
    band_id: Mapped[int] = mapped_column(sa.ForeignKey("bands.id"), nullable=False)

    project: Mapped["Project"] = relationship()
    tile: Mapped["Tile"] = relationship()
    band: Mapped["Band"] = relationship()
    level2_calibrations: Mapped[list["Level2Calibration"]] = relationship(
        secondary=epoch_level2_calibration_association, back_populates="epochs"
    )


class Level2Image(TimestampMixin, Base):
    """Immutable record of a raw, MAST-provided Level 2 FITS image and its intrinsic metadata."""

    __tablename__ = "level2_images"
    __table_args__ = (
        sa.Index("ix_level2_image_q3c", sa.text("q3c_ang2ipix(ra, decl)")),
    )

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True)
    base_filename: Mapped[str] = mapped_column(sa.String, nullable=False)
    ra: Mapped[float] = mapped_column(sa.Float, nullable=False)
    decl: Mapped[float] = mapped_column(sa.Float, nullable=False)
    exp_time: Mapped[float] = mapped_column(sa.Float, nullable=False)
    mjd_avg: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    target_name: Mapped[str] = mapped_column(sa.String, nullable=False)
    obs_start: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False
    )
    instrument_id: Mapped[int] = mapped_column(
        sa.ForeignKey("instruments.id"), nullable=False
    )
    band_id: Mapped[int] = mapped_column(sa.ForeignKey("bands.id"), nullable=False)

    instrument: Mapped["Instrument"] = relationship()
    band: Mapped["Band"] = relationship()
    calibration: Mapped["Level2Calibration | None"] = relationship(
        back_populates="level2_image", uselist=False
    )


class Level2Calibration(TimestampMixin, Base):
    """Our application's derived, processed reference to a Level2Image, carrying its footprint and pipeline status."""

    __tablename__ = "level2_calibrations"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True)
    level2_image_id: Mapped[int] = mapped_column(
        sa.ForeignKey("level2_images.id"), unique=True, nullable=False
    )
    moc_str: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    current_file_ext: Mapped[str] = mapped_column(sa.String, nullable=False)
    plate_scale: Mapped[float] = mapped_column(sa.Float, nullable=False)
    status: Mapped[JobStatus] = mapped_column(
        sa.Enum(
            JobStatus,
            name="job_status",
            create_type=False,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=JobStatus.PENDING,
    )

    level2_image: Mapped["Level2Image"] = relationship(back_populates="calibration")
    tiles: Mapped[list["Tile"]] = relationship(
        secondary=tile_level2_calibration_association,
        back_populates="level2_calibrations",
    )
    epochs: Mapped[list["Epoch"]] = relationship(
        secondary=epoch_level2_calibration_association,
        back_populates="level2_calibrations",
    )


class Level3Mosaic(TimestampMixin, Base):
    """A Level 3 mosaic product: the unique combination of Tile, Epoch, Band, Instrument, and Project to be drizzled."""

    __tablename__ = "level3_mosaics"
    __table_args__ = (
        sa.UniqueConstraint(
            "instrument_id",
            "tile_id",
            "epoch_id",
            "band_id",
            "project_id",
            name="uq_level3_mosaic_identity",
        ),
    )

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True)
    filename: Mapped[str] = mapped_column(sa.String, nullable=False)
    target_plate_scale: Mapped[float] = mapped_column(sa.Float, nullable=False)
    moc_str: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    instrument_id: Mapped[int] = mapped_column(
        sa.ForeignKey("instruments.id"), nullable=False
    )
    band_id: Mapped[int] = mapped_column(sa.ForeignKey("bands.id"), nullable=False)
    epoch_id: Mapped[int] = mapped_column(sa.ForeignKey("epochs.id"), nullable=False)
    tile_id: Mapped[int] = mapped_column(sa.ForeignKey("tiles.id"), nullable=False)
    project_id: Mapped[int] = mapped_column(
        sa.ForeignKey("projects.id"), nullable=False
    )
    job_configuration_id: Mapped[int | None] = mapped_column(
        sa.ForeignKey("job_configurations.id"), nullable=True
    )
    status: Mapped[JobStatus] = mapped_column(
        sa.Enum(
            JobStatus,
            name="job_status",
            create_type=False,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=JobStatus.PENDING,
    )

    instrument: Mapped["Instrument"] = relationship()
    band: Mapped["Band"] = relationship()
    epoch: Mapped["Epoch"] = relationship()
    tile: Mapped["Tile"] = relationship()
    project: Mapped["Project"] = relationship()
    job_configuration: Mapped["JobConfiguration | None"] = relationship()
