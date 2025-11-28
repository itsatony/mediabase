#!/usr/bin/env python3
"""
Migration script for MEDIABASE v0.6.0 - Shared Core Architecture.

This script migrates from the old per-patient database architecture to the
new shared core + patient schemas architecture.

Usage:
    # Import single patient from CSV
    python scripts/migrate_to_shared_core.py \\
        --patient-id DEMO_HER2 \\
        --csv-file examples/synthetic_patient_HER2.csv \\
        --cancer-type "Breast Cancer" \\
        --cancer-subtype "HER2+"

    # Import multiple patients
    python scripts/migrate_to_shared_core.py \\
        --batch-import examples/patient_manifest.json

Architecture:
    OLD: Separate database per patient (mediabase_patient_<ID>)
    NEW: Single mbase database with patient_<ID> schemas
"""

import argparse
import csv
import json
import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.db.database import get_db_manager
from src.db.config import get_db_config
from src.db.patient_schema import (
    create_patient_schema,
    validate_patient_schema,
    get_patient_statistics,
    schema_exists,
    PatientSchemaError,
)
from src.utils.logging import setup_logging

logger = setup_logging(module_name=__name__)


class CSVImportError(Exception):
    """Raised when CSV import fails."""

    pass


def detect_csv_format(csv_path: Path) -> Dict[str, str]:
    """Detect CSV format by examining headers.

    Supported formats:
    - Standard: transcript_id, fold_change (or expression_fold_change)
    - DESeq2: SYMBOL (or gene), log2FoldChange (auto-converts to linear)

    Args:
        csv_path: Path to CSV file

    Returns:
        Dict with column mappings

    Raises:
        CSVImportError: If format cannot be detected
    """
    with open(csv_path, "r") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames

    if not headers:
        raise CSVImportError(f"CSV file has no headers: {csv_path}")

    logger.info(f"CSV headers: {headers}")

    # Detect transcript ID column
    transcript_col = None
    for col in ["transcript_id", "TRANSCRIPT_ID", "ensembl_transcript_id"]:
        if col in headers:
            transcript_col = col
            break

    # Detect fold change column
    fold_change_col = None
    is_log2 = False

    # Check for log2 format (DESeq2)
    for col in ["log2FoldChange", "log2FC", "logFC"]:
        if col in headers:
            fold_change_col = col
            is_log2 = True
            break

    # Check for linear format
    if not fold_change_col:
        for col in ["fold_change", "expression_fold_change", "cancer_fold", "fc", "FC"]:
            if col in headers:
                fold_change_col = col
                break

    if not transcript_col or not fold_change_col:
        raise CSVImportError(
            f"Could not detect required columns. "
            f"Headers: {headers}\n"
            f"Need: transcript_id and fold_change (or log2FoldChange)"
        )

    logger.info(
        f"Detected format: transcript_col={transcript_col}, "
        f"fold_change_col={fold_change_col}, is_log2={is_log2}"
    )

    return {
        "transcript_col": transcript_col,
        "fold_change_col": fold_change_col,
        "is_log2": is_log2,
    }


