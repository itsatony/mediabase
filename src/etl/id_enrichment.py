"""ID Enrichment module for Cancer Transcriptome Base.

This module handles downloading, processing, and integration of alternative
identifier mappings from UniProt for transcript records, enhancing cross-database 
compatibility and searchability.
"""

# Standard library imports
import csv
import gzip
import json
from pathlib import Path
from typing import Dict, List, Optional, Any, Set, Tuple, DefaultDict
from collections import defaultdict
from datetime import datetime
import re

# Third party imports
from tqdm import tqdm
from rich.console import Console
from rich.table import Table

# Local imports
from .base_processor import BaseProcessor, DownloadError, ProcessingError, DatabaseError
from ..utils.logging import get_progress_bar

# Constants
HUMAN_TAXID = '9606'  # NCBI taxonomy ID for humans

class IDEnrichmentProcessor(BaseProcessor):
    """Process and integrate alternative gene and transcript IDs using UniProt mappings."""

    def __init__(self, config: Dict[str, Any]) -> None:
        """Initialize the ID enrichment processor with configuration.
        
        Args:
            config: Configuration dictionary with settings
        """
        super().__init__(config)
        
        # Define specific directory for ID mapping data
        self.id_dir = self.cache_dir / 'id_mapping'
        self.id_dir.mkdir(exist_ok=True)
        
        # Source URLs for comprehensive ID mapping
        self.uniprot_mapping_url = config.get(
            'uniprot_mapping_url',
            'https://ftp.uniprot.org/pub/databases/uniprot/current_release/knowledgebase/idmapping/by_organism/HUMAN_9606_idmapping.dat.gz'
        )
        
        # PRIORITY 1: NCBI Gene2Ensembl - Authoritative gene ID mapping
        self.gene2ensembl_url = config.get(
            'gene2ensembl_url',
            'https://ftp.ncbi.nlm.nih.gov/gene/DATA/gene2ensembl.gz'
        )
        
        # PRIORITY 2: HGNC Complete - Official gene symbols and aliases  
        self.hgnc_url = config.get(
            'hgnc_url',
            'https://www.genenames.org/cgi-bin/download/custom?col=gd_hgnc_id&col=gd_app_sym&col=gd_aliases&col=gd_pub_ensembl_id&status=Approved&hgnc_dbtag=on&order_by=gd_app_sym_sort&format=text&submit=submit'
        )
        
        # Cache options
        self.filter_metadata: Dict[str, Any] = {
            'uniprot': {'filtered': False, 'total': 0, 'human': 0},
            'gene2ensembl': {'processed': False, 'total': 0, 'human': 0},
            'hgnc': {'processed': False, 'total': 0, 'aliases': 0}
        }
    
    def download_uniprot_mapping(self) -> Path:
        """Download UniProt ID mapping file with caching.
        
        Returns:
            Path to the downloaded file
            
        Raises:
            DownloadError: If download fails
        """
        try:
            self.logger.info("Downloading UniProt ID mapping file")
            # Use the BaseProcessor download method
            mapping_file = self.download_file(
                url=self.uniprot_mapping_url,
                file_path=self.id_dir / "uniprot_human_idmapping.dat.gz"
            )
            return mapping_file
        except Exception as e:
            raise DownloadError(f"Failed to download UniProt ID mapping: {e}")
    
    def _filter_uniprot_mapping(self, input_path: Path) -> Path:
        """Filter UniProt mapping file to include only human entries.
        
        Args:
            input_path: Path to the full mapping file
            
        Returns:
            Path to the filtered file
            
        Raises:
            ProcessingError: If filtering fails
        """
        output_path = self.id_dir / "uniprot_human_idmapping_filtered.dat.gz"
        
        # Check if already filtered
        meta_path = self.id_dir / "uniprot_filtered_meta.json"
        if output_path.exists() and meta_path.exists():
            try:
                with open(meta_path, 'r') as f:
                    self.filter_metadata['uniprot'] = json.load(f)
                if self.filter_metadata['uniprot'].get('filtered', False):
                    self.logger.info(
                        f"Using pre-filtered UniProt mapping with "
                        f"{self.filter_metadata['uniprot'].get('human', 0):,} human entries "
                        f"from {self.filter_metadata['uniprot'].get('total', 0):,} total"
                    )
                    return output_path
            except Exception as e:
                self.logger.warning(f"Error reading filter metadata, will re-filter: {e}")
        
        try:
            self.logger.info("Filtering UniProt ID mapping to ensure human entries only")
            
            total_entries = 0
            human_entries = 0
            
            # Improved filtering with better progress reporting
            with gzip.open(input_path, 'rt') as f_in:
                # Count lines first to set up progress bar
                self.logger.info("Counting lines in UniProt mapping file...")
                line_count = sum(1 for _ in f_in)
                self.logger.info(f"UniProt mapping file contains {line_count:,} lines")
                f_in.seek(0)  # Reset file pointer
                
                # First pass: identify human UniProt IDs 
                human_uniprot_ids = set()
                self.logger.info("First pass: identifying human UniProt IDs...")
                
                # Fix: Use get_progress_bar instead of direct tqdm
                pbar = get_progress_bar(
                    total=line_count,
                    desc="Identifying human entries",
                    module_name="etl.id_enrichment"
                )
                
                for line in f_in:
                    total_entries += 1
                    pbar.update(1)
                    
                    parts = line.strip().split('\t')
                    if len(parts) >= 3 and parts[1] == "NCBI_TaxID" and parts[2] == HUMAN_TAXID:
                        human_uniprot_ids.add(parts[0])
                
                # Close the first progress bar
                pbar.close()
                
                # Reset file pointer for second pass
                f_in.seek(0)
                
                # Second pass: extract all entries for human UniProt IDs
                self.logger.info(f"Second pass: extracting {len(human_uniprot_ids):,} human UniProt entries...")
                
                # Fix: Use get_progress_bar again for the second pass
                pbar = get_progress_bar(
                    total=line_count,
                    desc="Filtering human entries",
                    module_name="etl.id_enrichment"
                )
                
                with gzip.open(output_path, 'wt') as f_out:
                    for line in f_in:
                        pbar.update(1)
                        parts = line.strip().split('\t')
                        if parts[0] in human_uniprot_ids:
                            human_entries += 1
                            f_out.write(line)
                
                # Close the second progress bar
                pbar.close()
            
            # Update and save metadata
            self.filter_metadata['uniprot'] = {
                'filtered': True,
                'total': total_entries,
                'human': human_entries,
                'uniprot_ids': len(human_uniprot_ids),
                'filter_date': datetime.now().isoformat()
            }
            
            with open(meta_path, 'w') as f:
                json.dump(self.filter_metadata['uniprot'], f)
                
            self.logger.info(
                f"UniProt mapping filtered: kept {human_entries:,} human entries "
                f"from {total_entries:,} total ({human_entries/max(1, total_entries)*100:.1f}%)"
            )
            
            return output_path
            
        except Exception as e:
            raise ProcessingError(f"Failed to filter UniProt mapping: {e}")
    
    def process_uniprot_mapping(self, mapping_file: Path) -> Dict[str, Dict[str, List[str]]]:
        """Process UniProt ID mapping to extract comprehensive ID mappings.
        
        Args:
            mapping_file: Path to the UniProt ID mapping file
            
        Returns:
            Dictionary mapping gene symbols to various ID systems
            
        Raises:
            ProcessingError: If processing fails
        """
        try:
            self.logger.info("Processing UniProt ID mapping")
            
            # Make sure we're using the human-filtered version
            mapping_file = self._filter_uniprot_mapping(mapping_file)
            
            # Initialize mapping dictionaries
            # First by UniProt ID to collect all IDs per protein
            uniprot_mapping: DefaultDict[str, Dict[str, List[str]]] = defaultdict(
                lambda: defaultdict(list)
            )
            
            # Then by gene symbol for final output
            gene_mapping: DefaultDict[str, Dict[str, List[str]]] = defaultdict(
                lambda: defaultdict(list)
            )
            
            # Track statistics
            id_stats = {
                'uniprot_ids': 0,
                'gene_symbols': 0,
                'ncbi_ids': 0,
                'ensembl_ids': 0,
                'refseq_ids': 0,
                'hgnc_ids': 0,
                'mim_ids': 0, 
                'kegg_ids': 0,
                'pdb_ids': 0
            }
            
            # Process the mapping file
            with gzip.open(mapping_file, 'rt') as f:
                # Count lines for progress bar
                line_count = sum(1 for _ in f)
                f.seek(0)  # Reset file pointer
                
                # Fix: Use get_progress_bar instead of direct tqdm
                pbar = get_progress_bar(
                    total=line_count,
                    desc="Processing UniProt mapping",
                    module_name="etl.id_enrichment"
                )
                
                for line in f:
                    pbar.update(1)
                    
                    parts = line.strip().split('\t')
                    if len(parts) < 3:
                        continue
                        
                    uniprot_id = parts[0]
                    id_type = parts[1]
                    id_value = parts[2]
                    
                    # Skip empty values
                    if not id_value or id_value == '-':
                        continue
                        
                    # Map ID types to our standardized types and collect in uniprot_mapping
                    if id_type == "Gene_Name":
                        uniprot_mapping[uniprot_id]["gene_symbol"].append(id_value)
                        id_stats['gene_symbols'] += 1
                    elif id_type == "GeneID":
                        uniprot_mapping[uniprot_id]["ncbi_id"].append(id_value)
                        id_stats['ncbi_ids'] += 1
                    elif id_type == "Ensembl":
                        if id_value.startswith('ENSG'):  # Ensembl gene ID
                            uniprot_mapping[uniprot_id]["ensembl_gene_id"].append(id_value)
                            id_stats['ensembl_ids'] += 1
                        elif id_value.startswith('ENST'):  # Ensembl transcript ID
                            uniprot_mapping[uniprot_id]["ensembl_transcript_id"].append(id_value)
                            id_stats['ensembl_ids'] += 1
                    elif id_type == "RefSeq":
                        if id_value.startswith('NP_') or id_value.startswith('XP_'):
                            uniprot_mapping[uniprot_id]["refseq_protein_id"].append(id_value)
                            id_stats['refseq_ids'] += 1
                        elif id_value.startswith('NM_') or id_value.startswith('XM_'):
                            uniprot_mapping[uniprot_id]["refseq_mrna_id"].append(id_value)
                            id_stats['refseq_ids'] += 1
                    elif id_type == "HGNC":
                        uniprot_mapping[uniprot_id]["hgnc_id"].append(id_value)
                        id_stats['hgnc_ids'] += 1
                    elif id_type == "MIM":
                        uniprot_mapping[uniprot_id]["omim_id"].append(id_value)
                        id_stats['mim_ids'] += 1
                    elif id_type == "KEGG":
                        uniprot_mapping[uniprot_id]["kegg_id"].append(id_value)
                        id_stats['kegg_ids'] += 1
                    elif id_type == "PDB":
                        uniprot_mapping[uniprot_id]["pdb_id"].append(id_value)
                        id_stats['pdb_ids'] += 1
            
                # Close the progress bar
                pbar.close()
            
            # Now reorganize by gene symbol for easier database updates
            for uniprot_id, id_dict in uniprot_mapping.items():
                gene_symbols = id_dict.get("gene_symbol", [])
                
                # Skip entries without gene symbols
                if not gene_symbols:
                    continue
                
                # Add this UniProt ID to each gene symbol's entry
                for gene_symbol in gene_symbols:
                    # Add UniProt ID to list
                    if uniprot_id not in gene_mapping[gene_symbol]["uniprot_ids"]:
                        gene_mapping[gene_symbol]["uniprot_ids"].append(uniprot_id)
                    
                    # Copy all other IDs to gene mapping
                    for id_type, id_list in id_dict.items():
                        if id_type != "gene_symbol":  # Skip to avoid duplication
                            for id_value in id_list:
                                if id_value not in gene_mapping[gene_symbol][id_type]:
                                    gene_mapping[gene_symbol][id_type].append(id_value)
            
            # Log ID type statistics
            id_stats['uniprot_ids'] = len(uniprot_mapping)
            self.logger.info(f"ID mapping statistics:")
            for id_type, count in id_stats.items():
                self.logger.info(f"  - {id_type}: {count:,}")
            
            # Convert defaultdict to regular dict for return
            return {k: dict(v) for k, v in gene_mapping.items()}
            
        except Exception as e:
            raise ProcessingError(f"Failed to process UniProt mapping: {e}")
    
    def update_transcript_ids(self, gene_mapping: Dict[str, Dict[str, List[str]]]) -> None:
        """Update transcript records with alternative IDs from UniProt.
        
        Args:
            gene_mapping: Consolidated ID mapping by gene symbol
            
        Raises:
            DatabaseError: If database operations fail
        """
        if not self.ensure_connection():
            raise DatabaseError("Database connection failed")
            
        if not gene_mapping:
            self.logger.warning("No ID mappings to update transcripts with")
            return
            
        try:
            self.logger.info("Updating transcript records with alternative IDs")
            
            # Get existing gene symbols from database (normalized genes table)
            if not self.db_manager.cursor:
                raise DatabaseError("No database cursor available")

            # Improved query to handle case-insensitive matching from normalized schema
            self.db_manager.cursor.execute("""
                SELECT DISTINCT gene_symbol
                FROM genes
                WHERE gene_symbol IS NOT NULL
            """)
            
            db_gene_symbols = {row[0] for row in self.db_manager.cursor.fetchall() if row[0]}
            self.logger.info(f"Found {len(db_gene_symbols):,} unique gene symbols in database")
            
            # Find overlapping gene symbols with improved case handling
            mapping_symbols = set(gene_mapping.keys())
            
            # Create case-insensitive mappings for better matching
            case_insensitive_mapping = {}
            for symbol in mapping_symbols:
                case_insensitive_mapping[symbol.upper()] = symbol
            
            # Find overlap using case-insensitive matching
            overlap_symbols = set()
            for db_symbol in db_gene_symbols:
                # Direct match
                if db_symbol in mapping_symbols:
                    overlap_symbols.add(db_symbol)
                # Case-insensitive match
                elif db_symbol.upper() in case_insensitive_mapping:
                    # Use the original case from UniProt mapping
                    orig_symbol = case_insensitive_mapping[db_symbol.upper()]
                    # Add both to ensure we catch all variations
                    overlap_symbols.add(orig_symbol)
                    overlap_symbols.add(db_symbol)
            
            self.logger.info(
                f"ID mapping analysis:\n"
                f"- Symbols in database: {len(db_gene_symbols):,}\n"
                f"- Symbols in UniProt mappings: {len(mapping_symbols):,}\n"
                f"- Overlap symbols: {len(overlap_symbols):,} "
                f"({len(overlap_symbols)/max(1, len(db_gene_symbols))*100:.1f}% coverage)"
            )
            
            # Prepare updates
            updates = []
            
            for gene_symbol in tqdm(overlap_symbols, desc="Preparing ID updates"):
                # Handle both direct and case-insensitive matches
                if gene_symbol in gene_mapping:
                    mapping = gene_mapping[gene_symbol]
                elif gene_symbol.upper() in case_insensitive_mapping:
                    orig_symbol = case_insensitive_mapping[gene_symbol.upper()]
                    mapping = gene_mapping[orig_symbol]
                else:
                    continue  # Skip if no match found
                
                # Rest of the function remains the same
                # ...existing code...
                
                # Skip empty mappings
                if not mapping:
                    continue
                    
                # Extract ID arrays for direct array columns
                uniprot_ids = mapping.get("uniprot_ids", [])
                ncbi_ids = mapping.get("ncbi_id", [])
                
                # Consolidate RefSeq IDs from different subtypes (mRNA and protein)
                refseq_ids = []
                if "refseq_protein_id" in mapping:
                    refseq_ids.extend(mapping["refseq_protein_id"])
                if "refseq_mrna_id" in mapping:
                    refseq_ids.extend(mapping["refseq_mrna_id"])
                
                # Extract alternative gene IDs for JSONB field
                alt_gene_ids = {}
                
                # Add HGNC IDs
                if "hgnc_id" in mapping and mapping["hgnc_id"]:
                    alt_gene_ids["HGNC"] = mapping["hgnc_id"][0]  # Use first HGNC ID
                
                # Add Ensembl gene IDs
                if "ensembl_gene_id" in mapping and mapping["ensembl_gene_id"]:
                    alt_gene_ids["Ensembl"] = mapping["ensembl_gene_id"][0]
                
                # Add OMIM IDs
                if "omim_id" in mapping and mapping["omim_id"]:
                    alt_gene_ids["OMIM"] = mapping["omim_id"][0]
                
                # Add KEGG IDs
                if "kegg_id" in mapping and mapping["kegg_id"]:
                    alt_gene_ids["KEGG"] = mapping["kegg_id"][0]
                
                # Extract alternative transcript IDs
                alt_transcript_ids = {}
                
                # Add Ensembl transcript IDs
                if "ensembl_transcript_id" in mapping and mapping["ensembl_transcript_id"]:
                    alt_transcript_ids["Ensembl"] = mapping["ensembl_transcript_id"][0]
                
                # Add RefSeq IDs (using first mRNA ID if available)
                if "refseq_mrna_id" in mapping and mapping["refseq_mrna_id"]:
                    alt_transcript_ids["RefSeq"] = mapping["refseq_mrna_id"][0]
                
                # Add update to batch
                updates.append((
                    uniprot_ids,
                    ncbi_ids,
                    refseq_ids,
                    json.dumps(alt_gene_ids),
                    json.dumps(alt_transcript_ids),
                    gene_symbol
                ))
                
                # Process in batches - with a smaller batch size for testing
                if len(updates) >= min(1000, self.batch_size):
                    self._update_id_batch(updates)
                    # Add verification after each batch during debugging
                    self.logger.info(f"Processed batch of {len(updates)} records")
                    updates = []
            
            # Process remaining updates
            if updates:
                self._update_id_batch(updates)
                self.logger.info(f"Processed final batch of {len(updates)} records")
                
            # Verify the updates
            self._verify_id_updates()
            
        except Exception as e:
            self.logger.error(f"Failed to update transcript IDs: {e}")
            raise DatabaseError(f"Transcript ID update failed: {e}")
    
    def _update_id_batch(self, updates: List[Tuple]) -> None:
        """Update a batch of transcript records with alternative IDs.
        
        Args:
            updates: List of update tuples (uniprot_ids, ncbi_ids, refseq_ids, 
                    alt_gene_ids_json, alt_transcript_ids_json, gene_symbol)
            
        Raises:
            DatabaseError: If batch update fails
        """
        if not self.db_manager.cursor:
            raise DatabaseError("No database cursor available")
            
        try:
            # Log some sample updates for debugging
            sample_update = updates[0] if updates else None
            self.logger.info(f"Processing batch update with {len(updates)} records")
            if sample_update:
                self.logger.debug(f"Sample update - Gene: {sample_update[5]}, " +
                                 f"UniProt IDs: {sample_update[0]}, " +
                                 f"NCBI IDs: {sample_update[1]}")
            
            # Use our database manager's connection and cursor directly
            if self.db_manager.conn and self.db_manager.cursor:
                # Safer approach that doesn't alter connection state during a transaction
                try:
                    # Execute the batch update using executemany
                    self.db_manager.cursor.executemany(
                        """
                        UPDATE cancer_transcript_base
                        SET
                            uniprot_ids = %s::text[],
                            ncbi_ids = %s::text[],
                            refseq_ids = %s::text[],
                            alt_gene_ids = COALESCE(alt_gene_ids, '{}'::jsonb) || %s::jsonb,
                            alt_transcript_ids = COALESCE(alt_transcript_ids, '{}'::jsonb) || %s::jsonb
                        WHERE gene_symbol = %s
                        """,
                        updates
                    )

                    # ALSO populate normalized gene_cross_references table with NCBI IDs
                    # This is critical for pathways module which queries gene_cross_references
                    cross_ref_inserts = []
                    for update in updates:
                        uniprot_ids, ncbi_ids, refseq_ids, _, _, gene_symbol = update
                        if ncbi_ids:  # ncbi_ids is a list
                            for ncbi_id in ncbi_ids:
                                if ncbi_id:  # Skip empty strings
                                    # FIXED: Correct parameter order - (external_db, external_id, gene_symbol)
                                    cross_ref_inserts.append(('GeneID', ncbi_id, gene_symbol))

                    if cross_ref_inserts:
                        self.logger.info(f"Inserting {len(cross_ref_inserts)} NCBI cross-references into gene_cross_references")
                        self.db_manager.cursor.executemany(
                            """
                            INSERT INTO gene_cross_references (gene_id, external_db, external_id)
                            SELECT g.gene_id, %s, %s
                            FROM genes g
                            WHERE g.gene_symbol = %s
                            ON CONFLICT DO NOTHING
                            """,
                            cross_ref_inserts
                        )

                    # Only commit if the connection is not in autocommit mode already
                    if not self.db_manager.conn.autocommit:
                        self.db_manager.conn.commit()
                        self.logger.debug(f"Committed batch update of {len(updates)} records and {len(cross_ref_inserts)} cross-references")
                    
                except Exception as e:
                    # Rollback only if not in autocommit mode
                    if self.db_manager.conn and not self.db_manager.conn.autocommit:
                        self.db_manager.conn.rollback()
                    raise e
            else:
                raise DatabaseError("No database connection or cursor available")
                
        except Exception as e:
            self.logger.error(f"Batch ID update failed: {e}")
            raise DatabaseError(f"Failed to update ID batch: {e}")
    
    def _verify_id_updates(self) -> None:
        """Verify ID updates with database statistics."""
        if not self.ensure_connection():
            self.logger.warning("Cannot verify results - database connection unavailable")
            return
            
        try:
            if not self.db_manager.cursor:
                self.logger.warning("Cannot verify results - no database cursor available")
                return
                
            self.db_manager.cursor.execute("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(CASE WHEN uniprot_ids IS NOT NULL 
                              AND array_length(uniprot_ids, 1) > 0 
                         THEN 1 END) as with_uniprot,
                    COUNT(CASE WHEN ncbi_ids IS NOT NULL 
                              AND array_length(ncbi_ids, 1) > 0 
                         THEN 1 END) as with_ncbi,
                    COUNT(CASE WHEN refseq_ids IS NOT NULL 
                              AND array_length(refseq_ids, 1) > 0 
                         THEN 1 END) as with_refseq,
                    COUNT(CASE WHEN alt_gene_ids != '{}'::jsonb 
                         THEN 1 END) as with_alt_gene,
                    COUNT(CASE WHEN alt_transcript_ids != '{}'::jsonb 
                         THEN 1 END) as with_alt_transcript
                FROM cancer_transcript_base
            """)
            
            stats = self.db_manager.cursor.fetchone()
            if stats:
                # Create table for better visualization
                table = Table(title="ID Enrichment Results")
                table.add_column("Metric", style="cyan")
                table.add_column("Count", style="green")
                table.add_column("Coverage", style="yellow")
                
                total = stats[0]
                with_uniprot = stats[1]
                with_ncbi = stats[2]
                with_refseq = stats[3]
                with_alt_gene = stats[4]
                with_alt_transcript = stats[5]
                
                table.add_row(
                    "Total Records", 
                    f"{total:,}", 
                    "100.0%"
                )
                table.add_row(
                    "With UniProt IDs", 
                    f"{with_uniprot:,}", 
                    f"{with_uniprot/max(1, total)*100:.1f}%"
                )
                table.add_row(
                    "With NCBI IDs", 
                    f"{with_ncbi:,}", 
                    f"{with_ncbi/max(1, total)*100:.1f}%"
                )
                table.add_row(
                    "With RefSeq IDs", 
                    f"{with_refseq:,}", 
                    f"{with_refseq/max(1, total)*100:.1f}%"
                )
                table.add_row(
                    "With Alt Gene IDs", 
                    f"{with_alt_gene:,}", 
                    f"{with_alt_gene/max(1, total)*100:.1f}%"
                )
                table.add_row(
                    "With Alt Transcript IDs", 
                    f"{with_alt_transcript:,}", 
                    f"{with_alt_transcript/max(1, total)*100:.1f}%"
                )
                
                console = Console()
                console.print(table)
                
                self.logger.info(
                    f"ID enrichment statistics:\n"
                    f"- Total records: {total:,}\n"
                    f"- Records with UniProt IDs: {with_uniprot:,} ({with_uniprot/max(1, total)*100:.1f}%)\n"
                    f"- Records with NCBI IDs: {with_ncbi:,} ({with_ncbi/max(1, total)*100:.1f}%)\n"
                    f"- Records with RefSeq IDs: {with_refseq:,} ({with_refseq/max(1, total)*100:.1f}%)\n"
                    f"- Records with Alt Gene IDs: {with_alt_gene:,} ({with_alt_gene/max(1, total)*100:.1f}%)\n"
                    f"- Records with Alt Transcript IDs: {with_alt_transcript:,} ({with_alt_transcript/max(1, total)*100:.1f}%)"
                )
                
        except Exception as e:
            self.logger.warning(f"Failed to verify ID updates: {e}")
    
    def download_gene2ensembl(self) -> Path:
        """Download NCBI Gene2Ensembl mapping file with caching.
        
        Returns:
            Path to the downloaded file
            
        Raises:
            DownloadError: If download fails
        """
        try:
            self.logger.info("Downloading NCBI Gene2Ensembl mapping file")
            # Use the BaseProcessor download method
            mapping_file = self.download_file(
                url=self.gene2ensembl_url,
                file_path=self.id_dir / "gene2ensembl.gz"
            )
            return mapping_file
        except Exception as e:
            raise DownloadError(f"Failed to download Gene2Ensembl mapping: {e}")
    
    def process_gene2ensembl(self, mapping_file: Path) -> Dict[str, Dict[str, str]]:
        """Process NCBI Gene2Ensembl mapping for comprehensive ID mapping.
        
        Args:
            mapping_file: Path to the Gene2Ensembl mapping file
            
        Returns:
            Dictionary mapping Ensembl gene IDs to NCBI gene information
            
        Raises:
            ProcessingError: If processing fails
        """
        try:
            self.logger.info("Processing NCBI Gene2Ensembl mapping")
            
            gene_mapping = {}
            total_entries = 0
            human_entries = 0
            
            with gzip.open(mapping_file, 'rt') as f:
                # Skip header
                header = next(f)
                self.logger.info(f"Gene2Ensembl header: {header.strip()}")
                
                for line in f:
                    total_entries += 1
                    parts = line.strip().split('\t')
                    
                    if len(parts) < 6:
                        continue
                        
                    tax_id = parts[0]
                    if tax_id != '9606':  # Human only
                        continue
                        
                    human_entries += 1
                    ncbi_gene_id = parts[1]
                    ensembl_gene_id = parts[2] 
                    rna_accession = parts[3] if parts[3] != '-' else None
                    ensembl_transcript_id = parts[4] if parts[4] != '-' else None
                    protein_accession = parts[5] if parts[5] != '-' else None
                    ensembl_protein_id = parts[6] if len(parts) > 6 and parts[6] != '-' else None
                    
                    # Map by Ensembl gene ID (primary key in our system)
                    if ensembl_gene_id and ensembl_gene_id != '-':
                        gene_mapping[ensembl_gene_id] = {
                            'ncbi_gene_id': ncbi_gene_id,
                            'ensembl_transcript_id': ensembl_transcript_id,
                            'rna_accession': rna_accession,
                            'protein_accession': protein_accession,
                            'ensembl_protein_id': ensembl_protein_id
                        }
            
            # Update metadata
            self.filter_metadata['gene2ensembl'] = {
                'processed': True,
                'total': total_entries,
                'human': human_entries,
                'mapped_genes': len(gene_mapping),
                'process_date': datetime.now().isoformat()
            }
            
            self.logger.info(
                f"Gene2Ensembl mapping processed: {human_entries:,} human entries "
                f"from {total_entries:,} total, resulting in {len(gene_mapping):,} gene mappings"
            )
            
            return gene_mapping
            
        except Exception as e:
            raise ProcessingError(f"Failed to process Gene2Ensembl mapping: {e}")
    
    def download_hgnc_complete(self) -> Path:
        """Download HGNC complete dataset with caching.
        
        Returns:
            Path to the downloaded file
            
        Raises:
            DownloadError: If download fails
        """
        try:
            self.logger.info("Downloading HGNC complete dataset")
            # Use the BaseProcessor download method
            hgnc_file = self.download_file(
                url=self.hgnc_url,
                file_path=self.id_dir / "hgnc_complete.txt"
            )
            return hgnc_file
        except Exception as e:
            raise DownloadError(f"Failed to download HGNC complete dataset: {e}")
    
    def process_hgnc_complete(self, hgnc_file: Path) -> Dict[str, str]:
        """Process HGNC complete dataset for gene symbol resolution.
        
        Args:
            hgnc_file: Path to the HGNC complete file
            
        Returns:
            Dictionary mapping all gene symbols/aliases to official symbols
            
        Raises:
            ProcessingError: If processing fails
        """
        try:
            self.logger.info("Processing HGNC complete dataset")
            
            symbol_mapping = {}
            total_genes = 0
            total_aliases = 0
            
            with open(hgnc_file, 'r') as f:
                header = next(f)
                self.logger.info(f"HGNC header: {header.strip()}")
                
                for line in f:
                    parts = line.strip().split('\t')
                    if len(parts) < 4:
                        continue
                        
                    hgnc_id = parts[0]
                    official_symbol = parts[1]
                    alias_symbols = parts[2] if parts[2] else ""
                    ensembl_gene_id = parts[3] if parts[3] else ""
                    
                    total_genes += 1
                    
                    # Map official symbol to itself
                    symbol_mapping[official_symbol] = official_symbol
                    
                    # Map all aliases to official symbol
                    if alias_symbols:
                        aliases = alias_symbols.split('|')
                        for alias in aliases:
                            alias = alias.strip()
                            if alias and alias != official_symbol:
                                symbol_mapping[alias] = official_symbol
                                total_aliases += 1
            
            # Update metadata
            self.filter_metadata['hgnc'] = {
                'processed': True,
                'total': total_genes,
                'aliases': total_aliases,
                'total_mappings': len(symbol_mapping),
                'process_date': datetime.now().isoformat()
            }
            
            self.logger.info(
                f"HGNC dataset processed: {total_genes:,} official symbols, "
                f"{total_aliases:,} aliases, {len(symbol_mapping):,} total mappings"
            )
            
            return symbol_mapping
            
        except Exception as e:
            raise ProcessingError(f"Failed to process HGNC complete dataset: {e}")
    
    def create_comprehensive_mapping(self) -> Dict[str, Dict[str, List[str]]]:
        """Create comprehensive ID mapping by combining all sources.
        
        Returns:
            Dictionary mapping gene symbols to comprehensive ID information
            
        Raises:
            ProcessingError: If comprehensive mapping creation fails
        """
        try:
            self.logger.info("Creating comprehensive ID mapping from all sources")
            
            # Download and process all sources
            self.logger.info("Phase 1: Downloading all ID mapping sources")
            
            # 1. NCBI Gene2Ensembl (authoritative)
            gene2ensembl_file = self.download_gene2ensembl()
            gene2ensembl_mapping = self.process_gene2ensembl(gene2ensembl_file)
            
            # 2. HGNC Complete (gene symbol resolution)
            hgnc_file = self.download_hgnc_complete()
            hgnc_symbol_mapping = self.process_hgnc_complete(hgnc_file)
            
            # 3. UniProt (protein-centric IDs)
            uniprot_file = self.download_uniprot_mapping()
            uniprot_gene_mapping = self.process_uniprot_mapping(uniprot_file)
            
            self.logger.info("Phase 2: Integrating all ID mapping sources")
            
            # Create comprehensive mapping by gene symbol
            comprehensive_mapping: DefaultDict[str, Dict[str, List[str]]] = defaultdict(
                lambda: defaultdict(list)
            )
            
            # Start with database gene symbols from normalized genes table
            if not self.db_manager.cursor:
                raise DatabaseError("No database cursor available")

            self.db_manager.cursor.execute("""
                SELECT DISTINCT gene_symbol, gene_id
                FROM genes
                WHERE gene_symbol IS NOT NULL AND gene_id IS NOT NULL
            """)
            
            db_genes = self.db_manager.cursor.fetchall()
            self.logger.info(f"Found {len(db_genes):,} unique genes in database")
            
            # Integrate data for each database gene
            integration_stats = {
                'total_genes': len(db_genes),
                'gene2ensembl_matches': 0,
                'hgnc_symbol_resolved': 0,
                'uniprot_matches': 0,
                'comprehensive_records': 0
            }
            
            for gene_symbol, ensembl_gene_id in db_genes:
                # Resolve gene symbol using HGNC if needed
                resolved_symbol = hgnc_symbol_mapping.get(gene_symbol, gene_symbol)
                if resolved_symbol != gene_symbol:
                    integration_stats['hgnc_symbol_resolved'] += 1
                
                # Add Gene2Ensembl data
                if ensembl_gene_id in gene2ensembl_mapping:
                    gene2ensembl_data = gene2ensembl_mapping[ensembl_gene_id]
                    comprehensive_mapping[gene_symbol]['ncbi_id'].append(gene2ensembl_data['ncbi_gene_id'])
                    if gene2ensembl_data['ensembl_transcript_id']:
                        comprehensive_mapping[gene_symbol]['ensembl_transcript_id'].append(gene2ensembl_data['ensembl_transcript_id'])
                    if gene2ensembl_data['rna_accession']:
                        comprehensive_mapping[gene_symbol]['refseq_mrna_id'].append(gene2ensembl_data['rna_accession'])
                    if gene2ensembl_data['protein_accession']:
                        comprehensive_mapping[gene_symbol]['refseq_protein_id'].append(gene2ensembl_data['protein_accession'])
                    integration_stats['gene2ensembl_matches'] += 1
                
                # Add UniProt data (use resolved symbol)
                if resolved_symbol in uniprot_gene_mapping:
                    uniprot_data = uniprot_gene_mapping[resolved_symbol]
                    for id_type, id_list in uniprot_data.items():
                        comprehensive_mapping[gene_symbol][id_type].extend(id_list)
                    integration_stats['uniprot_matches'] += 1
                
                # Count comprehensive records (those with multiple ID types)
                if len(comprehensive_mapping[gene_symbol]) >= 2:
                    integration_stats['comprehensive_records'] += 1
            
            # Convert to regular dict and log statistics
            final_mapping = {k: dict(v) for k, v in comprehensive_mapping.items()}
            
            self.logger.info(f"Comprehensive ID mapping integration statistics:")
            for stat_name, count in integration_stats.items():
                percentage = (count / integration_stats['total_genes']) * 100 if integration_stats['total_genes'] > 0 else 0
                self.logger.info(f"  - {stat_name}: {count:,} ({percentage:.1f}%)")
            
            return final_mapping
            
        except Exception as e:
            raise ProcessingError(f"Failed to create comprehensive mapping: {e}")

    def run(self) -> None:
        """Run the comprehensive ID enrichment pipeline using multiple authoritative sources.
        
        Steps:
        1. Download and process NCBI Gene2Ensembl mapping (authoritative)
        2. Download and process HGNC complete dataset (gene symbol resolution)
        3. Download and process UniProt mapping (protein-centric IDs)
        4. Create comprehensive mapping by integrating all sources
        5. Update transcript records with comprehensive ID information
        
        Raises:
            Various ETLError subclasses based on failure point
        """
        try:
            self.logger.info("Starting comprehensive ID enrichment pipeline")
            
            # Add diagnostic query to count transcripts before processing
            if not self.ensure_connection() or not self.db_manager.cursor:
                raise DatabaseError("Database connection failed")
                    
            self.db_manager.cursor.execute("""
                SELECT 
                    COUNT(*) as total_records,
                    COUNT(CASE WHEN uniprot_ids IS NOT NULL AND array_length(uniprot_ids, 1) > 0 THEN 1 END) as with_uniprot,
                    COUNT(CASE WHEN ncbi_ids IS NOT NULL AND array_length(ncbi_ids, 1) > 0 THEN 1 END) as with_ncbi,
                    COUNT(CASE WHEN alt_gene_ids IS NOT NULL AND alt_gene_ids != '{}'::jsonb THEN 1 END) as with_alt_gene_ids,
                    COUNT(CASE WHEN alt_transcript_ids IS NOT NULL AND alt_transcript_ids != '{}'::jsonb THEN 1 END) as with_alt_transcript_ids
                FROM cancer_transcript_base
            """)
            
            stats = self.db_manager.cursor.fetchone()
            if stats:
                self.logger.info(
                    f"Before ID enrichment:\n"
                    f"- Total records: {stats[0]:,}\n"
                    f"- Records with UniProt IDs: {stats[1]:,} ({stats[1]/max(1, stats[0])*100:.1f}%)\n"
                    f"- Records with NCBI IDs: {stats[2]:,} ({stats[2]/max(1, stats[0])*100:.1f}%)\n"
                    f"- Records with alt gene IDs: {stats[3]:,} ({stats[3]/max(1, stats[0])*100:.1f}%)\n"
                    f"- Records with alt transcript IDs: {stats[4]:,} ({stats[4]/max(1, stats[0])*100:.1f}%)"
                )
            
            # Check schema version
            if not self.ensure_schema_version('v0.1.4'):
                raise DatabaseError("Incompatible database schema version")
            
            # Create comprehensive mapping from all sources
            comprehensive_mapping = self.create_comprehensive_mapping()
            
            # Update transcript records with comprehensive ID information
            self.update_transcript_ids(comprehensive_mapping)
            
            self.logger.info("Comprehensive ID enrichment completed successfully")
            
        except Exception as e:
            self.logger.error(f"ID enrichment failed: {e}")
            raise
