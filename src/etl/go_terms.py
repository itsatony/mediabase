"""GO terms enrichment module for Cancer Transcriptome Base."""

import logging
import gzip
import json
from pathlib import Path
from typing import Dict, List, Optional, Any, Set, Tuple, Iterator, TypedDict
import requests
from tqdm import tqdm
import obonet
import networkx as nx
from datetime import datetime, timedelta
import hashlib
from ..db.database import get_db_manager
from psycopg2.extras import execute_batch
from io import TextIOWrapper
from rich.console import Console
from rich.table import Table
from ..utils.publication_utils import extract_pmid_from_text, extract_pmids_from_text
from ..etl.publications import Publication, PublicationsProcessor

logger = logging.getLogger(__name__)
console = Console()

# Constants
DEFAULT_CACHE_TTL = 86400  # 24 hours in seconds
DEFAULT_BATCH_SIZE = 1000

class GOTerm(TypedDict):
    """Type definition for GO term data."""
    term: str
    evidence: str
    aspect: str

class GOTermProcessor:
    """Process GO terms and enrich transcript data."""

    def __init__(self, config: Dict[str, Any]) -> None:
        """Initialize the GO term processor."""
        self.config = config
        self.cache_dir = Path(config['cache_dir'])
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.go_dir = self.cache_dir / 'go_terms'
        self.go_dir.mkdir(exist_ok=True)
        self.batch_size = config.get('batch_size', 1000)
        self.cache_ttl = config.get('cache_ttl', 86400)  # 24 hours default
        self.goa_url = config.get('goa_url', 'http://ftp.ebi.ac.uk/pub/databases/GO/goa/HUMAN/goa_human.gaf.gz')
        self.db_manager = get_db_manager(config)
        
        # Initialize graph storage
        self.go_graph: Optional[nx.MultiDiGraph] = None
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

    def _ensure_connection(self) -> None:
        """Ensure database connection is active."""
        if not self.db_manager.conn or self.db_manager.conn.closed:
            logger.info("Reconnecting to database...")
            self.db_manager.connect()
        if not self.db_manager.cursor or self.db_manager.cursor.closed:
            if self.db_manager.conn:
                self.db_manager.cursor = self.db_manager.conn.cursor()

    def _get_cache_key(self, url: str) -> str:
        """Generate a cache key from URL."""
        return hashlib.sha256(url.encode()).hexdigest()

    def download_obo(self) -> Path:
        """Download GO OBO file if not in cache or cache is invalid."""
        cache_key = self._get_cache_key(self.config['go_obo_url'])
        obo_path = self.go_dir / f"go_{cache_key}.obo"
        meta_path = self.go_dir / "meta.json"
        
        # Check cache validity
        if obo_path.exists() and meta_path.exists():
            try:
                with open(meta_path, 'r') as f:
                    meta = json.load(f)
                if cache_key in meta:
                    cache_time = datetime.fromisoformat(meta[cache_key]['timestamp'])
                    if datetime.now() - cache_time < timedelta(seconds=self.cache_ttl):
                        return obo_path
            except (json.JSONDecodeError, KeyError):
                pass

        # Download new file
        logger.info("Downloading GO OBO file...")
        response = requests.get(self.config['go_obo_url'], stream=True)
        total_size = int(response.headers.get('content-length', 0))

        with open(obo_path, 'wb') as f, tqdm(
            desc="Downloading",
            total=total_size,
            unit='iB',
            unit_scale=True
        ) as pbar:
            for data in response.iter_content(chunk_size=1024):
                size = f.write(data)
                pbar.update(size)

        # Update metadata
        meta = {}
        if meta_path.exists():
            with open(meta_path, 'r') as f:
                try:
                    meta = json.load(f)
                except json.JSONDecodeError:
                    pass

        meta[cache_key] = {
            'timestamp': datetime.now().isoformat(),
            'file_path': str(obo_path)
        }

        with open(meta_path, 'w') as f:
            json.dump(meta, f)

        return obo_path

    def download_goa(self) -> Path:
        """Download GOA file if not in cache or cache is invalid."""
        cache_key = self._get_cache_key(self.goa_url)
        goa_path = self.go_dir / f"goa_{cache_key}.gaf.gz"
        meta_path = self.go_dir / "meta.json"
        
        # Check cache validity
        if goa_path.exists() and meta_path.exists():
            try:
                with open(meta_path, 'r') as f:
                    meta = json.load(f)
                if cache_key in meta:
                    cache_time = datetime.fromisoformat(meta[cache_key]['timestamp'])
                    if datetime.now() - cache_time < timedelta(seconds=self.cache_ttl):
                        return goa_path
            except (json.JSONDecodeError, KeyError):
                pass

        # Download new file
        logger.info("Downloading GOA file...")
        response = requests.get(self.goa_url, stream=True)
        total_size = int(response.headers.get('content-length', 0))

        with open(goa_path, 'wb') as f, tqdm(
            desc="Downloading",
            total=total_size,
            unit='iB',
            unit_scale=True
        ) as pbar:
            for data in response.iter_content(chunk_size=1024):
                size = f.write(data)
                pbar.update(size)

        # Update metadata
        self._update_cache_meta(cache_key, goa_path)
        return goa_path

    def _update_cache_meta(self, cache_key: str, file_path: Path) -> None:
        """Update cache metadata."""
        meta_path = self.go_dir / "meta.json"
        meta = {}
        if meta_path.exists():
            with open(meta_path, 'r') as f:
                try:
                    meta = json.load(f)
                except json.JSONDecodeError:
                    pass

        meta[cache_key] = {
            'timestamp': datetime.now().isoformat(),
            'file_path': str(file_path)
        }

        with open(meta_path, 'w') as f:
            json.dump(meta, f)

    def load_go_graph(self, obo_path: Path) -> None:
        """Load GO terms into a networkx graph."""
        logger.info("Loading GO graph...")
        self.go_graph = obonet.read_obo(obo_path)
        logger.info(f"Loaded {len(self.go_graph)} GO terms")

    def get_ancestors(self, term_id: str, aspect: Optional[str] = None) -> Set[str]:
        """Get all ancestors of a GO term up to the root."""
        if not self.go_graph:
            raise ValueError("GO graph not loaded")
            
        ancestors = set()
        to_visit = {term_id}
        
        while to_visit:
            current = to_visit.pop()
            ancestors.add(current)
            
            # Get all parents through 'is_a' and 'part_of' relationships
            parents = set()
            for _, parent, data in self.go_graph.out_edges(current, data=True):
                if data.get('relation') in {'is_a', 'part_of'}:
                    parents.add(parent)
            
            # Add unvisited parents to the queue
            to_visit.update(parents - ancestors)
        
        # Filter by aspect if specified
        if aspect and aspect in self.aspect_roots:
            root = self.aspect_roots[aspect]
            if root in ancestors:
                return {a for a in ancestors if self.get_aspect(a) == aspect}
            return set()
            
        return ancestors - {term_id}  # Exclude the term itself

    def get_aspect(self, term_id: str) -> Optional[str]:
        """Get the aspect (namespace) of a GO term."""
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

    def enrich_transcripts(self) -> None:
        """Enrich transcript data with GO term hierarchies."""
        self._ensure_connection()
        if not self.go_graph:
            raise ValueError("GO graph not loaded")

        if not self.db_manager.cursor:
            raise RuntimeError("No database connection")

        try:
            cur = self.db_manager.cursor
            
            # Get transcripts with existing GO terms
            cur.execute("""
                SELECT transcript_id, go_terms 
                FROM cancer_transcript_base 
                WHERE go_terms IS NOT NULL 
                AND gene_type = 'protein_coding'
            """)
            
            total_processed = 0
            total_enriched = 0
            
            updates = []
            for transcript_id, go_terms in tqdm(cur.fetchall(), desc="Processing GO terms"):
                if not go_terms:
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
                
                updates.append((
                    json.dumps(enriched_terms),
                    transcript_id
                ))
                
                if len(updates) >= self.batch_size:
                    self._update_batch(cur, updates)
                    if self.db_manager.conn is not None:
                        self.db_manager.conn.commit()
                    updates = []
            
            # Process remaining updates
            if updates:
                self._update_batch(cur, updates)
                if self.db_manager.conn is not None:
                    self.db_manager.conn.commit()
            
            logger.info(
                f"GO term enrichment completed:\n"
                f"- Total transcripts processed: {total_processed}\n"
                f"- Transcripts enriched with ancestors: {total_enriched}"
            )
            
        except Exception as e:
            logger.error(f"GO term enrichment failed: {e}")
            if self.db_manager.conn is not None and not self.db_manager.conn.closed:
                self.db_manager.conn.rollback()
            raise

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
        """Extract publication references from GO terms.
        
        Args:
            go_terms: Dictionary of GO terms
            
        Returns:
            List[Publication]: List of extracted publication references
        """
        publications: List[Publication] = []
        
        for go_id, term_data in go_terms.items():
            # Extract PMID from evidence code
            evidence_code = term_data.get('evidence', '')
            evidence_text = f"{evidence_code} {go_id} {term_data.get('term', '')}"
            
            # First use the utility to try to extract PMIDs
            pmids = extract_pmids_from_text(evidence_text)
            
            # If that doesn't work, check if evidence code itself contains references
            if not pmids and ':' in evidence_code:
                # Some evidence codes might have format "ECO:0000269|PubMed:12345678"
                parts = evidence_code.split('|')
                for part in parts:
                    if 'PubMed:' in part or 'PMID:' in part:
                        pmid = part.split(':')[-1].strip()
                        if pmid.isdigit():
                            pmids.add(pmid)
            
            # Create publication references for each PMID found
            for pmid in pmids:
                publication = PublicationsProcessor.create_publication_reference(
                    pmid=pmid,
                    evidence_type=term_data.get('evidence', 'unknown'),
                    source_db='GO'
                )
                publications.append(publication)
            
            # If no PMIDs found but we have evidence code, still create a reference
            if not pmids and evidence_code:
                publication = PublicationsProcessor.create_publication_reference(
                    pmid=None,
                    evidence_type=evidence_code,
                    source_db='GO'
                )
                publications.append(publication)
        
        return publications

    def _update_batch(self, cur, updates: List[Tuple[str, str]]) -> None:
        """Update a batch of enriched GO terms."""
        try:
            # First ensure schema is at correct version
            if not self.db_manager.check_column_exists('cancer_transcript_base', 'source_references'):
                # Add required columns for v0.1.4
                cur.execute("""
                    ALTER TABLE cancer_transcript_base 
                    ADD COLUMN IF NOT EXISTS molecular_functions TEXT[] DEFAULT '{}',
                    ADD COLUMN IF NOT EXISTS cellular_location TEXT[] DEFAULT '{}',
                    ADD COLUMN IF NOT EXISTS alt_transcript_ids JSONB DEFAULT '{}'::jsonb,
                    ADD COLUMN IF NOT EXISTS alt_gene_ids JSONB DEFAULT '{}'::jsonb,
                    ADD COLUMN IF NOT EXISTS uniprot_ids TEXT[] DEFAULT '{}',
                    ADD COLUMN IF NOT EXISTS ncbi_ids TEXT[] DEFAULT '{}',
                    ADD COLUMN IF NOT EXISTS refseq_ids TEXT[] DEFAULT '{}',
                    ADD COLUMN IF NOT EXISTS source_references JSONB DEFAULT '{
                        "go_terms": [],
                        "uniprot": [],
                        "drugs": [],
                        "pathways": []
                    }'::jsonb;

                    -- Add indices for new columns
                    CREATE INDEX IF NOT EXISTS idx_molecular_functions 
                    ON cancer_transcript_base USING GIN(molecular_functions);
                    
                    CREATE INDEX IF NOT EXISTS idx_cellular_location 
                    ON cancer_transcript_base USING GIN(cellular_location);
                    
                    CREATE INDEX IF NOT EXISTS idx_source_references 
                    ON cancer_transcript_base USING GIN(source_references);
                    
                    CREATE INDEX IF NOT EXISTS idx_alt_ids 
                    ON cancer_transcript_base USING GIN(alt_transcript_ids, alt_gene_ids);
                """)
                if self.db_manager.conn:
                    self.db_manager.conn.commit()
                    logger.info("Schema updated to include required columns")
            
            # Process each update to extract publications
            for go_terms_json, gene_symbol in updates:
                try:
                    # Parse GO terms from JSON string
                    go_terms = json.loads(go_terms_json)
                    
                    # Extract publications from GO terms
                    publications = self.extract_publication_references(go_terms)
                    
                    # Add publications to source_references
                    if publications:
                        pub_json = json.dumps(publications)
                        
                        # Update source_references for this gene
                        cur.execute("""
                            UPDATE cancer_transcript_base
                            SET source_references = jsonb_set(
                                COALESCE(source_references, '{}'::jsonb),
                                '{go_terms}',
                                COALESCE(
                                    source_references->'go_terms',
                                    '[]'::jsonb
                                ) || %s::jsonb
                            )
                            WHERE gene_symbol = %s
                        """, (pub_json, gene_symbol))
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON for gene {gene_symbol}: {go_terms_json}")
                except Exception as e:
                    logger.warning(f"Error processing GO terms for {gene_symbol}: {e}")
            
            # Original batch update for go_terms, molecular_functions, etc.
            # ... rest of the existing _update_batch implementation ...
            execute_batch(
                cur,
                """
                WITH term_extraction AS (
                    SELECT 
                        gene_symbol,
                        go_terms,
                        (
                            SELECT array_agg(DISTINCT value->>'term')
                            FROM jsonb_each(go_terms::jsonb) AS t(key, value)
                            WHERE (value->>'aspect')::text = 'molecular_function'
                        ) AS molecular_functions,
                        (
                            SELECT array_agg(DISTINCT value->>'term')
                            FROM jsonb_each(go_terms::jsonb) AS t(key, value)
                            WHERE (value->>'aspect')::text = 'cellular_component'
                        ) AS cellular_location
                    FROM (
                        SELECT 
                            unnest(%s::text[]) AS gene_symbol,
                            unnest(%s::jsonb[]) AS go_terms
                    ) AS updates
                )
                UPDATE cancer_transcript_base AS ctb
                SET 
                    go_terms = te.go_terms,
                    molecular_functions = COALESCE(te.molecular_functions, '{}'),
                    cellular_location = COALESCE(te.cellular_location, '{}')
                FROM term_extraction te
                WHERE ctb.gene_symbol = te.gene_symbol
                AND ctb.gene_type = 'protein_coding'
                RETURNING ctb.gene_symbol, ctb.go_terms IS NOT NULL as updated;
                """,
                [(
                    [u[1] for u in batch],  # gene_symbols
                    [u[0] for u in batch]   # go_terms
                ) for batch in [updates]],
                page_size=self.batch_size
            )
            
            if self.db_manager.conn:
                self.db_manager.conn.commit()
                
        except Exception as e:
            logger.error(f"Batch update failed: {e}")
            raise

    def process_goa_file(self, goa_path: Path) -> Dict[str, Dict[str, GOTerm]]:
        """Process GOA file and extract gene-GO term mappings."""
        gene_go_terms: Dict[str, Dict[str, GOTerm]] = {}
        
        # First, get and show sample of valid gene symbols
        valid_genes = self._get_valid_genes()
        sample_entries: List[List[str]] = []
        
        with gzip.open(goa_path, 'rt') as f:
            for line in tqdm(f, 'Processing GOA entries'):
                if line.startswith('!'):
                    continue
                
                fields = line.strip().split('\t')
                if len(fields) < 15:
                    continue
                
                if not self.go_graph:
                    logger.error("GO graph not loaded")
                    continue
                    
                # Store sample entries before any filtering
                if len(sample_entries) < 5 and not line.startswith('!'):
                    sample_entries.append(fields)
                
                # Extract required fields with safe access
                gene_symbol = fields[2].upper() if len(fields) > 2 else ''
                go_id = fields[4] if len(fields) > 4 else ''
                evidence = fields[6] if len(fields) > 6 else ''
                aspect = fields[8] if len(fields) > 8 else ''
                
                if not (gene_symbol and go_id and evidence and aspect):
                    continue
                
                if gene_symbol not in valid_genes or go_id not in self.go_graph:
                    continue
                
                # Get GO term data with safe access
                node_data = self.go_graph.nodes.get(go_id, {})
                term_name = node_data.get('name', '')
                if not term_name:  # Skip if no term name found
                    continue
                
                # Initialize gene entry if needed
                if gene_symbol not in gene_go_terms:
                    gene_go_terms[gene_symbol] = {}
                
                # Store GO term with safe type construction
                gene_go_terms[gene_symbol][go_id] = {
                    'term': term_name,
                    'evidence': evidence,
                    'aspect': self._convert_aspect(aspect)
                }
        
        # Display statistics and samples
        self._display_goa_stats(
            processed=len(sample_entries),
            matched=len(gene_go_terms),
            gene_go_terms=gene_go_terms,
            sample_entries=sample_entries
        )
        
        return gene_go_terms

    def _display_goa_stats(
        self, 
        processed: int, 
        matched: int, 
        gene_go_terms: Dict[str, Dict[str, GOTerm]], 
        sample_entries: List[List[str]]
    ) -> None:
        """Display GOA processing statistics and samples."""
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
        
        logger.info(
            f"GOA Processing Stats:\n"
            f"- Total entries processed: {processed:,}\n"
            f"- Matched to database genes: {matched:,}\n"
            f"- Genes with GO terms: {len(gene_go_terms):,}"
        )

    def _get_valid_genes(self) -> Set[str]:
        """Get set of valid gene symbols from database."""
        valid_genes: Set[str] = set()
        if not self.db_manager.cursor:
            raise RuntimeError("No database connection")
            
        try:
            self.db_manager.cursor.execute("""
                SELECT DISTINCT gene_symbol 
                FROM cancer_transcript_base 
                WHERE gene_type = 'protein_coding'
                AND gene_symbol IS NOT NULL
            """)
            valid_genes = {row[0] for row in self.db_manager.cursor.fetchall() if row[0]}
            logger.info(f"Found {len(valid_genes)} valid gene symbols in database")
        except Exception as e:
            logger.error(f"Error getting valid genes: {e}")
            raise
        return valid_genes

    def _convert_aspect(self, aspect_code: str) -> str:
        """Convert single-letter aspect code to full name."""
        aspects = {
            'P': 'biological_process',
            'F': 'molecular_function',
            'C': 'cellular_component'
        }
        return aspects.get(aspect_code, '')

    def populate_initial_terms(self) -> None:
        """Populate initial GO terms from GOA data."""
        self._ensure_connection()
        # Download and process GOA file
        goa_path = self.download_goa()
        gene_go_terms = self.process_goa_file(goa_path)
        
        if not gene_go_terms:
            logger.warning("No GO terms found to populate")
            return

        if not self.db_manager.cursor:
            raise RuntimeError("No database connection")

        try:
            cur = self.db_manager.cursor
            
            # First, get a count of existing terms
            cur.execute("""
                SELECT COUNT(*) FROM cancer_transcript_base 
                WHERE go_terms IS NOT NULL
            """)
            result = cur.fetchone()
            initial_count = result[0] if result else 0
            logger.info(f"Initial GO terms count: {initial_count}")

            # Clear existing GO terms
            cur.execute("""
                UPDATE cancer_transcript_base 
                SET go_terms = NULL, molecular_functions = NULL
                WHERE gene_type = 'protein_coding'
            """)
            
            # Process in smaller batches with regular commits
            updates = []
            processed = 0
            batch_size = min(1000, self.batch_size)
            
            with tqdm(total=len(gene_go_terms), desc="Updating GO terms") as pbar:
                for gene_symbol, go_terms in gene_go_terms.items():
                    if go_terms:
                        updates.append((
                            json.dumps(go_terms),
                            gene_symbol
                        ))
                        
                        if len(updates) >= batch_size:
                            self._update_batch(cur, updates)
                            if self.db_manager.conn is not None:
                                self.db_manager.conn.commit()
                            processed += len(updates)
                            pbar.update(len(updates))
                            updates = []
            
            # Process remaining updates
            if updates:
                self._update_batch(cur, updates)
                if self.db_manager.conn is not None:
                    self.db_manager.conn.commit()
                processed += len(updates)
                pbar.update(len(updates))

            # Verify the updates
            cur.execute("""
                SELECT 
                    COUNT(*) as total_genes,
                    COUNT(CASE WHEN go_terms IS NOT NULL THEN 1 END) as with_terms,
                    COUNT(CASE WHEN molecular_functions IS NOT NULL THEN 1 END) as with_mf
                FROM cancer_transcript_base
                WHERE gene_type = 'protein_coding'
            """)
            stats = cur.fetchone()
            
            if stats:
                logger.info(
                    "Database Update Results:\n"
                    f"- Total genes processed: {processed:,}\n"
                    f"- Genes in database: {stats[0]:,}\n"
                    f"- Genes with GO terms: {stats[1]:,}\n"
                    f"- Genes with molecular functions: {stats[2]:,}"
                )
            else:
                logger.warning("No statistics available from the database query.")
                
            if self.db_manager.conn is not None:
                self.db_manager.conn.commit()
            logger.info("Initial GO terms population completed successfully")
            
        except Exception as e:
            logger.error(f"Initial GO terms population failed: {e}")
            if self.db_manager.conn is not None and not self.db_manager.conn.closed:
                self.db_manager.conn.rollback()
            raise

    def run(self) -> None:
        """Run the complete GO term enrichment pipeline."""
        try:
            self._ensure_connection()
            
            # First check schema version
            current_version = self.db_manager.get_current_version()
            if current_version != 'v0.1.4':
                logger.info(f"Current schema version {current_version} needs update to v0.1.4")
                if not self.db_manager.migrate_to_version('v0.1.4'):
                    raise RuntimeError("Failed to migrate database schema to v0.1.4")
                logger.info("Schema successfully updated to v0.1.4")
            
            # Then proceed with normal pipeline
            obo_path = self.download_obo()
            self.load_go_graph(obo_path)
            
            logger.info("Populating initial GO terms from GOA...")
            self.populate_initial_terms()
            
            # Ensure connection is still valid before enrichment
            self._ensure_connection()
            
            logger.info("Enriching GO terms with ancestors...")
            self.enrich_transcripts()
            
            logger.info("GO term processing completed successfully")
            
        except Exception as e:
            logger.error(f"GO term processing failed: {e}")
            raise
        finally:
            # Only close connection when completely done
            if hasattr(self, 'db_manager'):
                self.db_manager.close()