def parse_csv_file(
    csv_path: Path, column_mapping: Dict[str, str]
) -> List[Dict[str, Any]]:
    """Parse CSV file and extract expression data.

    Args:
        csv_path: Path to CSV file
        column_mapping: Column name mappings from detect_csv_format()

    Returns:
        List of dicts with transcript_id and fold_change

    Raises:
        CSVImportError: If parsing fails
    """
    transcript_col = column_mapping["transcript_col"]
    fold_change_col = column_mapping["fold_change_col"]
    is_log2 = column_mapping["is_log2"]

    expression_data = []
    skipped_count = 0
    invalid_count = 0

    logger.info(f"Parsing CSV file: {csv_path}")

    with open(csv_path, "r") as f:
        reader = csv.DictReader(f)
        total_rows = 0

        for row in reader:
            total_rows += 1

            # Extract values
            transcript_id = row.get(transcript_col, "").strip()
            fold_change_str = row.get(fold_change_col, "").strip()

            # Validate transcript ID
            if not transcript_id or not transcript_id.startswith("ENST"):
                invalid_count += 1
                continue

            # Parse fold change
            try:
                if is_log2:
                    log2_fc = float(fold_change_str)
                    fold_change = 2**log2_fc  # Convert log2 to linear
                else:
                    fold_change = float(fold_change_str)

                # Skip baseline values (sparse storage)
                if fold_change == 1.0:
                    skipped_count += 1
                    continue

                # Validate positive fold change
                if fold_change <= 0:
                    logger.warning(
                        f"Invalid fold_change {fold_change} for {transcript_id}, skipping"
                    )
                    invalid_count += 1
                    continue

                expression_data.append(
                    {"transcript_id": transcript_id, "fold_change": fold_change}
                )

            except (ValueError, TypeError) as e:
                logger.warning(
                    f"Could not parse fold_change '{fold_change_str}' "
                    f"for {transcript_id}: {e}"
                )
                invalid_count += 1
                continue

    logger.info(
        f"Parsed {total_rows} rows: "
        f"{len(expression_data)} valid, "
        f"{skipped_count} skipped (baseline), "
        f"{invalid_count} invalid"
    )

    if len(expression_data) == 0:
        raise CSVImportError("No valid expression data found in CSV")

    return expression_data


def import_expression_data(
    patient_id: str, expression_data: List[Dict[str, Any]], db_manager
) -> Dict[str, int]:
    """Import expression data into patient schema.

    Args:
        patient_id: Patient identifier
        expression_data: List of {transcript_id, fold_change} dicts
        db_manager: Database manager instance

    Returns:
        Dict with import statistics

    Raises:
        CSVImportError: If import fails
    """
    from src.db.patient_schema import get_schema_name

    schema_name = get_schema_name(patient_id)

    inserted_count = 0
    matched_count = 0
    unmatched_count = 0

    logger.info(f"Importing {len(expression_data)} expression values")

    # Batch insert for performance
    batch_size = 1000
    batches = [
        expression_data[i : i + batch_size]
        for i in range(0, len(expression_data), batch_size)
    ]

    try:
        # Ensure database connection
        if not db_manager.cursor:
            db_manager.connect()
        cursor = db_manager.cursor

        for batch_idx, batch in enumerate(batches):
            # First, check which transcripts exist in public.transcripts
            transcript_ids = [item["transcript_id"] for item in batch]
            placeholders = ",".join(["%s"] * len(transcript_ids))

            cursor.execute(
                f"SELECT transcript_id FROM public.transcripts WHERE transcript_id IN ({placeholders})",
                transcript_ids,
            )
            valid_ids = {row[0] for row in cursor.fetchall()}

            # Filter to only valid transcripts
            valid_data = [item for item in batch if item["transcript_id"] in valid_ids]

            matched_count += len(valid_data)
            unmatched_count += len(batch) - len(valid_data)

            # Batch insert valid data
            if valid_data:
                insert_query = f"""
                        INSERT INTO {schema_name}.expression_data
                            (transcript_id, expression_fold_change)
                        VALUES (%s, %s)
                        ON CONFLICT (transcript_id) DO UPDATE
                        SET expression_fold_change = EXCLUDED.expression_fold_change,
                            updated_at = CURRENT_TIMESTAMP
                    """

                values = [
                    (item["transcript_id"], item["fold_change"]) for item in valid_data
                ]

                cursor.executemany(insert_query, values)
                inserted_count += cursor.rowcount

                logger.info(
                    f"Batch {batch_idx + 1}/{len(batches)}: "
                    f"Inserted {cursor.rowcount} rows"
                )

        logger.info(
            f"Import complete: {inserted_count} inserted, "
            f"{matched_count} matched, {unmatched_count} unmatched"
        )

        return {
            "inserted": inserted_count,
            "matched": matched_count,
            "unmatched": unmatched_count,
            "total": len(expression_data),
        }

    except Exception as e:
        logger.error(f"Failed to import expression data: {e}")
        raise CSVImportError(f"Import failed: {e}") from e


