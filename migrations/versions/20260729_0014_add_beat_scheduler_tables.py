"""add sqlalchemy-celery-beat scheduler schema and tables

Revision ID: 0014
Revises: 0013
Create Date: 2026-07-29

Doc 30 §4. Creates the dedicated ``celery_schema`` Postgres schema and the
relational tables `sqlalchemy-celery-beat` uses for its database-backed Celery
Beat scheduler (DatabaseScheduler), so schedules can be created/edited/paused at
runtime via SQLAdmin.

Table (and Enum type) creation is delegated to the package's own
``ModelBase.metadata`` rather than transcribing six tables + two schema-qualified
enums by hand: that keeps this migration faithful to the package's real schema and
lets a future package upgrade re-run the same delegation instead of drifting from
a hand-copied definition. The tables live in their own schema, so autogenerate
(which runs with the default ``include_schemas=False``) never sees them and this
migration is the sole authority over their lifecycle. Downgrade drops the whole
schema (tables + enum types) in one cascade.
"""

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from sqlalchemy_celery_beat.models import ModelBase as BeatBase

    op.execute("CREATE SCHEMA IF NOT EXISTS celery_schema")
    BeatBase.metadata.create_all(op.get_bind())


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS celery_schema CASCADE")
