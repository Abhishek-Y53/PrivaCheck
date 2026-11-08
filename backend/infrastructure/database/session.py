"""Synchronous SQLAlchemy engine and session factory for PostgreSQL."""

from collections.abc import Generator

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from backend.core.config import settings


engine: Engine = create_engine(
    settings.DATABASE_URL,
    echo=settings.DATABASE_ECHO,
    pool_pre_ping=True,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
)

SessionLocal = sessionmaker(
    bind=engine,
    class_=Session,
    autoflush=False,
    expire_on_commit=False,
)


def get_db() -> Generator[Session, None, None]:
    """Yield one database session and always close it afterward.

    FastAPI routes can use this function as a dependency. Worker entry points
    can use ``with SessionLocal() as session`` directly.
    """
    with SessionLocal() as session:
        yield session


def check_database_connection() -> None:
    """Raise the underlying SQLAlchemy error if PostgreSQL is unavailable."""
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