def import_patient_from_csv(
    patient_id: str,
    csv_path: Path,
    metadata: Dict[str, Any],
    db_manager,
    overwrite: bool = False,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Import patient data from CSV file.

    Args:
        patient_id: Patient identifier
        csv_path: Path to CSV file
        metadata: Patient metadata dict
        db_manager: Database manager instance
        overwrite: If True, drop existing schema
        dry_run: If True, validate only without import

    Returns:
        Dict with import results

    Raises:
        CSVImportError: If import fails
    """
    logger.info(
        f"{'[DRY RUN] ' if dry_run else ''}Importing patient {patient_id} from {csv_path}"
    )

    # Detect CSV format
    column_mapping = detect_csv_format(csv_path)

    # Parse CSV
    expression_data = parse_csv_file(csv_path, column_mapping)

    if dry_run:
        logger.info(f"[DRY RUN] Would import {len(expression_data)} expression values")
        return {
            "success": True,
            "dry_run": True,
            "expression_count": len(expression_data),
        }

    # Create patient schema
    if schema_exists(patient_id, db_manager):
        if overwrite:
            logger.warning(f"Dropping existing schema for {patient_id}")
        else:
            raise CSVImportError(
                f"Schema for {patient_id} already exists. Use --overwrite to replace."
            )

    # Add import statistics to metadata
    metadata.update(
        {
            "source_file": str(csv_path.name),
            "total_transcripts_uploaded": len(expression_data),
        }
    )

    # Create schema
    create_result = create_patient_schema(
        patient_id=patient_id,
        db_manager=db_manager,
        metadata=metadata,
        overwrite=overwrite,
    )

    # Import expression data
    import_stats = import_expression_data(
        patient_id=patient_id, expression_data=expression_data, db_manager=db_manager
    )

    # Update metadata with final statistics
    from src.db.patient_schema import get_schema_name, insert_metadata

    final_metadata = metadata.copy()
    final_metadata.update(
        {
            "transcripts_matched": import_stats["matched"],
            "transcripts_unmatched": import_stats["unmatched"],
            "matching_success_rate": (
                import_stats["matched"] / import_stats["total"]
                if import_stats["total"] > 0
                else 0.0
            ),
        }
    )

    insert_metadata(
        patient_id=patient_id, metadata=final_metadata, db_manager=db_manager
    )

    # Validate schema
    validation = validate_patient_schema(patient_id, db_manager)

    # Get statistics
    stats = get_patient_statistics(patient_id, db_manager)

    logger.info(
        f"Successfully imported patient {patient_id}: "
        f"{stats['total_transcripts']} transcripts, "
        f"{stats['overexpressed_count']} overexpressed, "
        f"{stats['underexpressed_count']} underexpressed"
    )

    return {
        "success": True,
        "patient_id": patient_id,
        "schema_name": create_result["schema_name"],
        "import_stats": import_stats,
        "statistics": stats,
        "validation": validation,
    }


def batch_import_patients(
    manifest_path: Path, db_manager, dry_run: bool = False
) -> List[Dict]:
    """Import multiple patients from manifest file.

    Manifest JSON format:
    {
        "patients": [
            {
                "patient_id": "DEMO_HER2",
                "csv_file": "examples/synthetic_patient_HER2.csv",
                "cancer_type": "Breast Cancer",
                "cancer_subtype": "HER2+",
                "tissue_type": "breast",
                "sample_type": "tumor"
            },
            ...
        ]
    }

    Args:
        manifest_path: Path to manifest JSON file
        db_manager: Database manager instance
        dry_run: If True, validate only

    Returns:
        List of import results
    """
    logger.info(f"Loading manifest: {manifest_path}")

    with open(manifest_path, "r") as f:
        manifest = json.load(f)

    patients = manifest.get("patients", [])
    if not patients:
        raise CSVImportError("Manifest contains no patients")

    logger.info(f"Found {len(patients)} patients in manifest")

    results = []

    for patient_config in patients:
        patient_id = patient_config.get("patient_id")
        csv_file = patient_config.get("csv_file")

        if not patient_id or not csv_file:
            logger.error(f"Invalid patient config: {patient_config}")
            continue

        csv_path = Path(csv_file)
        if not csv_path.is_absolute():
            csv_path = PROJECT_ROOT / csv_path

        if not csv_path.exists():
            logger.error(f"CSV file not found: {csv_path}")
            continue

        # Extract metadata
        metadata = {
            k: v
            for k, v in patient_config.items()
            if k not in ["patient_id", "csv_file"]
        }

        try:
            result = import_patient_from_csv(
                patient_id=patient_id,
                csv_path=csv_path,
                metadata=metadata,
                db_manager=db_manager,
                overwrite=True,  # Batch import overwrites existing
                dry_run=dry_run,
            )
            results.append(result)

        except Exception as e:
            logger.error(f"Failed to import {patient_id}: {e}")
            results.append(
                {"success": False, "patient_id": patient_id, "error": str(e)}
            )

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Migrate to MEDIABASE v0.6.0 shared core architecture",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("--patient-id", help="Patient identifier (e.g., DEMO_HER2)")

    parser.add_argument("--csv-file", type=Path, help="Path to patient CSV file")

    parser.add_argument("--cancer-type", help='Cancer type (e.g., "Breast Cancer")')

    parser.add_argument("--cancer-subtype", help='Cancer subtype (e.g., "HER2+")')

    parser.add_argument("--tissue-type", help='Tissue type (e.g., "breast")')

    parser.add_argument(
        "--sample-type", default="tumor", help="Sample type (default: tumor)"
    )

    parser.add_argument(
        "--batch-import",
        type=Path,
        help="Import multiple patients from manifest JSON file",
    )

    parser.add_argument(
        "--overwrite", action="store_true", help="Overwrite existing patient schema"
    )

    parser.add_argument(
        "--dry-run", action="store_true", help="Validate CSV without importing"
    )

    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
    )

    args = parser.parse_args()

    # Set logging level
    logging.getLogger().setLevel(getattr(logging, args.log_level))

    # Load database config
    config = get_db_config()

    # Get database manager
    db_manager = get_db_manager(config)
    db_manager.connect()

    try:
        if args.batch_import:
            # Batch import mode
            results = batch_import_patients(
                manifest_path=args.batch_import,
                db_manager=db_manager,
                dry_run=args.dry_run,
            )

            # Print summary
            print("\n" + "=" * 70)
            print("BATCH IMPORT SUMMARY")
            print("=" * 70)

            for result in results:
                if result["success"]:
                    stats = result.get("statistics", {})
                    print(f"\n✓ {result['patient_id']}")
                    print(f"  Total transcripts: {stats.get('total_transcripts', 0)}")
                    print(f"  Overexpressed: {stats.get('overexpressed_count', 0)}")
                    print(f"  Underexpressed: {stats.get('underexpressed_count', 0)}")
                else:
                    print(
                        f"\n✗ {result['patient_id']}: {result.get('error', 'Unknown error')}"
                    )

            print("\n" + "=" * 70)

        elif args.patient_id and args.csv_file:
            # Single patient import mode
            metadata = {}

            if args.cancer_type:
                metadata["cancer_type"] = args.cancer_type
            if args.cancer_subtype:
                metadata["cancer_subtype"] = args.cancer_subtype
            if args.tissue_type:
                metadata["tissue_type"] = args.tissue_type
            if args.sample_type:
                metadata["sample_type"] = args.sample_type

            result = import_patient_from_csv(
                patient_id=args.patient_id,
                csv_path=args.csv_file,
                metadata=metadata,
                db_manager=db_manager,
                overwrite=args.overwrite,
                dry_run=args.dry_run,
            )

            if result["success"]:
                print(f"\n✓ Successfully imported {args.patient_id}")
                if not args.dry_run:
                    stats = result["statistics"]
                    print(f"  Schema: {result['schema_name']}")
                    print(f"  Total transcripts: {stats['total_transcripts']}")
                    print(f"  Overexpressed (>2x): {stats['overexpressed_count']}")
                    print(f"  Underexpressed (<0.5x): {stats['underexpressed_count']}")

        else:
            parser.print_help()
            sys.exit(1)

    except Exception as e:
        logger.error(f"Migration failed: {e}", exc_info=True)
        sys.exit(1)

    finally:
        db_manager.close()


if __name__ == "__main__":
    main()
