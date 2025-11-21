"""Patient schema management utilities for MEDIABASE.

This module provides functions for creating, validating, and managing
patient-specific schemas in the shared core database architecture.

Architecture:
- Single mbase database with public schema (core data)
- Patient-specific schemas: patient_<PATIENT_ID>
- Sparse storage: Only fold_change != 1.0 values stored

Usage:
    from src.db.patient_schema import create_patient_schema, validate_patient_schema

    # Create new patient schema
    create_patient_schema(
        patient_id="DEMO_HER2",
        db_manager=db_manager
    )

    # Validate schema integrity
    validation_results = validate_patient_schema(
        patient_id="DEMO_HER2",
        db_manager=db_manager
    )
"""

import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
import re

from .database import DatabaseManager
from ..utils.logging import setup_logging

# Create logger
logger = setup_logging(module_name=__name__)

# Path to patient schema template
TEMPLATE_PATH = Path(__file__).parent / "patient_schema_template.sql"


class PatientSchemaError(Exception):
    """Base exception for patient schema operations."""

    pass


class InvalidPatientIDError(PatientSchemaError):
    """Raised when patient ID is invalid."""

    pass


class SchemaExistsError(PatientSchemaError):
    """Raised when attempting to create existing schema."""

    pass


class SchemaNotFoundError(PatientSchemaError):
    """Raised when schema does not exist."""

    pass


def validate_patient_id(patient_id: str) -> bool:
    """Validate patient ID format.

    Rules:
    - Alphanumeric characters, underscores, hyphens only
    - 3-100 characters long
    - Cannot start with number
    - Cannot be SQL reserved words

    Args:
        patient_id: Patient identifier to validate

    Returns:
        True if valid

    Raises:
        InvalidPatientIDError: If patient_id is invalid
    """
    # SQL reserved words to reject
    reserved_words = {
        "public",
        "schema",
        "table",
        "select",
        "insert",
        "update",
        "delete",
        "drop",
        "create",
        "alter",
        "grant",
        "revoke",
        "user",
        "admin",
    }

    # Check length
    if not (3 <= len(patient_id) <= 100):
        raise InvalidPatientIDError(
            f"Patient ID must be 3-100 characters, got {len(patient_id)}"
        )

    # Check format
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9_-]*$", patient_id):
        raise InvalidPatientIDError(
            f"Patient ID must start with letter and contain only "
            f"alphanumeric, underscore, hyphen characters. Got: {patient_id}"
        )

    # Check reserved words
    if patient_id.lower() in reserved_words:
        raise InvalidPatientIDError(
            f"Patient ID cannot be SQL reserved word: {patient_id}"
        )

    logger.debug(f"Patient ID validated: {patient_id}")
    return True


def get_schema_name(patient_id: str) -> str:
    """Get PostgreSQL schema name for patient.

    Args:
        patient_id: Patient identifier

    Returns:
        Schema name (format: patient_<patient_id>)

    Note:
        Patient ID is lowercased to match PostgreSQL's identifier folding behavior.
        PostgreSQL converts unquoted identifiers to lowercase, so we explicitly
        lowercase to ensure consistency across all schema operations.
    """
    validate_patient_id(patient_id)
    return f"patient_{patient_id.lower()}"


def schema_exists(patient_id: str, db_manager: DatabaseManager) -> bool:
    """Check if patient schema exists in database.

    Args:
        patient_id: Patient identifier
        db_manager: Database manager instance

    Returns:
        True if schema exists
    """
    schema_name = get_schema_name(patient_id)

    query = """
        SELECT EXISTS(
            SELECT 1 FROM information_schema.schemata
            WHERE schema_name = %s
        );
    """

    # Ensure database connection
    if not db_manager.cursor:
        db_manager.connect()
    cursor = db_manager.cursor
    cursor.execute(query, (schema_name,))
    result = cursor.fetchone()
    exists = result[0] if result else False

    logger.debug(f"Schema {schema_name} exists: {exists}")
    return exists


