import sqlalchemy as sa
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from src.db.enums import CeleryQueue, JobStatus

class Base(DeclarativeBase):
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
