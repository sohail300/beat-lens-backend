"""API routers, grouped by area and mounted under /api."""
from fastapi import APIRouter

from app.routes import health, recognition, songs

api_router = APIRouter(prefix="/api")
api_router.include_router(health.router)
api_router.include_router(recognition.router)
api_router.include_router(songs.router)
