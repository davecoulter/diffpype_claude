"""SQLAdmin model views providing a web-based CRUD dashboard at /admin."""
from sqladmin import ModelView

from src.db.models import DummyImage, JobConfiguration, Project, StepDefinition, User


class UserAdmin(ModelView, model=User):
    """Admin view for inspecting and managing User records."""

    column_list = [User.id, User.username, User.email, User.is_active, User.created_at]


class ProjectAdmin(ModelView, model=Project):
    """Admin view for inspecting and managing Project records."""

    column_list = [Project.id, Project.name, Project.description, Project.user_id, Project.created_at]


class StepDefinitionAdmin(ModelView, model=StepDefinition):
    """Admin view for inspecting and managing StepDefinition records."""

    column_list = [StepDefinition.id, StepDefinition.name, StepDefinition.task_name, StepDefinition.queue]


class DummyImageAdmin(ModelView, model=DummyImage):
    """Admin view for inspecting and managing DummyImage records."""

    column_list = [DummyImage.id, DummyImage.status, DummyImage.latest_job_id, DummyImage.job_started_at, DummyImage.created_at]


class JobConfigurationAdmin(ModelView, model=JobConfiguration):
    """Admin view for inspecting and managing JobConfiguration records."""

    column_list = [JobConfiguration.id, JobConfiguration.user_id, JobConfiguration.execution_command, JobConfiguration.created_at]
