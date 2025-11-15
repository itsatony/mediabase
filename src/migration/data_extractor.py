"""Robust Data Extractor for MEDIABASE Migration.

This module provides comprehensive data extraction from the corrupted current system
with extensive error handling, data validation, and recovery mechanisms for handling
real-world data quality issues.
"""

import re
import json
import uuid
from typing import Dict, List, Optional, Any, Tuple, Set
from collections import defaultdict, Counter
from pathlib import Path

import pandas as pd
from tqdm import tqdm

from ..db.database import DatabaseManager
from ..utils.logging import get_logger
from ..utils.gene_matcher import normalize_gene_symbol, match_genes_bulk

logger = get_logger(__name__)


class ExtractionError(Exception):
    """Custom exception for data extraction errors."""
    pass


class RobustDataExtractor:
    """Extract data from corrupted current system with comprehensive error handling."""

    def __init__(self, db_manager: DatabaseManager, config: Dict[str, Any]):
        """Initialize data extractor.

        Args:
            db_manager: Database manager instance
            config: Configuration dictionary
        """
        self.db_manager = db_manager
        self.config = config
        self.extraction_stats = {}
        self.gene_symbol_conflicts = []
        self.error_log = []

        # Gene normalization cache
        self._gene_symbol_cache = {}

    def extract_clean_genes(self) -> Tuple[List[Dict], List[Dict]]:
        """Extract unique genes with symbol normalization and validation.

        Returns:
            Tuple of (unique_genes, gene_symbol_conflicts)

        Raises:
            ExtractionError: If critical extraction fails
        """
        logger.info("🔍 Extracting genes from corrupted current system...")

        # Multi-pass extraction to handle various gene ID formats and quality issues
        gene_extraction_queries = [
            {
                'name': 'clean_records',
                'description': 'Primary extraction - clean records with valid Ensembl IDs',
                'query': """
                    SELECT DISTINCT
                        gene_id,
                        gene_symbol,
                        gene_type,
                        chromosome,
                        coordinates
                    FROM cancer_transcript_base
                    WHERE gene_symbol IS NOT NULL
                      AND gene_symbol != ''
                      AND gene_symbol !~ '^\\s*$'  -- Not just whitespace
                      AND gene_id IS NOT NULL
                      AND gene_id != ''
                      AND gene_id ~ '^ENSG[0-9]+(\.[0-9]+)?$'  -- Valid Ensembl format
                      AND LENGTH(gene_symbol) BETWEEN 1 AND 50  -- Reasonable symbol length
                """,
                'critical': True
            },
            {
                'name': 'missing_gene_id',
                'description': 'Secondary extraction - handle missing gene_id',
                'query': """
                    SELECT DISTINCT
                        COALESCE(
                            NULLIF(gene_id, ''),
                            'UNKNOWN_' || UPPER(TRIM(gene_symbol)) || '_' || extract(epoch from now())::text
                        ) as gene_id,
                        UPPER(TRIM(gene_symbol)) as gene_symbol,
                        gene_type,
                        chromosome,
                        coordinates
                    FROM cancer_transcript_base
                    WHERE gene_symbol IS NOT NULL
                      AND gene_symbol != ''
                      AND gene_symbol !~ '^\\s*$'
                      AND LENGTH(gene_symbol) BETWEEN 1 AND 50
                      AND (gene_id IS NULL OR gene_id = '' OR gene_id ~ '^\\s*$')
                """,
                'critical': False
            },
            {
                'name': 'recover_from_transcript_ids',
                'description': 'Tertiary extraction - recover from transcript IDs',
                'query': """
                    SELECT DISTINCT
                        CASE
                            WHEN transcript_id ~ '^ENST[0-9]+' THEN
                                regexp_replace(transcript_id, '\.[0-9]+$', '')
                            ELSE
                                'RECOVERED_' || substring(transcript_id, 1, 15) || '_' || extract(epoch from now())::text
                        END as gene_id,
                        COALESCE(
                            NULLIF(UPPER(TRIM(gene_symbol)), ''),
                            'UNKNOWN_GENE_' || substring(transcript_id, 1, 15)
                        ) as gene_symbol,
                        COALESCE(gene_type, 'unknown') as gene_type,
                        chromosome,
                        coordinates
                    FROM cancer_transcript_base
                    WHERE transcript_id IS NOT NULL
                      AND transcript_id != ''
                      AND (
                          gene_symbol IS NULL OR gene_symbol = '' OR
                          gene_id IS NULL OR gene_id = ''
                      )
                      AND LENGTH(transcript_id) > 5
                """,
                'critical': False
            }
        ]

        extracted_genes = []
        extraction_summary = {}

        for extraction_pass in gene_extraction_queries:
            pass_name = extraction_pass['name']
            logger.info(f"Running gene extraction pass: {pass_name}")

            try:
                start_time = pd.Timestamp.now()

                self.db_manager.cursor.execute(extraction_pass['query'])
                batch_results = self.db_manager.cursor.fetchall()

                processing_errors = 0
                pass_genes = []

                for row in batch_results:
                    try:
                        gene_data = self._process_gene_record(row)

                        # Validate and normalize gene symbol
                        if gene_data['gene_symbol']:
                            normalized_symbol = self._normalize_gene_symbol_robust(
                                gene_data['gene_symbol']
                            )

                            if normalized_symbol != gene_data['gene_symbol']:
                                self.gene_symbol_conflicts.append({
                                    'original': gene_data['gene_symbol'],
                                    'normalized': normalized_symbol,
                                    'gene_id': gene_data['gene_id'],
                                    'extraction_pass': pass_name
                                })

                            gene_data['gene_symbol'] = normalized_symbol

                        pass_genes.append(gene_data)

                    except Exception as e:
                        processing_errors += 1
                        if processing_errors <= 10:  # Log first 10 errors
                            logger.warning(f"Failed to process gene record in {pass_name}: {e}")

                extracted_genes.extend(pass_genes)
                elapsed = (pd.Timestamp.now() - start_time).total_seconds()

                extraction_summary[pass_name] = {
                    'records_extracted': len(batch_results),
                    'genes_processed': len(pass_genes),
                    'processing_errors': processing_errors,
                    'elapsed_seconds': round(elapsed, 2)
                }

                logger.info(f"✅ Pass {pass_name}: {len(pass_genes)} genes extracted")

            except Exception as e:
                logger.error(f"❌ Gene extraction pass {pass_name} failed: {e}")

                if extraction_pass['critical']:
                    raise ExtractionError(f"Critical extraction pass failed: {pass_name} - {e}")

                extraction_summary[pass_name] = {
                    'status': 'failed',
                    'error': str(e)
                }

        # Deduplicate and resolve conflicts
        logger.info("🔄 Deduplicating genes and resolving conflicts...")
        unique_genes = self._deduplicate_genes(extracted_genes)

        # Final validation
        self._validate_extracted_genes(unique_genes)

        final_stats = {
            'total_extracted': len(extracted_genes),
            'unique_genes': len(unique_genes),
            'symbol_conflicts': len(self.gene_symbol_conflicts),
            'extraction_passes': extraction_summary
        }

        self.extraction_stats['genes'] = final_stats

        logger.info(f"✅ Gene extraction complete:")
        logger.info(f"   📊 Total records processed: {len(extracted_genes)}")
        logger.info(f"   🧬 Unique genes identified: {len(unique_genes)}")
        logger.info(f"   🔄 Symbol conflicts resolved: {len(self.gene_symbol_conflicts)}")

        return unique_genes, self.gene_symbol_conflicts

    def extract_drug_data_from_corrupted_field(self) -> Tuple[List[Dict], Dict]:
        """Extract actual drug data from corrupted drugs JSONB field.

        The current system has PharmGKB pathway data incorrectly stored in the drugs field.
        This method separates actual drug interactions from pathway data.

        Returns:
            Tuple of (drug_interactions_list, extraction_statistics)
        """
        logger.info("🔍 Extracting drug data from corrupted JSONB field...")

        drug_extraction_patterns = [
            {
                'source': 'drugcentral',
                'description': 'Extract DrugCentral drug interaction data',
                'query': """
                    SELECT
                        gene_symbol,
                        gene_id,
                        drugs
                    FROM cancer_transcript_base
                    WHERE drugs::text LIKE '%drugcentral%'
                      AND drugs::text LIKE '%drug_name%'
                      AND jsonb_typeof(drugs) = 'object'
                """,
                'parser': self._parse_drugcentral_structure
            },
            {
                'source': 'chembl',
                'description': 'Extract ChEMBL drug data',
                'query': """
                    SELECT
                        gene_symbol,
                        gene_id,
                        drugs
                    FROM cancer_transcript_base
                    WHERE drugs::text LIKE '%chembl%'
                      AND (drugs::text LIKE '%molecule%' OR drugs::text LIKE '%compound%')
                      AND jsonb_typeof(drugs) = 'object'
                """,
                'parser': self._parse_chembl_structure
            },
            {
                'source': 'pharmgkb_drugs',
                'description': 'Extract drugs from PharmGKB data incorrectly stored in drugs field',
                'query': """
                    SELECT
                        gene_symbol,
                        gene_id,
                        drugs
                    FROM cancer_transcript_base
                    WHERE drugs::text LIKE '%pharmgkb_data%'
                      AND drugs::text LIKE '%drugs%'
                      AND jsonb_typeof(drugs) = 'object'
                """,
                'parser': self._parse_pharmgkb_drugs_from_corrupted_field
            }
        ]

        all_drug_interactions = []
        extraction_stats = {}

        for pattern in drug_extraction_patterns:
            source = pattern['source']
            logger.info(f"🔄 Extracting {source} drug data...")

            try:
                start_time = pd.Timestamp.now()

                self.db_manager.cursor.execute(pattern['query'])
                raw_records = self.db_manager.cursor.fetchall()

                extracted_count = 0
                error_count = 0
                source_interactions = []

                # Process records with progress bar
                for record in tqdm(raw_records, desc=f"Processing {source}", leave=False):
                    try:
                        drug_interactions = pattern['parser'](record)
                        if drug_interactions:
                            source_interactions.extend(drug_interactions)
                            extracted_count += len(drug_interactions)

                    except Exception as e:
                        error_count += 1
                        if error_count <= 10:  # Log first 10 errors
                            logger.warning(f"Failed to parse {source} record: {e}")

                        # Log error details for debugging
                        self.error_log.append({
                            'source': source,
                            'error': str(e),
                            'record_preview': str(record)[:200] + '...' if len(str(record)) > 200 else str(record)
                        })

                all_drug_interactions.extend(source_interactions)
                elapsed = (pd.Timestamp.now() - start_time).total_seconds()

                extraction_stats[source] = {
                    'records_processed': len(raw_records),
                    'interactions_extracted': extracted_count,
                    'errors': error_count,
                    'error_rate': error_count / max(len(raw_records), 1),
                    'elapsed_seconds': round(elapsed, 2)
                }

                logger.info(f"✅ {source}: {extracted_count} interactions extracted from {len(raw_records)} records")

            except Exception as e:
                logger.error(f"❌ Failed to extract {source} data: {e}")
                extraction_stats[source] = {
                    'status': 'failed',
                    'error': str(e)
                }

        # Deduplicate drug interactions
        logger.info("🔄 Deduplicating drug interactions...")
        deduplicated_interactions = self._deduplicate_drug_interactions(all_drug_interactions)

        final_stats = {
            'total_extracted': len(all_drug_interactions),
            'deduplicated_count': len(deduplicated_interactions),
            'sources': extraction_stats,
            'error_count': len(self.error_log)
        }

        self.extraction_stats['drug_interactions'] = final_stats

        logger.info(f"✅ Drug extraction complete:")
        logger.info(f"   💊 Total interactions extracted: {len(all_drug_interactions)}")
        logger.info(f"   🔄 After deduplication: {len(deduplicated_interactions)}")
        logger.info(f"   ❌ Processing errors: {len(self.error_log)}")

        return deduplicated_interactions, final_stats

    def extract_pharmgkb_pathways_separate(self) -> Tuple[List[Dict], Dict]:
        """Extract PharmGKB pathway data separate from drug interactions.

        This method properly separates pathway data from drug data, which are
        currently incorrectly mixed in the drugs field.

        Returns:
            Tuple of (pathway_data_list, extraction_statistics)
        """
        logger.info("🔍 Extracting PharmGKB pathway data (separate from drugs)...")

        try:
            # Extract pathway data from drugs field where it's incorrectly stored
            query = """
                SELECT
                    gene_symbol,
                    gene_id,
                    drugs
                FROM cancer_transcript_base
                WHERE drugs::text LIKE '%pharmgkb_data%'
                  AND drugs::text LIKE '%pathway_data%'
                  AND jsonb_typeof(drugs) = 'object'
            """

            start_time = pd.Timestamp.now()
            self.db_manager.cursor.execute(query)
            raw_records = self.db_manager.cursor.fetchall()

            pathway_data = []
            processing_errors = 0

            for record in tqdm(raw_records, desc="Processing PharmGKB pathways"):
                try:
                    pathways = self._parse_pharmgkb_pathways_from_corrupted_field(record)
                    if pathways:
                        pathway_data.extend(pathways)

                except Exception as e:
                    processing_errors += 1
                    if processing_errors <= 10:
                        logger.warning(f"Failed to parse PharmGKB pathway record: {e}")

            elapsed = (pd.Timestamp.now() - start_time).total_seconds()

            extraction_stats = {
                'records_processed': len(raw_records),
                'pathways_extracted': len(pathway_data),
                'processing_errors': processing_errors,
                'error_rate': processing_errors / max(len(raw_records), 1),
                'elapsed_seconds': round(elapsed, 2)
            }

            self.extraction_stats['pharmgkb_pathways'] = extraction_stats

            logger.info(f"✅ PharmGKB pathway extraction complete:")
            logger.info(f"   🛤️ Pathways extracted: {len(pathway_data)}")
            logger.info(f"   ❌ Processing errors: {processing_errors}")

            return pathway_data, extraction_stats

        except Exception as e:
            logger.error(f"❌ PharmGKB pathway extraction failed: {e}")
            raise ExtractionError(f"PharmGKB pathway extraction failed: {e}")

    def extract_go_terms_and_annotations(self) -> Tuple[List[Dict], Dict]:
        """Extract GO terms and other annotations.

        Returns:
            Tuple of (annotations_list, extraction_statistics)
        """
        logger.info("🔍 Extracting GO terms and annotations...")

        try:
            query = """
                SELECT DISTINCT
                    gene_symbol,
                    gene_id,
                    go_terms,
                    pathways,
                    product_type,
                    molecular_functions,
                    cellular_location,
                    uniprot_ids,
                    ncbi_ids,
                    refseq_ids
                FROM cancer_transcript_base
                WHERE gene_symbol IS NOT NULL
                  AND gene_id IS NOT NULL
            """

            start_time = pd.Timestamp.now()
            self.db_manager.cursor.execute(query)
            raw_records = self.db_manager.cursor.fetchall()

            annotations = []
            processing_errors = 0

            for record in tqdm(raw_records, desc="Processing annotations"):
                try:
                    annotation_data = self._process_annotation_record(record)
                    if annotation_data:
                        annotations.append(annotation_data)

                except Exception as e:
                    processing_errors += 1
                    if processing_errors <= 10:
                        logger.warning(f"Failed to process annotation record: {e}")

            # Deduplicate by gene_id
            unique_annotations = {}
            for ann in annotations:
                gene_id = ann.get('gene_id')
                if gene_id and gene_id not in unique_annotations:
                    unique_annotations[gene_id] = ann
                elif gene_id in unique_annotations:
                    # Merge annotations for same gene
                    unique_annotations[gene_id] = self._merge_gene_annotations(
                        unique_annotations[gene_id], ann
                    )

            deduplicated_annotations = list(unique_annotations.values())
            elapsed = (pd.Timestamp.now() - start_time).total_seconds()

            extraction_stats = {
                'records_processed': len(raw_records),
                'annotations_extracted': len(annotations),
                'unique_genes_annotated': len(deduplicated_annotations),
                'processing_errors': processing_errors,
                'elapsed_seconds': round(elapsed, 2)
            }

            self.extraction_stats['annotations'] = extraction_stats

            logger.info(f"✅ Annotation extraction complete:")
            logger.info(f"   📝 Annotations extracted: {len(annotations)}")
            logger.info(f"   🧬 Unique genes annotated: {len(deduplicated_annotations)}")

            return deduplicated_annotations, extraction_stats

        except Exception as e:
            logger.error(f"❌ Annotation extraction failed: {e}")
            raise ExtractionError(f"Annotation extraction failed: {e}")

    def get_extraction_summary(self) -> Dict:
        """Get comprehensive extraction summary.

        Returns:
            Dictionary with extraction statistics and summary
        """
        return {
            'extraction_timestamp': pd.Timestamp.now().isoformat(),
            'extraction_stats': self.extraction_stats,
            'gene_symbol_conflicts': len(self.gene_symbol_conflicts),
            'total_errors': len(self.error_log),
            'sample_errors': self.error_log[:5]  # First 5 errors for debugging
        }

    # Private helper methods

    def _process_gene_record(self, row: Tuple) -> Dict:
        """Process a single gene record with validation."""
        try:
            gene_data = {
                'gene_id': row[0] if row[0] and row[0].strip() else None,
                'gene_symbol': row[1] if row[1] and row[1].strip() else None,
                'gene_type': row[2] if row[2] and row[2].strip() else 'unknown',
                'chromosome': row[3] if row[3] and row[3].strip() else None,
                'coordinates': row[4] if row[4] else {}
            }

            # Basic validation
            if not gene_data['gene_id']:
                raise ValueError("Gene ID is required")

            if not gene_data['gene_symbol']:
                raise ValueError("Gene symbol is required")

            return gene_data

        except Exception as e:
            raise ValueError(f"Failed to process gene record: {e}")

    def _normalize_gene_symbol_robust(self, symbol: str) -> Optional[str]:
        """Normalize gene symbol with comprehensive error handling."""
        if not symbol or not symbol.strip():
            return None

        # Use cache for performance
        if symbol in self._gene_symbol_cache:
            return self._gene_symbol_cache[symbol]

        try:
            # Clean up the symbol
            cleaned = symbol.strip().upper()

            # Remove common problematic characters
            cleaned = re.sub(r'[^\w\-@\.]', '', cleaned)

            # Handle common formatting issues
            cleaned = re.sub(r'^LOC(\d+)$', r'LOC\1', cleaned)  # Fix LOC genes
            cleaned = re.sub(r'_+', '_', cleaned)  # Multiple underscores
            cleaned = re.sub(r'\-+', '-', cleaned)  # Multiple hyphens

            # Validate length
            if len(cleaned) < 1 or len(cleaned) > 50:
                logger.warning(f"Gene symbol length issue: {symbol} -> {cleaned}")
                return None

            # Cache result
            self._gene_symbol_cache[symbol] = cleaned
            return cleaned

        except Exception as e:
            logger.warning(f"Failed to normalize gene symbol {symbol}: {e}")
            return None

    def _is_valid_gene_symbol(self, gene_symbol: str) -> bool:
        """Check if a gene symbol is valid for human genes.

        Args:
            gene_symbol: Gene symbol to validate

        Returns:
            True if gene symbol appears valid, False otherwise
        """
        if not gene_symbol or len(gene_symbol.strip()) == 0:
            return False

        # Filter out clearly non-human or corrupted gene symbols
        invalid_patterns = [
            'metazoa',  # Non-human phylogenetic annotation
            'scaffold',  # Genomic scaffold annotations
            'contig',    # Assembly contigs
            'uncharacterized',  # Generic annotations
            'loc',       # Generic location annotations (when not followed by numbers)
        ]

        gene_symbol_lower = gene_symbol.lower()

        # Check for invalid patterns
        for pattern in invalid_patterns:
            if pattern in gene_symbol_lower:
                return False

        # Additional checks for clearly invalid symbols
        if len(gene_symbol) > 50:  # Unreasonably long
            return False

        if gene_symbol.count('_') > 3:  # Too many underscores suggest annotation artifact
            return False

        return True

    def _deduplicate_genes(self, genes: List[Dict]) -> List[Dict]:
        """Deduplicate genes and resolve conflicts."""
        # First filter out genes with invalid symbols
        valid_genes = []
        invalid_count = 0

        for gene in genes:
            if self._is_valid_gene_symbol(gene.get('gene_symbol', '')):
                valid_genes.append(gene)
            else:
                invalid_count += 1

        logger.info(f"Gene filtering: {invalid_count} genes with invalid symbols removed")

        # Now deduplicate by gene_id
        unique_genes = {}
        conflicts = []

        for gene in valid_genes:
            gene_id = gene['gene_id']

            if gene_id not in unique_genes:
                unique_genes[gene_id] = gene
            else:
                # Handle conflicts - prefer record with better data quality
                existing = unique_genes[gene_id]
                better_record = self._choose_better_gene_record(existing, gene)

                if better_record != existing:
                    conflicts.append({
                        'gene_id': gene_id,
                        'replaced': existing,
                        'with': better_record
                    })
                    unique_genes[gene_id] = better_record

        # Finally, handle gene symbol duplicates (different genes with same symbol)
        symbol_groups = {}
        for gene in unique_genes.values():
            symbol = gene['gene_symbol']
            if symbol not in symbol_groups:
                symbol_groups[symbol] = []
            symbol_groups[symbol].append(gene)

        # For duplicate symbols, keep the gene with the best quality score
        final_genes = []
        symbol_conflicts = 0

        for symbol, gene_group in symbol_groups.items():
            if len(gene_group) == 1:
                final_genes.append(gene_group[0])
            else:
                # Multiple genes with same symbol - keep the best one
                best_gene = max(gene_group, key=self._score_gene_record)
                final_genes.append(best_gene)
                symbol_conflicts += len(gene_group) - 1
                logger.warning(f"Gene symbol conflict: {symbol} found in {len(gene_group)} genes, kept best scoring gene {best_gene['gene_id']}")

        logger.info(f"Gene deduplication: {len(conflicts)} ID conflicts and {symbol_conflicts} symbol conflicts resolved")
        return final_genes

    def _choose_better_gene_record(self, record1: Dict, record2: Dict) -> Dict:
        """Choose the better of two gene records based on data quality."""
        score1 = self._score_gene_record(record1)
        score2 = self._score_gene_record(record2)

        return record1 if score1 >= score2 else record2

    def _score_gene_record(self, record: Dict) -> int:
        """Score a gene record based on data quality."""
        score = 0

        # Valid Ensembl gene ID
        if record.get('gene_id', '').startswith('ENSG'):
            score += 3

        # Gene symbol quality
        symbol = record.get('gene_symbol', '')
        if symbol and len(symbol) > 1 and not symbol.startswith('UNKNOWN'):
            score += 2

        # Gene type present
        if record.get('gene_type') and record['gene_type'] != 'unknown':
            score += 1

        # Chromosome information
        if record.get('chromosome'):
            score += 1

        # Coordinates present
        if record.get('coordinates') and isinstance(record['coordinates'], dict):
            score += 1

        return score

    def _validate_extracted_genes(self, genes: List[Dict]):
        """Validate extracted gene data."""
        if not genes:
            raise ExtractionError("No genes extracted")

        # Check for required fields
        missing_fields = 0
        for gene in genes[:100]:  # Check first 100
            if not gene.get('gene_id') or not gene.get('gene_symbol'):
                missing_fields += 1

        if missing_fields > 10:  # More than 10% missing critical fields
            raise ExtractionError(f"Too many genes missing critical fields: {missing_fields}")

        logger.info(f"Gene validation passed for {len(genes)} genes")

    # Drug extraction parsers

    def _parse_drugcentral_structure(self, record: Tuple) -> List[Dict]:
        """Parse DrugCentral data structure from corrupted drugs field."""
        interactions = []

        try:
            gene_symbol, gene_id, drugs_json = record

            if not drugs_json or drugs_json == '{}':
                return interactions

            # Parse the drugs JSON structure
            if isinstance(drugs_json, str):
                drugs_data = json.loads(drugs_json)
            else:
                drugs_data = drugs_json

            # Extract DrugCentral specific data
            # Implementation will depend on actual structure found
            # This is a template that will need to be adapted based on real data structure

            drugcentral_data = drugs_data.get('drugcentral_data', {})
            if drugcentral_data:
                for drug_entry in drugcentral_data.get('drugs', []):
                    interaction = {
                        'gene_id': gene_id,
                        'gene_symbol': gene_symbol,
                        'drug_name': drug_entry.get('name', ''),
                        'drug_chembl_id': drug_entry.get('chembl_id', ''),
                        'drugcentral_id': drug_entry.get('drugcentral_id', ''),
                        'interaction_type': drug_entry.get('action_type', ''),
                        'mechanism_of_action': drug_entry.get('mechanism', ''),
                        'clinical_phase': drug_entry.get('phase', ''),
                        'source_database': 'drugcentral',
                        'raw_data': drug_entry
                    }

                    if interaction['drug_name']:  # Only add if drug name exists
                        interactions.append(interaction)

        except Exception as e:
            logger.warning(f"Failed to parse DrugCentral structure for {gene_symbol}: {e}")

        return interactions

    def _parse_chembl_structure(self, record: Tuple) -> List[Dict]:
        """Parse ChEMBL data structure from corrupted drugs field."""
        interactions = []

        try:
            gene_symbol, gene_id, drugs_json = record

            if not drugs_json or drugs_json == '{}':
                return interactions

            if isinstance(drugs_json, str):
                drugs_data = json.loads(drugs_json)
            else:
                drugs_data = drugs_json

            # Extract ChEMBL specific data
            chembl_data = drugs_data.get('chembl_data', {})
            if chembl_data:
                for drug_entry in chembl_data.get('compounds', []):
                    interaction = {
                        'gene_id': gene_id,
                        'gene_symbol': gene_symbol,
                        'drug_name': drug_entry.get('molecule_name', ''),
                        'drug_chembl_id': drug_entry.get('molecule_chembl_id', ''),
                        'interaction_type': drug_entry.get('target_type', ''),
                        'mechanism_of_action': drug_entry.get('mechanism_of_action', ''),
                        'clinical_phase': drug_entry.get('max_phase', ''),
                        'source_database': 'chembl',
                        'raw_data': drug_entry
                    }

                    if interaction['drug_name']:
                        interactions.append(interaction)

        except Exception as e:
            logger.warning(f"Failed to parse ChEMBL structure for {gene_symbol}: {e}")

        return interactions

    def _parse_pharmgkb_drugs_from_corrupted_field(self, record: Tuple) -> List[Dict]:
        """Extract drug names from PharmGKB data stored in drugs field."""
        interactions = []

        try:
            gene_symbol, gene_id, drugs_json = record

            if not drugs_json or drugs_json == '{}':
                return interactions

            if isinstance(drugs_json, str):
                drugs_data = json.loads(drugs_json)
            else:
                drugs_data = drugs_json

            # Navigate PharmGKB structure to find drugs
            pharmgkb_data = drugs_data.get('pharmgkb_data', {})
            pathway_data = pharmgkb_data.get('pathway_data', {})

            for pathway_id, pathway_info in pathway_data.items():
                if isinstance(pathway_info, dict):
                    reactions = pathway_info.get('reactions', [])

                    for reaction in reactions:
                        if isinstance(reaction, dict):
                            drug_names = reaction.get('drugs', [])

                            for drug_name in drug_names:
                                if drug_name and isinstance(drug_name, str):
                                    interaction = {
                                        'gene_id': gene_id,
                                        'gene_symbol': gene_symbol,
                                        'drug_name': drug_name.strip(),
                                        'interaction_type': 'pharmgkb_pathway',
                                        'source_database': 'pharmgkb',
                                        'pathway_id': pathway_id,
                                        'pmids': reaction.get('pmids', [])
                                    }

                                    interactions.append(interaction)

        except Exception as e:
            logger.warning(f"Failed to parse PharmGKB drugs for {gene_symbol}: {e}")

        return interactions

    def _parse_pharmgkb_pathways_from_corrupted_field(self, record: Tuple) -> List[Dict]:
        """Extract PharmGKB pathway data from corrupted drugs field."""
        pathways = []

        try:
            gene_symbol, gene_id, drugs_json = record

            if not drugs_json or drugs_json == '{}':
                return pathways

            if isinstance(drugs_json, str):
                drugs_data = json.loads(drugs_json)
            else:
                drugs_data = drugs_json

            # Extract pathway data
            pharmgkb_data = drugs_data.get('pharmgkb_data', {})
            pathway_data = pharmgkb_data.get('pathway_data', {})

            for pathway_id, pathway_info in pathway_data.items():
                if isinstance(pathway_info, dict):
                    reactions = pathway_info.get('reactions', [])

                    for reaction in reactions:
                        if isinstance(reaction, dict):
                            pathway_record = {
                                'gene_id': gene_id,
                                'gene_symbol': gene_symbol,
                                'pathway_id': pathway_id,
                                'reaction_type': reaction.get('reaction_type', ''),
                                'control_type': reaction.get('control_type', ''),
                                'controller_genes': reaction.get('controller_genes', []),
                                'target_genes': [reaction.get('to', '')],
                                'from_genes': [reaction.get('from', '')],
                                'drugs_involved': reaction.get('drugs', []),
                                'pmids': reaction.get('pmids', []),
                                'diseases': reaction.get('diseases', []),
                                'cell_type': reaction.get('cell_type', '')
                            }

                            pathways.append(pathway_record)

        except Exception as e:
            logger.warning(f"Failed to parse PharmGKB pathways for {gene_symbol}: {e}")

        return pathways

    def _deduplicate_drug_interactions(self, interactions: List[Dict]) -> List[Dict]:
        """Deduplicate drug interactions based on gene + drug combination."""
        unique_interactions = {}

        for interaction in interactions:
            key = (
                interaction.get('gene_id', ''),
                interaction.get('drug_name', '').lower().strip(),
                interaction.get('source_database', '')
            )

            if key not in unique_interactions:
                unique_interactions[key] = interaction
            else:
                # Merge information from duplicate
                existing = unique_interactions[key]
                merged = self._merge_drug_interactions(existing, interaction)
                unique_interactions[key] = merged

        return list(unique_interactions.values())

    def _merge_drug_interactions(self, interaction1: Dict, interaction2: Dict) -> Dict:
        """Merge two drug interaction records."""
        merged = interaction1.copy()

        # Merge non-empty fields from interaction2
        for key, value in interaction2.items():
            if value and not merged.get(key):
                merged[key] = value
            elif key == 'pmids' and isinstance(value, list):
                # Merge PMID lists
                existing_pmids = set(merged.get('pmids', []))
                new_pmids = set(value)
                merged['pmids'] = list(existing_pmids.union(new_pmids))

        return merged

    def _process_annotation_record(self, record: Tuple) -> Dict:
        """Process an annotation record."""
        try:
            annotation_data = {
                'gene_symbol': record[0],
                'gene_id': record[1],
                'go_terms': record[2] if record[2] else {},
                'pathways': record[3] if record[3] else [],
                'product_type': record[4] if record[4] else [],
                'molecular_functions': record[5] if record[5] else [],
                'cellular_location': record[6] if record[6] else [],
                'uniprot_ids': record[7] if record[7] else [],
                'ncbi_ids': record[8] if record[8] else [],
                'refseq_ids': record[9] if record[9] else []
            }

            # Clean and structure GO terms
            if isinstance(annotation_data['go_terms'], dict):
                annotation_data['go_molecular_functions'] = annotation_data['go_terms'].get('molecular_function', [])
                annotation_data['go_biological_processes'] = annotation_data['go_terms'].get('biological_process', [])
                annotation_data['go_cellular_components'] = annotation_data['go_terms'].get('cellular_component', [])
            else:
                annotation_data['go_molecular_functions'] = []
                annotation_data['go_biological_processes'] = []
                annotation_data['go_cellular_components'] = []

            return annotation_data

        except Exception as e:
            raise ValueError(f"Failed to process annotation record: {e}")

    def _merge_gene_annotations(self, ann1: Dict, ann2: Dict) -> Dict:
        """Merge annotations for the same gene."""
        merged = ann1.copy()

        # Merge array fields
        array_fields = [
            'pathways', 'product_type', 'molecular_functions', 'cellular_location',
            'uniprot_ids', 'ncbi_ids', 'refseq_ids', 'go_molecular_functions',
            'go_biological_processes', 'go_cellular_components'
        ]

        for field in array_fields:
            existing = set(merged.get(field, []))
            new_items = set(ann2.get(field, []))
            merged[field] = list(existing.union(new_items))

        # Merge GO terms dict
        if isinstance(ann2.get('go_terms'), dict):
            if not isinstance(merged.get('go_terms'), dict):
                merged['go_terms'] = {}

            for go_type, terms in ann2['go_terms'].items():
                if go_type not in merged['go_terms']:
                    merged['go_terms'][go_type] = []
                existing_terms = set(merged['go_terms'][go_type])
                new_terms = set(terms if isinstance(terms, list) else [terms])
                merged['go_terms'][go_type] = list(existing_terms.union(new_terms))

        return merged