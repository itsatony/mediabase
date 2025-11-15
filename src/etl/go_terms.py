"""GO terms enrichment module for Cancer Transcriptome Base.

This module handles downloading, processing, and enrichment of Gene Ontology (GO) terms
for transcript records, providing structured access to functional classifications.
"""

import logging
import gzip
import json
from pathlib import Path
from typing import Dict, List, Optional, Any, Set, Tuple, Iterator, TypedDict
import networkx as nx
from tqdm import tqdm
import obonet
from rich.console import Console
from rich.table import Table

from .base_processor import BaseProcessor, DownloadError, ProcessingError, DatabaseError
from .publications import Publication, PublicationsProcessor
from ..utils.publication_utils import extract_pmids_from_text, format_pmid_url
# Fix: Add get_progress_bar to the imports
from ..utils.progress import tqdm_with_logging, SuppressPandasWarnings, get_progress_bar
from ..utils.pandas_helpers import safe_assign, safe_batch_assign
# Add new import at the top with other imports
from ..utils.gene_matcher import normalize_gene_symbol, match_genes_bulk, get_gene_match_stats

# Constants
HUMAN_SPECIES = 'Homo sapiens'

class GOTerm(TypedDict):
    """Type definition for GO term data."""
    term: str
    evidence: str
    aspect: str