def create_patient_schema(
    patient_id: str,
    db_manager: DatabaseManager,
    metadata: Optional[Dict[str, Any]] = None,
    overwrite: bool = False,
) -> Dict[str, Any]:
    """Create patient-specific schema from template.

    Args:
        patient_id: Unique patient identifier
        db_manager: Database manager instance
        metadata: Optional metadata dict to populate metadata table
        overwrite: If True, drop existing schema first (DANGEROUS)

    Returns:
        Dict with creation results including schema_name, created_date

    Raises:
        SchemaExistsError: If schema exists and overwrite=False
        InvalidPatientIDError: If patient_id format is invalid
        PatientSchemaError: If creation fails

    Example:
        >>> result = create_patient_schema(
        ...     patient_id="DEMO_HER2",
        ...     db_manager=db_manager,
        ...     metadata={
        ...         "cancer_type": "Breast Cancer",
        ...         "cancer_subtype": "HER2+",
        ...         "source_file": "demo_her2.csv"
        ...     }
        ... )
        >>> print(result["schema_name"])
        patient_DEMO_HER2
    """
    validate_patient_id(patient_id)
    schema_name = get_schema_name(patient_id)

    # Check if schema exists
    if schema_exists(patient_id, db_manager):
        if not overwrite:
            raise SchemaExistsError(
                f"Schema {schema_name} already exists. "
                f"Use overwrite=True to drop and recreate."
            )
        else:
            logger.warning(f"Dropping existing schema: {schema_name}")
            drop_patient_schema(patient_id, db_manager)

    # Read template
    if not TEMPLATE_PATH.exists():
        raise PatientSchemaError(f"Schema template not found: {TEMPLATE_PATH}")

    template_sql = TEMPLATE_PATH.read_text()

    # Substitute template variables
    created_date = datetime.utcnow().isoformat()
    db_user = db_manager.db_config.get("user", "mbase_user")

    substitutions = {
        "${SCHEMA_NAME}": schema_name,
        "${PATIENT_ID}": patient_id,
        "${CREATED_DATE}": created_date,
        "${DB_USER}": db_user,
    }

    schema_sql = template_sql
    for var, value in substitutions.items():
        schema_sql = schema_sql.replace(var, value)

    # Execute schema creation
    logger.info(f"Creating patient schema: {schema_name}")

    try:
        # Ensure database connection
        if not db_manager.cursor:
            db_manager.connect()
        cursor = db_manager.cursor

        # Execute the schema creation SQL
        cursor.execute(schema_sql)

        # Insert metadata if provided
        if metadata:
            insert_metadata(
                patient_id=patient_id, metadata=metadata, db_manager=db_manager
            )

        # Commit the transaction so schema is visible to other connections
        db_manager.conn.commit()

        logger.info(f"Successfully created schema: {schema_name}")

        return {
            "schema_name": schema_name,
            "patient_id": patient_id,
            "created_date": created_date,
            "success": True,
        }

    except Exception as e:
        logger.error(f"Failed to create schema {schema_name}: {e}")
        raise PatientSchemaError(f"Schema creation failed: {e}") from e


def insert_metadata(
    patient_id: str, metadata: Dict[str, Any], db_manager: DatabaseManager
) -> None:
    """Insert metadata into patient schema.

    Args:
        patient_id: Patient identifier
        metadata: Metadata dictionary
        db_manager: Database manager instance

    Raises:
        PatientSchemaError: If insert fails
    """
    schema_name = get_schema_name(patient_id)

    # Build INSERT statement with provided fields
    columns = ["patient_id"]
    values = [patient_id]
    placeholders = ["%s"]

    # Map metadata fields to table columns
    field_mapping = {
        "source_file": "source_file",
        "file_format": "file_format",
        "normalization_method": "normalization_method",
        "total_transcripts_uploaded": "total_transcripts_uploaded",
        "transcripts_matched": "transcripts_matched",
        "transcripts_unmatched": "transcripts_unmatched",
        "matching_success_rate": "matching_success_rate",
        "clinical_notes": "clinical_notes",
        "cancer_type": "cancer_type",
        "cancer_subtype": "cancer_subtype",
        "tissue_type": "tissue_type",
        "sample_type": "sample_type",
        "sequencing_platform": "sequencing_platform",
        "read_depth_millions": "read_depth_millions",
    }

    for meta_key, table_col in field_mapping.items():
        if meta_key in metadata:
            columns.append(table_col)
            values.append(metadata[meta_key])
            placeholders.append("%s")

    # Handle JSONB metadata field
    if "metadata_json" in metadata:
        columns.append("metadata_json")
        values.append(metadata["metadata_json"])
        placeholders.append("%s::jsonb")

    query = f"""
        INSERT INTO {schema_name}.metadata ({', '.join(columns)})
        VALUES ({', '.join(placeholders)})
        ON CONFLICT (patient_id) DO UPDATE SET
            {', '.join(f"{col} = EXCLUDED.{col}" for col in columns if col != 'patient_id')}
    """

    try:
        # Ensure database connection
        if not db_manager.cursor:
            db_manager.connect()
        cursor = db_manager.cursor
        cursor.execute(query, values)
        logger.info(f"Inserted metadata for patient {patient_id}")
    except Exception as e:
        logger.error(f"Failed to insert metadata for {patient_id}: {e}")
        raise PatientSchemaError(f"Metadata insert failed: {e}") from e


