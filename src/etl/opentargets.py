"""
Open Targets Platform ETL processor for cancer-gene-drug associations.

This module downloads and processes Open Targets Platform data, focusing on:
- Disease-gene associations (cancer-specific)
- Known drugs with clinical phases
- Target tractability assessments
- Drug mechanisms of action

Data source: ftp.ebi.ac.uk/pub/databases/opentargets/platform/
Format: Parquet files (preferred for efficiency)
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from tqdm import tqdm

from .base_processor import BaseProcessor, DownloadError, ProcessingError, DatabaseError
from ..db.database import DatabaseManager

logger = logging.getLogger(__name__)


@dataclass
class OpenTargetsConfig:
    """Configuration for Open Targets data processing."""

    version: str = "24.09"  # Release version
    base_url: str = "ftp://ftp.ebi.ac.uk/pub/databases/opentargets/platform"

    # Score thresholds for filtering
    min_overall_score: float = 0.5  # Moderate evidence threshold
    high_confidence_score: float = 0.7  # Strong evidence threshold

    # Cancer filtering
    cancer_therapeutic_areas: List[str] = None
    cancer_disease_ids: List[str] = None

    def __post_init__(self):
        """Initialize default cancer filters."""
        if self.cancer_therapeutic_areas is None:
            self.cancer_therapeutic_areas = [
                "neoplasm",
                "cancer",
                "carcinoma",
                "lymphoma",
                "leukemia",
                "sarcoma",
                "myeloma",
                "adenocarcinoma"
            ]

        if self.cancer_disease_ids is None:
            # Key EFO root terms for cancer
            self.cancer_disease_ids = [
                "EFO_0000616",  # neoplasm
                "MONDO_0004992",  # cancer
                "EFO_0000311",  # carcinoma
                "EFO_0000095",  # haematologic neoplasm
            ]


class OpenTargetsProcessor(BaseProcessor):
    """
    Process Open Targets Platform data for cancer genomics integration.

    This processor handles:
    1. Disease ontology with cancer classification
    2. Gene-disease associations with evidence scores
    3. Known drugs with clinical phase information
    4. Target tractability assessments
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        """
        Initialize Open Targets processor with configuration.

        Args:
            config: Configuration dictionary with settings
        """
        super().__init__(config)

        # Open Targets-specific configuration
        self.ot_config = OpenTargetsConfig()

        # Override with user-provided config values if present
        if 'opentargets_version' in config:
            self.ot_config.version = config['opentargets_version']
        if 'opentargets_min_score' in config:
            self.ot_config.min_overall_score = config['opentargets_min_score']

        # Build dataset URLs
        base = f"{self.ot_config.base_url}/{self.ot_config.version}/output/etl/parquet"
        self.dataset_urls = {
            "diseases": f"{base}/diseases",
            "associations": f"{base}/associationByOverallDirect",
            "known_drugs": f"{base}/knownDrugsAggregated",
            "targets": f"{base}/targets",
            "mechanisms": f"{base}/mechanismOfAction",
            "evidence_by_datatype": f"{base}/associationByDatatypeDirect"
        }

        # Define specific directory for Open Targets data
        self.opentargets_dir = self.cache_dir / 'opentargets'
        self.opentargets_dir.mkdir(exist_ok=True, parents=True)

        # Processing statistics
        self.stats: Dict[str, int] = {
            'diseases': 0,
            'cancer_diseases': 0,
            'associations': 0,
            'known_drugs': 0,
            'tractability': 0
        }

    def run(self) -> None:
        """Entry point for ETL orchestrator - calls process method."""
        try:
            success = self.process()
            if not success:
                raise ProcessingError("Open Targets ETL processing failed")
        except Exception as e:
            self.logger.error(f"Open Targets ETL failed: {e}", exc_info=True)
            raise

    def validate_requirements(self) -> bool:
        """
        Validate that required modules are processed.

        Open Targets requires:
        - transcript: For gene_id mapping
        - id_enrichment: For cross-database ID resolution

        Returns:
            bool: True if requirements are met
        """
        from ..db.database import DatabaseManager

        # Check required tables exist
        required_tables = ["genes", "gene_cross_references"]

        if not self.ensure_connection() or not self.db_manager.cursor:
            self.logger.error("Database connection failed")
            return False

        for table in required_tables:
            self.db_manager.cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'public'
                    AND table_name = %s
                )
            """, (table,))
            exists = self.db_manager.cursor.fetchone()[0]
            if not exists:
                self.logger.error(f"Required table {table} does not exist. "
                               f"Run transcripts and id_enrichment ETL first.")
                return False

        return True

    def process(self) -> bool:
        """
        Execute complete Open Targets ETL pipeline.

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            logger.info(f"Starting Open Targets ETL (version {self.ot_config.version})")

            # Validate prerequisites
            if not self.validate_requirements():
                return False

            # Schema tables already created by v0.5.0 migration
            # Skipping schema creation
            logger.info("Using existing Open Targets schema (created by v0.5.0 migration)")

            # Phase 1: Diseases
            logger.info("Processing diseases...")
            disease_count = self._process_diseases()
            logger.info(f"Loaded {disease_count} diseases ({self._count_cancer_diseases()} cancer)")

            # Phase 2: Gene-disease associations
            logger.info("Processing gene-disease associations...")
            assoc_count = self._process_associations()
            logger.info(f"Loaded {assoc_count} associations")

            # Phase 3: Known drugs
            logger.info("Processing known drugs...")
            drug_count = self._process_known_drugs()
            logger.info(f"Loaded {drug_count} drug-target-disease entries")

            # Phase 4: Target tractability
            logger.info("Processing target tractability...")
            tract_count = self._process_tractability()
            logger.info(f"Loaded {tract_count} tractability assessments")

            # Create indexes
            logger.info("Creating indexes...")
            self._create_indexes()

            # Record metadata
            self._record_metadata({
                "diseases": disease_count,
                "associations": assoc_count,
                "known_drugs": drug_count,
                "tractability": tract_count
            })

            logger.info("Open Targets ETL completed successfully")
            return True

        except Exception as e:
            logger.error(f"Open Targets ETL failed: {e}", exc_info=True)
            return False

    def _create_schema(self) -> None:
        """Create Open Targets database schema."""

        # Diseases table
        self.db_manager.cursor.execute("""
            CREATE TABLE IF NOT EXISTS opentargets_diseases (
                disease_id TEXT PRIMARY KEY,
                disease_name TEXT NOT NULL,
                disease_description TEXT,
                therapeutic_areas TEXT[],
                ontology_source TEXT,
                is_cancer BOOLEAN DEFAULT false,
                parent_disease_ids TEXT[],
                metadata JSONB,
                ot_version TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            );

            COMMENT ON TABLE opentargets_diseases IS
            'Disease ontology from Open Targets Platform. Contains cancer classifications and hierarchies for disease-gene associations. Use disease_id to join with associations.';

            COMMENT ON COLUMN opentargets_diseases.disease_id IS
            'EFO, MONDO, or other ontology identifier (e.g., EFO_0000616 for neoplasm)';

            COMMENT ON COLUMN opentargets_diseases.is_cancer IS
            'Boolean flag: true if disease is classified under neoplasm/cancer therapeutic areas';

            COMMENT ON COLUMN opentargets_diseases.parent_disease_ids IS
            'Array of parent disease IDs in ontology hierarchy (e.g., breast cancer -> carcinoma -> neoplasm)';
        """)

        # Gene-disease associations table
        self.db_manager.cursor.execute("""
            CREATE TABLE IF NOT EXISTS opentargets_gene_disease_associations (
                association_id SERIAL PRIMARY KEY,
                gene_id TEXT NOT NULL,
                disease_id TEXT NOT NULL REFERENCES opentargets_diseases(disease_id),
                overall_score NUMERIC(5,4) NOT NULL,

                genetic_association_score NUMERIC(5,4),
                somatic_mutation_score NUMERIC(5,4),
                known_drug_score NUMERIC(5,4),
                literature_score NUMERIC(5,4),
                rna_expression_score NUMERIC(5,4),
                pathways_systems_biology_score NUMERIC(5,4),
                animal_model_score NUMERIC(5,4),

                is_direct BOOLEAN DEFAULT true,
                evidence_count INTEGER,
                datasource_count INTEGER,

                tractability_clinical_precedence BOOLEAN,
                tractability_discovery_precedence BOOLEAN,

                metadata JSONB,
                ot_version TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),

                UNIQUE(gene_id, disease_id, ot_version)
            );

            COMMENT ON TABLE opentargets_gene_disease_associations IS
            'Gene-disease associations from Open Targets with evidence scores. Overall_score ≥0.5 indicates moderate evidence, ≥0.7 strong evidence. Join with gene_transcript on gene_id and opentargets_diseases on disease_id for clinical queries.';

            COMMENT ON COLUMN opentargets_gene_disease_associations.overall_score IS
            'Combined evidence score from 0-1. Threshold: ≥0.5 moderate, ≥0.7 strong, ≥0.85 very strong evidence';

            COMMENT ON COLUMN opentargets_gene_disease_associations.somatic_mutation_score IS
            'Cancer somatic mutation evidence score (Cancer Gene Census, COSMIC, IntOGen). Higher scores indicate well-established cancer genes.';

            COMMENT ON COLUMN opentargets_gene_disease_associations.known_drug_score IS
            'Evidence from approved or clinical-phase drugs targeting this gene for this disease. Higher scores indicate actionable targets.';
        """)

        # Known drugs table
        self.db_manager.cursor.execute("""
            CREATE TABLE IF NOT EXISTS opentargets_known_drugs (
                drug_id SERIAL PRIMARY KEY,
                molecule_chembl_id TEXT,
                molecule_name TEXT NOT NULL,
                molecule_type TEXT,

                target_gene_id TEXT,
                disease_id TEXT REFERENCES opentargets_diseases(disease_id),

                clinical_phase NUMERIC(3,1),
                clinical_phase_label TEXT,
                clinical_status TEXT,

                mechanism_of_action TEXT,
                action_type TEXT,

                drug_type TEXT,
                is_approved BOOLEAN,
                approval_year INTEGER,

                clinical_trial_ids TEXT[],

                metadata JSONB,
                ot_version TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            );

            COMMENT ON TABLE opentargets_known_drugs IS
            'Approved and clinical-stage drugs with target and disease associations from Open Targets. Clinical_phase=4 indicates approved drugs. Use for identifying actionable drug-target-disease combinations.';

            COMMENT ON COLUMN opentargets_known_drugs.clinical_phase IS
            'Clinical development phase: 0=preclinical, 1-3=clinical trials, 4=approved. NULL for withdrawn/terminated.';

            COMMENT ON COLUMN opentargets_known_drugs.is_approved IS
            'True if drug is approved for any indication (may differ from specific disease indication in this row)';
        """)

        # Target tractability table
        self.db_manager.cursor.execute("""
            CREATE TABLE IF NOT EXISTS opentargets_target_tractability (
                gene_id TEXT PRIMARY KEY,

                sm_clinical_precedence BOOLEAN,
                sm_discovery_precedence BOOLEAN,
                sm_predicted_tractable BOOLEAN,
                sm_top_bucket TEXT,

                ab_clinical_precedence BOOLEAN,
                ab_predicted_tractable BOOLEAN,
                ab_top_bucket TEXT,

                other_modality_tractable BOOLEAN,

                tractability_summary TEXT,

                metadata JSONB,
                ot_version TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            );

            COMMENT ON TABLE opentargets_target_tractability IS
            'Druggability assessment for gene targets from Open Targets. Clinical_precedence indicates drugs exist for this target or related family members. Use to assess likelihood of successful drug development.';
        """)

        # Metadata tracking table
        self.db_manager.cursor.execute("""
            CREATE TABLE IF NOT EXISTS opentargets_metadata (
                version TEXT PRIMARY KEY,
                release_date DATE,
                loaded_date TIMESTAMP DEFAULT NOW(),
                record_counts JSONB,
                validation_results JSONB,
                notes TEXT
            );
        """)

    def _process_diseases(self) -> int:
        """
        Download and process disease ontology data.

        Returns:
            int: Number of diseases loaded
        """
        # Download diseases Parquet file
        cache_path = self._download_dataset("diseases")

        # Read Parquet file
        df = pq.read_table(cache_path).to_pandas()

        # Transform to database format
        records = []
        for _, row in tqdm(df.iterrows(), total=len(df), desc="Processing diseases"):
            # Determine if cancer-related
            therapeutic_areas = row.get("therapeuticAreas", [])
            if therapeutic_areas is None or (hasattr(therapeutic_areas, '__len__') and len(therapeutic_areas) == 0):
                therapeutic_areas = []
            is_cancer = self._is_cancer_disease(
                therapeutic_areas,
                row.get("id", ""),
                row.get("name", "")
            )

            # Extract parent IDs from ontology
            parents = self._extract_parent_ids(row.get("parents", []))

            record = {
                "disease_id": row.get("id", "").replace(":", "_"),
                "disease_name": row.get("name", ""),
                "disease_description": row.get("description"),
                "therapeutic_areas": self._to_json_serializable(therapeutic_areas),
                "ontology_source": self._get_ontology_source(row.get("id", "")),
                "is_cancer": is_cancer,
                "parent_disease_ids": self._to_json_serializable(parents),
                "metadata": self._extract_disease_metadata(row),
                "ot_version": self.ot_config.version
            }
            records.append(record)

        # Batch insert
        if records:
            self._batch_insert_diseases(records)

        return len(records)

    def _process_associations(self) -> int:
        """
        Download and process gene-disease associations.

        Returns:
            int: Number of associations loaded
        """
        # Download associations Parquet file(s)
        cache_path = self._download_dataset("associations")

        # Read Parquet - may be partitioned
        df = self._read_parquet_dataset(cache_path)

        # Filter for cancer diseases and score threshold
        logger.info(f"Filtering associations: score >= {self.ot_config.min_overall_score}, cancer only")
        df = df[df["score"] >= self.ot_config.min_overall_score]

        # Get cancer disease IDs from database
        cancer_disease_ids = self._get_cancer_disease_ids()
        df = df[df["diseaseId"].isin(cancer_disease_ids)]

        logger.info(f"Retained {len(df)} associations after filtering")

        # Get gene ID mapping from database
        gene_id_map = self._get_gene_id_mapping()

        # Transform to database format
        records = []
        skipped = 0

        for _, row in tqdm(df.iterrows(), total=len(df), desc="Processing associations"):
            # Map target ID to our gene_id format
            target_id = row.get("targetId", "")
            gene_id = gene_id_map.get(target_id)

            if not gene_id:
                skipped += 1
                continue

            # Handle NULL disease_id safely
            disease_id_raw = row.get("diseaseId")
            if not disease_id_raw or pd.isna(disease_id_raw):
                skipped += 1
                continue
            disease_id = disease_id_raw.replace(":", "_")

            record = {
                "gene_id": gene_id,
                "disease_id": disease_id,
                "overall_score": self._safe_float(row.get("score", 0)),
                "is_direct": True,  # Using direct associations dataset
                "metadata": self._extract_association_metadata(row),
                "ot_version": self.ot_config.version
            }

            records.append(record)

        if skipped > 0:
            logger.warning(f"Skipped {skipped} associations due to unmapped gene IDs")

        # Batch insert
        if records:
            self._batch_insert_associations(records)

        return len(records)

    def _process_known_drugs(self) -> int:
        """
        Download and process known drugs data.

        Returns:
            int: Number of drug entries loaded
        """
        cache_path = self._download_dataset("known_drugs")

        df = self._read_parquet_dataset(cache_path)

        # Filter for cancer diseases
        cancer_disease_ids = self._get_cancer_disease_ids()
        df = df[df["diseaseId"].isin(cancer_disease_ids)]

        logger.info(f"Processing {len(df)} cancer drug entries")

        gene_id_map = self._get_gene_id_mapping()

        records = []
        for _, row in tqdm(df.iterrows(), total=len(df), desc="Processing drugs"):
            target_id = row.get("targetId", "")
            gene_id = gene_id_map.get(target_id)

            disease_id = row.get("diseaseId", "").replace(":", "_")

            # Determine if approved
            phase = row.get("phase", 0)
            # Safely handle None status values
            status = row.get("status") or ""
            is_approved = phase == 4 or status.lower() == "approved"

            record = {
                "molecule_chembl_id": row.get("drugId"),
                "molecule_name": row.get("prefName", ""),  # FIX Issue #21: Use prefName field
                "molecule_type": row.get("drugType"),
                "target_gene_id": gene_id,
                "disease_id": disease_id,
                "clinical_phase": self._safe_float(phase),
                "clinical_phase_label": self._format_phase_label(phase),
                "clinical_status": row.get("status"),
                "mechanism_of_action": row.get("mechanismOfAction"),
                "action_type": row.get("actionType"),
                "drug_type": row.get("drugType"),
                "is_approved": is_approved,
                "clinical_trial_ids": self._to_json_serializable(row.get("urls", [])),
                "metadata": self._extract_drug_metadata(row),
                "ot_version": self.ot_config.version
            }

            records.append(record)

        if records:
            self._batch_insert_drugs(records)

        return len(records)

    def _process_tractability(self) -> int:
        """
        Download and process target tractability data.

        Returns:
            int: Number of tractability assessments loaded
        """
        cache_path = self._download_dataset("targets")

        df = self._read_parquet_dataset(cache_path)

        gene_id_map = self._get_gene_id_mapping()

        records = []
        for _, row in tqdm(df.iterrows(), total=len(df), desc="Processing tractability"):
            target_id = row.get("id", "")
            gene_id = gene_id_map.get(target_id)

            if not gene_id:
                continue

            # Extract tractability assessments - FIX Issue #22: Parse array structure
            # Tractability is array of dicts: [{'modality': 'SM', 'id': 'Approved Drug', 'value': True}, ...]
            tractability_array = row.get("tractability", [])

            # Initialize flags
            sm_clinical = False
            sm_discovery = False
            sm_predicted = False
            ab_clinical = False
            ab_predicted = False
            sm_bucket = None
            ab_bucket = None

            # Parse tractability array if it exists and is not None
            if tractability_array is not None and not (isinstance(tractability_array, np.ndarray) and len(tractability_array) == 0):
                try:
                    for item in tractability_array:
                        if not isinstance(item, dict):
                            continue

                        modality = item.get("modality", "")
                        category = item.get("id", "")
                        value = item.get("value", False)

                        if modality == "SM":  # Small molecule
                            if value:
                                if category in ["Approved Drug", "Advanced Clinical"]:
                                    sm_clinical = True
                                    if not sm_bucket:
                                        sm_bucket = category
                                elif category in ["Phase 1 Clinical", "Structure with Ligand"]:
                                    sm_discovery = True
                                    if not sm_bucket:
                                        sm_bucket = category
                                elif category in ["High-Quality Ligand", "Druggable Family"]:
                                    sm_predicted = True
                                    if not sm_bucket:
                                        sm_bucket = category

                        elif modality == "AB":  # Antibody
                            if value:
                                if category in ["Approved Drug", "Advanced Clinical"]:
                                    ab_clinical = True
                                    if not ab_bucket:
                                        ab_bucket = category
                                elif category in ["Phase 1 Clinical", "UniProt loc high conf", "GO CC high conf"]:
                                    ab_predicted = True
                                    if not ab_bucket:
                                        ab_bucket = category
                except Exception as e:
                    logger.warning(f"Error parsing tractability for {target_id}: {e}")

            record = {
                "gene_id": gene_id,
                "sm_clinical_precedence": sm_clinical,
                "sm_discovery_precedence": sm_discovery,
                "sm_predicted_tractable": sm_predicted,
                "sm_top_bucket": sm_bucket,
                "ab_clinical_precedence": ab_clinical,
                "ab_predicted_tractable": ab_predicted,
                "ab_top_bucket": ab_bucket,
                "tractability_summary": self._generate_tractability_summary_from_flags(
                    sm_clinical, sm_discovery, sm_predicted, ab_clinical, ab_predicted
                ),
                # FIX Issue #23: Wrap array in dict for JSONB object compatibility
                "metadata": {"tractability": self._to_json_serializable(tractability_array)} if tractability_array is not None else {},
                "ot_version": self.ot_config.version
            }

            records.append(record)

        if records:
            self._batch_insert_tractability(records)

        return len(records)

    def _create_indexes(self) -> None:
        """Create indexes for query optimization."""

        indexes = [
            # Disease indexes
            "CREATE INDEX IF NOT EXISTS idx_ot_diseases_name ON opentargets_diseases USING gin(to_tsvector('english', disease_name))",
            "CREATE INDEX IF NOT EXISTS idx_ot_diseases_cancer ON opentargets_diseases(is_cancer) WHERE is_cancer = true",

            # Association indexes
            "CREATE INDEX IF NOT EXISTS idx_ot_assoc_gene ON opentargets_gene_disease_associations(gene_id)",
            "CREATE INDEX IF NOT EXISTS idx_ot_assoc_disease ON opentargets_gene_disease_associations(disease_id)",
            "CREATE INDEX IF NOT EXISTS idx_ot_assoc_score ON opentargets_gene_disease_associations(overall_score DESC)",
            "CREATE INDEX IF NOT EXISTS idx_ot_assoc_gene_score ON opentargets_gene_disease_associations(gene_id, overall_score DESC)",
            "CREATE INDEX IF NOT EXISTS idx_ot_assoc_cancer_genes ON opentargets_gene_disease_associations(gene_id, overall_score) WHERE overall_score >= 0.5",

            # Drug indexes
            "CREATE INDEX IF NOT EXISTS idx_ot_drugs_target ON opentargets_known_drugs(target_gene_id)",
            "CREATE INDEX IF NOT EXISTS idx_ot_drugs_disease ON opentargets_known_drugs(disease_id)",
            "CREATE INDEX IF NOT EXISTS idx_ot_drugs_approved ON opentargets_known_drugs(is_approved, clinical_phase)",
            "CREATE INDEX IF NOT EXISTS idx_ot_drugs_chembl ON opentargets_known_drugs(molecule_chembl_id) WHERE molecule_chembl_id IS NOT NULL",
            "CREATE INDEX IF NOT EXISTS idx_ot_drugs_name ON opentargets_known_drugs USING gin(to_tsvector('english', molecule_name))",

            # Tractability indexes
            "CREATE INDEX IF NOT EXISTS idx_ot_tract_sm ON opentargets_target_tractability(gene_id) WHERE sm_clinical_precedence = true OR sm_predicted_tractable = true",
        ]

        for idx_sql in tqdm(indexes, desc="Creating indexes"):
            try:
                self.db_manager.cursor.execute(idx_sql)
            except Exception as e:
                logger.warning(f"Index creation failed (may already exist): {e}")

    # Helper methods

    def _download_dataset(self, dataset_name: str) -> Path:
        """Download dataset from Open Targets FTP using wget.

        Args:
            dataset_name: Name of dataset to download

        Returns:
            Path to cached directory/file
        """
        import subprocess
        from ftplib import FTP
        import os

        url = self.dataset_urls[dataset_name]
        cache_key = self._get_cache_key(url)

        # Create dataset-specific cache directory
        cache_path = self.cache_dir / "opentargets" / dataset_name
        cache_path.mkdir(parents=True, exist_ok=True)

        # Check if already cached (recursively search subdirectories)
        if cache_path.exists() and list(cache_path.glob("**/*.parquet")):
            if not self.force_download:
                logger.info(f"Using cached {dataset_name} data at {cache_path}")
                return cache_path

        logger.info(f"Downloading {dataset_name} from Open Targets FTP...")

        # Use wget for FTP download with resume support
        try:
            cmd = [
                "wget",
                "-r",  # Recursive
                "-np",  # No parent directories
                "-nH",  # No host directories
                "--cut-dirs=6",  # Remove directory prefix
                "-P", str(cache_path),
                "-q",  # Quiet (use progress bar instead)
                "--show-progress",
                url
            ]

            subprocess.run(cmd, check=True)
            logger.info(f"Downloaded {dataset_name} to {cache_path}")
            return cache_path

        except subprocess.CalledProcessError as e:
            logger.error(f"FTP download failed for {dataset_name}: {e}")
            raise DownloadError(f"Failed to download {dataset_name}")

    def _get_cache_key(self, url: str) -> str:
        """Generate cache key from URL."""
        import hashlib
        return hashlib.sha256(url.encode()).hexdigest()[:16]

    def _read_parquet_dataset(self, path: Path) -> pd.DataFrame:
        """Read Parquet file or partitioned dataset."""
        if path.is_dir():
            return pq.read_table(path).to_pandas()
        else:
            return pq.read_table(path).to_pandas()

    def _is_cancer_disease(
        self,
        therapeutic_areas: List[str],
        disease_id: str,
        disease_name: str
    ) -> bool:
        """Determine if disease is cancer-related."""
        # Check therapeutic areas
        for area in therapeutic_areas:
            if any(keyword in area.lower() for keyword in self.ot_config.cancer_therapeutic_areas):
                return True

        # Check disease ID
        disease_id_normalized = disease_id.replace(":", "_")
        if disease_id_normalized in self.ot_config.cancer_disease_ids:
            return True

        # Check disease name
        cancer_keywords = ["cancer", "carcinoma", "neoplasm", "tumor", "lymphoma", "leukemia", "sarcoma"]
        disease_name_lower = disease_name.lower()
        return any(keyword in disease_name_lower for keyword in cancer_keywords)

    def _get_ontology_source(self, disease_id: str) -> str:
        """Extract ontology source from ID."""
        if ":" in disease_id:
            return disease_id.split(":")[0]
        elif "_" in disease_id:
            return disease_id.split("_")[0]
        return "UNKNOWN"

    def _extract_parent_ids(self, parents: List) -> List[str]:
        """Extract parent disease IDs from ontology."""
        if parents is None or (hasattr(parents, '__len__') and len(parents) == 0):
            return []
        return [p.replace(":", "_") for p in parents if isinstance(p, str)]

    def _to_json_serializable(self, value):
        """Convert numpy arrays/pandas Series to JSON-serializable types recursively."""
        import numpy as np
        if value is None:
            return None
        if isinstance(value, (np.ndarray, pd.Series)):
            return value.tolist()
        if isinstance(value, dict):
            return {k: self._to_json_serializable(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._to_json_serializable(item) for item in value]
        # Handle numpy scalar types
        if isinstance(value, (np.integer, np.floating)):
            return value.item()
        if isinstance(value, np.str_):
            return str(value)
        if isinstance(value, np.bool_):
            return bool(value)
        return value

    def _safe_float(self, value) -> Optional[float]:
        """Safely convert value to float, handling pandas.NA and numpy.nan.

        Args:
            value: Value to convert

        Returns:
            Float value or None if invalid
        """
        if value is None or pd.isna(value):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _extract_disease_metadata(self, row: pd.Series) -> Dict:
        """Extract additional disease metadata."""
        return {
            "synonyms": self._to_json_serializable(row.get("synonyms", [])),
            "dbXRefs": self._to_json_serializable(row.get("dbXRefs", []))
        }

    def _extract_association_metadata(self, row: pd.Series) -> Dict:
        """Extract association metadata."""
        return self._to_json_serializable({
            "datasources": row.get("datasources", [])
        })

    def _extract_drug_metadata(self, row: pd.Series) -> Dict:
        """Extract drug metadata."""
        return self._to_json_serializable({
            "references": row.get("references", [])
        })

    def _format_phase_label(self, phase: Optional[float]) -> str:
        """Format clinical phase as label."""
        if phase is None:
            return "Unknown"
        phase_map = {
            0: "Preclinical",
            1: "Phase I",
            2: "Phase II",
            3: "Phase III",
            4: "Approved"
        }
        return phase_map.get(int(phase), "Unknown")

    def _generate_tractability_summary(self, sm_data: Dict, ab_data: Dict) -> str:
        """Generate human-readable tractability summary."""
        parts = []

        if sm_data.get("clinicalPrecedence"):
            parts.append("Small molecule: Clinical precedence")
        elif sm_data.get("predictedTractable"):
            parts.append("Small molecule: Predicted tractable")

        if ab_data.get("clinicalPrecedence"):
            parts.append("Antibody: Clinical precedence")
        elif ab_data.get("predictedTractable"):
            parts.append("Antibody: Predicted tractable")

        return "; ".join(parts) if parts else "No tractability assessment"

    def _generate_tractability_summary_from_flags(
        self,
        sm_clinical: bool,
        sm_discovery: bool,
        sm_predicted: bool,
        ab_clinical: bool,
        ab_predicted: bool
    ) -> str:
        """Generate human-readable tractability summary from boolean flags.

        Used with new array-based tractability parsing (Fix Issue #22).
        """
        parts = []

        if sm_clinical:
            parts.append("Small molecule: Clinical precedence")
        elif sm_discovery:
            parts.append("Small molecule: Discovery precedence")
        elif sm_predicted:
            parts.append("Small molecule: Predicted tractable")

        if ab_clinical:
            parts.append("Antibody: Clinical precedence")
        elif ab_predicted:
            parts.append("Antibody: Predicted tractable")

        return "; ".join(parts) if parts else "No tractability assessment"

    def _get_cancer_disease_ids(self) -> List[str]:
        """Query cancer disease IDs from database."""
        if not self.ensure_connection() or not self.db_manager.cursor:
            return []
        self.db_manager.cursor.execute(
            "SELECT disease_id FROM opentargets_diseases WHERE is_cancer = true"
        )
        result = self.db_manager.cursor.fetchall()
        return [row[0] for row in result]

    def _get_gene_id_mapping(self) -> Dict[str, str]:
        """Get mapping from Ensembl gene ID to our gene_id format.

        In our schema, gene_id IS the Ensembl gene ID (ENSG...).
        This method returns a mapping for consistency with expected interface.
        """
        if not self.ensure_connection() or not self.db_manager.cursor:
            return {}
        # In our schema, gene_id column in genes table IS the Ensembl gene ID
        self.db_manager.cursor.execute("""
            SELECT gene_id, gene_id
            FROM genes
            WHERE gene_id LIKE 'ENSG%'
        """)
        result = self.db_manager.cursor.fetchall()
        return {row[0]: row[1] for row in result}

    def _count_cancer_diseases(self) -> int:
        """Count cancer diseases in database."""
        if not self.ensure_connection() or not self.db_manager.cursor:
            return 0
        self.db_manager.cursor.execute(
            "SELECT COUNT(*) FROM opentargets_diseases WHERE is_cancer = true"
        )
        result = self.db_manager.cursor.fetchone()
        return result[0] if result else 0

    def _batch_insert_diseases(self, records: List[Dict]) -> None:
        """Batch insert disease records."""
        from psycopg2.extras import execute_batch

        insert_sql = """
            INSERT INTO opentargets_diseases (
                disease_id, disease_name, disease_description,
                therapeutic_areas, ontology_source, is_cancer,
                parent_disease_ids, metadata, ot_version
            ) VALUES (
                %(disease_id)s, %(disease_name)s, %(disease_description)s,
                %(therapeutic_areas)s, %(ontology_source)s, %(is_cancer)s,
                %(parent_disease_ids)s, %(metadata)s::jsonb, %(ot_version)s
            )
            ON CONFLICT (disease_id) DO UPDATE SET
                disease_name = EXCLUDED.disease_name,
                disease_description = EXCLUDED.disease_description,
                therapeutic_areas = EXCLUDED.therapeutic_areas,
                is_cancer = EXCLUDED.is_cancer,
                parent_disease_ids = EXCLUDED.parent_disease_ids,
                metadata = EXCLUDED.metadata,
                updated_at = NOW()
        """

        if not self.ensure_connection() or not self.db_manager.cursor:
            raise DatabaseError("Database connection failed")

        # Convert metadata to JSON strings
        for record in records:
            if isinstance(record.get('metadata'), dict):
                import json
                record['metadata'] = json.dumps(record['metadata'])

        execute_batch(self.db_manager.cursor, insert_sql, records, page_size=self.batch_size)
        if self.db_manager.conn and not self.db_manager.conn.closed:
            self.db_manager.conn.commit()

    def _batch_insert_associations(self, records: List[Dict]) -> None:
        """Batch insert association records."""
        from psycopg2.extras import execute_batch

        insert_sql = """
            INSERT INTO opentargets_gene_disease_associations (
                gene_id, disease_id, overall_score,
                is_direct, metadata, ot_version
            ) VALUES (
                %(gene_id)s, %(disease_id)s, %(overall_score)s,
                %(is_direct)s, %(metadata)s::jsonb, %(ot_version)s
            )
            ON CONFLICT (gene_id, disease_id, ot_version) DO UPDATE SET
                overall_score = EXCLUDED.overall_score,
                is_direct = EXCLUDED.is_direct,
                metadata = EXCLUDED.metadata,
                updated_at = NOW()
        """

        if not self.ensure_connection() or not self.db_manager.cursor:
            raise DatabaseError("Database connection failed")

        # Convert metadata to JSON strings
        for record in records:
            if isinstance(record.get('metadata'), dict):
                import json
                record['metadata'] = json.dumps(record['metadata'])

        execute_batch(self.db_manager.cursor, insert_sql, records, page_size=self.batch_size)
        if self.db_manager.conn and not self.db_manager.conn.closed:
            self.db_manager.conn.commit()

    def _batch_insert_drugs(self, records: List[Dict]) -> None:
        """Batch insert drug records."""
        from psycopg2.extras import execute_batch

        insert_sql = """
            INSERT INTO opentargets_known_drugs (
                molecule_chembl_id, molecule_name, molecule_type,
                target_gene_id, disease_id, clinical_phase,
                clinical_phase_label, clinical_status, mechanism_of_action,
                action_type, drug_type, is_approved, clinical_trial_ids,
                metadata, ot_version
            ) VALUES (
                %(molecule_chembl_id)s, %(molecule_name)s, %(molecule_type)s,
                %(target_gene_id)s, %(disease_id)s, %(clinical_phase)s,
                %(clinical_phase_label)s, %(clinical_status)s, %(mechanism_of_action)s,
                %(action_type)s, %(drug_type)s, %(is_approved)s, %(clinical_trial_ids)s,
                %(metadata)s::jsonb, %(ot_version)s
            )
        """

        if not self.ensure_connection() or not self.db_manager.cursor:
            raise DatabaseError("Database connection failed")

        # Convert metadata to JSON strings
        for record in records:
            if isinstance(record.get('metadata'), dict):
                import json
                record['metadata'] = json.dumps(record['metadata'])

        execute_batch(self.db_manager.cursor, insert_sql, records, page_size=self.batch_size)
        if self.db_manager.conn and not self.db_manager.conn.closed:
            self.db_manager.conn.commit()

    def _batch_insert_tractability(self, records: List[Dict]) -> None:
        """Batch insert tractability records."""
        from psycopg2.extras import execute_batch

        insert_sql = """
            INSERT INTO opentargets_target_tractability (
                gene_id, sm_clinical_precedence, sm_discovery_precedence,
                sm_predicted_tractable, sm_top_bucket, ab_clinical_precedence,
                ab_predicted_tractable, ab_top_bucket, tractability_summary,
                metadata, ot_version
            ) VALUES (
                %(gene_id)s, %(sm_clinical_precedence)s, %(sm_discovery_precedence)s,
                %(sm_predicted_tractable)s, %(sm_top_bucket)s, %(ab_clinical_precedence)s,
                %(ab_predicted_tractable)s, %(ab_top_bucket)s, %(tractability_summary)s,
                %(metadata)s::jsonb, %(ot_version)s
            )
            ON CONFLICT (gene_id) DO UPDATE SET
                sm_clinical_precedence = EXCLUDED.sm_clinical_precedence,
                sm_discovery_precedence = EXCLUDED.sm_discovery_precedence,
                sm_predicted_tractable = EXCLUDED.sm_predicted_tractable,
                sm_top_bucket = EXCLUDED.sm_top_bucket,
                ab_clinical_precedence = EXCLUDED.ab_clinical_precedence,
                ab_predicted_tractable = EXCLUDED.ab_predicted_tractable,
                ab_top_bucket = EXCLUDED.ab_top_bucket,
                tractability_summary = EXCLUDED.tractability_summary,
                metadata = EXCLUDED.metadata,
                updated_at = NOW()
        """

        if not self.ensure_connection() or not self.db_manager.cursor:
            raise DatabaseError("Database connection failed")

        # Convert metadata to JSON strings
        for record in records:
            if isinstance(record.get('metadata'), dict):
                import json
                record['metadata'] = json.dumps(record['metadata'])

        execute_batch(self.db_manager.cursor, insert_sql, records, page_size=self.batch_size)
        if self.db_manager.conn and not self.db_manager.conn.closed:
            self.db_manager.conn.commit()

    def _record_metadata(self, counts: Dict[str, int]) -> None:
        """Record ETL metadata."""
        self.db_manager.cursor.execute("""
            INSERT INTO opentargets_metadata (version, record_counts)
            VALUES (%s, %s)
            ON CONFLICT (version) DO UPDATE
            SET record_counts = EXCLUDED.record_counts,
                loaded_date = NOW()
        """, (self.ot_config.version, counts))
