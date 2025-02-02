"""
Database schema definitions for Cancer Transcriptome Base.
"""
from typing import List, Dict
import psycopg2

def create_tables() -> None:
    """Create all required database tables."""
    pass

CREATE TABLE cancer_transcript_base (
    // ...existing code...
    molecular_functions TEXT[] DEFAULT '{}',  -- Array of molecular function terms
    cellular_location TEXT[] DEFAULT '{}',    -- Array of cellular locations
    // ...existing code...
);

-- Add GIN indices for new arrays
CREATE INDEX idx_molecular_functions ON cancer_transcript_base USING GIN(molecular_functions);
CREATE INDEX idx_cellular_location ON cancer_transcript_base USING GIN(cellular_location);
