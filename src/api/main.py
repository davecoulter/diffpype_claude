from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from opentelemetry import trace
from starlette_exporter import PrometheusMiddleware, handle_metrics

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
from src.core.tracing import setup_tracing
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


def sqladmin_exception_handler(request: Request, exc: Exception) -> None:
    """Log exceptions raised inside the mounted sqladmin sub-app, then re-raise.

    sqladmin is a separate ASGI sub-application, so exceptions in its routes never
    reach FastAPI's ``unhandled_exception_handler`` and are invisible to both OTel
    error recording and structlog. Registering this on the sub-app closes that gap.
    """
    get_logger().error("sqladmin_unhandled_exception", exc_info=exc)
    raise exc


admin.admin.add_exception_handler(Exception, sqladmin_exception_handler)

app.add_middleware(PrometheusMiddleware, app_name="diffpype")
app.add_route("/metrics", handle_metrics)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    """Expose the active OTel trace ID as the X-Correlation-ID response header."""
    span_context = trace.get_current_span().get_span_context()
    correlation_id = format(span_context.trace_id, "032x") if span_context.is_valid else None
    response = await call_next(request)
    if correlation_id is not None:
        response.headers["X-Correlation-ID"] = correlation_id
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Framework backstop: log the full traceback and return a clean HTTP 500."""
    get_logger().error("unhandled_exception", path=request.url.path, exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})


app.include_router(jobs_router, prefix="/api/v1")
app.include_router(meta_router, prefix="/api/v1")

# Instrument the app, the SQLAlchemy engine, and Celery. Called last so the router
# and middleware stack are fully assembled before OTel wraps the ASGI app.
setup_tracing(app=app, engine=engine)
