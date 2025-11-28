"""Drug Repurposing Hub integration module for Cancer Transcriptome Base.

This module downloads, processes, and integrates drug data from the Broad Institute 
Drug Repurposing Hub into transcript records, providing clinical trial phase information
and therapeutic targeting data.
"""

# Standard library imports
import csv
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Any, Set, Tuple
from datetime import datetime
from collections import defaultdict, Counter

# Third party imports
import pandas as pd
import requests
from tqdm import tqdm
from rich.console import Console
from rich.table import Table

# Local imports
from .base_processor import BaseProcessor, DownloadError, ProcessingError, DatabaseError
from ..utils.logging import get_progress_bar

# Constants
REPURPOSING_HUB_URL = "https://s3.amazonaws.com/data.clue.io/repurposing/downloads/repurposing_drugs_20200324.txt"
REPURPOSING_HUB_CACHE_TTL = 30 * 24 * 60 * 60  # 30 days in seconds

# Clinical phase mapping for scoring
CLINICAL_PHASE_SCORES = {
    "Launched": 5,  # FDA approved drugs
    "Phase 3": 4,  # Late-stage clinical trials
    "Phase 2": 3,  # Mid-stage clinical trials
    "Phase 1": 2,  # Early-stage clinical trials
    "Preclinical": 1,  # Pre-human studies
    "Unknown": 0,  # No clinical information
}


