"""PostgreSQL adapters for custom data types."""

import json
from typing import Any
import psycopg2.extensions

def register_adapters() -> None:
    """Register custom adapters for PostgreSQL."""
    
    def adapt_dict(dict_value: dict) -> psycopg2.extensions.AsIs:
        """Adapt Python dict to PostgreSQL JSON."""
        return psycopg2.extensions.AsIs(f"'{json.dumps(dict_value)}'::jsonb")
    
    # Register the dict adapter
    psycopg2.extensions.register_adapter(dict, adapt_dict)
