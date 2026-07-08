"""Add hashed_password to users table.

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-08
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Step 1: add as nullable so existing sysadmin row is not immediately violated.
    op.add_column("users", sa.Column("hashed_password", sa.String(), nullable=True))

    # Step 2: backfill existing rows with a placeholder bcrypt hash of "changeme".
    # seed-db must be re-run after migration to stamp the real ADMIN_PASSWORD hash.
    import bcrypt as _bcrypt
    placeholder = _bcrypt.hashpw(b"changeme", _bcrypt.gensalt()).decode("utf-8")
    op.get_bind().execute(
        text("UPDATE users SET hashed_password = :h WHERE hashed_password IS NULL"),
        {"h": placeholder},
    )

    # Step 3: enforce not-null now that all rows have a value.
    op.alter_column("users", "hashed_password", nullable=False)


def downgrade() -> None:
    op.drop_column("users", "hashed_password")