class DrugRepurposingHubProcessor(BaseProcessor):
    """Process drug data from Broad Institute Drug Repurposing Hub."""

    def __init__(self, config: Dict[str, Any]) -> None:
        """Initialize Drug Repurposing Hub processor with configuration.

        Args:
            config: Configuration dictionary containing settings
        """
        super().__init__(config)

        # Create Drug Repurposing Hub specific directory
        self.hub_dir = self.cache_dir / "drug_repurposing_hub"
        self.hub_dir.mkdir(exist_ok=True)

        # Data source URL
        self.hub_url = config.get("drug_repurposing_hub_url", REPURPOSING_HUB_URL)

        # Processing options
        self.skip_scores = config.get("skip_scores", False)
        self.force_download = config.get("force_download", False)

        # Schema version tracking
        self.required_schema_version = "0.1.5"  # Minimum schema version required

    def download_repurposing_hub_data(self) -> Path:
        """Download Drug Repurposing Hub dataset with caching.

        Returns:
            Path to the downloaded file

        Raises:
            DownloadError: If download fails
        """
        try:
            self.logger.info("Downloading Drug Repurposing Hub dataset")
            # Use the BaseProcessor download method
            hub_file = self.download_file(
                url=self.hub_url, file_path=self.hub_dir / "repurposing_drugs.txt"
            )
            return hub_file
        except Exception as e:
            raise DownloadError(f"Failed to download Drug Repurposing Hub data: {e}")

    def parse_target_string(self, target_string: str) -> List[str]:
        """Parse target string into individual gene symbols.

        Args:
            target_string: Pipe-separated string of gene symbols

        Returns:
            List of cleaned gene symbols
        """
        if not target_string or pd.isna(target_string):
            return []

        # Split by pipe and clean each symbol
        targets = [
            target.strip().upper()
            for target in str(target_string).split("|")
            if target.strip()
        ]
        return targets

    def process_repurposing_hub_data(
        self, hub_file: Path
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Process Drug Repurposing Hub data file.

        Args:
            hub_file: Path to the repurposing hub data file

        Returns:
            Dictionary mapping gene symbols to drug records

        Raises:
            ProcessingError: If processing fails
        """
        try:
            self.logger.info("Processing Drug Repurposing Hub data")

            # Read the file, skipping comment lines starting with !
            data_lines = []
            with open(hub_file, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip().startswith("!"):
                        data_lines.append(line)

            # Parse as TSV
            from io import StringIO

            data_text = "".join(data_lines)
            df = pd.read_csv(StringIO(data_text), sep="\t")

            self.logger.info(
                f"Loaded {len(df):,} drug records from Drug Repurposing Hub"
            )

            # Group drugs by target genes
            gene_drug_mapping = defaultdict(list)

            processing_stats = {
                "total_drugs": len(df),
                "drugs_with_targets": 0,
                "unique_targets": set(),
                "phase_distribution": Counter(),
            }

            progress_bar = get_progress_bar(
                total=len(df),
                desc="Processing drug records",
                module_name="drug_repurposing_hub",
            )

            try:
                for _, row in df.iterrows():
                    drug_name = (
                        str(row["pert_iname"])
                        if pd.notna(row["pert_iname"])
                        else "Unknown"
                    )
                    clinical_phase = (
                        str(row["clinical_phase"])
                        if pd.notna(row["clinical_phase"])
                        else "Unknown"
                    )
                    moa = (
                        str(row["moa"]) if pd.notna(row["moa"]) else "Unknown mechanism"
                    )
                    target_string = row["target"] if pd.notna(row["target"]) else ""
                    disease_area = (
                        str(row["disease_area"])
                        if pd.notna(row["disease_area"])
                        else "Unknown"
                    )
                    indication = (
                        str(row["indication"])
                        if pd.notna(row["indication"])
                        else "Unknown"
                    )

                    # Parse targets
                    targets = self.parse_target_string(target_string)

                    if targets:
                        processing_stats["drugs_with_targets"] += 1
                        processing_stats["unique_targets"].update(targets)

                    processing_stats["phase_distribution"][clinical_phase] += 1

                    # Create drug record
                    drug_record = {
                        "name": drug_name,
                        "clinical_phase": clinical_phase,
                        "mechanism_of_action": moa,
                        "disease_area": disease_area,
                        "indication": indication,
                        "clinical_score": CLINICAL_PHASE_SCORES.get(clinical_phase, 0),
                        "source": "Drug_Repurposing_Hub",
                        "targets": targets,
                    }

                    # Add to gene mapping for each target
                    for target in targets:
                        gene_drug_mapping[target].append(drug_record)

                    progress_bar.update(1)

            finally:
                progress_bar.close()

            # Log processing statistics
            self.logger.info(f"Drug Repurposing Hub processing statistics:")
            self.logger.info(f"  - Total drugs: {processing_stats['total_drugs']:,}")
            self.logger.info(
                f"  - Drugs with targets: {processing_stats['drugs_with_targets']:,}"
            )
            self.logger.info(
                f"  - Unique target genes: {len(processing_stats['unique_targets']):,}"
            )

            self.logger.info("Clinical phase distribution:")
            for phase, count in processing_stats["phase_distribution"].most_common():
                self.logger.info(f"  - {phase}: {count:,}")

            return dict(gene_drug_mapping)

        except Exception as e:
            raise ProcessingError(f"Failed to process Drug Repurposing Hub data: {e}")

    def update_transcript_drug_data(
        self, gene_drug_mapping: Dict[str, List[Dict[str, Any]]]
    ) -> None:
        """Update transcript records with Drug Repurposing Hub data.

        Args:
            gene_drug_mapping: Dictionary mapping gene symbols to drug records

        Raises:
            DatabaseError: If database operations fail
        """
        if not self.ensure_connection():
            raise DatabaseError("Database connection failed")

        try:
            self.logger.info(
                "Updating transcript records with Drug Repurposing Hub data"
            )

            # Get all genes in database that have drug repurposing targets
            if not self.db_manager.cursor:
                raise DatabaseError("No database cursor available")

            # Find genes in database that match our drug targets
            db_genes = set()
            self.db_manager.cursor.execute(
                """
                SELECT DISTINCT gene_symbol 
                FROM cancer_transcript_base 
                WHERE gene_symbol IS NOT NULL
            """
            )

            for row in self.db_manager.cursor.fetchall():
                db_genes.add(row[0])

            # Find intersection with drug targets
            target_genes = set(gene_drug_mapping.keys())
            matching_genes = db_genes.intersection(target_genes)

            self.logger.info(
                f"Found {len(matching_genes):,} genes in database that have drug repurposing data"
            )
            self.logger.info(
                f"Database genes: {len(db_genes):,}, Drug targets: {len(target_genes):,}"
            )

            if not matching_genes:
                self.logger.warning(
                    "No gene overlap found between database and Drug Repurposing Hub"
                )
                return

            # Process updates in batches
            update_data = []

            progress_bar = get_progress_bar(
                total=len(matching_genes),
                desc="Preparing drug updates",
                module_name="drug_repurposing_hub",
            )

            try:
                for gene_symbol in matching_genes:
                    drugs = gene_drug_mapping[gene_symbol]

                    # Create drug data structure for database
                    drug_data = {}
                    for i, drug in enumerate(drugs):
                        drug_key = f"repurposing_{i+1}"
                        drug_data[drug_key] = {
                            "name": drug["name"],
                            "clinical_phase": drug["clinical_phase"],
                            "mechanism_of_action": drug["mechanism_of_action"],
                            "disease_area": drug["disease_area"],
                            "indication": drug["indication"],
                            "clinical_score": drug["clinical_score"],
                            "source": drug["source"],
                        }

                    update_data.append((json.dumps(drug_data), gene_symbol))
                    progress_bar.update(1)

            finally:
                progress_bar.close()

            # Execute batch update
            self.logger.info(
                f"Updating {len(update_data):,} transcript records with drug repurposing data"
            )

            try:
                self.db_manager.cursor.executemany(
                    """
                    UPDATE cancer_transcript_base 
                    SET drugs = COALESCE(drugs, '{}'::jsonb) || %s::jsonb
                    WHERE gene_symbol = %s
                """,
                    update_data,
                )

                if self.db_manager.conn:
                    self.db_manager.conn.commit()
            except Exception as e:
                if self.db_manager.conn:
                    self.db_manager.conn.rollback()
                raise e

            # Verify updates
            self.db_manager.cursor.execute(
                """
                SELECT COUNT(*) 
                FROM cancer_transcript_base 
                WHERE drugs ? 'repurposing_1'
            """
            )

            updated_count = self.db_manager.cursor.fetchone()[0]
            self.logger.info(
                f"Successfully updated {updated_count:,} records with drug repurposing data"
            )

        except Exception as e:
            raise DatabaseError(f"Failed to update transcript drug data: {e}")

    def calculate_repurposing_scores(self) -> None:
        """Calculate drug repurposing scores for genes with multiple drug options.

        Raises:
            DatabaseError: If score calculation fails
        """
        if not self.ensure_connection():
            raise DatabaseError("Database connection failed")

        try:
            self.logger.info("Calculating drug repurposing scores")

            if not self.db_manager.cursor:
                raise DatabaseError("No database cursor available")

            # Get genes with drug repurposing data
            self.db_manager.cursor.execute(
                """
                SELECT gene_symbol, drugs 
                FROM cancer_transcript_base 
                WHERE drugs ? 'repurposing_1'
            """
            )

            genes_with_drugs = self.db_manager.cursor.fetchall()
            self.logger.info(
                f"Calculating scores for {len(genes_with_drugs):,} genes with drug repurposing data"
            )

            if not genes_with_drugs:
                self.logger.warning("No genes found with drug repurposing data")
                return

            score_updates = []

            progress_bar = get_progress_bar(
                total=len(genes_with_drugs),
                desc="Calculating repurposing scores",
                module_name="drug_repurposing_hub",
            )

            try:
                for gene_symbol, drugs_json in genes_with_drugs:
                    drugs_data = drugs_json if isinstance(drugs_json, dict) else {}

                    # Calculate overall repurposing score
                    repurposing_scores = {}
                    max_clinical_score = 0
                    total_drugs = 0

                    for drug_key, drug_info in drugs_data.items():
                        if drug_key.startswith("repurposing_"):
                            clinical_score = drug_info.get("clinical_score", 0)
                            repurposing_scores[drug_key] = clinical_score
                            max_clinical_score = max(max_clinical_score, clinical_score)
                            total_drugs += 1

                    if total_drugs > 0:
                        # Overall score considers max clinical phase and number of options
                        overall_score = max_clinical_score + (
                            total_drugs * 0.1
                        )  # Bonus for multiple options
                        repurposing_scores["overall_repurposing_score"] = round(
                            overall_score, 2
                        )
                        repurposing_scores["total_repurposing_drugs"] = total_drugs
                        repurposing_scores[
                            "max_clinical_phase_score"
                        ] = max_clinical_score

                        score_updates.append(
                            (json.dumps(repurposing_scores), gene_symbol)
                        )

                    progress_bar.update(1)

            finally:
                progress_bar.close()

            # Update drug scores
            if score_updates:
                self.logger.info(
                    f"Updating drug scores for {len(score_updates):,} genes"
                )

                try:
                    self.db_manager.cursor.executemany(
                        """
                        UPDATE cancer_transcript_base 
                        SET drug_scores = COALESCE(drug_scores, '{}'::jsonb) || %s::jsonb
                        WHERE gene_symbol = %s
                    """,
                        score_updates,
                    )

                    if self.db_manager.conn:
                        self.db_manager.conn.commit()
                except Exception as e:
                    if self.db_manager.conn:
                        self.db_manager.conn.rollback()
                    raise e

                self.logger.info("Drug repurposing score calculation completed")

        except Exception as e:
            raise DatabaseError(f"Failed to calculate repurposing scores: {e}")

    def generate_repurposing_summary(self) -> None:
        """Generate summary statistics for drug repurposing integration."""
        try:
            if not self.ensure_connection() or not self.db_manager.cursor:
                return

            console = Console()

            # Get summary statistics
            self.db_manager.cursor.execute(
                """
                SELECT 
                    COUNT(*) as total_genes,
                    COUNT(*) FILTER (WHERE drugs ? 'repurposing_1') as genes_with_repurposing,
                    AVG((drug_scores->>'overall_repurposing_score')::float) FILTER (WHERE drug_scores ? 'overall_repurposing_score') as avg_repurposing_score
                FROM cancer_transcript_base
            """
            )

            stats = self.db_manager.cursor.fetchone()

            # Create summary table
            table = Table(title="Drug Repurposing Hub Integration Results")
            table.add_column("Metric", style="cyan")
            table.add_column("Count", style="green")
            table.add_column("Coverage", style="yellow")

            total_genes = stats[0]
            genes_with_repurposing = stats[1]
            avg_score = stats[2] if stats[2] else 0

            coverage = (
                (genes_with_repurposing / total_genes * 100) if total_genes > 0 else 0
            )

            table.add_row("Total Genes", f"{total_genes:,}", "100.0%")
            table.add_row(
                "With Repurposing Data",
                f"{genes_with_repurposing:,}",
                f"{coverage:.1f}%",
            )
            table.add_row("Avg Repurposing Score", f"{avg_score:.2f}", "-")

            console.print(table)

            # Log key statistics
            self.logger.info(f"Drug Repurposing Hub integration statistics:")
            self.logger.info(f"  - Total genes: {total_genes:,}")
            self.logger.info(
                f"  - Genes with repurposing data: {genes_with_repurposing:,} ({coverage:.1f}%)"
            )
            self.logger.info(f"  - Average repurposing score: {avg_score:.2f}")

        except Exception as e:
            self.logger.warning(f"Failed to generate repurposing summary: {e}")

    def run(self) -> None:
        """Run the complete Drug Repurposing Hub processing pipeline.

        Steps:
        1. Download Drug Repurposing Hub dataset
        2. Process drug-target relationships
        3. Update transcript records with drug data
        4. Calculate repurposing scores
        5. Generate summary statistics

        Raises:
            Various ETLError subclasses based on failure point
        """
        try:
            self.logger.info("Starting Drug Repurposing Hub processing pipeline")

            # Ensure database connection and schema
            if not self.ensure_connection():
                raise DatabaseError("Database connection failed")

            if not self.ensure_schema_version(self.required_schema_version):
                raise DatabaseError(f"Incompatible database schema version")

            # Download Drug Repurposing Hub data
            hub_file = self.download_repurposing_hub_data()

            # Process drug-target data
            gene_drug_mapping = self.process_repurposing_hub_data(hub_file)

            # Update transcript records
            self.update_transcript_drug_data(gene_drug_mapping)

            # Calculate scores if not skipped
            if not self.skip_scores:
                self.calculate_repurposing_scores()

            # Generate summary
            self.generate_repurposing_summary()

            self.logger.info("Drug Repurposing Hub processing completed successfully")

        except Exception as e:
            self.logger.error(f"Drug Repurposing Hub processing failed: {e}")
            raise
