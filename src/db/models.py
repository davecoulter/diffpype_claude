from sqlalchemy import Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class StepDefinition(Base):
    """Maps a pipeline action to its Celery task name and execution queue."""

    __tablename__ = "step_definitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    task_name: Mapped[str] = mapped_column(String, nullable=False)
    queue: Mapped[str] = mapped_column(String, nullable=False, default="light")


class DummyImage(Base):
    """Stage 0 domain entity used only to prove status tracking end-to-end."""

    __tablename__ = "dummy_images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="Pending")
    latest_job_id: Mapped[str | None] = mapped_column(String, nullable=True)
