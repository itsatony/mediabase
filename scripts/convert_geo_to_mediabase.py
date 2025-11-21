#!/usr/bin/env python3
"""
Convert GEO expression data to MEDIABASE-compatible CSV format.

Handles multiple input formats:
- Gene symbols → Ensembl transcript ID lookup
- FPKM/TPM → fold-change vs. reference
- Log2 expression → linear fold-change
- z-scores → fold-change approximation

Usage:
    poetry run python scripts/convert_geo_to_mediabase.py \
        --input geo_expression.txt \
        --sample-id GSM123456 \
        --output patient_HER2.csv \
        --reference-type median
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Dict, Optional, Tuple

import pandas as pd
import numpy as np
from rich.console import Console
from rich.progress import track

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db.database import get_db_manager
from src.utils.logging import setup_logging

console = Console()
logger = logging.getLogger(__name__)


class GeoToMediabaseConverter:
    """Convert GEO expression data to MEDIABASE format."""

    def __init__(self):
        """Initialize converter with database connection."""
        self.db_manager = get_db_manager()
        self.gene_symbol_to_transcript = self._load_gene_mappings()

    def _load_gene_mappings(self) -> Dict[str, str]:
        """Load gene symbol → Ensembl transcript ID mappings from database."""
        logger.info("Loading gene symbol → transcript ID mappings from database")

        query = """
            SELECT DISTINCT
                gene_symbol,
                transcript_id
            FROM cancer_transcript_base
            WHERE gene_symbol IS NOT NULL
              AND transcript_id IS NOT NULL
        """

        with self.db_manager.get_cursor() as cursor:
            cursor.execute(query)
            mappings = {row[0]: row[1] for row in cursor.fetchall()}

        logger.info(f"Loaded {len(mappings):,} gene symbol mappings")
        return mappings

    def detect_format(
        self, df: pd.DataFrame, sample_column: str
    ) -> Tuple[str, Optional[str]]:
        """
        Detect input data format.

        Returns:
            Tuple of (format_type, value_column_name)
            format_type: 'fpkm', 'log2fc', 'zscore', 'counts'
        """
        # Get sample values
        values = df[sample_column].dropna()

        # Check for negative values (suggests log-scale or z-scores)
        has_negatives = (values < 0).any()

        # Check value range
        value_range = values.max() - values.min()
        value_mean = values.mean()

        if has_negatives and abs(value_mean) < 1:
            # Likely z-scores (mean ~0, range typically -3 to +3)
            return "zscore", sample_column
        elif has_negatives:
            # Likely log2 fold-change
            return "log2fc", sample_column
        elif value_range > 1000:
            # Likely raw counts
            return "counts", sample_column
        else:
            # Likely FPKM/TPM/normalized expression
            return "fpkm", sample_column

    def convert_to_fold_change(
        self,
        df: pd.DataFrame,
        sample_column: str,
        format_type: str,
        reference_values: Optional[pd.Series] = None,
    ) -> pd.Series:
        """
        Convert expression values to fold-change.

        Args:
            df: Input dataframe
            sample_column: Column with sample expression values
            format_type: Detected format type
            reference_values: Reference values for computing fold-change (optional)

        Returns:
            Series with fold-change values
        """
        values = df[sample_column]

        if format_type == "log2fc":
            # Already log2 fold-change, convert to linear
            return 2**values

        elif format_type == "zscore":
            # z-score: approximate fold-change
            # z = (x - mean) / sd
            # Approximate: FC = 2^(z * 0.5) for z>0, 1/(2^(|z|*0.5)) for z<0
            fold_changes = values.apply(
                lambda z: 2 ** (z * 0.5) if z >= 0 else 1 / (2 ** (abs(z) * 0.5))
            )
            return fold_changes

        elif format_type in ("fpkm", "counts"):
            # Need reference for fold-change calculation
            if reference_values is None:
                # Use median across all samples as reference
                reference = values.median()
            else:
                reference = reference_values

            # Avoid division by zero
            reference = reference.replace(0, 0.01)
            fold_changes = values / reference

            return fold_changes

        else:
            raise ValueError(f"Unsupported format type: {format_type}")

    def convert_geo_file(
        self,
        input_file: Path,
        sample_id: str,
        output_file: Path,
        gene_column: str = "gene_symbol",
        reference_type: str = "median",
    ) -> Dict[str, int]:
        """
        Convert GEO expression file to MEDIABASE format.

        Args:
            input_file: Path to input GEO file
            sample_id: Column name or sample ID in the file
            output_file: Path to output CSV
            gene_column: Name of column with gene symbols
            reference_type: 'median', 'mean', or 'normal' for reference calculation

        Returns:
            Statistics dictionary
        """
        console.print(f"\n[bold]Converting GEO data to MEDIABASE format[/bold]")
        console.print(f"Input: {input_file}")
        console.print(f"Output: {output_file}")

        # Read input file
        logger.info(f"Reading input file: {input_file}")
        df = pd.read_csv(input_file, sep="\t", comment="#")
        logger.info(f"Loaded {len(df):,} rows")

        # Detect format
        format_type, value_column = self.detect_format(df, sample_id)
        console.print(f"Detected format: [cyan]{format_type}[/cyan]")

        # Convert to fold-change
        logger.info("Converting to fold-change values")
        df["fold_change"] = self.convert_to_fold_change(df, sample_id, format_type)

        # Map gene symbols to transcript IDs
        logger.info("Mapping gene symbols to Ensembl transcript IDs")
        mapped_count = 0
        unmapped_genes = []

        output_rows = []
        for _, row in track(df.iterrows(), total=len(df), description="Mapping genes"):
            gene_symbol = row[gene_column]

            if gene_symbol in self.gene_symbol_to_transcript:
                transcript_id = self.gene_symbol_to_transcript[gene_symbol]
                output_rows.append(
                    {"transcript_id": transcript_id, "cancer_fold": row["fold_change"]}
                )
                mapped_count += 1
            else:
                unmapped_genes.append(gene_symbol)

        # Create output dataframe
        output_df = pd.DataFrame(output_rows)

        # Filter out invalid fold-change values
        output_df = output_df[
            (output_df["cancer_fold"] > 0)
            & (output_df["cancer_fold"] < 1000)
            & (~output_df["cancer_fold"].isna())
        ]

        # Write output
        output_df.to_csv(output_file, index=False)

        # Statistics
        stats = {
            "total_input_genes": len(df),
            "mapped_genes": mapped_count,
            "mapping_rate": mapped_count / len(df) * 100,
            "output_rows": len(output_df),
            "unmapped_genes": len(unmapped_genes),
        }

        console.print(f"\n[bold green]Conversion complete![/bold green]")
        console.print(f"Total input genes: {stats['total_input_genes']:,}")
        console.print(
            f"Mapped genes: {stats['mapped_genes']:,} ({stats['mapping_rate']:.1f}%)"
        )
        console.print(f"Output rows: {stats['output_rows']:,}")

        if unmapped_genes and len(unmapped_genes) < 20:
            console.print(f"\n[yellow]Unmapped genes:[/yellow]")
            for gene in unmapped_genes[:10]:
                console.print(f"  - {gene}")

        return stats


def main():
    """Main conversion function."""
    parser = argparse.ArgumentParser(
        description="Convert GEO expression data to MEDIABASE format"
    )
    parser.add_argument(
        "--input", type=Path, required=True, help="Input GEO expression file"
    )
    parser.add_argument(
        "--sample-id",
        type=str,
        required=True,
        help="Sample ID or column name with expression values",
    )
    parser.add_argument(
        "--output", type=Path, required=True, help="Output CSV file path"
    )
    parser.add_argument(
        "--gene-column",
        type=str,
        default="gene_symbol",
        help="Column name with gene symbols",
    )
    parser.add_argument(
        "--reference-type",
        type=str,
        choices=["median", "mean", "normal"],
        default="median",
        help="Reference calculation method",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level",
    )

    args = parser.parse_args()

    # Setup logging
    setup_logging(level=args.log_level)

    # Convert
    converter = GeoToMediabaseConverter()
    stats = converter.convert_geo_file(
        input_file=args.input,
        sample_id=args.sample_id,
        output_file=args.output,
        gene_column=args.gene_column,
        reference_type=args.reference_type,
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
