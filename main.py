"""FastAPI application entry point."""
import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, WebSocket
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware

from app.config import CORS_ORIGINS, ENV, PORT, SENTRY_DSN, TMP_DIR, TMP_MAX_AGE_SECONDS
from app.db.schema import require_current_schema
from app.routes import api_router
from app.routes.websocket import websocket_endpoint
from app.utils.helpers import create_folder, delete_old_files
from app.utils.logger import logger

if SENTRY_DSN:
    import sentry_sdk

    sentry_sdk.init(dsn=SENTRY_DSN, environment=ENV, send_default_pii=False)


async def clean_tmp_periodically() -> None:
    """Remove uploads left behind by crashed or killed requests."""
    while True:
        deleted = await run_in_threadpool(delete_old_files, TMP_DIR, TMP_MAX_AGE_SECONDS)
        if deleted:
            logger.info(f"Deleted {deleted} stale file(s) from {TMP_DIR}")
        await asyncio.sleep(TMP_MAX_AGE_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown handler."""
    logger.info(f"Beat Lens Backend starting up (environment: {ENV})")

    require_current_schema()

    # The server only needs scratch space for uploads; songs are added with app/cli.py
    create_folder(TMP_DIR)
    cleaner = asyncio.create_task(clean_tmp_periodically())

    yield

    cleaner.cancel()
    with suppress(asyncio.CancelledError):
        await cleaner
    logger.info("Beat Lens Backend shutting down...")


app = FastAPI(
    title="Beat Lens Backend",
    description="FastAPI backend for song recognition",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.websocket("/ws")
async def websocket_route(websocket: WebSocket):
    await websocket_endpoint(websocket)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
