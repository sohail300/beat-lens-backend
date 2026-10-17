"""Health check endpoint."""
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.db.session import db_dependency
from app.utils.logger import logger

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check(db: db_dependency):
    """Reports 503 when the database is unreachable, so the host can restart or stop routing to this instance."""
    try:
        db.execute(text("SELECT 1"))
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(status_code=503, content={"status": "error", "database": "unreachable"})
    return {"status": "ok", "database": "ok"}