class GOTermProcessor(BaseProcessor):
    """Process GO terms and enrich transcript data."""

    def __init__(self, config: Dict[str, Any]) -> None:
        """Initialize the GO term processor with configuration.
        
        Args:
            config: Configuration dictionary with settings
        """
        super().__init__(config)
        
        # Define specific directory for GO data
        self.go_dir = self.cache_dir / 'go_terms'
        self.go_dir.mkdir(exist_ok=True)
        
        # GO OBO data URL
        self.go_obo_url = config.get(
            'go_obo_url',
            'http://purl.obolibrary.org/obo/go.obo'
        )
        
        # GOA annotation URL
        self.goa_url = config.get(
            'goa_url', 
            'http://ftp.ebi.ac.uk/pub/databases/GO/goa/HUMAN/goa_human.gaf.gz'
        )
        
        # Initialize graph storage
        self.go_graph: Optional[nx.MultiDiGraph] = None
        
        # Define aspect roots
        self.aspect_roots = {
            'molecular_function': 'GO:0003674',
            'biological_process': 'GO:0008150',
            'cellular_component': 'GO:0005575'
        }
        
        # Add mappings for special term types
        self.molecular_function_roots = {
            'GO:0003674',  # molecular_function
        }
        
        self.cellular_location_roots = {
            'GO:0005575',  # cellular_component
        }
    
    def download_obo(self) -> Path:
        """Download GO OBO file with caching.
        
        Returns:
            Path to the downloaded OBO file
            
        Raises:
            DownloadError: If download fails
        """
        try:
            # Use the BaseProcessor download method
            obo_file = self.download_file(
                url=self.go_obo_url,
                file_path=self.go_dir / "go.obo"
            )
            return obo_file
        except Exception as e:
            raise DownloadError(f"Failed to download GO OBO file: {e}")
    
    def download_goa(self) -> Path:
        """Download GOA file with caching.
        
        Returns:
            Path to the downloaded GOA file
            
        Raises:
            DownloadError: If download fails
        """
        try:
            # Use the BaseProcessor download method
            goa_file = self.download_file(
                url=self.goa_url,
                file_path=self.go_dir / "goa_human.gaf.gz"
            )
            return goa_file
        except Exception as e:
            raise DownloadError(f"Failed to download GOA file: {e}")
    
    def load_go_graph(self, obo_path: Path) -> None:
        """Load GO terms into a networkx graph.
        
        Args:
            obo_path: Path to the OBO file
            
        Raises:
            ProcessingError: If graph loading fails
        """
        try:
            self.logger.info("Loading GO graph...")
            self.go_graph = obonet.read_obo(obo_path)
            self.logger.info(f"Loaded {len(self.go_graph)} GO terms")
        except Exception as e:
            raise ProcessingError(f"Failed to load GO graph: {e}")
    
    def get_ancestors(self, term_id: str, aspect: Optional[str] = None) -> Set[str]:
        """Get all ancestors of a GO term up to the root.

        Args:
            term_id: GO term ID
            aspect: Optional aspect to filter ancestors

        Returns:
            Set of ancestor term IDs

        Raises:
            ProcessingError: If graph is not loaded
        """
        if not self.go_graph:
            raise ProcessingError("GO graph not loaded")

        ancestors = set()
        to_visit = {term_id}

        while to_visit:
            current = to_visit.pop()
            ancestors.add(current)

            # Get all parent terms via out_edges (obonet creates edges for is_a relationships)
            # The edge data may contain a 'relation' key for part_of, but is_a edges have no data
            parents = set()
            for _, parent, data in self.go_graph.out_edges(current, data=True):
                # Accept all edges (is_a relationships) and specifically marked part_of relationships
                if not data or 'relation' not in data or data.get('relation') in {'is_a', 'part_of'}:
                    parents.add(parent)

            # Add unvisited parents to the queue
            to_visit.update(parents - ancestors)

        # Filter by aspect if specified
        if aspect and aspect in self.aspect_roots:
            root = self.aspect_roots[aspect]
            if root in ancestors:
                return {a for a in ancestors if self.get_aspect(a) == aspect} - {term_id}
            return set()

        return ancestors - {term_id}  # Exclude the term itself
    
    def get_aspect(self, term_id: str) -> Optional[str]:
        """Get the aspect (namespace) of a GO term.
        
        Args:
            term_id: GO term ID
            
        Returns:
            Aspect string or None if not found
        """
        if not self.go_graph or term_id not in self.go_graph:
            return None
        
        term_data = self.go_graph.nodes.get(term_id, {})
        namespace = term_data.get('namespace')
        
        if namespace == 'molecular_function':
            return 'molecular_function'
        elif namespace == 'biological_process':
            return 'biological_process'
        elif namespace == 'cellular_component':
            return 'cellular_component'
        return None
    
    def _convert_aspect(self, aspect_code: str) -> str:
        """Convert single-letter aspect code to full name.
        
        Args:
            aspect_code: Single letter aspect code (P, F, C)
            
        Returns:
            Full aspect name
        """
        aspects = {
            'P': 'biological_process',
            'F': 'molecular_function',
            'C': 'cellular_component'
        }
        return aspects.get(aspect_code, '')
    
    def _get_valid_genes(self) -> Set[str]:
        """Get set of valid gene symbols from database.
        
        Returns:
            Set of valid gene symbols
            
        Raises:
            DatabaseError: If database query fails
        """
        valid_genes: Set[str] = set()
        
        if not self.ensure_connection() or not self.db_manager.cursor:
            raise DatabaseError("Cannot get valid genes: no database connection")
            
        try:
            self.db_manager.cursor.execute("""
                SELECT DISTINCT gene_symbol 
                FROM cancer_transcript_base 
                WHERE gene_symbol IS NOT NULL
            """)
            valid_genes = {row[0] for row in self.db_manager.cursor.fetchall() if row[0]}
            self.logger.info(f"Found {len(valid_genes)} valid gene symbols in database")
        except Exception as e:
            raise DatabaseError(f"Failed to get valid genes: {e}")
            
        return valid_genes
    
    def process_goa_file(self, goa_path: Path) -> Dict[str, Dict[str, GOTerm]]:
        """Process GOA file and extract gene-GO term mappings.
        
        Args:
            goa_path: Path to the GOA file
            
        Returns:
            Dictionary mapping gene symbols to GO term dictionaries
            
        Raises:
            ProcessingError: If GO data processing fails
        """
        try:
            gene_go_terms: Dict[str, Dict[str, GOTerm]] = {}
            
            # First, get and show sample of valid gene symbols
            valid_genes = self._get_valid_genes()
            sample_entries: List[List[str]] = []
            
            # Build normalized gene symbol map for faster matching
            valid_gene_list = list(valid_genes)
            self.logger.info(f"Building normalized gene symbol map for {len(valid_gene_list)} genes")
            gene_matches = {normalize_gene_symbol(g): g for g in valid_gene_list if g}
            
            with gzip.open(goa_path, 'rt') as f:
                for line in tqdm_with_logging(f, desc='Processing GOA entries', module_name="etl.go_terms"):
                    if line.startswith('!'):
                        continue
                    
                    fields = line.strip().split('\t')
                    if len(fields) < 15:
                        continue
                    
                    if not self.go_graph:
                        raise ProcessingError("GO graph not loaded")
                        
                    # Store sample entries before any filtering
                    if len(sample_entries) < 5 and not line.startswith('!'):
                        sample_entries.append(fields)
                    
                    # Extract required fields with safe access
                    gene_symbol = fields[2] if len(fields) > 2 else ''
                    go_id = fields[4] if len(fields) > 4 else ''
                    evidence = fields[6] if len(fields) > 6 else ''
                    aspect = fields[8] if len(fields) > 8 else ''
                    
                    if not (gene_symbol and go_id and evidence and aspect):
                        continue
                    
                    # Use case-insensitive matching with the normalized map
                    norm_gene = normalize_gene_symbol(gene_symbol)
                    if norm_gene not in gene_matches or go_id not in self.go_graph:
                        continue
                    
                    # Get matched database gene symbol
                    db_gene = gene_matches[norm_gene]
                    
                    # Get GO term data with safe access
                    node_data = self.go_graph.nodes.get(go_id, {})
                    term_name = node_data.get('name', '')
                    if not term_name:  # Skip if no term name found
                        continue
                    
                    # Initialize gene entry if needed
                    if db_gene not in gene_go_terms:
                        gene_go_terms[db_gene] = {}
                    
                    # Extract PMID from evidence code if present
                    pmid = None
                    if evidence.startswith('PMID:'):
                        pmid = evidence.replace('PMID:', '').strip()
                    
                    # Store GO term with safe type construction
                    gene_go_terms[db_gene][go_id] = {
                        'term': term_name,
                        'evidence': evidence,
                        'aspect': self._convert_aspect(aspect),
                        'pmid': pmid  # Add PMID if found
                    }
            
            # Display statistics and samples
            self._display_goa_stats(
                processed=len(sample_entries),
                matched=len(gene_go_terms),
                gene_go_terms=gene_go_terms,
                sample_entries=sample_entries
            )
            
            return gene_go_terms
            
        except Exception as e:
            raise ProcessingError(f"Failed to process GOA file: {e}")
    
    def _display_goa_stats(
        self, 
        processed: int, 
        matched: int, 
        gene_go_terms: Dict[str, Dict[str, GOTerm]], 
        sample_entries: List[List[str]]
    ) -> None:
        """Display GOA processing statistics and samples.
        
        Args:
            processed: Number of entries processed
            matched: Number of entries matched to genes
            gene_go_terms: Dictionary of gene-to-GO-term mappings
            sample_entries: Sample of GOA entries
        """
        console = Console()
        
        # Display sample entries
        table = Table(title="Sample GOA Entries")
        table.add_column("DB")
        table.add_column("Object ID")
        table.add_column("Gene Symbol")
        table.add_column("GO ID")
        table.add_column("Evidence")
        table.add_column("Aspect")
        
        for entry in sample_entries:
            if len(entry) >= 9:
                db = entry[0]
                obj_id = entry[1]
                gene = entry[2]
                go_id = entry[4]
                evidence = entry[6]
                aspect = entry[8]
                table.add_row(db, obj_id, gene, go_id, evidence, aspect)
        console.print(table)

        # Display processed terms sample
        if gene_go_terms:
            sample_gene = next(iter(gene_go_terms))
            sample_terms = gene_go_terms.get(sample_gene, {})
            
            if sample_terms:  # Only create table if we have terms
                table = Table(title=f"Sample Processed GO Terms for {sample_gene}")
                table.add_column("GO ID")
                table.add_column("Term")
                table.add_column("Evidence")
                table.add_column("Aspect")
                
                for go_id, term_data in list(sample_terms.items())[:5]:
                    table.add_row(
                        go_id,
                        term_data['term'],
                        term_data['evidence'],
                        term_data['aspect']
                    )
                console.print(table)
        
        self.logger.info(
            f"GOA Processing Stats:\n"
            f"- Total entries processed: {processed:,}\n"
            f"- Matched to database genes: {matched:,}\n"
            f"- Genes with GO terms: {len(gene_go_terms):,}"
        )
    
    def _extract_special_terms(self, go_terms: Dict[str, GOTerm]) -> Tuple[List[str], List[str]]:
        """Extract molecular functions and cellular locations from GO terms.
        
        Args:
            go_terms: Dictionary of GO terms
            
        Returns:
            Tuple of (molecular_functions, cellular_locations)
        """
        molecular_functions: Set[str] = set()
        cellular_locations: Set[str] = set()
        
        for go_id, term_data in go_terms.items():
            # Skip terms without proper data
            if not isinstance(term_data, dict) or 'aspect' not in term_data or 'term' not in term_data:
                continue
                
            term_name = term_data.get('term', '')
            aspect = term_data.get('aspect', '')
            
            # Classify terms based on aspect
            if aspect == 'molecular_function':
                molecular_functions.add(term_name)
            elif aspect == 'cellular_component':
                cellular_locations.add(term_name)
        
        return list(molecular_functions), list(cellular_locations)
    
    def extract_publication_references(self, go_terms: Dict[str, GOTerm]) -> List[Publication]:
        """Extract publication references from GO terms with evidence codes.
        
        Args:
            go_terms: Dictionary of GO terms with evidence codes
            
        Returns:
            List of publication references
        """
        publications: List[Publication] = []
        pmids_found = 0
        
        for go_id, term_data in go_terms.items():
            # Direct PMID extraction from stored pmid field
            pmid = term_data.get('pmid')
            if pmid and pmid.strip():
                publication = PublicationsProcessor.create_publication_reference(
                    pmid=pmid.strip(),
                    evidence_type='experimental',  # PMID evidence is experimental
                    source_db="GO",
                    url=f"http://amigo.geneontology.org/amigo/term/{go_id}"
                )
                publications.append(publication)
                pmids_found += 1
            
            # Also check evidence text for any missed PMIDs
            evidence_text = term_data.get('evidence', '')
            if evidence_text and 'PMID:' in evidence_text:
                pmids = extract_pmids_from_text(evidence_text)
                for extracted_pmid in pmids:
                    # Avoid duplicates
                    if extracted_pmid != pmid:
                        publication = PublicationsProcessor.create_publication_reference(
                            pmid=extracted_pmid,
                            evidence_type='experimental',
                            source_db="GO",
                            url=f"http://amigo.geneontology.org/amigo/term/{go_id}"
                        )
                        publications.append(publication)
                        pmids_found += 1
        
        # Log PMID extraction statistics for monitoring
        if pmids_found > 0:
            self.logger.debug(f"Extracted {pmids_found} PMIDs from {len(go_terms)} GO terms")
        
        return publications
    
    def populate_initial_terms(self) -> None:
        """Populate initial GO terms from GOA data.
        
        Raises:
            DatabaseError: If database operations fail
        """
        if not self.ensure_connection():
            raise DatabaseError("Database connection failed")
            
        try:
            # Add diagnostic query to count genes before processing
            if not self.db_manager.cursor:
                raise DatabaseError("No database cursor available")
                
            self.db_manager.cursor.execute("""
                SELECT 
                    COUNT(*) as total_genes,
                    COUNT(CASE WHEN gene_type = 'protein_coding' THEN 1 END) as protein_coding,
                    COUNT(CASE WHEN go_terms IS NOT NULL THEN 1 END) as with_go_terms,
                    COUNT(CASE WHEN molecular_functions IS NOT NULL AND array_length(molecular_functions, 1) > 0 THEN 1 END) as with_functions,
                    COUNT(CASE WHEN cellular_location IS NOT NULL AND array_length(cellular_location, 1) > 0 THEN 1 END) as with_locations
                FROM cancer_transcript_base
            """)
            
            stats = self.db_manager.cursor.fetchone()
            if stats:
                self.logger.info(
                    f"Before GO term processing:\n"
                    f"- Total genes: {stats[0]:,}\n"
                    f"- Protein-coding genes: {stats[1]:,} ({stats[1]/max(1, stats[0])*100:.1f}%)\n"
                    f"- Genes with GO terms: {stats[2]:,} ({stats[2]/max(1, stats[0])*100:.1f}%)\n"
                    f"- Genes with molecular functions: {stats[3]:,} ({stats[3]/max(1, stats[0])*100:.1f}%)\n"
                    f"- Genes with cellular locations: {stats[4]:,} ({stats[4]/max(1, stats[0])*100:.1f}%)"
                )
            
            # Download and process GOA file
            goa_path = self.download_goa()
            gene_go_terms = self.process_goa_file(goa_path)
            
            if not gene_go_terms:
                self.logger.warning("No GO terms found to populate")
                return
                
            # First, get a count of existing terms
            self.db_manager.cursor.execute("""
                SELECT COUNT(*) FROM cancer_transcript_base 
                WHERE go_terms IS NOT NULL
            """)
            result = self.db_manager.cursor.fetchone()
            initial_count = result[0] if result else 0
            self.logger.info(f"Initial GO terms count: {initial_count}")
            
            # Use a separate transaction for clearing existing GO terms
            with self.get_db_transaction() as transaction:
                # Clear existing GO terms - REMOVED gene_type filter
                transaction.cursor.execute("""
                    UPDATE cancer_transcript_base 
                    SET go_terms = NULL, molecular_functions = NULL, cellular_location = NULL
                """)
            
            # Process in smaller batches with separate transactions
            updates = []
            processed = 0
            batch_size = min(1000, self.batch_size)
            
            # Use get_progress_bar for tracking progress
            progress_bar = get_progress_bar(len(gene_go_terms), "Updating GO terms", "etl.go_terms")
            for i, (gene_symbol, go_terms) in enumerate(gene_go_terms.items()):
                if go_terms:
                    # Extract special term arrays
                    molecular_functions, cellular_locations = self._extract_special_terms(go_terms)
                    
                    # Extract publications
                    publications = self.extract_publication_references(go_terms)
                    
                    updates.append((
                        json.dumps(go_terms),
                        molecular_functions,
                        cellular_locations,
                        json.dumps(publications) if publications else None,
                        gene_symbol
                    ))
                    
                    if len(updates) >= batch_size:
                        self._update_go_terms_batch(updates)
                        processed += len(updates)
                        progress_bar.update(len(updates))
                        updates = []
                
                # Update progress
                progress_bar.update(1)
            
            # Process remaining updates
            if updates:
                self._update_go_terms_batch(updates)
                processed += len(updates)
                    
            # Close progress bar
            progress_bar.close()
            
            # Verify the updates
            if not self.db_manager.cursor:
                raise DatabaseError("No database cursor available")
                
            self.db_manager.cursor.execute("""
                SELECT 
                    COUNT(*) as total_genes,
                    COUNT(CASE WHEN go_terms IS NOT NULL THEN 1 END) as with_terms,
                    COUNT(CASE WHEN molecular_functions IS NOT NULL THEN 1 END) as with_mf,
                    COUNT(CASE WHEN cellular_location IS NOT NULL THEN 1 END) as with_cl
                FROM cancer_transcript_base
            """)
            stats = self.db_manager.cursor.fetchone()
            
            if stats:
                self.logger.info(
                    "Database Update Results:\n"
                    f"- Total genes processed: {processed:,}\n"
                    f"- Genes in database: {stats[0]:,}\n"
                    f"- Genes with GO terms: {stats[1]:,}\n"
                    f"- Genes with molecular functions: {stats[2]:,}\n"
                    f"- Genes with cellular locations: {stats[3]:,}"
                )
            
            self.logger.info("Initial GO terms population completed successfully")
            
        except Exception as e:
            self.logger.error(f"Initial GO terms population failed: {e}")
            raise
    
    def _update_go_terms_batch(self, updates: List[Tuple]) -> None:
        """Update a batch of GO terms in the database.
        
        Args:
            updates: List of update tuples (go_terms, molecular_functions, cellular_locations, publications, gene_symbol)
            
        Raises:
            DatabaseError: If batch update fails
        """
        if not self.db_manager.cursor:
            raise DatabaseError("No database cursor available")
            
        try:
            # Use a transaction context manager for better control
            with self.get_db_transaction() as transaction:
                # Create temporary table for this batch
                transaction.cursor.execute("""
                    CREATE TEMP TABLE temp_go_terms (
                        gene_symbol TEXT PRIMARY KEY,
                        go_terms JSONB,
                        molecular_functions TEXT[],
                        cellular_location TEXT[],
                        publications JSONB
                    ) ON COMMIT DROP
                """)
                
                # Insert batch data one at a time with conflict handling
                for update in updates:
                    # Extract data from update tuple
                    gene_symbol = update[4]
                    go_terms_json = update[0] 
                    molecular_functions = update[1]
                    cellular_location = update[2]
                    publications = update[3]
                    
                    # Use ON CONFLICT to handle duplicate gene symbols by merging data
                    transaction.cursor.execute(
                        """
                        INSERT INTO temp_go_terms 
                        (gene_symbol, go_terms, molecular_functions, cellular_location, publications)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (gene_symbol) DO UPDATE SET
                            go_terms = temp_go_terms.go_terms || EXCLUDED.go_terms,
                            molecular_functions = array(
                                SELECT DISTINCT unnest(
                                    array_cat(temp_go_terms.molecular_functions, EXCLUDED.molecular_functions)
                                )
                            ),
                            cellular_location = array(
                                SELECT DISTINCT unnest(
                                    array_cat(temp_go_terms.cellular_location, EXCLUDED.cellular_location)
                                )
                            ),
                            publications = COALESCE(temp_go_terms.publications, '[]'::jsonb) || 
                                          COALESCE(EXCLUDED.publications, '[]'::jsonb)
                        """,
                        (gene_symbol, go_terms_json, molecular_functions, cellular_location, publications)
                    )
                
                # Update normalized schema: create transcript GO term relationships
                transaction.cursor.execute("""
                    INSERT INTO transcript_go_terms (transcript_id, go_id, go_term, go_category, evidence_code)
                    SELECT
                        tr.transcript_id,
                        go_entry.value->>'go_id' as go_id,
                        go_entry.value->>'name' as go_term,
                        go_entry.value->>'category' as go_category,
                        COALESCE(go_entry.value->>'evidence', 'IEA') as evidence_code
                    FROM temp_go_terms t
                    INNER JOIN genes g ON g.gene_symbol = t.gene_symbol
                    INNER JOIN transcripts tr ON tr.gene_id = g.gene_id
                    CROSS JOIN LATERAL jsonb_array_elements(t.go_terms) as go_entry
                    ON CONFLICT DO NOTHING
                """)

                # Also create gene annotations for molecular functions and cellular location
                transaction.cursor.execute("""
                    INSERT INTO gene_annotations (gene_id, annotation_type, annotation_value, source)
                    SELECT
                        g.gene_id,
                        'molecular_function' as annotation_type,
                        unnest(t.molecular_functions) as annotation_value,
                        'Gene Ontology' as source
                    FROM temp_go_terms t
                    INNER JOIN genes g ON g.gene_symbol = t.gene_symbol
                    WHERE array_length(t.molecular_functions, 1) > 0
                    ON CONFLICT DO NOTHING
                """)

                transaction.cursor.execute("""
                    INSERT INTO gene_annotations (gene_id, annotation_type, annotation_value, source)
                    SELECT
                        g.gene_id,
                        'cellular_location' as annotation_type,
                        unnest(t.cellular_location) as annotation_value,
                        'Gene Ontology' as source
                    FROM temp_go_terms t
                    INNER JOIN genes g ON g.gene_symbol = t.gene_symbol
                    WHERE array_length(t.cellular_location, 1) > 0
                    ON CONFLICT DO NOTHING
                """)

                # Update legacy table for backwards compatibility (if it exists)
                try:
                    transaction.cursor.execute("""
                        SELECT 1 FROM information_schema.tables
                        WHERE table_name = 'cancer_transcript_base'
                    """)
                    if transaction.cursor.fetchone():
                        transaction.cursor.execute("""
                            UPDATE cancer_transcript_base c
                            SET
                                go_terms = t.go_terms,
                                molecular_functions = t.molecular_functions,
                                cellular_location = t.cellular_location,
                                source_references = jsonb_set(
                                    COALESCE(c.source_references, '{
                                        "go_terms": [],
                                        "uniprot": [],
                                        "drugs": [],
                                        "pathways": []
                                    }'::jsonb),
                                    '{go_terms}',
                                    COALESCE(t.publications, '[]'::jsonb),
                                    true
                                )
                            FROM temp_go_terms t
                            WHERE c.gene_symbol = t.gene_symbol
                        """)
                except Exception as e:
                    self.logger.info(f"Legacy table update skipped (normal after migration): {e}")
                
                # The temp table will be automatically dropped on COMMIT
        except Exception as e:
            raise DatabaseError(f"Failed to update GO terms batch: {e}")
    
    def enrich_transcripts(self) -> None:
        """Enrich transcript records with GO term hierarchies.
        
        Raises:
            DatabaseError: If database operations fail
            ProcessingError: If GO graph is not loaded
        """
        if not self.ensure_connection():
            raise DatabaseError("Database connection failed")
            
        if not self.go_graph:
            raise ProcessingError("GO graph not loaded")
            
        if not self.db_manager.cursor:
            raise DatabaseError("No database cursor available")
            
        try:
            # Get transcripts with existing GO terms - REMOVED gene_type filter
            self.db_manager.cursor.execute("""
                SELECT transcript_id, gene_symbol, go_terms 
                FROM cancer_transcript_base 
                WHERE go_terms IS NOT NULL
            """)
            
            transcripts = self.db_manager.cursor.fetchall()
            total_processed = 0
            total_enriched = 0
            
            updates = []
            # Use get_progress_bar for progress tracking
            progress_bar = get_progress_bar(len(transcripts), "Enriching GO terms", "etl.go_terms")
            for i, (transcript_id, gene_symbol, go_terms) in enumerate(transcripts):
                if not go_terms:
                    progress_bar.update(1)
                    continue
                    
                initial_term_count = len(go_terms)
                enriched_terms = {}
                
                # Process existing terms
                for go_id, term_data in go_terms.items():
                    # Get original term data
                    term_info = {
                        'term': term_data.get('term', ''),
                        'evidence': term_data.get('evidence', ''),
                        'aspect': term_data.get('aspect', '')
                    }
                    enriched_terms[go_id] = term_info
                    
                    # Add ancestors with inherited evidence
                    ancestors = self.get_ancestors(go_id, term_data.get('aspect', ''))
                    for ancestor in ancestors:
                        if ancestor in self.go_graph.nodes:
                            ancestor_data = self.go_graph.nodes.get(ancestor, {})
                            if ancestor not in enriched_terms:
                                enriched_terms[ancestor] = {
                                    'term': ancestor_data.get('name', ''),
                                    'evidence': f"Inherited from {go_id}",
                                    'aspect': ancestor_data.get('namespace', '')
                                }
                
                final_term_count = len(enriched_terms)
                if final_term_count > initial_term_count:
                    total_enriched += 1
                    
                total_processed += 1
                
                # Extract special term arrays for the enriched terms
                molecular_functions, cellular_locations = self._extract_special_terms(enriched_terms)
                
                updates.append((
                    json.dumps(enriched_terms),
                    molecular_functions,
                    cellular_locations,
                    gene_symbol
                ))
                
                if len(updates) >= self.batch_size:
                    self._update_enriched_terms_batch(updates)
                    updates = []
                    
                progress_bar.update(1)
            
            # Process remaining updates
            if updates:
                self._update_enriched_terms_batch(updates)
                
            # Close progress bar
            progress_bar.close()
            
            self.logger.info(
                f"GO term enrichment completed:\n"
                f"- Total transcripts processed: {total_processed}\n"
                f"- Transcripts enriched with ancestors: {total_enriched}"
            )
            
        except Exception as e:
            self.logger.error(f"GO term enrichment failed: {e}")
            raise
    
    def _update_enriched_terms_batch(self, updates: List[Tuple]) -> None:
        """Update a batch of enriched GO terms in the database.
        
        Args:
            updates: List of update tuples (go_terms, molecular_functions, cellular_locations, gene_symbol)
            
        Raises:
            DatabaseError: If batch update fails
        """
        if not self.db_manager.cursor:
            raise DatabaseError("No database cursor available")
            
        try:
            # Use a transaction context manager for better control
            with self.get_db_transaction() as transaction:
                # Create temporary table for this batch
                transaction.cursor.execute("""
                    CREATE TEMP TABLE temp_enriched_terms (
                        gene_symbol TEXT PRIMARY KEY,
                        go_terms JSONB,
                        molecular_functions TEXT[],
                        cellular_location TEXT[]
                    ) ON COMMIT DROP
                """)
                
                # Insert batch data one at a time with conflict handling
                for update in updates:
                    # Extract data from update tuple
                    gene_symbol = update[3]
                    go_terms_json = update[0]
                    molecular_functions = update[1]
                    cellular_location = update[2]
                    
                    # Use ON CONFLICT to handle duplicate gene symbols by merging data
                    transaction.cursor.execute(
                        """
                        INSERT INTO temp_enriched_terms 
                        (gene_symbol, go_terms, molecular_functions, cellular_location)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (gene_symbol) DO UPDATE SET
                            go_terms = temp_enriched_terms.go_terms || EXCLUDED.go_terms,
                            molecular_functions = array(
                                SELECT DISTINCT unnest(
                                    array_cat(temp_enriched_terms.molecular_functions, EXCLUDED.molecular_functions)
                                )
                            ),
                            cellular_location = array(
                                SELECT DISTINCT unnest(
                                    array_cat(temp_enriched_terms.cellular_location, EXCLUDED.cellular_location)
                                )
                            )
                        """,
                        (gene_symbol, go_terms_json, molecular_functions, cellular_location)
                    )
                
                # Update from temp table to main table in same transaction
                transaction.cursor.execute("""
                    UPDATE cancer_transcript_base c
                    SET 
                        go_terms = t.go_terms,
                        molecular_functions = t.molecular_functions,
                        cellular_location = t.cellular_location
                    FROM temp_enriched_terms t
                    WHERE c.gene_symbol = t.gene_symbol
                """)
                
                # The temp table will be automatically dropped on COMMIT
        except Exception as e:
            raise DatabaseError(f"Failed to update enriched GO terms batch: {e}")
    
    def run(self) -> None:
        """Run the complete GO term enrichment pipeline.
        
        Steps:
        1. Download GO OBO file
        2. Load GO graph
        3. Populate initial terms from GOA
        4. Enrich terms with hierarchy
        
        Raises:
            Various ETLError subclasses based on failure point
        """
        try:
            self.logger.info("Starting GO term enrichment pipeline")
            
            # Check schema version using enhanced base class method
            if not self.ensure_schema_version('v0.1.3'):
                raise DatabaseError("Incompatible database schema version")
            
            # Download GO OBO file and load graph
            obo_path = self.download_obo()
            self.load_go_graph(obo_path)
            
            # Populate initial terms from GOA
            self.logger.info("Populating initial GO terms from GOA")
            self.populate_initial_terms()
            
            # Ensure connection is still valid before enrichment
            self.ensure_connection()
            
            # Enrich terms with hierarchy
            self.logger.info("Enriching GO terms with ancestors")
            self.enrich_transcripts()
            
            self.logger.info("GO term processing completed successfully")
        except Exception as e:
            self.logger.error(f"GO term processing failed: {e}")
            raise

