"""SQLAlchemy engine and session factory for the application database."""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.core.config import settings

engine = create_engine(
    settings.database_url,
    future=True,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db():
    """Yield a database session and guarantee it is closed after use."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
