"""Configuration and environment variables."""
import os
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

# Database configuration
DB_URL = os.getenv("DB_URL")
if not DB_URL:
    raise ValueError("DB_URL is not set")

# Spotify configuration
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "")

# Directories
SONGS_DIR = "songs"
RECORDINGS_DIR = "recordings"
TMP_DIR = "tmp"

# Audio processing
FINGERPRINT_STEREO = os.getenv("FINGERPRINT_STEREO", "false").lower() == "true"

# Server configuration
ENV = os.getenv("ENV", "development")
PORT = int(os.getenv("PORT", "5000"))

