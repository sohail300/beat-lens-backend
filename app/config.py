"""Configuration and environment variables."""
import os

from dotenv import load_dotenv

load_dotenv()

# Database configuration
DB_URL = os.getenv("DB_URL")
if not DB_URL:
    raise ValueError("DB_URL is not set")

# Spotify configuration
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "")

# Directories (default to folders inside the backend, wherever the server is started from)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SONGS_DIR = os.getenv("SONGS_DIR") or os.path.join(BASE_DIR, "songs")
RECORDINGS_DIR = os.getenv("RECORDINGS_DIR") or os.path.join(BASE_DIR, "recordings")
TMP_DIR = os.getenv("TMP_DIR") or os.path.join(BASE_DIR, "tmp")

# Audio processing
FINGERPRINT_STEREO = os.getenv("FINGERPRINT_STEREO", "false").lower() == "true"
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_MB", "20")) * 1024 * 1024
# Recognition: only the first MAX_CLIP_SECONDS of a sample are used. A match is reported only if
# its score is at least MIN_MATCH_SCORE and MIN_MATCH_RATIO times the runner-up's score.
# Calibrated on real music with noisy / Opus / phone-band clips, including unknown songs by the same
# composer as library songs: no false matches; ~87% of 5 s, ~93% of 10 s and ~98% of 20 s clips found.
MAX_CLIP_SECONDS = int(os.getenv("MAX_CLIP_SECONDS", "20"))
MIN_MATCH_SCORE = float(os.getenv("MIN_MATCH_SCORE", "10"))
MIN_MATCH_RATIO = float(os.getenv("MIN_MATCH_RATIO", "2.5"))
# Abuse protection for recognition endpoints (per client IP, per server process; 0 disables)
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "30"))
# How many samples may be fingerprinted at once per process (0 = one per CPU core)
RECOGNITION_CONCURRENCY = int(os.getenv("RECOGNITION_CONCURRENCY", "0"))
# Upper bound on fingerprints accepted by /api/recognition/find (a 20 s clip has roughly 1,000)
MAX_SAMPLE_FINGERPRINTS = int(os.getenv("MAX_SAMPLE_FINGERPRINTS", "20000"))
# Keep each added song's WAV in SONGS_DIR (needed to re-index or rename it later)
KEEP_AUDIO = os.getenv("KEEP_AUDIO", "true").lower() == "true"

# Server configuration
ENV = os.getenv("ENV", "development")
LOG_LEVEL = os.getenv("LOG_LEVEL", "").upper()  # Defaults to INFO in production, DEBUG otherwise
# Error reporting: set to a Sentry DSN to send unhandled errors to Sentry
SENTRY_DSN = os.getenv("SENTRY_DSN", "")
# Files in TMP_DIR older than this are leftovers from crashed requests and get deleted
TMP_MAX_AGE_SECONDS = int(os.getenv("TMP_MAX_AGE_SECONDS", "3600"))
PORT = int(os.getenv("PORT", "5000"))
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
    if origin.strip()
]

