"""Business logic for creating Projects, shared by the API and CLI boundaries."""

from slugify import slugify
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.db.models import Project


def create_project(
    db: Session, name: str, description: str | None, user_id: int
) -> Project:
    """Create a Project with a name-derived slug, raising ValueError if the slug already exists."""
    slug = slugify(name)
    project = Project(name=name, slug=slug, description=description, user_id=user_id)
    db.add(project)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ValueError(f"A project with slug '{slug}' already exists") from None
    db.refresh(project)
    return project
