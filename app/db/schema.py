"""Check that the database has every Alembic migration applied."""
import logging
import os

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory

from app.config import BASE_DIR
from app.db.session import engine


def alembic_config() -> Config:
    return Config(os.path.join(BASE_DIR, "alembic.ini"))


def require_current_schema() -> None:
    """Fail fast if migrations are missing, rather than erroring on the first query."""
    logging.getLogger("alembic.runtime.migration").setLevel(logging.WARNING)
    head = ScriptDirectory.from_config(alembic_config()).get_current_head()
    with engine.connect() as connection:
        current = MigrationContext.configure(connection).get_current_revision()
    if current != head:
        raise RuntimeError(
            f"Database schema is at revision {current or 'none'}, expected {head}. "
            "Run `alembic upgrade head` from the backend folder first."
        )
