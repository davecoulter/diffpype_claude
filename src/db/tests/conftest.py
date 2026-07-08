import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    os.environ.get("DATABASE_URL", ""),
)


@pytest.fixture(scope="session")
def test_engine():
    """Create the test engine and run migrations once per test session."""
    engine = create_engine(TEST_DATABASE_URL)
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    command.upgrade(cfg, "head")
    yield engine
    engine.dispose()


@pytest.fixture
def user(db):
    """Create a test owner User in the current test transaction."""
    from src.db.models import User

    u = User(username="testowner", email="testowner@diffpype.local", is_active=True)
    db.add(u)
    db.flush()
    return u


@pytest.fixture
def db(test_engine):
    """Transactional session — rolls back after each test for full isolation."""
    connection = test_engine.connect()
    transaction = connection.begin()
    SessionFactory = sessionmaker(bind=connection)
    session = SessionFactory()
    yield session
    session.close()
    transaction.rollback()
    connection.close()
