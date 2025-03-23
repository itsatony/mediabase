"""Base processor class for ETL modules."""

import logging
from typing import Dict, Any, Optional
from ..db.database import get_db_manager

logger = logging.getLogger(__name__)

class BaseProcessor:
    """Base class for all ETL processors."""
    
    def __init__(self, config: Dict[str, Any]) -> None:
        """Initialize base processor.
        
        Args:
            config: Configuration dictionary containing all settings
                   including nested db configuration
        """
        self.config = config
        
        # Extract nested db config if present
        db_config = config.get('db')
        if not db_config:
            logger.warning("No nested db config found, checking root level")
            # Try to extract db config from root level
            db_config = {
                'host': config.get('host', 'localhost'),
                'port': config.get('port', 5432),
                'dbname': config.get('dbname', 'mediabase'),
                'user': config.get('user', 'postgres'),
                'password': config.get('password', 'postgres')
            }
        
        logger.debug(f"Using database config: {db_config}")
        self.db_manager = get_db_manager(db_config)
