import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from structlog.contextvars import bind_contextvars, clear_contextvars

from sqladmin import Admin

from src.api.admin import (
    DiffpypeAuthBackend,
    DummyImageAdmin,
    JobConfigurationAdmin,
    ProjectAdmin,
    StepDefinitionAdmin,
    UserAdmin,
)
from src.api.routes.jobs import router as jobs_router
from src.api.routes.meta import router as meta_router
from src.core.config import settings
from src.core.logger import configure_logging, get_logger
from src.db.session import engine

configure_logging()

app = FastAPI(title="Diffpype API")

_auth_backend = DiffpypeAuthBackend(secret_key=settings.admin_secret_key)
admin = Admin(app, engine, authentication_backend=_auth_backend)
admin.add_view(UserAdmin)
admin.add_view(ProjectAdmin)
admin.add_view(StepDefinitionAdmin)
admin.add_view(DummyImageAdmin)
admin.add_view(JobConfigurationAdmin)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    """Bind a fresh correlation_id to the structlog context for each request."""
    clear_contextvars()
    correlation_id = str(uuid.uuid4())
    bind_contextvars(correlation_id=correlation_id)
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = correlation_id
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Framework backstop: log the full traceback and return a clean HTTP 500."""
    get_logger().error("unhandled_exception", path=request.url.path, exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})


app.include_router(jobs_router)
app.include_router(meta_router)
