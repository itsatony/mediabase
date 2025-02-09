# Coding Instructions

Be the smartest, most complete, most far-thinking and diligent developer ever.

For everything you do, document each step and key improvement in the README.md file under the appropriate section - usually "## Project Status and Progress".

## Environment

We are using poetry for managing dependencies.

We are using python >=3.10 for development.


## Code Style Guide

### General Principles

1. **Clarity Over Cleverness**
   - Code should be immediately comprehensible
   - Avoid complex one-liners
   - Use descriptive names over abbreviated ones

2. **Type Safety**
   - Use Python type hints everywhere
   - Enforce with mypy in strict mode
   ```python
   from typing import List, Dict, Optional
   
   def process_genes(genes: List[str]) -> Dict[str, float]:
       ...
   ```

3. **Documentation**
   - Every module starts with a docstring explaining its purpose
   - Every function/class has a docstring following Google style
   ```python
   def calculate_fold_change(
       base_expression: float,
       sample_expression: float
   ) -> float:
       """Calculate expression fold change between sample and base.
       
       Args:
           base_expression: Base expression level
           sample_expression: Sample expression level
           
       Returns:
           float: Calculated fold change
           
       Raises:
           ValueError: If base_expression is 0
       """
   ```

### Python Specific Rules
1. **Imports**
   ```python
   # Standard library
   from typing import List, Dict
   import json
   
   # Third party
   import pandas as pd
   import numpy as np
   
   # Local
   from src.etl.transcript import TranscriptProcessor
   from src.utils.validation import validate_expression
   ```

2. **Classes**
   ```python
   class GeneProcessor:
       """Process gene-related data and transformations."""
       
       def __init__(self, config: Dict[str, Any]) -> None:
           """Initialize processor with configuration.
           
           Args:
               config: Configuration dictionary
           """
           self.config = config
           self._validate_config()
           
       def _validate_config(self) -> None:
           """Validate configuration settings."""
           ...
   ```

3. **Error Handling**
   ```python
   class ETLError(Exception):
       """Base class for ETL-related errors."""
       
   def process_data(data: pd.DataFrame) -> pd.DataFrame:
       try:
           validated_data = validate_input(data)
           processed_data = transform_data(validated_data)
           return processed_data
       except ValidationError as e:
           logger.error(f"Validation failed: {e}")
           raise ETLError(f"Processing failed: {e}") from e
   ```

4. **Testing**
   ```python
   import pytest
   from src.etl.transcript import TranscriptProcessor
   
   @pytest.fixture
   def processor():
       return TranscriptProcessor(config={'threshold': 0.5})
   
   def test_fold_change_calculation(processor):
       """Test fold change calculation with valid inputs."""
       result = processor.calculate_fold_change(base=1.0, sample=2.0)
       assert result == pytest.approx(2.0)
   ```

### SQL Style

1. **Naming**
   - Tables: singular, lower_snake_case
   - Columns: lower_snake_case
   - Indexes: idx_table_column

2. **Queries**
   ```sql
   -- Multiple lines for complex queries
   SELECT 
       t.gene_symbol,
       t.expression_fold_change,
       jsonb_object_keys(t.drugs) as drug_id
   FROM 
       cancer_transcript_base t
   WHERE 
       t.expression_fold_change > 2.0
   ORDER BY 
       t.expression_fold_change DESC;
   ```

### Version Control

1. **Commit Messages**
   ```
   <type>(<scope>): <description>
   
   [optional body]
   
   [optional footer]
   ```
   Types: feat, fix, docs, style, refactor, test, chore

2. **Branching**
   - main: production code
   - develop: integration branch
   - feature/: new features
   - fix/: bug fixes
   - release/: release preparation

