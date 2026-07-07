"""SQLAlchemy ORM models for Diffpype domain entities and job provenance."""
import sqlalchemy as sa
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from src.db.enums import CeleryQueue, JobStatus


class Base(DeclarativeBase):
    """Declarative base class for all Diffpype ORM models."""

    pass


class StepDefinition(Base):
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


class JobConfiguration(Base):
    """Normalized job provenance: the exact kwargs and shell command for a run."""

    __tablename__ = "job_configurations"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True)
    job_kwargs: Mapped[dict | None] = mapped_column(sa.JSON, nullable=True)
    execution_command: Mapped[str | None] = mapped_column(sa.String, nullable=True)

    dummy_images: Mapped[list["DummyImage"]] = relationship(
        back_populates="job_configuration"
    )


class DummyImage(Base):
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
    job_configuration_id: Mapped[int | None] = mapped_column(
        sa.ForeignKey("job_configurations.id"), nullable=True
    )

    job_configuration: Mapped["JobConfiguration | None"] = relationship(
        back_populates="dummy_images"
    )
