"""ETL package for Cancer Transcriptome Base."""

# Import base classes first to prevent circular imports
from .base_processor import (
    BaseProcessor,
    ETLError,
    DownloadError,
    ProcessingError,
    DatabaseError,
    CacheError
)

# Avoid importing publications directly to prevent circular reference
# With our new publication_types.py file, other modules can import the Publication
# type from there instead of from publications.py

# Import processor classes
from .transcript import TranscriptProcessor
from .products import ProductClassifier, ProductProcessor
from .go_terms import GOTermProcessor
from .pathways import PathwayProcessor
from .drugs import DrugProcessor
from .id_enrichment import IDEnrichmentProcessor
# Import publications last to avoid circular references
from .publications import PublicationsProcessor

# Export all main processor classes
__all__ = [
    'TranscriptProcessor', 
    'ProductClassifier', 
    'ProductProcessor', 
    'PathwayProcessor', 
    'DrugProcessor', 
    'GOTermProcessor',
    'IDEnrichmentProcessor',
    'PublicationsProcessor',
]
