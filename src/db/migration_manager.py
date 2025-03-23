"""Database migration manager.

This module manages database migrations between versions.
"""
import logging
from typing import Dict, Any, Optional
import sqlite3  # or whatever database you're using

logger = logging.getLogger(__name__)

class MigrationManager:
    """Handles database migrations between versions."""
    
    def __init__(self, db_connection: Any) -> None:
        """Initialize the migration manager.
        
        Args:
            db_connection: Database connection object
        """
        self.conn = db_connection
        
    def check_version(self) -> str:
        """Check the current database version.
        
        Returns:
            Current database version string
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT value FROM metadata WHERE key = 'version'")
            result = cursor.fetchone()
            if result:
                return result[0]
            return "unknown"
        except Exception as e:
            logger.error(f"Failed to get database version: {e}")
            return "unknown"
    
    def migrate_if_needed(self) -> bool:
        """Perform migration if needed.
        
        Returns:
            True if migration was performed, False otherwise
        """
        current_version = self.check_version()
        
        # We no longer support versions before 0.1.5
        if current_version == "unknown" or self._compare_versions(current_version, "0.1.5") < 0:
            logger.error(f"Database version {current_version} is not supported. Please upgrade to v0.1.5 first.")
            return False
            
        # Migration logic for versions >= 0.1.5 would go here if needed
        logger.info(f"Database version {current_version} is supported. No migration needed.")
        return True
    
    def _compare_versions(self, version1: str, version2: str) -> int:
        """Compare two version strings.
        
        Args:
            version1: First version string
            version2: Second version string
            
        Returns:
            -1 if version1 < version2, 0 if equal, 1 if version1 > version2
        """
        v1_parts = [int(x) for x in version1.replace('v', '').split('.')]
        v2_parts = [int(x) for x in version2.replace('v', '').split('.')]
        
        for i in range(max(len(v1_parts), len(v2_parts))):
            v1 = v1_parts[i] if i < len(v1_parts) else 0
            v2 = v2_parts[i] if i < len(v2_parts) else 0
            
            if v1 < v2:
                return -1
            if v1 > v2:
                return 1
                
        return 0
