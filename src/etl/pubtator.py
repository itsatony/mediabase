"""PubTator Central module for Cancer Transcriptome Base.

This module handles downloading, processing, and integration of gene-publication
associations from PubTator Central, providing literature support for genes
and enabling research paper discovery for clinical contexts.

Source: PubTator Central (NCBI)
URL: https://ftp.ncbi.nlm.nih.gov/pub/lu/PubTatorCentral/
License: Public Domain (US Government work)
Update Frequency: Monthly
"""

# Standard library imports
import gzip
from pathlib import Path
from typing import Dict, List, Optional, Any, Set, Tuple, DefaultDict
from collections import defaultdict
from datetime import datetime

# Third party imports
from tqdm import tqdm
from rich.console import Console
from rich.table import Table

# Local imports
from .base_processor import BaseProcessor, DownloadError, ProcessingError, DatabaseError
from ..utils.logging import get_progress_bar

# Constants
PUBTATOR_URL = (
    "https://ftp.ncbi.nlm.nih.gov/pub/lu/PubTatorCentral/gene2pubtatorcentral.gz"
)
EXPECTED_COLUMNS = 5  # PMID, Type, GeneID, Mention, Method


class PubTatorProcessor(BaseProcessor):
    """Process and integrate gene-publication associations from PubTator Central.

    This processor:
    1. Downloads gene2pubtatorcentral.gz (~5GB compressed)
    2. Parses tab-separated gene-PMID associations
    3. Maps NCBI Gene IDs to internal gene_ids
    4. Aggregates mentions per gene-publication pair
    5. Stores in gene_publications table for LLM-assisted queries
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        """Initialize the PubTator processor with configuration.

        Args:
            config: Configuration dictionary with settings
        """
        super().__init__(config)

        # Define specific directory for PubTator data
        self.pubtator_dir = self.cache_dir / "pubtator"
        self.pubtator_dir.mkdir(exist_ok=True)

        # Source URL
        self.pubtator_url = config.get("pubtator_url", PUBTATOR_URL)

        # Processing statistics
        self.stats: Dict[str, int] = {
            "total_lines": 0,
            "valid_entries": 0,
            "unique_gene_pmid_pairs": 0,
            "mapped_genes": 0,
            "unmapped_genes": 0,
            "inserted_publications": 0,
        }

        # Console for rich output
        self.console = Console()

    def download_pubtator_data(self) -> Path:
        """Download PubTator Central gene2pubtatorcentral.gz file with caching.

        Returns:
            Path to the downloaded file

        Raises:
            DownloadError: If download fails
        """
        try:
            self.logger.info(
                "Downloading PubTator Central gene2pubtatorcentral.gz (~5GB)"
            )
            self.logger.info(
                "This may take several minutes depending on connection speed"
            )

            # Use the BaseProcessor download method with caching
            pubtator_file = self.download_file(
                url=self.pubtator_url,
                file_path=self.pubtator_dir / "gene2pubtatorcentral.gz",
            )

            self.logger.info(f"PubTator data available at: {pubtator_file}")
            return pubtator_file

        except Exception as e:
            raise DownloadError(f"Failed to download PubTator Central data: {e}")

    def _load_gene_id_mapping(self) -> Dict[str, str]:
        """Load mapping from NCBI Gene IDs to internal gene_ids.

        Queries gene_cross_references table for GeneID entries to map
        external NCBI Gene IDs to our internal gene_id values.

        Returns:
            Dictionary mapping NCBI Gene ID (string) to internal gene_id

        Raises:
            DatabaseError: If query fails
        """
        try:
            self.logger.info("Loading NCBI Gene ID mappings from database")

            query = """
                SELECT DISTINCT external_id, gene_id
                FROM gene_cross_references
                WHERE external_db = 'GeneID'
                ORDER BY gene_id
            """

            if not self.ensure_connection() or not self.db_manager.cursor:
                raise DatabaseError(
                    "Cannot load gene ID mapping: no database connection"
                )

            self.db_manager.cursor.execute(query)
            results = self.db_manager.cursor.fetchall()

            # Build mapping dictionary: external_id (NCBI Gene ID) -> gene_id
            id_mapping = {row[0]: row[1] for row in results}

            self.logger.info(f"Loaded {len(id_mapping):,} NCBI Gene ID mappings")
            return id_mapping

        except Exception as e:
            raise DatabaseError(f"Failed to load gene ID mapping: {e}")

    def parse_pubtator_file(
        self, file_path: Path, gene_id_mapping: Dict[str, str]
    ) -> Dict[Tuple[str, str], Dict[str, Any]]:
        """Parse PubTator Central file and aggregate gene-publication associations.

        File format (tab-separated):
        PMID    Type    GeneID    Mention    Method

        Args:
            file_path: Path to gene2pubtatorcentral.gz file
            gene_id_mapping: Mapping from NCBI Gene ID to internal gene_id

        Returns:
            Dictionary with (gene_id, pmid) tuples as keys, containing:
            - mention_count: Number of times gene mentioned in paper
            - mentions: Set of unique mention text forms
            - methods: Set of identification methods used

        Raises:
            ProcessingError: If parsing fails
        """
        try:
            self.logger.info(f"Parsing PubTator Central file: {file_path}")

            # Data structure: {(gene_id, pmid): mention_count}
            # Memory optimization: Store only mention count (not unused mentions/methods sets)
            gene_publications: DefaultDict[Tuple[str, str], int] = defaultdict(int)

            unmapped_genes: Set[str] = set()
            line_count = 0

            # Open gzipped file and parse with progress bar
            with gzip.open(file_path, "rt", encoding="utf-8") as f:
                # Count total lines for progress bar (approximate from file size)
                # Rough estimate: ~50 bytes per line compressed
                file_size = file_path.stat().st_size
                estimated_lines = file_size // 50

                # Wrap the file iterator with tqdm for progress tracking
                for line in tqdm(
                    f,
                    desc="Parsing PubTator data",
                    total=estimated_lines,
                    unit=" lines",
                ):
                    line_count += 1

                    # Skip empty lines
                    if not line.strip():
                        continue

                    # Parse tab-separated fields
                    fields = line.strip().split("\t")

                    # Validate field count
                    if len(fields) != EXPECTED_COLUMNS:
                        self.logger.debug(
                            f"Skipping malformed line {line_count}: {len(fields)} fields"
                        )
                        continue

                    pmid, entry_type, gene_id_str, mention, method = fields

                    # Only process Gene entries (skip Disease, Chemical, etc.)
                    if entry_type != "Gene":
                        continue

                    # Map NCBI Gene ID to internal gene_id
                    internal_gene_id = gene_id_mapping.get(gene_id_str)

                    if internal_gene_id is None:
                        unmapped_genes.add(gene_id_str)
                        self.stats["unmapped_genes"] += 1
                        continue

                    # Aggregate data for this gene-publication pair
                    key = (internal_gene_id, pmid)
                    gene_publications[key] += 1

                    self.stats["valid_entries"] += 1

            self.stats["total_lines"] = line_count
            self.stats["unique_gene_pmid_pairs"] = len(gene_publications)
            self.stats["mapped_genes"] = len(
                set(gid for gid, _ in gene_publications.keys())
            )

            self.logger.info(f"Parsed {line_count:,} lines")
            self.logger.info(
                f"Found {self.stats['unique_gene_pmid_pairs']:,} unique gene-publication pairs"
            )
            self.logger.info(
                f"Mapped to {self.stats['mapped_genes']:,} genes in database"
            )

            if unmapped_genes:
                sample_unmapped = list(unmapped_genes)[:10]
                self.logger.warning(
                    f"Could not map {len(unmapped_genes):,} NCBI Gene IDs "
                    f"(sample: {', '.join(sample_unmapped)})"
                )

            return dict(gene_publications)

        except Exception as e:
            raise ProcessingError(f"Failed to parse PubTator file: {e}")

    def _extract_publication_year(self, pmid: str) -> Optional[int]:
        """Extract publication year from PMID by querying first digit.

        For now, returns None - full implementation would query PubMed API
        or use a PMID-to-year lookup table. This is a placeholder for future
        enhancement.

        Args:
            pmid: PubMed ID

        Returns:
            Publication year or None
        """
        # TODO: Implement PMID-to-year lookup
        # Options:
        # 1. Query PubMed E-utilities API (rate limited)
        # 2. Download PMID-year mapping file from NCBI
        # 3. Parse from full PubTator Central JSON files
        return None

    def insert_gene_publications(
        self, gene_publications: Dict[Tuple[str, str], Dict[str, Any]]
    ) -> None:
        """Insert gene-publication associations into database.

        Uses batch inserts for efficiency with ON CONFLICT handling to enable
        reprocessing without duplicates.

        Args:
            gene_publications: Dictionary of (gene_id, pmid) -> metadata

        Raises:
            DatabaseError: If insertion fails
        """
        try:
            self.logger.info("Inserting gene-publication associations into database")

            # Prepare batch data
            batch_data = []
            for (gene_id, pmid), mention_count in gene_publications.items():
                first_seen_year = self._extract_publication_year(pmid)

                batch_data.append((gene_id, pmid, mention_count, first_seen_year))

            # Insert in batches
            insert_query = """
                INSERT INTO gene_publications (gene_id, pmid, mention_count, first_seen_year)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (gene_id, pmid)
                DO UPDATE SET
                    mention_count = EXCLUDED.mention_count,
                    first_seen_year = EXCLUDED.first_seen_year,
                    last_updated = CURRENT_TIMESTAMP
            """

            # Ensure database connection is available
            if not self.ensure_connection() or not self.db_manager.cursor:
                raise DatabaseError("No database cursor available")

            # Use progress bar for batch inserts
            total_batches = (len(batch_data) + self.batch_size - 1) // self.batch_size

            with tqdm(
                total=len(batch_data), desc="Inserting publications", unit=" records"
            ) as pbar:
                for i in range(0, len(batch_data), self.batch_size):
                    batch = batch_data[i : i + self.batch_size]

                    self.db_manager.cursor.executemany(insert_query, batch)
                    if self.db_manager.conn and not self.db_manager.conn.closed:
                        self.db_manager.conn.commit()

                    pbar.update(len(batch))
                    self.stats["inserted_publications"] += len(batch)

            self.logger.info(
                f"Successfully inserted {self.stats['inserted_publications']:,} gene-publication associations"
            )

        except Exception as e:
            self.db_manager.conn.rollback()
            raise DatabaseError(f"Failed to insert gene publications: {e}")

    def _display_summary_statistics(self) -> None:
        """Display summary statistics in formatted table."""
        table = Table(title="PubTator Central Integration Summary", show_header=True)
        table.add_column("Metric", style="cyan", no_wrap=True)
        table.add_column("Count", style="magenta", justify="right")

        table.add_row("Total lines processed", f"{self.stats['total_lines']:,}")
        table.add_row("Valid gene entries", f"{self.stats['valid_entries']:,}")
        table.add_row(
            "Unique gene-PMID pairs", f"{self.stats['unique_gene_pmid_pairs']:,}"
        )
        table.add_row("Mapped genes", f"{self.stats['mapped_genes']:,}")
        table.add_row("Unmapped NCBI Gene IDs", f"{self.stats['unmapped_genes']:,}")
        table.add_row(
            "Inserted associations", f"{self.stats['inserted_publications']:,}"
        )

        self.console.print(table)

    def _verify_integration(self) -> Dict[str, Any]:
        """Verify gene_publications table after integration.

        Returns:
            Dictionary with verification metrics

        Raises:
            DatabaseError: If verification queries fail
        """
        try:
            self.logger.info("Verifying gene_publications table")

            verification_queries = {
                "total_associations": "SELECT COUNT(*) FROM gene_publications",
                "unique_genes": "SELECT COUNT(DISTINCT gene_id) FROM gene_publications",
                "unique_pmids": "SELECT COUNT(DISTINCT pmid) FROM gene_publications",
                "avg_mentions_per_gene": """
                    SELECT ROUND(AVG(pub_count)::numeric, 1)
                    FROM (
                        SELECT gene_id, COUNT(*) as pub_count
                        FROM gene_publications
                        GROUP BY gene_id
                    ) AS gene_counts
                """,
                "genes_with_high_literature": """
                    SELECT COUNT(*)
                    FROM (
                        SELECT gene_id, COUNT(*) as pub_count
                        FROM gene_publications
                        GROUP BY gene_id
                        HAVING COUNT(*) >= 100
                    ) AS high_lit_genes
                """,
            }

            # Ensure we have a valid connection and cursor
            if not self.ensure_connection() or not self.db_manager.cursor:
                raise DatabaseError("No database cursor available for verification")

            results = {}
            cursor = self.db_manager.cursor
            for metric, query in verification_queries.items():
                cursor.execute(query)
                result = cursor.fetchone()[0]
                results[metric] = result
                self.logger.info(f"{metric}: {result}")

            return results

        except Exception as e:
            raise DatabaseError(f"Failed to verify gene_publications: {e}")

    def run(self) -> None:
        """Execute the complete PubTator Central ETL workflow.

        Workflow:
        1. Download gene2pubtatorcentral.gz (~5GB)
        2. Load gene ID mappings from database
        3. Parse and aggregate gene-publication associations
        4. Insert into gene_publications table
        5. Verify and display statistics

        Raises:
            ETLError: If any step fails
        """
        try:
            self.logger.info("=" * 80)
            self.logger.info("Starting PubTator Central ETL Process")
            self.logger.info("=" * 80)

            # Step 1: Download data
            pubtator_file = self.download_pubtator_data()

            # Step 2: Load gene ID mappings
            gene_id_mapping = self._load_gene_id_mapping()

            if not gene_id_mapping:
                raise ProcessingError(
                    "No gene ID mappings found. Ensure id_enrichment module has been run."
                )

            # Step 3: Parse file and aggregate associations
            gene_publications = self.parse_pubtator_file(pubtator_file, gene_id_mapping)

            # Step 4: Insert into database
            self.insert_gene_publications(gene_publications)

            # Step 5: Verify integration
            verification_results = self._verify_integration()

            # Display summary
            self._display_summary_statistics()

            self.logger.info("=" * 80)
            self.logger.info("PubTator Central ETL Process Completed Successfully")
            self.logger.info("=" * 80)

        except Exception as e:
            self.logger.error(f"PubTator Central ETL failed: {e}")
            raise


def main() -> None:
    """Main entry point for standalone execution."""
    import sys
    from pathlib import Path

    # Add project root to path
    project_root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(project_root))

    from src.db.database import get_db_manager

    # Configuration
    config = {
        "cache_dir": "/tmp/mediabase/cache",
        "cache_ttl": 86400 * 7,  # 7 days for large files
        "batch_size": 5000,  # Larger batches for bulk insert
        "log_level": "INFO",
        "db": {
            "host": "localhost",
            "port": 5435,
            "dbname": "mbase",
            "user": "mbase_user",
            "password": "mbase_secret",
        },
    }

    # Run processor
    processor = PubTatorProcessor(config)
    processor.run()


if __name__ == "__main__":
    main()