def integrate_go_terms(self, go_data: Dict[str, Any]) -> None:
    """Integrate GO term data into the transcript database.
    
    Args:
        go_data: Dictionary containing GO term data by gene ID
        
    Raises:
        DatabaseError: If database operations fail
    """
    if not self.ensure_connection():
        raise DatabaseError("Database connection failed")
        
    try:
        self.logger.info("Integrating GO terms with transcript data")
        
        # Create temp table for batch updates with additional ID support
        with self.get_db_transaction() as transaction:
            transaction.cursor.execute("""
                CREATE TEMP TABLE temp_go_data (
                    gene_symbol TEXT,
                    uniprot_ids TEXT[],
                    go_terms JSONB,
                    go_references JSONB
                ) ON COMMIT DROP
            """)
        
        updates = []
        processed = 0
        
        # Prepare gene mappings using all ID types
        for gene_symbol, terms in go_data.items():
            # Skip empty or invalid data
            if not gene_symbol or not terms:
                continue
            
            # Get additional IDs for this gene for more comprehensive mapping
            uniprot_ids = []
            if self.db_manager.cursor:
                self.db_manager.cursor.execute("""
                    SELECT uniprot_ids 
                    FROM cancer_transcript_base 
                    WHERE gene_symbol = %s AND uniprot_ids IS NOT NULL
                """, (gene_symbol,))
                result = self.db_manager.cursor.fetchone()
                if result and result[0]:
                    uniprot_ids = result[0]
            
            # Format GO terms as JSONB object with evidence codes
            go_terms_json = {}
            go_references = []
            for go_id, details in terms.items():
                go_terms_json[go_id] = {
                    'name': details.get('name', ''),
                    'namespace': details.get('namespace', ''),
                    'evidence': details.get('evidence', [])
                }
                # Extract references for this GO term
                if 'references' in details:
                    go_references.extend(details['references'])
            
            updates.append((
                gene_symbol,
                uniprot_ids,
                json.dumps(go_terms_json),
                json.dumps(go_references)
            ))
            processed += 1
            
            # Process in batches
            if len(updates) >= self.batch_size:
                self._update_go_batch(updates)
                updates = []
                self.logger.info(f"Processed {processed} genes with GO terms")
        
        # Process any remaining updates
        if updates:
            self._update_go_batch(updates)
        
        # Update main table from temp table with both gene symbol and UniProt ID mappings
        with self.get_db_transaction() as transaction:
            # Update by gene symbol first
            transaction.cursor.execute("""
                UPDATE cancer_transcript_base cb
                SET 
                    go_terms = COALESCE(cb.go_terms, '{}'::jsonb) || go.go_terms,
                    source_references = jsonb_set(
                        COALESCE(cb.source_references, '{
                            "go_terms": [],
                            "uniprot": [],
                            "drugs": [],
                            "pathways": []
                        }'::jsonb),
                        '{go_terms}',
                        go.go_references,
                        true
                    )
                FROM temp_go_data go
                WHERE cb.gene_symbol = go.gene_symbol
            """)
            
            # Also update by UniProt ID for broader coverage
            transaction.cursor.execute("""
                UPDATE cancer_transcript_base cb
                SET 
                    go_terms = COALESCE(cb.go_terms, '{}'::jsonb) || go.go_terms,
                    source_references = jsonb_set(
                        COALESCE(cb.source_references, '{
                            "go_terms": [],
                            "uniprot": [],
                            "drugs": [],
                            "pathways": []
                        }'::jsonb),
                        '{go_terms}',
                        go.go_references,
                        true
                    )
                FROM temp_go_data go
                WHERE cb.uniprot_ids && go.uniprot_ids
                AND cb.gene_symbol != go.gene_symbol  -- Only update non-direct matches
                AND go.uniprot_ids IS NOT NULL
                AND array_length(go.uniprot_ids, 1) > 0
            """)
            
            # Clean up
            transaction.cursor.execute("DROP TABLE IF EXISTS temp_go_data")
        
        self.logger.info(f"Successfully integrated GO terms for {processed} genes")
    except Exception as e:
        self.logger.error(f"Failed to integrate GO terms: {e}")
        raise DatabaseError(f"GO term integration failed: {e}")

def _update_go_batch(self, updates: List[Tuple[str, List[str], str, str]]) -> None:
    """Update a batch of GO term data.
    
    Args:
        updates: List of tuples with (gene_symbol, uniprot_ids, go_terms_json, go_references_json)
        
    Raises:
        DatabaseError: If batch update fails
    """
    try:
        # Use transaction context manager for better control
        with self.get_db_transaction() as transaction:
            # Create temporary table for this batch if it doesn't exist yet
            transaction.cursor.execute("""
                CREATE TEMP TABLE IF NOT EXISTS temp_go_data (
                    gene_symbol TEXT PRIMARY KEY,
                    uniprot_ids TEXT[],
                    go_terms JSONB,
                    go_references JSONB
                ) ON COMMIT DROP
            """)
            
            # Insert batch data into temp table
            transaction.cursor.executemany(
                """
                INSERT INTO temp_go_data 
                (gene_symbol, uniprot_ids, go_terms, go_references)
                VALUES (%s, %s, %s::jsonb, %s::jsonb)
                """,
                updates
            )
            
            # Update operations will happen in the calling function after all batches are processed
    except Exception as e:
        raise DatabaseError(f"Failed to update GO term batch: {e}")
