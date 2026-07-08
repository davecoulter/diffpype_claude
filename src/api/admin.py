"""SQLAdmin model views and authentication backend for the /admin dashboard."""
import bcrypt
from sqladmin import ModelView
from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request

from src.core.logger import get_logger
from src.db.models import DummyImage, JobConfiguration, Project, StepDefinition, User
from src.db.session import SessionLocal


class DiffpypeAuthBackend(AuthenticationBackend):
    """Session-cookie authentication backend that verifies credentials against the User table."""

    async def login(self, request: Request) -> bool:
        form = await request.form()
        username = form.get("username", "")
        password = form.get("password", "")
        db = SessionLocal()
        try:
            user = db.query(User).filter_by(username=username, is_active=True).one_or_none()
            if user and bcrypt.checkpw(
                password.encode("utf-8"), user.hashed_password.encode("utf-8")
            ):
                request.session.update({"authenticated": True})
                return True
        except ValueError:
            get_logger().warning(
                "admin_login_hash_invalid",
                username=username,
                detail="stored hashed_password is not a valid bcrypt hash",
            )
        except Exception:
            get_logger().error("admin_login_error", username=username, exc_info=True)
        finally:
            db.close()
        return False

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        """Return True if the session carries a valid authentication token."""
        return request.session.get("authenticated", False)


class UserAdmin(ModelView, model=User):
    """Admin view for inspecting and managing User records."""

    column_list = [User.id, User.username, User.email, User.is_active, User.created_at]
    form_excluded_columns = [
        User.created_at,
        User.updated_at,
        User.projects,
        User.step_definitions,
        User.job_configurations,
    ]

    async def on_model_change(self, data: dict, model: User, is_created: bool, request: Request) -> None:
        """Hash plain-text password input before persisting to the database."""
        if "hashed_password" in data and data["hashed_password"]:
            data["hashed_password"] = bcrypt.hashpw(
                data["hashed_password"].encode("utf-8"), bcrypt.gensalt()
            ).decode("utf-8")


class ProjectAdmin(ModelView, model=Project):
    """Admin view for inspecting and managing Project records."""

    column_list = [Project.id, Project.name, Project.description, Project.user_id, Project.created_at]
    form_excluded_columns = [Project.created_at, Project.updated_at]


class StepDefinitionAdmin(ModelView, model=StepDefinition):
    """Admin view for inspecting and managing StepDefinition records."""

    column_list = [StepDefinition.id, StepDefinition.name, StepDefinition.task_name, StepDefinition.queue]
    form_excluded_columns = [StepDefinition.created_at, StepDefinition.updated_at]


class DummyImageAdmin(ModelView, model=DummyImage):
    """Admin view for inspecting and managing DummyImage records."""

    column_list = [DummyImage.id, DummyImage.status, DummyImage.latest_job_id, DummyImage.job_started_at, DummyImage.created_at]
    form_excluded_columns = [
        DummyImage.created_at,
        DummyImage.updated_at,
        DummyImage.job_started_at,
        DummyImage.job_finished_at,
        DummyImage.latest_job_id,
    ]


class JobConfigurationAdmin(ModelView, model=JobConfiguration):
    """Admin view for inspecting and managing JobConfiguration records."""

    column_list = [JobConfiguration.id, JobConfiguration.user_id, JobConfiguration.execution_command, JobConfiguration.created_at]
    form_excluded_columns = [
        JobConfiguration.created_at,
        JobConfiguration.updated_at,
        JobConfiguration.dummy_images,
    ]
