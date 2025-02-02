"""Database connection utilities."""
from typing import Dict, Any
import psycopg2
from psycopg2.extensions import connection as pg_connection
from .adapters import register_adapters

# Register adapters on module import
register_adapters()

def get_db_connection(config: Dict[str, Any]) -> pg_connection:
    """Create a database connection from configuration.
    
    Args:
        config: Configuration dictionary with database parameters
        
    Returns:
        PostgreSQL database connection
        
    Raises:
        psycopg2.Error: If connection fails
    """
    return psycopg2.connect(
        host=config['host'],
        port=config['port'],
        dbname=config['dbname'],
        user=config['user'],
        password=config['password']
    )
