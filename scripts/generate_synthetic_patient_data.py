#!/usr/bin/env python3
"""
Generate biologically realistic synthetic patient transcriptome data.

Creates patient-specific expression profiles based on published cancer signatures:
- HER2+ breast cancer (ERBB2 amplification signature)
- TNBC (triple-negative, basal-like signature)
- Lung adenocarcinoma (EGFR-mutant signature)

Data is based on:
- Perou et al. Nature 2000 (breast cancer subtypes)
- Cancer Genome Atlas studies
- Clinical drug target expression thresholds

Usage:
    poetry run python scripts/generate_synthetic_patient_data.py \
        --cancer-type HER2_POSITIVE \
        --output examples/synthetic_patient_HER2.csv \
        --num-genes 500
"""

import argparse
import logging
import random
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import numpy as np
from rich.console import Console
from rich.table import Table

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db.database import get_db_manager
from src.utils.logging import setup_logging

console = Console()
logger = logging.getLogger(__name__)


# Cancer-specific expression signatures
# Format: {gene_symbol: (mean_fold_change, std_dev)}
CANCER_SIGNATURES = {
    "HER2_POSITIVE": {
        # HER2 amplicon (chromosome 17q12)
        "ERBB2": (6.0, 1.0),  # Strong amplification
        "GRB7": (4.5, 0.8),  # Co-amplified
        "PGAP3": (3.8, 0.7),  # Co-amplified
        "PNMT": (3.5, 0.6),  # Co-amplified
        # PI3K/AKT pathway activation
        "PIK3CA": (2.8, 0.5),
        "AKT1": (2.2, 0.4),
        "MTOR": (1.8, 0.3),
        # Cell cycle genes (proliferation)
        "MKI67": (3.5, 0.6),
        "CCND1": (3.2, 0.5),
        "CDK4": (2.5, 0.4),
        "E2F1": (2.8, 0.5),
        # ER signaling (if ER+/HER2+)
        "ESR1": (2.0, 0.4),
        "PGR": (1.8, 0.3),
        "GATA3": (2.2, 0.4),
        # Immune suppression
        "CD274": (0.6, 0.2),  # PD-L1 low
        "PDCD1": (0.5, 0.2),  # PD-1 low
        "CD8A": (0.4, 0.15),  # T cell infiltration low
        # Tumor suppressors (often intact in HER2+)
        "TP53": (0.9, 0.2),
        "PTEN": (0.7, 0.2),
        "RB1": (1.0, 0.2),
    },
    "TNBC": {
        # Triple-negative markers
        "ESR1": (0.2, 0.05),  # ER negative
        "PGR": (0.25, 0.05),  # PR negative
        "ERBB2": (0.8, 0.15),  # HER2 normal/low
        # Basal-like markers
        "KRT5": (4.5, 0.8),
        "KRT14": (4.2, 0.7),
        "KRT17": (3.8, 0.6),
        "EGFR": (3.5, 0.6),  # Basal EGFR expression
        # High proliferation
        "MKI67": (5.5, 1.0),  # Very high
        "CCNE1": (4.0, 0.7),
        "CDK1": (4.2, 0.7),
        "PCNA": (4.5, 0.8),
        # TP53 pathway loss (80% of TNBC)
        "TP53": (0.3, 0.1),
        "CDKN1A": (0.4, 0.1),  # p21
        "MDM2": (0.5, 0.15),
        "BAX": (0.6, 0.15),
        # DNA repair deficiency
        "BRCA1": (0.5, 0.15),
        "RAD51": (0.6, 0.15),
        # Immune infiltration (variable, using moderate)
        "CD8A": (2.5, 0.5),
        "CD274": (2.0, 0.4),  # PD-L1 often high
        "PDCD1": (1.8, 0.4),
        # EMT markers
        "VIM": (3.5, 0.6),  # Vimentin
        "CDH2": (3.0, 0.5),  # N-cadherin
        "CDH1": (0.5, 0.15),  # E-cadherin loss
    },
    "LUAD_EGFR": {
        # EGFR pathway activation
        "EGFR": (4.5, 0.8),
        "ERBB3": (2.8, 0.5),
        "KRAS": (1.2, 0.3),  # Mutually exclusive with EGFR
        "BRAF": (1.0, 0.2),
        # Downstream EGFR signaling
        "AKT1": (3.2, 0.6),
        "MAPK1": (2.8, 0.5),
        "PIK3CA": (2.5, 0.5),
        "STAT3": (3.0, 0.6),
        # Loss of lung differentiation
        "SFTPA1": (0.3, 0.1),  # Surfactant protein A1
        "SFTPB": (0.3, 0.1),  # Surfactant protein B
        "SFTPC": (0.25, 0.08),  # Surfactant protein C
        "SCGB1A1": (0.4, 0.12),  # Clara cell marker
        # Angiogenesis
        "VEGFA": (4.0, 0.7),
        "ANGPT2": (3.2, 0.6),
        "FGF2": (2.8, 0.5),
        # Proliferation
        "MKI67": (3.5, 0.6),
        "CCND1": (3.0, 0.5),
        "CDK4": (2.5, 0.4),
        # Tumor suppressors (often mutated in LUAD)
        "TP53": (0.6, 0.2),
        "STK11": (0.5, 0.15),  # LKB1
        "KEAP1": (0.6, 0.15),
        # Immune markers (variable)
        "CD274": (1.5, 0.3),
        "PDCD1": (1.2, 0.3),
        "CD8A": (1.8, 0.4),
        # Breast-specific genes (should be very low)
        "ESR1": (0.1, 0.03),
        "PGR": (0.1, 0.03),
        "ERBB2": (0.8, 0.2),
    },
}


