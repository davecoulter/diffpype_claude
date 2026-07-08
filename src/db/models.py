"""SQLAlchemy ORM models for Diffpype domain entities and job provenance."""
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from src.db.enums import CeleryQueue, JobStatus


class Base(DeclarativeBase):
    """Declarative base class for all Diffpype ORM models."""

    pass


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
    step_definitions: Mapped[list["StepDefinition"]] = relationship(back_populates="user")
    job_configurations: Mapped[list["JobConfiguration"]] = relationship(back_populates="user")


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