def drop_patient_schema(
    patient_id: str, db_manager: DatabaseManager, cascade: bool = True
) -> bool:
    """Drop patient schema from database.

    Args:
        patient_id: Patient identifier
        db_manager: Database manager instance
        cascade: If True, drop all objects in schema (default True)

    Returns:
        True if dropped successfully

    Raises:
        SchemaNotFoundError: If schema doesn't exist
        PatientSchemaError: If drop fails
    """
    if not schema_exists(patient_id, db_manager):
        raise SchemaNotFoundError(f"Schema for patient {patient_id} does not exist")

    schema_name = get_schema_name(patient_id)
    cascade_clause = "CASCADE" if cascade else "RESTRICT"

    query = f"DROP SCHEMA {schema_name} {cascade_clause};"

    try:
        logger.warning(f"Dropping patient schema: {schema_name}")
        # Ensure database connection
        if not db_manager.cursor:
            db_manager.connect()
        cursor = db_manager.cursor
        cursor.execute(query)
        logger.info(f"Successfully dropped schema: {schema_name}")
        return True
    except Exception as e:
        logger.error(f"Failed to drop schema {schema_name}: {e}")
        raise PatientSchemaError(f"Schema drop failed: {e}") from e


def list_patient_schemas(db_manager: DatabaseManager) -> List[Dict[str, Any]]:
    """List all patient schemas in database.

    Args:
        db_manager: Database manager instance

    Returns:
        List of dicts with schema information

    Example:
        >>> schemas = list_patient_schemas(db_manager)
        >>> for schema in schemas:
        ...     print(f"{schema['patient_id']}: {schema['schema_name']}")
        DEMO_HER2: patient_DEMO_HER2
        DEMO_TNBC: patient_DEMO_TNBC
    """
    query = """
        SELECT
            schema_name,
            REGEXP_REPLACE(schema_name, '^patient_', '') as patient_id
        FROM information_schema.schemata
        WHERE schema_name LIKE 'patient_%'
        ORDER BY schema_name;
    """

    schemas = []
    # Ensure database connection
    if not db_manager.cursor:
        db_manager.connect()
    cursor = db_manager.cursor
    cursor.execute(query)
    for row in cursor.fetchall():
        schemas.append({"schema_name": row[0], "patient_id": row[1]})

    logger.debug(f"Found {len(schemas)} patient schemas")
    return schemas


