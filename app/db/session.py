"""Database configuration and session management."""
from typing import Annotated, Iterator
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from fastapi import Depends

from app.config import DB_URL
from app.db.models import Base


# Convert postgresql:// to postgresql+psycopg2:// for SQLAlchemy
def _prepare_database_url(url: str) -> str:
    """Convert standard postgresql:// URL to SQLAlchemy format."""
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    else:
        # Assume it's already in the correct format or add psycopg2 driver
        return url


def _engine_options(url: str) -> dict:
    if url.startswith("sqlite"):
        # Sessions are used from FastAPI's thread pool
        return {"connect_args": {"check_same_thread": False}}
    return {
        # Hosted Postgres (e.g. Neon) closes idle connections; test each one before use
        "pool_pre_ping": True,
        "pool_recycle": 300,
        "pool_size": 5,
        "max_overflow": 5,
    }


_url = _prepare_database_url(DB_URL)
engine = create_engine(_url, future=True, **_engine_options(_url))

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db() -> None:
    """Create all tables directly, bypassing migrations. Only for tests and throwaway databases."""
    Base.metadata.create_all(bind=engine)


# Dependency for getting database session
def get_db() -> Iterator[Session]:
    """Get database session dependency."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Type alias for dependency injection
db_dependency = Annotated[Session, Depends(get_db)]
