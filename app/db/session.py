"""Database configuration and session management."""
from typing import Annotated
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


# Create engine
engine = create_engine(_prepare_database_url(DB_URL), future=True)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Initialize database tables
def init_db() -> None:
    """Create all tables."""
    Base.metadata.create_all(bind=engine)


# Dependency for getting database session
def get_db() -> Session:
    """Get database session dependency."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Type alias for dependency injection
db_dependency = Annotated[Session, Depends(get_db)]