def validate_patient_schema(
    patient_id: str, db_manager: DatabaseManager
) -> Dict[str, Any]:
    """Validate patient schema integrity.

    Checks:
    - Schema exists
    - Required tables exist (expression_data, metadata)
    - No fold_change = 1.0 values (sparse storage constraint)
    - All transcript_ids exist in public.transcripts
    - Metadata table has exactly one row

    Args:
        patient_id: Patient identifier
        db_manager: Database manager instance

    Returns:
        Dict with validation results

    Example:
        >>> result = validate_patient_schema("DEMO_HER2", db_manager)
        >>> print(result['valid'])
        True
        >>> print(result['expression_count'])
        1247
    """
    if not schema_exists(patient_id, db_manager):
        return {
            "valid": False,
            "error": f"Schema does not exist for patient {patient_id}",
        }

    schema_name = get_schema_name(patient_id)
    results = {
        "valid": True,
        "schema_name": schema_name,
        "patient_id": patient_id,
        "checks": {},
    }

    # Ensure database connection
    if not db_manager.cursor:
        db_manager.connect()
    cursor = db_manager.cursor

    # Check 1: expression_data table exists and has data
    try:
        cursor.execute(f"SELECT COUNT(*) FROM {schema_name}.expression_data;")
        expression_count = cursor.fetchone()[0]
        results["expression_count"] = expression_count
        results["checks"]["expression_table"] = "PASS"
    except Exception as e:
        results["valid"] = False
        results["checks"]["expression_table"] = f"FAIL: {e}"

    # Check 2: No fold_change = 1.0 (sparse storage constraint)
    try:
        cursor.execute(
            f"""
            SELECT COUNT(*) FROM {schema_name}.expression_data
            WHERE expression_fold_change = 1.0;
        """
        )
        invalid_count = cursor.fetchone()[0]
        if invalid_count > 0:
            results["valid"] = False
            results["checks"][
                "sparse_storage"
            ] = f"FAIL: Found {invalid_count} rows with fold_change=1.0"
        else:
            results["checks"]["sparse_storage"] = "PASS"
    except Exception as e:
        results["checks"]["sparse_storage"] = f"SKIP: {e}"

    # Check 3: All transcript_ids exist in public.transcripts
    try:
        cursor.execute(
            f"""
            SELECT COUNT(*) FROM {schema_name}.expression_data pe
            LEFT JOIN public.transcripts t ON pe.transcript_id = t.transcript_id
            WHERE t.transcript_id IS NULL;
        """
        )
        orphaned = cursor.fetchone()[0]
        if orphaned > 0:
            results["valid"] = False
            results["checks"][
                "transcript_references"
            ] = f"FAIL: Found {orphaned} orphaned transcript_ids"
        else:
            results["checks"]["transcript_references"] = "PASS"
    except Exception as e:
        results["checks"]["transcript_references"] = f"SKIP: {e}"

    # Check 4: Metadata table exists with exactly one row
    try:
        cursor.execute(f"SELECT COUNT(*) FROM {schema_name}.metadata;")
        metadata_count = cursor.fetchone()[0]
        if metadata_count == 1:
            results["checks"]["metadata"] = "PASS"

            # Fetch metadata
            cursor.execute(f"SELECT * FROM {schema_name}.metadata;")
            row = cursor.fetchone()
            if row:
                cols = [desc[0] for desc in cursor.description]
                results["metadata"] = dict(zip(cols, row))
        elif metadata_count == 0:
            results["checks"]["metadata"] = "WARN: No metadata row"
        else:
            results["valid"] = False
            results["checks"][
                "metadata"
            ] = f"FAIL: Multiple metadata rows ({metadata_count})"
    except Exception as e:
        results["checks"]["metadata"] = f"SKIP: {e}"

    logger.info(
        f"Schema validation for {patient_id}: "
        f"{'PASSED' if results['valid'] else 'FAILED'}"
    )

    return results


def get_patient_statistics(
    patient_id: str, db_manager: DatabaseManager
) -> Dict[str, Any]:
    """Get statistics for patient expression data.

    Args:
        patient_id: Patient identifier
        db_manager: Database manager instance

    Returns:
        Dict with statistics

    Example:
        >>> stats = get_patient_statistics("DEMO_HER2", db_manager)
        >>> print(f"Overexpressed genes: {stats['overexpressed_count']}")
        Overexpressed genes: 342
    """
    schema_name = get_schema_name(patient_id)

    stats = {"patient_id": patient_id, "schema_name": schema_name}

    # Ensure database connection
    if not db_manager.cursor:
        db_manager.connect()
    cursor = db_manager.cursor

    # Total transcripts with non-default expression
    cursor.execute(f"SELECT COUNT(*) FROM {schema_name}.expression_data;")
    stats["total_transcripts"] = cursor.fetchone()[0]

    # Overexpressed (fold_change > 2.0)
    cursor.execute(
        f"""
        SELECT COUNT(*) FROM {schema_name}.expression_data
        WHERE expression_fold_change > 2.0;
    """
    )
    stats["overexpressed_count"] = cursor.fetchone()[0]

    # Underexpressed (fold_change < 0.5)
    cursor.execute(
        f"""
        SELECT COUNT(*) FROM {schema_name}.expression_data
        WHERE expression_fold_change < 0.5;
    """
    )
    stats["underexpressed_count"] = cursor.fetchone()[0]

    # Fold change range
    cursor.execute(
        f"""
        SELECT
            MIN(expression_fold_change) as min_fc,
            MAX(expression_fold_change) as max_fc,
            AVG(expression_fold_change) as avg_fc,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY expression_fold_change) as median_fc
        FROM {schema_name}.expression_data;
    """
    )
    row = cursor.fetchone()
    stats["min_fold_change"] = float(row[0]) if row[0] else None
    stats["max_fold_change"] = float(row[1]) if row[1] else None
    stats["avg_fold_change"] = float(row[2]) if row[2] else None
    stats["median_fold_change"] = float(row[3]) if row[3] else None

    logger.debug(f"Statistics for {patient_id}: {stats}")
    return stats
