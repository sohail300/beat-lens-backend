"""Logging setup."""
import logging
import sys
from app.config import ENV

# Configure logging
logging.basicConfig(
    level=logging.INFO if ENV == "production" else logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger("beat-lens-backend")

