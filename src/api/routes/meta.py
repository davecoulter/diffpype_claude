from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.api.schemas import StatusMetadata
from src.db.session import get_db

router = APIRouter(prefix="/meta", tags=["meta"])

_STATUS_COLORS: dict[str, str] = {
    "pending": "#9e9e9e",
    "in_process": "#e0a800",
    "complete": "#2e7d32",
    "failed": "#c62828",
}


@router.get("/statuses", response_model=list[StatusMetadata])
def get_statuses(db: Session = Depends(get_db)) -> list[StatusMetadata]:
    """Return all job_status enum values with display labels and traffic-light colors.

    Values are read directly from the live Postgres enum type so that any future
    migration adding a new status is automatically reflected in the UI without a
    frontend deploy.
    """
    rows = db.execute(
        text("SELECT unnest(enum_range(NULL::job_status))::text AS value")
    ).fetchall()
    return [
        StatusMetadata(
            value=row.value,
            label=row.value.replace("_", " ").title(),
            color=_STATUS_COLORS.get(row.value, "#9e9e9e"),
        )
        for row in rows
    ]
