"""ETL modules for the MediaBase project."""

# Import all main processor classes for easier access
from .transcript import TranscriptProcessor
from .products import ProductClassifier, ProductProcessor
from .pathways import PathwayProcessor
from .drugs import DrugProcessor
from .go_terms import GOTermProcessor

# Export all main processor classes
__all__ = [
    'TranscriptProcessor', 
    'ProductClassifier', 
    'ProductProcessor', 
    'PathwayProcessor', 
    'DrugProcessor', 
    'GOTermProcessor',
]
