"""SQLAdmin model views and authentication backend for the /admin dashboard."""

import bcrypt
from sqladmin import ModelView
from sqlalchemy_celery_beat.models import (
    CrontabSchedule,
    IntervalSchedule,
    PeriodicTask,
)
from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request

from src.core.logger import get_logger
from src.db.models import JobConfiguration, Project, StepDefinition, User
from src.db.session import SessionLocal


class DiffpypeAuthBackend(AuthenticationBackend):
    """Session-cookie authentication backend that verifies credentials against the User table."""

    async def login(self, request: Request) -> bool:
        form = await request.form()
        username = form.get("username", "")
        password = form.get("password", "")
        if not isinstance(username, str) or not isinstance(password, str):
            return False
        db = SessionLocal()
        try:
            user = (
                db.query(User)
                .filter_by(username=username, is_active=True)
                .one_or_none()
            )
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

    async def on_model_change(
        self, data: dict, model: User, is_created: bool, request: Request
    ) -> None:
        """Hash plain-text password input before persisting to the database."""
        if "hashed_password" in data and data["hashed_password"]:
            data["hashed_password"] = bcrypt.hashpw(
                data["hashed_password"].encode("utf-8"), bcrypt.gensalt()
            ).decode("utf-8")


class ProjectAdmin(ModelView, model=Project):
    """Admin view for inspecting and managing Project records."""

    column_list = [
        Project.id,
        Project.name,
        Project.description,
        Project.user_id,
        Project.created_at,
    ]
    form_excluded_columns = [Project.created_at, Project.updated_at]


class StepDefinitionAdmin(ModelView, model=StepDefinition):
    """Admin view for inspecting and managing StepDefinition records."""

    column_list = [
        StepDefinition.id,
        StepDefinition.name,
        StepDefinition.task_name,
        StepDefinition.queue,
    ]
    form_excluded_columns = [StepDefinition.created_at, StepDefinition.updated_at]


class JobConfigurationAdmin(ModelView, model=JobConfiguration):
    """Admin view for inspecting and managing JobConfiguration records."""

    column_list = [
        JobConfiguration.id,
        JobConfiguration.user_id,
        JobConfiguration.task_name,
        JobConfiguration.execution_command,
        JobConfiguration.created_at,
    ]
    form_excluded_columns = [
        JobConfiguration.created_at,
        JobConfiguration.updated_at,
    ]


class PeriodicTaskAdmin(ModelView, model=PeriodicTask):
    """Admin view for creating, editing, and pausing database-backed Celery Beat schedules."""

    name = "Periodic Task"
    name_plural = "Periodic Tasks"
    column_list = [
        PeriodicTask.id,
        PeriodicTask.name,
        PeriodicTask.task,
        PeriodicTask.enabled,
        PeriodicTask.last_run_at,
    ]
    # Only IntervalSchedule is used today (see doc 30 §4) — excluding the other
    # three schedule-type relations avoids SQLAdmin auto-generating a required
    # "Not a valid choice" dropdown for schedule types no PeriodicTask actually uses.
    # Plain strings (not PeriodicTask.model_crontabschedule etc.) are deliberate:
    # PeriodicTask comes from sqlalchemy_celery_beat's own separate declarative
    # registry, and referencing its relationship attributes directly at this
    # class body's evaluation time raced that registry's mapper configuration,
    # raising a spurious AttributeError. Strings defer resolution to request time.
    form_excluded_columns = [
        "model_crontabschedule",
        "model_solarschedule",
        "model_clockedschedule",
    ]


class IntervalScheduleAdmin(ModelView, model=IntervalSchedule):
    """Admin view for the interval (every-N-period) schedules a PeriodicTask can reference."""

    name = "Interval Schedule"
    name_plural = "Interval Schedules"
    # Each PeriodicTask gets its own dedicated IntervalSchedule row (never
    # shared), so two rows with identical every/period are easy to mistake for
    # duplicates. Surfacing the owning task name(s) disambiguates them.
    # String keys (not IntervalSchedule.periodic_tasks) for the same reason
    # PeriodicTaskAdmin.form_excluded_columns uses strings above: this model's
    # relationships live in sqlalchemy_celery_beat's own declarative registry.
    column_list = [
        IntervalSchedule.id,
        IntervalSchedule.every,
        IntervalSchedule.period,
        "periodic_tasks",
    ]
    column_formatters = {
        # sqladmin's own ClassVar annotation types the formatter's first arg as
        # bare `type`, but it's actually the model instance at render time.
        # Must return a list aligned 1:1 with the relation's items, not a
        # single joined string: for to-many columns, list.html zips the raw
        # related-object list against whatever this returns, one link per
        # pair — a joined string got zipped character-by-character against a
        # single-item list, silently rendering only its first letter.
        "periodic_tasks": lambda model, _attr: [
            pt.name
            for pt in model.periodic_tasks  # type: ignore[attr-defined]
        ],
    }


class CrontabScheduleAdmin(ModelView, model=CrontabSchedule):
    """Admin view for the crontab schedules a PeriodicTask can reference."""

    name = "Crontab Schedule"
    name_plural = "Crontab Schedules"
    column_list = [
        CrontabSchedule.id,
        CrontabSchedule.minute,
        CrontabSchedule.hour,
        CrontabSchedule.day_of_week,
        CrontabSchedule.day_of_month,
        CrontabSchedule.month_of_year,
    ]
