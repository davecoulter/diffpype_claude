from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.api.schemas import ProjectCreate, ProjectRead
from src.db.session import get_db
from src.services import project_service

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectRead)
def create_project(body: ProjectCreate, db: Session = Depends(get_db)) -> ProjectRead:
    try:
        project = project_service.create_project(
            db, body.name, body.description, body.user_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ProjectRead.model_validate(project)
