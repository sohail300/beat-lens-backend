"""FastAPI application entry point."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import routes
from app.api.websocket import websocket_endpoint
from app.config import ENV, PORT
from app.utils.helpers import create_folder
from app.config import SONGS_DIR, RECORDINGS_DIR, TMP_DIR
from app.utils.logger import logger

app = FastAPI(
    title="Beat Lens Backend",
    description="FastAPI backend for song recognition",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify allowed origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(routes.router, prefix="/api", tags=["api"])

# WebSocket endpoint
@app.websocket("/socket.io/")
async def websocket_route(websocket):
    await websocket_endpoint(websocket)

@app.on_event("startup")
async def startup_event():
    """Startup event handler."""
    logger.info("Beat Lens Backend starting up...")
    logger.info(f"Environment: {ENV}")
    logger.info(f"Port: {PORT}")

    # Initialize database
    from app.db.session import init_db
    init_db()
    logger.info("Database initialized successfully")

    # Create required directories
    create_folder(SONGS_DIR)
    create_folder(RECORDINGS_DIR)
    create_folder(TMP_DIR)
    logger.info("Directories created successfully")


@app.on_event("shutdown")
async def shutdown_event():
    """Shutdown event handler."""
    logger.info("Beat Lens Backend shutting down...")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)