class SyntheticPatientGenerator:
    """Generate synthetic patient transcriptome data."""

    def __init__(self, seed: int = 42):
        """Initialize generator."""
        # Initialize database manager with environment variables
        self.db_manager = get_db_manager(config={})
        self.seed = seed
        random.seed(seed)
        np.random.seed(seed)

    def get_random_transcripts(self, n: int = 500) -> pd.DataFrame:
        """Get random transcript IDs and gene symbols from database."""
        logger.info(f"Fetching {n} random transcripts from database")

        # Use subquery to get random transcripts (avoid DISTINCT + ORDER BY conflict)
        query = """
            SELECT
                t.transcript_id,
                g.gene_symbol
            FROM public.transcripts t
            JOIN public.genes g ON t.gene_id = g.gene_id
            WHERE g.gene_symbol IS NOT NULL
            ORDER BY RANDOM()
            LIMIT %s
        """

        # Ensure database connection
        if not self.db_manager.cursor:
            self.db_manager.connect()

        cursor = self.db_manager.cursor
        cursor.execute(query, (n,))
        transcripts = pd.DataFrame(
            cursor.fetchall(), columns=["transcript_id", "gene_symbol"]
        )

        logger.info(f"Retrieved {len(transcripts)} transcripts")
        return transcripts

    def generate_baseline_expression(self, n: int) -> np.ndarray:
        """
        Generate baseline expression for non-signature genes.

        Uses log-normal distribution centered at fold_change = 1.0
        with biological noise.
        """
        # Log-normal: mean=1.0, spread ~0.7-1.4 for most genes
        log_mean = 0.0  # log(1.0) = 0
        log_std = 0.15  # ~15% biological variation

        baseline = np.random.lognormal(log_mean, log_std, n)

        # Clip extreme outliers
        baseline = np.clip(baseline, 0.3, 3.0)

        return baseline

    def generate_patient_data(
        self, cancer_type: str, num_genes: int = 500, output_file: Optional[Path] = None
    ) -> pd.DataFrame:
        """
        Generate synthetic patient data for specified cancer type.

        Args:
            cancer_type: One of 'HER2_POSITIVE', 'TNBC', 'LUAD_EGFR'
            num_genes: Total number of genes to include
            output_file: Optional output CSV path

        Returns:
            DataFrame with transcript_id and cancer_fold columns
        """
        if cancer_type not in CANCER_SIGNATURES:
            raise ValueError(
                f"Unknown cancer type: {cancer_type}. "
                f"Choose from: {list(CANCER_SIGNATURES.keys())}"
            )

        console.print(f"\n[bold]Generating synthetic patient data[/bold]")
        console.print(f"Cancer type: [cyan]{cancer_type}[/cyan]")
        console.print(f"Number of genes: {num_genes:,}")

        # Get random transcripts
        transcripts = self.get_random_transcripts(num_genes)

        # Get signature for this cancer type
        signature = CANCER_SIGNATURES[cancer_type]

        # Generate baseline expression
        fold_changes = self.generate_baseline_expression(len(transcripts))

        # Apply cancer signature
        signature_genes_found = 0
        for idx, row in transcripts.iterrows():
            gene_symbol = row["gene_symbol"]

            if gene_symbol in signature:
                mean_fc, std_fc = signature[gene_symbol]
                # Sample from normal distribution, clip to positive
                fc = np.random.normal(mean_fc, std_fc)
                fc = max(0.05, fc)  # Ensure positive
                fold_changes[idx] = fc
                signature_genes_found += 1

        # Create output dataframe
        output_df = pd.DataFrame(
            {"transcript_id": transcripts["transcript_id"], "cancer_fold": fold_changes}
        )

        # Statistics
        console.print(f"\n[bold green]Generation complete![/bold green]")
        console.print(
            f"Signature genes found: {signature_genes_found}/{len(signature)}"
        )
        console.print(f"Mean fold-change: {fold_changes.mean():.2f}")
        console.print(f"Median fold-change: {np.median(fold_changes):.2f}")

        # Show signature gene values
        table = Table(title="Signature Gene Expression")
        table.add_column("Gene", style="cyan")
        table.add_column("Expected FC", style="yellow")
        table.add_column("Generated FC", style="green")

        for gene_symbol in list(signature.keys())[:10]:
            mask = transcripts["gene_symbol"] == gene_symbol
            if mask.any():
                idx = transcripts[mask].index[0]
                expected_fc = signature[gene_symbol][0]
                generated_fc = fold_changes[idx]
                table.add_row(gene_symbol, f"{expected_fc:.2f}", f"{generated_fc:.2f}")

        console.print(table)

        # Write output
        if output_file:
            output_df.to_csv(output_file, index=False)
            console.print(f"\nWritten to: {output_file}")

        return output_df


def main():
    """Main generation function."""
    parser = argparse.ArgumentParser(
        description="Generate synthetic patient transcriptome data"
    )
    parser.add_argument(
        "--cancer-type",
        type=str,
        required=True,
        choices=["HER2_POSITIVE", "TNBC", "LUAD_EGFR"],
        help="Cancer type to simulate",
    )
    parser.add_argument(
        "--output", type=Path, required=True, help="Output CSV file path"
    )
    parser.add_argument(
        "--num-genes",
        type=int,
        default=500,
        help="Number of genes to include (default: 500)",
    )
    parser.add_argument(
        "--seed", type=int, default=42, help="Random seed for reproducibility"
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
    setup_logging(log_level=args.log_level)

    # Generate data
    generator = SyntheticPatientGenerator(seed=args.seed)
    generator.generate_patient_data(
        cancer_type=args.cancer_type, num_genes=args.num_genes, output_file=args.output
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
