"""Logging setup."""
import logging
import sys
from app.config import ENV, LOG_LEVEL

# Third-party libraries log at INFO; our own logger follows LOG_LEVEL
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger("beat-lens-backend")
logger.setLevel(LOG_LEVEL or ("INFO" if ENV == "production" else "DEBUG"))
