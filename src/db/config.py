"""Database configuration module."""
import os
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


def get_db_config() -> Dict[str, Any]:
    """Get database configuration from environment variables with defaults."""
    config = {
        "host": os.getenv("MB_POSTGRES_HOST", "localhost"),
        "port": int(os.getenv("MB_POSTGRES_PORT", "5432")),
        "dbname": os.getenv("MB_POSTGRES_NAME", "mediabase"),
        "user": os.getenv("MB_POSTGRES_USER", "postgres"),
        "password": os.getenv("MB_POSTGRES_PASSWORD", "postgres"),
    }

    # Debug log the configuration (with password masked)
    debug_config = config.copy()
    debug_config["password"] = "****" if debug_config["password"] else None
    logger.debug(f"Database configuration: {debug_config}")

    # Validate required fields
    for key in ["host", "port", "dbname", "user", "password"]:
        if not config.get(key):
            logger.warning(f"Missing required database config: {key}")

    return config
