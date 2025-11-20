"""PharmGKB Clinical Annotations integration module for Cancer Transcriptome Base.

This module downloads, processes, and integrates pharmacogenomic annotations from PharmGKB
into transcript records, providing evidence-based drug-gene interaction data with clinical significance.
"""

# Standard library imports
import csv
import json
import re
import zipfile
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
from .publications import Publication, PublicationsProcessor
from ..utils.publication_utils import extract_pmids_from_text, format_pmid_url
from ..utils.logging import get_progress_bar

# Constants
# Direct download URLs from PharmGKB API (no registration required)
PHARMGKB_CLINICAL_ANNOTATIONS_URL = "https://api.pharmgkb.org/v1/download/file/data/clinicalAnnotations.zip"
PHARMGKB_VARIANT_ANNOTATIONS_URL = "https://api.pharmgkb.org/v1/download/file/data/variantAnnotations.zip"
PHARMGKB_VIP_SUMMARIES_URL = "https://www.pharmgkb.org/downloads/vipSummaries.tsv"  # Not available via API
PHARMGKB_CACHE_TTL = 7 * 24 * 60 * 60  # 7 days in seconds

# Evidence level mapping for scoring
EVIDENCE_LEVEL_SCORES = {
    '1A': 5,    # High level of evidence
    '1B': 4,    # Moderate level of evidence
    '2A': 3,    # Moderate level of evidence
    '2B': 2,    # Weak level of evidence
    '3': 1,     # Insufficient evidence
    '4': 0      # Evidence of no effect
}

# Clinical significance scoring
CLINICAL_SIGNIFICANCE_SCORES = {
    'High': 3,
    'Moderate': 2,
    'Low': 1,
    'Unknown': 0
}

class PharmGKBAnnotationsProcessor(BaseProcessor):
    """Process pharmacogenomic annotations from PharmGKB."""

    def __init__(self, config: Dict[str, Any]) -> None:
        """Initialize PharmGKB annotations processor with configuration.
        
        Args:
            config: Configuration dictionary containing settings
        """
        super().__init__(config)
        
        # Create PharmGKB specific directory
        self.pharmgkb_dir = self.cache_dir / 'pharmgkb'
        self.pharmgkb_dir.mkdir(exist_ok=True)
        
        # Data source URLs
        self.clinical_annotations_url = config.get('pharmgkb_clinical_annotations_url', PHARMGKB_CLINICAL_ANNOTATIONS_URL)
        self.variant_annotations_url = config.get('pharmgkb_variant_annotations_url', PHARMGKB_VARIANT_ANNOTATIONS_URL)
        self.vip_summaries_url = config.get('pharmgkb_vip_summaries_url', PHARMGKB_VIP_SUMMARIES_URL)
        
        # Processing options
        self.skip_scores = config.get('skip_scores', False)
        self.force_download = config.get('force_download', False)
        self.include_variant_annotations = config.get('include_variant_annotations', True)
        self.include_vip_summaries = config.get('include_vip_summaries', True)
        self.include_pathways = config.get('include_pathways', True)
        
        # Schema version tracking
        self.required_schema_version = "v0.1.9"  # Minimum schema version required for PharmGKB variants

    def download_pharmgkb_data(self) -> Tuple[Path, Optional[Path], Optional[Path], Optional[Path]]:
        """Download and extract PharmGKB datasets from API (no registration required).

        Returns:
            Tuple of paths to extracted files (clinical_annotations, variant_annotations, vip_summaries, pathways_dir)

        Raises:
            DownloadError: If download or extraction fails
        """
        try:
            self.logger.info("Downloading PharmGKB datasets from API (no registration required)")

            # Create extraction directories
            clinical_dir = self.pharmgkb_dir / "clinical_annotations"
            variant_dir = self.pharmgkb_dir / "variant_annotations"
            clinical_dir.mkdir(parents=True, exist_ok=True)
            variant_dir.mkdir(parents=True, exist_ok=True)

            # Download and extract clinical annotations
            self.logger.info(f"Downloading clinical annotations from {self.clinical_annotations_url}")
            clinical_zip = self.download_file(
                self.clinical_annotations_url,
                self.pharmgkb_dir / "clinicalAnnotations.zip"
            )

            self.logger.info("Extracting clinical annotations ZIP file")
            with zipfile.ZipFile(clinical_zip, 'r') as zip_ref:
                zip_ref.extractall(clinical_dir)

            # Find the extracted clinical annotations TSV file
            clinical_file = clinical_dir / "clinical_annotations.tsv"
            if not clinical_file.exists():
                # Try to find any TSV file in the directory
                tsv_files = list(clinical_dir.glob("*.tsv"))
                if tsv_files:
                    clinical_file = tsv_files[0]
                    self.logger.info(f"Using clinical annotations file: {clinical_file.name}")
                else:
                    raise DownloadError("No TSV file found in clinical annotations ZIP")

            # Download and extract variant annotations if enabled
            variant_file = None
            if self.include_variant_annotations:
                self.logger.info(f"Downloading variant annotations from {self.variant_annotations_url}")
                variant_zip = self.download_file(
                    self.variant_annotations_url,
                    self.pharmgkb_dir / "variantAnnotations.zip"
                )

                self.logger.info("Extracting variant annotations ZIP file")
                with zipfile.ZipFile(variant_zip, 'r') as zip_ref:
                    zip_ref.extractall(variant_dir)

                # Find the main variant annotations TSV file
                # The ZIP contains: var_drug_ann.tsv, var_fa_ann.tsv, var_pheno_ann.tsv
                variant_drug_file = variant_dir / "var_drug_ann.tsv"
                if variant_drug_file.exists():
                    variant_file = variant_drug_file
                    self.logger.info(f"Found variant annotations file: {variant_file.name}")
                else:
                    # Try to find any variant TSV file
                    var_files = list(variant_dir.glob("var_*.tsv"))
                    if var_files:
                        variant_file = var_files[0]
                        self.logger.info(f"Using variant annotations file: {variant_file.name}")
                    else:
                        self.logger.warning("No variant TSV files found, skipping variant annotations")

            # VIP summaries not available via API (requires authentication)
            vip_file = None
            if self.include_vip_summaries:
                self.logger.info("VIP summaries require authentication (skipping automated download)")

            # Pathway data not available via API
            pathways_dir = None
            if self.include_pathways:
                pathways_dir_path = self.pharmgkb_dir / "pathways"
                if pathways_dir_path.exists() and pathways_dir_path.is_dir():
                    pathway_files = list(pathways_dir_path.glob("*.tsv"))
                    if pathway_files:
                        pathways_dir = pathways_dir_path
                        self.logger.info(f"Found {len(pathway_files)} PharmGKB pathway files")
                    else:
                        self.logger.info("Pathway data not available via API (requires manual download)")
                else:
                    self.logger.info("Pathway data not available via API (requires manual download)")

            self.logger.info("PharmGKB data download and extraction completed successfully")
            return clinical_file, variant_file, vip_file, pathways_dir

        except Exception as e:
            raise DownloadError(f"Failed to download PharmGKB data: {e}")

    def parse_gene_symbols(self, gene_string: str) -> List[str]:
        """Parse gene symbols from PharmGKB gene field.
        
        Args:
            gene_string: String containing gene symbols (may be comma-separated)
            
        Returns:
            List of cleaned gene symbols
        """
        if not gene_string or pd.isna(gene_string):
            return []
        
        # Handle various separators and clean symbols
        symbols = re.split(r'[,;|]', str(gene_string))
        cleaned_symbols = []
        
        for symbol in symbols:
            # Clean up symbol (remove spaces, brackets, etc.)
            cleaned = re.sub(r'[^\w-]', '', symbol.strip().upper())
            if cleaned and len(cleaned) > 1:  # Filter out single characters
                cleaned_symbols.append(cleaned)
        
        return cleaned_symbols


    def process_clinical_annotations(self, clinical_file: Path) -> Dict[str, List[Dict[str, Any]]]:
        """Process PharmGKB clinical annotations file.
        
        Args:
            clinical_file: Path to the clinical annotations TSV file
            
        Returns:
            Dictionary mapping gene symbols to clinical annotation records
            
        Raises:
            ProcessingError: If processing fails
        """
        try:
            self.logger.info("Processing PharmGKB clinical annotations")
            
            # Read the TSV file
            df = pd.read_csv(clinical_file, sep='\t', low_memory=False)
            
            # Check if dataframe is empty or has no relevant columns
            if len(df) == 0 or 'Gene' not in df.columns:
                raise ProcessingError("PharmGKB file appears empty or has unexpected format")
            
            self.logger.info(f"Loaded {len(df):,} clinical annotation records from PharmGKB")
            
            # Group annotations by gene symbols
            gene_annotation_mapping = defaultdict(list)
            
            processing_stats = {
                'total_annotations': len(df),
                'annotations_with_genes': 0,
                'unique_genes': set(),
                'evidence_levels': Counter(),
                'phenotype_categories': Counter(),
                'scores': []
            }
            
            progress_bar = get_progress_bar(
                total=len(df),
                desc="Processing clinical annotations",
                module_name="pharmgkb_annotations"
            )
            
            try:
                for _, row in df.iterrows():
                    # Extract key fields based on actual column names
                    annotation_id = str(row.get('Clinical Annotation ID', '')) if pd.notna(row.get('Clinical Annotation ID')) else ''
                    gene_field = row.get('Gene', '') if pd.notna(row.get('Gene')) else ''
                    variant = str(row.get('Variant/Haplotypes', '')) if pd.notna(row.get('Variant/Haplotypes')) else ''
                    drug = str(row.get('Drug(s)', '')) if pd.notna(row.get('Drug(s)')) else ''
                    phenotype_category = str(row.get('Phenotype Category', '')) if pd.notna(row.get('Phenotype Category')) else ''
                    phenotypes = str(row.get('Phenotype(s)', '')) if pd.notna(row.get('Phenotype(s)')) else ''
                    evidence_level = str(row.get('Level of Evidence', '')) if pd.notna(row.get('Level of Evidence')) else ''
                    level_modifiers = str(row.get('Level Modifiers', '')) if pd.notna(row.get('Level Modifiers')) else ''
                    score = row.get('Score', 0) if pd.notna(row.get('Score')) else 0
                    pmid_count = row.get('PMID Count', 0) if pd.notna(row.get('PMID Count')) else 0
                    evidence_count = row.get('Evidence Count', 0) if pd.notna(row.get('Evidence Count')) else 0
                    url = str(row.get('URL', '')) if pd.notna(row.get('URL')) else ''
                    specialty_population = str(row.get('Specialty Population', '')) if pd.notna(row.get('Specialty Population')) else ''
                    
                    # Parse gene symbols
                    gene_symbols = self.parse_gene_symbols(gene_field)
                    
                    if gene_symbols:
                        processing_stats['annotations_with_genes'] += 1
                        processing_stats['unique_genes'].update(gene_symbols)
                    
                    processing_stats['evidence_levels'][evidence_level] += 1
                    processing_stats['phenotype_categories'][phenotype_category] += 1
                    if isinstance(score, (int, float)):
                        processing_stats['scores'].append(score)
                    
                    # Create annotation record
                    annotation_record = {
                        'annotation_id': annotation_id,
                        'variant': variant,
                        'drug': drug,
                        'phenotype_category': phenotype_category,
                        'phenotypes': phenotypes,
                        'evidence_level': evidence_level,
                        'level_modifiers': level_modifiers,
                        'score': float(score) if isinstance(score, (int, float)) else 0.0,
                        'evidence_score': EVIDENCE_LEVEL_SCORES.get(evidence_level, 0),
                        'pmid_count': int(pmid_count) if isinstance(pmid_count, (int, float)) else 0,
                        'evidence_count': int(evidence_count) if isinstance(evidence_count, (int, float)) else 0,
                        'url': url,
                        'specialty_population': specialty_population,
                        'source': 'PharmGKB_Clinical_Annotations'
                    }
                    
                    # Add to gene mapping for each gene
                    for gene_symbol in gene_symbols:
                        gene_annotation_mapping[gene_symbol].append(annotation_record)
                    
                    progress_bar.update(1)
                    
            finally:
                progress_bar.close()
            
            # Log processing statistics
            self.logger.info(f"PharmGKB clinical annotations processing statistics:")
            self.logger.info(f"  - Total annotations: {processing_stats['total_annotations']:,}")
            self.logger.info(f"  - Annotations with genes: {processing_stats['annotations_with_genes']:,}")
            self.logger.info(f"  - Unique genes: {len(processing_stats['unique_genes']):,}")
            
            if processing_stats['scores']:
                avg_score = sum(processing_stats['scores']) / len(processing_stats['scores'])
                self.logger.info(f"  - Average score: {avg_score:.2f}")
            
            self.logger.info("Evidence level distribution:")
            for level, count in processing_stats['evidence_levels'].most_common():
                self.logger.info(f"  - {level}: {count:,}")
            
            self.logger.info("Phenotype category distribution:")
            for category, count in processing_stats['phenotype_categories'].most_common():
                self.logger.info(f"  - {category}: {count:,}")
            
            return dict(gene_annotation_mapping)
            
        except Exception as e:
            raise ProcessingError(f"Failed to process PharmGKB clinical annotations: {e}")

    def process_vip_summaries(self, vip_file: Path) -> Dict[str, Dict[str, Any]]:
        """Process PharmGKB VIP (Very Important Pharmacogene) summaries.
        
        Args:
            vip_file: Path to the VIP summaries TSV file
            
        Returns:
            Dictionary mapping gene symbols to VIP summary data
            
        Raises:
            ProcessingError: If processing fails
        """
        try:
            self.logger.info("Processing PharmGKB VIP gene summaries")
            
            # Check if file is actually HTML (authentication/access issue)
            with open(vip_file, 'r') as f:
                first_line = f.readline().strip()
                if first_line.startswith('<!doctype html') or first_line.startswith('<html'):
                    self.logger.warning("PharmGKB VIP file returned HTML - creating mock VIP data")
                    return self._create_mock_vip_data()
            
            # Read the TSV file
            df = pd.read_csv(vip_file, sep='\t', low_memory=False)
            
            # Check if dataframe is empty or has no relevant columns
            if len(df) == 0 or 'Gene Symbol' not in df.columns:
                self.logger.warning("PharmGKB VIP file appears empty or has unexpected format")
                self.logger.warning("Creating mock VIP data for demonstration purposes")
                return self._create_mock_vip_data()
            
            self.logger.info(f"Loaded {len(df):,} VIP gene summary records from PharmGKB")
            
            vip_mapping = {}
            
            for _, row in df.iterrows():
                gene_symbol = str(row.get('Gene Symbol', '')).strip().upper() if pd.notna(row.get('Gene Symbol')) else ''
                gene_name = str(row.get('Gene Name', '')) if pd.notna(row.get('Gene Name')) else ''
                clinical_annotation = str(row.get('Clinical Annotation', '')) if pd.notna(row.get('Clinical Annotation')) else ''
                variant_annotation = str(row.get('Variant Annotation', '')) if pd.notna(row.get('Variant Annotation')) else ''
                vip_summary = str(row.get('VIP Summary', '')) if pd.notna(row.get('VIP Summary')) else ''
                
                if gene_symbol:
                    vip_mapping[gene_symbol] = {
                        'gene_name': gene_name,
                        'clinical_annotation_count': len(clinical_annotation.split(',')) if clinical_annotation else 0,
                        'variant_annotation_count': len(variant_annotation.split(',')) if variant_annotation else 0,
                        'vip_summary': vip_summary,
                        'is_vip': True,
                        'source': 'PharmGKB_VIP_Summaries'
                    }
            
            self.logger.info(f"Processed {len(vip_mapping):,} VIP genes")
            return vip_mapping
            
        except Exception as e:
            raise ProcessingError(f"Failed to process PharmGKB VIP summaries: {e}")

    def process_pharmgkb_pathways(self, pathways_dir: Path) -> Dict[str, Dict[str, Any]]:
        """Process PharmGKB pathway files to extract drug-specific metabolic networks.
        
        Args:
            pathways_dir: Directory containing PharmGKB pathway TSV files
            
        Returns:
            Dictionary mapping gene symbols to pathway data
            
        Raises:
            ProcessingError: If processing fails
        """
        try:
            self.logger.info("Processing PharmGKB pathway data")
            
            # Get all TSV files in pathways directory
            pathway_files = list(pathways_dir.glob("*.tsv"))
            if not pathway_files:
                raise ProcessingError("No pathway TSV files found in pathways directory")
            
            self.logger.info(f"Found {len(pathway_files)} pathway files to process")
            
            # Gene-to-pathway mapping
            gene_pathway_mapping = defaultdict(lambda: defaultdict(list))
            
            # Processing statistics
            processing_stats = {
                'total_pathway_files': len(pathway_files),
                'total_reactions': 0,
                'unique_genes': set(),
                'pathway_types': Counter(),
                'drug_focus_types': Counter(),
                'reaction_types': Counter(),
                'cell_types': Counter(),
                'cancer_relevant_pathways': 0
            }
            
            # Known cancer drugs for filtering
            cancer_drugs = {
                'tamoxifen', 'cisplatin', 'carboplatin', 'oxaliplatin', 'paclitaxel', 'docetaxel',
                '5-fluorouracil', 'capecitabine', 'irinotecan', 'doxorubicin', 'cyclophosphamide',
                'methotrexate', 'gemcitabine', 'bevacizumab', 'trastuzumab', 'rituximab',
                'imatinib', 'gefitinib', 'erlotinib', 'sorafenib', 'sunitinib', 'vemurafenib',
                'dabrafenib', 'trametinib', 'pembrolizumab', 'nivolumab', 'ipilimumab'
            }
            
            progress_bar = get_progress_bar(
                total=len(pathway_files),
                desc="Processing pathway files",
                module_name="pharmgkb_pathways"
            )
            
            try:
                for pathway_file in pathway_files:
                    # Extract pathway information from filename
                    filename = pathway_file.stem
                    pathway_parts = filename.split('-', 1)
                    
                    if len(pathway_parts) != 2:
                        self.logger.warning(f"Unexpected pathway filename format: {filename}")
                        continue
                    
                    pathway_id = pathway_parts[0]
                    pathway_name = pathway_parts[1].replace('_', ' ')
                    
                    # Determine pathway type and drug focus
                    pathway_type = "Unknown"
                    drug_focus = "Unknown"
                    
                    if "Pharmacokinetics" in pathway_name:
                        pathway_type = "Pharmacokinetics"
                    elif "Pharmacodynamics" in pathway_name:
                        pathway_type = "Pharmacodynamics"
                    elif "Adverse_Drug_Reaction" in pathway_name:
                        pathway_type = "Adverse_Drug_Reaction"
                    
                    # Extract drug name from pathway name
                    pathway_lower = pathway_name.lower()
                    for drug in cancer_drugs:
                        if drug.lower() in pathway_lower:
                            drug_focus = drug
                            processing_stats['cancer_relevant_pathways'] += 1
                            break
                    
                    processing_stats['pathway_types'][pathway_type] += 1
                    processing_stats['drug_focus_types'][drug_focus] += 1
                    
                    # Process pathway file
                    try:
                        df = pd.read_csv(pathway_file, sep='\t', low_memory=False)
                        
                        if len(df) == 0:
                            self.logger.warning(f"Empty pathway file: {pathway_file}")
                            continue
                        
                        # Process each reaction in the pathway
                        pathway_reactions = []
                        gene_roles = defaultdict(lambda: {
                            'role': 'participant',
                            'reactions': [],
                            'importance': 'moderate'
                        })
                        
                        for _, row in df.iterrows():
                            processing_stats['total_reactions'] += 1
                            
                            # Extract reaction data
                            reaction_data = {
                                'from': str(row.get('From', '')) if pd.notna(row.get('From')) else '',
                                'to': str(row.get('To', '')) if pd.notna(row.get('To')) else '',
                                'reaction_type': str(row.get('Reaction Type', '')) if pd.notna(row.get('Reaction Type')) else '',
                                'controller_genes': [],
                                'control_type': str(row.get('Control Type', '')) if pd.notna(row.get('Control Type')) else '',
                                'cell_type': str(row.get('Cell Type', '')) if pd.notna(row.get('Cell Type')) else '',
                                'pmids': [],
                                'drugs': [],
                                'diseases': [],
                                'summary': str(row.get('Summary', '')) if pd.notna(row.get('Summary')) else ''
                            }
                            
                            # Parse controller genes
                            controller_field = row.get('Controller', '') if pd.notna(row.get('Controller')) else ''
                            if controller_field:
                                controller_genes = [gene.strip() for gene in str(controller_field).split(',') if gene.strip()]
                                reaction_data['controller_genes'] = controller_genes
                                processing_stats['unique_genes'].update(controller_genes)
                            
                            # Parse additional genes field
                            genes_field = row.get('Genes', '') if pd.notna(row.get('Genes')) else ''
                            if genes_field:
                                additional_genes = [gene.strip() for gene in str(genes_field).split(',') if gene.strip()]
                                reaction_data['controller_genes'].extend(additional_genes)
                                processing_stats['unique_genes'].update(additional_genes)
                            
                            # Remove duplicates from controller genes
                            reaction_data['controller_genes'] = list(set(reaction_data['controller_genes']))
                            
                            # Parse PMIDs
                            pmids_field = row.get('PMIDs', '') if pd.notna(row.get('PMIDs')) else ''
                            if pmids_field:
                                pmids = [pmid.strip() for pmid in str(pmids_field).split(',') if pmid.strip()]
                                reaction_data['pmids'] = pmids
                            
                            # Parse drugs
                            drugs_field = row.get('Drugs', '') if pd.notna(row.get('Drugs')) else ''
                            if drugs_field:
                                drugs = [drug.strip() for drug in str(drugs_field).split(',') if drug.strip()]
                                reaction_data['drugs'] = drugs
                            
                            # Parse diseases
                            diseases_field = row.get('Diseases', '') if pd.notna(row.get('Diseases')) else ''
                            if diseases_field:
                                diseases = [disease.strip() for disease in str(diseases_field).split(',') if disease.strip()]
                                reaction_data['diseases'] = diseases
                            
                            # Update statistics
                            if reaction_data['reaction_type']:
                                processing_stats['reaction_types'][reaction_data['reaction_type']] += 1
                            if reaction_data['cell_type']:
                                processing_stats['cell_types'][reaction_data['cell_type']] += 1
                            
                            pathway_reactions.append(reaction_data)
                            
                            # Track gene roles in this pathway
                            for gene in reaction_data['controller_genes']:
                                gene_roles[gene]['reactions'].append(f"{reaction_data['from']} -> {reaction_data['to']}")
                                
                                # Determine gene importance based on role
                                if reaction_data['control_type'].lower() == 'catalysis':
                                    gene_roles[gene]['role'] = 'enzyme'
                                    gene_roles[gene]['importance'] = 'critical'
                                elif reaction_data['reaction_type'].lower() == 'transport':
                                    gene_roles[gene]['role'] = 'transporter'
                                elif reaction_data['reaction_type'].lower() == 'inhibition':
                                    gene_roles[gene]['role'] = 'inhibitor'
                                    gene_roles[gene]['importance'] = 'high'
                        
                        # Create pathway data structure
                        pathway_data = {
                            'pathway_name': pathway_name,
                            'pathway_id': pathway_id,
                            'drug_focus': drug_focus,
                            'pathway_type': pathway_type,
                            'reactions': pathway_reactions,
                            'gene_roles': dict(gene_roles),
                            'clinical_relevance': {
                                'cancer_relevance': drug_focus in cancer_drugs,
                                'drug_interactions': len(pathway_reactions) > 5,  # Complex pathways more likely to have interactions
                                'genetic_variants': any(gene in ['CYP2D6', 'CYP3A4', 'CYP2C19', 'TPMT', 'UGT1A1'] 
                                                      for gene in gene_roles.keys()),
                                'clinical_implications': f"Drug metabolism pathway for {drug_focus}"
                            },
                            'statistics': {
                                'total_reactions': len(pathway_reactions),
                                'unique_genes': len(gene_roles),
                                'pmid_count': sum(len(r['pmids']) for r in pathway_reactions),
                                'drug_mentions': sum(len(r['drugs']) for r in pathway_reactions)
                            }
                        }
                        
                        # Add pathway data to each gene
                        for gene_symbol in gene_roles.keys():
                            gene_pathway_mapping[gene_symbol][pathway_id] = pathway_data
                        
                    except Exception as e:
                        self.logger.error(f"Failed to process pathway file {pathway_file}: {e}")
                        continue
                    
                    progress_bar.update(1)
                    
            finally:
                progress_bar.close()
            
            # Log processing statistics
            self.logger.info(f"PharmGKB pathway processing statistics:")
            self.logger.info(f"  - Total pathway files: {processing_stats['total_pathway_files']:,}")
            self.logger.info(f"  - Total reactions: {processing_stats['total_reactions']:,}")
            self.logger.info(f"  - Unique genes: {len(processing_stats['unique_genes']):,}")
            self.logger.info(f"  - Cancer-relevant pathways: {processing_stats['cancer_relevant_pathways']:,}")
            
            self.logger.info("Pathway type distribution:")
            for ptype, count in processing_stats['pathway_types'].most_common():
                self.logger.info(f"  - {ptype}: {count:,}")
            
            self.logger.info("Top drug focus areas:")
            for drug, count in processing_stats['drug_focus_types'].most_common(10):
                self.logger.info(f"  - {drug}: {count:,}")
            
            self.logger.info("Reaction type distribution:")
            for rtype, count in processing_stats['reaction_types'].most_common():
                self.logger.info(f"  - {rtype}: {count:,}")
            
            return dict(gene_pathway_mapping)
            
        except Exception as e:
            raise ProcessingError(f"Failed to process PharmGKB pathways: {e}")

    def process_variant_annotations(self, variant_file: Path) -> Dict[str, List[Dict[str, Any]]]:
        """Process PharmGKB variant annotations for pharmacogenomics.
        
        Args:
            variant_file: Path to PharmGKB variant annotations TSV file
            
        Returns:
            Dictionary mapping gene symbols to variant annotation records
            
        Raises:
            ProcessingError: If processing fails
        """
        try:
            self.logger.info("Processing PharmGKB variant annotations")
            
            # Load variant annotations data
            df = pd.read_csv(variant_file, sep='\t', low_memory=False)
            self.logger.info(f"Loaded {len(df):,} variant annotation records from PharmGKB")
            
            gene_variant_mapping = defaultdict(list)
            processing_stats = {
                'total_records': len(df),
                'processed_records': 0,
                'genes_with_variants': set(),
                'phenotype_categories': Counter(),
                'significance_levels': Counter(),
                'variant_types': Counter(),
                'drug_associations': Counter()
            }
            
            progress_bar = get_progress_bar(
                total=len(df),
                desc="Processing variant annotations",
                module_name="pharmgkb_variants"
            )
            
            try:
                for _, row in df.iterrows():
                    # Extract key fields
                    gene_symbol = str(row.get('Gene', '')).strip()
                    if not gene_symbol:
                        progress_bar.update(1)
                        continue
                    
                    variant_id = str(row.get('Variant Annotation ID', '')) if pd.notna(row.get('Variant Annotation ID')) else ''
                    variant_identifier = str(row.get('Variant/Haplotypes', '')) if pd.notna(row.get('Variant/Haplotypes')) else ''
                    drugs_str = str(row.get('Drug(s)', '')) if pd.notna(row.get('Drug(s)')) else ''
                    phenotype_category = str(row.get('Phenotype Category', '')) if pd.notna(row.get('Phenotype Category')) else ''
                    significance = str(row.get('Significance', '')) if pd.notna(row.get('Significance')) else ''
                    pmid = str(row.get('PMID', '')) if pd.notna(row.get('PMID')) else ''
                    
                    # Parse drug list
                    drugs = []
                    if drugs_str:
                        drugs = [drug.strip() for drug in drugs_str.split(',') if drug.strip()]
                    
                    # Calculate pharmacogenomic score
                    pharmacogenomic_score = self._calculate_variant_score(row)
                    
                    # Determine variant type
                    variant_type = 'unknown'
                    if variant_identifier:
                        if variant_identifier.startswith('rs'):
                            variant_type = 'SNP'
                        elif '*' in variant_identifier:
                            variant_type = 'star_allele'
                        elif 'del' in variant_identifier.lower() or 'ins' in variant_identifier.lower():
                            variant_type = 'indel'
                        elif 'dup' in variant_identifier.lower():
                            variant_type = 'duplication'
                    
                    # Build variant record
                    variant_record = {
                        'variant_annotation_id': variant_id,
                        'variant_identifier': variant_identifier,
                        'variant_type': variant_type,
                        'drugs': drugs,
                        'phenotype_category': phenotype_category,
                        'significance': significance,
                        'direction_of_effect': str(row.get('Direction of effect', '')) if pd.notna(row.get('Direction of effect')) else '',
                        'pmid': pmid,
                        'clinical_sentence': str(row.get('Sentence', '')) if pd.notna(row.get('Sentence')) else '',
                        'specialty_population': str(row.get('Specialty Population', '')) if pd.notna(row.get('Specialty Population')) else '',
                        'pharmacogenomic_score': pharmacogenomic_score,
                        'evidence_level': self._assess_variant_evidence_level(row),
                        'metabolizer_prediction': self._extract_metabolizer_info(variant_identifier, phenotype_category),
                        'clinical_actionability': self._assess_clinical_actionability(significance, phenotype_category),
                        'source': 'PharmGKB_Variant_Annotations'
                    }
                    
                    gene_variant_mapping[gene_symbol].append(variant_record)
                    
                    # Update statistics
                    processing_stats['processed_records'] += 1
                    processing_stats['genes_with_variants'].add(gene_symbol)
                    processing_stats['phenotype_categories'][phenotype_category] += 1
                    processing_stats['significance_levels'][significance] += 1
                    processing_stats['variant_types'][variant_type] += 1
                    
                    for drug in drugs:
                        processing_stats['drug_associations'][drug] += 1
                    
                    progress_bar.update(1)
                    
            finally:
                progress_bar.close()
            
            # Log processing statistics
            self.logger.info(f"PharmGKB variant annotation processing statistics:")
            self.logger.info(f"  - Total records: {processing_stats['total_records']:,}")
            self.logger.info(f"  - Processed records: {processing_stats['processed_records']:,}")
            self.logger.info(f"  - Genes with variants: {len(processing_stats['genes_with_variants']):,}")
            
            self.logger.info("Phenotype category distribution:")
            for category, count in processing_stats['phenotype_categories'].most_common():
                self.logger.info(f"  - {category}: {count:,}")
            
            self.logger.info("Significance level distribution:")
            for level, count in processing_stats['significance_levels'].most_common():
                self.logger.info(f"  - {level}: {count:,}")
            
            self.logger.info("Variant type distribution:")
            for vtype, count in processing_stats['variant_types'].most_common():
                self.logger.info(f"  - {vtype}: {count:,}")
            
            self.logger.info("Top drug associations:")
            for drug, count in processing_stats['drug_associations'].most_common(10):
                self.logger.info(f"  - {drug}: {count:,}")
            
            return dict(gene_variant_mapping)
            
        except Exception as e:
            raise ProcessingError(f"Failed to process PharmGKB variant annotations: {e}")

    def _calculate_variant_score(self, row: pd.Series) -> float:
        """Calculate pharmacogenomic importance score for a variant."""
        base_score = 0.0
        
        # Clinical significance scoring
        significance = str(row.get('Significance', '')).lower()
        if 'yes' in significance:
            base_score += 30.0
        elif 'no' in significance:
            base_score += 10.0
        elif significance:  # Any other non-empty significance
            base_score += 5.0
        
        # Phenotype category weighting
        category = str(row.get('Phenotype Category', '')).lower()
        if 'efficacy' in category:
            base_score += 25.0
        elif 'toxicity' in category:
            base_score += 20.0
        elif 'metabolism' in category or 'pk' in category:
            base_score += 15.0
        elif 'dosage' in category:
            base_score += 10.0
        
        # Direction of effect bonus
        direction = str(row.get('Direction of effect', '')).lower()
        if any(term in direction for term in ['increased', 'decreased', 'affected']):
            base_score += 15.0
        
        # PMID evidence bonus
        pmid = str(row.get('PMID', ''))
        if pmid and pmid.strip() and pmid != 'nan':
            base_score += 10.0
        
        # Special population bonus
        specialty_pop = str(row.get('Specialty Population', ''))
        if specialty_pop and specialty_pop.strip() and specialty_pop != 'nan':
            base_score += 5.0
        
        return min(base_score, 100.0)

    def _assess_variant_evidence_level(self, row: pd.Series) -> str:
        """Assess evidence level for variant annotation."""
        significance = str(row.get('Significance', '')).lower()
        pmid = str(row.get('PMID', ''))
        category = str(row.get('Phenotype Category', '')).lower()
        
        # High evidence: clinical significance with PMID and efficacy/toxicity
        if ('yes' in significance and pmid and pmid.strip() and 
            any(cat in category for cat in ['efficacy', 'toxicity'])):
            return 'high'
        # Moderate evidence: clinical significance or strong category with PMID
        elif (('yes' in significance or any(cat in category for cat in ['efficacy', 'toxicity'])) and 
              pmid and pmid.strip()):
            return 'moderate'
        # Low evidence: some significance or PMID
        elif significance or (pmid and pmid.strip()):
            return 'low'
        else:
            return 'insufficient'

    def _extract_metabolizer_info(self, variant_identifier: str, phenotype_category: str) -> Dict[str, Any]:
        """Extract metabolizer phenotype information from variant data."""
        metabolizer_info = {
            'phenotype': 'unknown',
            'confidence': 0.0,
            'basis': 'variant_annotation'
        }
        
        # Check for known CYP450 star alleles and their metabolizer implications
        if '*' in variant_identifier:
            gene_allele = variant_identifier.lower()
            
            # CYP2D6 metabolizer predictions
            if 'cyp2d6' in phenotype_category.lower():
                if any(allele in gene_allele for allele in ['*4', '*5', '*6', '*10']):
                    metabolizer_info.update({
                        'phenotype': 'poor_metabolizer',
                        'confidence': 0.85
                    })
                elif any(allele in gene_allele for allele in ['*9', '*41']):
                    metabolizer_info.update({
                        'phenotype': 'intermediate_metabolizer',
                        'confidence': 0.80
                    })
                elif any(allele in gene_allele for allele in ['*1', '*2']):
                    metabolizer_info.update({
                        'phenotype': 'extensive_metabolizer',
                        'confidence': 0.75
                    })
            
            # CYP2C19 metabolizer predictions
            elif 'cyp2c19' in phenotype_category.lower():
                if any(allele in gene_allele for allele in ['*2', '*3']):
                    metabolizer_info.update({
                        'phenotype': 'poor_metabolizer',
                        'confidence': 0.85
                    })
                elif '*17' in gene_allele:
                    metabolizer_info.update({
                        'phenotype': 'ultrarapid_metabolizer',
                        'confidence': 0.80
                    })
        
        return metabolizer_info

    def _assess_clinical_actionability(self, significance: str, phenotype_category: str) -> str:
        """Assess clinical actionability of variant annotation."""
        significance = significance.lower()
        category = phenotype_category.lower()
        
        # High actionability: clinically significant with dosage/efficacy/toxicity implications
        if ('yes' in significance and 
            any(cat in category for cat in ['dosage', 'efficacy', 'toxicity'])):
            return 'high'
        # Moderate actionability: clinical significance with metabolism implications
        elif 'yes' in significance and 'metabolism' in category:
            return 'moderate'
        # Low actionability: some significance but unclear clinical impact
        elif significance and significance != 'no':
            return 'low'
        else:
            return 'research_only'

    def extract_publication_references(self, gene_annotation_mapping: Dict[str, List[Dict[str, Any]]], 
                                     variant_mapping: Optional[Dict[str, List[Dict[str, Any]]]] = None) -> List[Publication]:
        """Extract publication references from PharmGKB data.
        
        Args:
            gene_annotation_mapping: Dictionary mapping gene symbols to clinical annotations
            variant_mapping: Optional dictionary mapping gene symbols to variant annotations
            
        Returns:
            List of Publication objects extracted from PharmGKB data
        """
        publications = []
        processed_pmids = set()
        
        self.logger.info("Extracting publication references from PharmGKB data")
        
        # Extract PMIDs from clinical annotations
        for gene_symbol, annotations in gene_annotation_mapping.items():
            for annotation in annotations:
                # Look for PMIDs in various fields
                pmid_sources = [
                    annotation.get('url', ''),
                    str(annotation.get('pmid_count', '')),
                    str(annotation.get('evidence_count', ''))
                ]
                
                for source_text in pmid_sources:
                    if source_text:
                        pmids = extract_pmids_from_text(str(source_text))
                        for pmid in pmids:
                            if pmid and pmid not in processed_pmids:
                                publications.append({
                                    'pmid': pmid,
                                    'evidence_type': 'clinical_annotation',
                                    'source_db': 'PharmGKB',
                                    'gene_symbol': gene_symbol,
                                    'annotation_id': annotation.get('annotation_id', ''),
                                    'phenotype_category': annotation.get('phenotype_category', ''),
                                    'evidence_level': annotation.get('evidence_level', ''),
                                    'drug': annotation.get('drug', ''),
                                    'url': format_pmid_url(pmid)
                                })
                                processed_pmids.add(pmid)
        
        # Extract PMIDs from variant annotations
        if variant_mapping:
            for gene_symbol, variants in variant_mapping.items():
                for variant in variants:
                    pmid = variant.get('pmid', '')
                    if pmid and pmid.strip() and pmid not in processed_pmids:
                        # Clean PMID if it has prefix
                        clean_pmid = pmid.replace('PMID:', '').strip()
                        if clean_pmid.isdigit():
                            publications.append({
                                'pmid': clean_pmid,
                                'evidence_type': 'variant_annotation',
                                'source_db': 'PharmGKB',
                                'gene_symbol': gene_symbol,
                                'variant_id': variant.get('variant_identifier', ''),
                                'variant_type': variant.get('variant_type', ''),
                                'phenotype_category': variant.get('phenotype_category', ''),
                                'significance': variant.get('significance', ''),
                                'drugs': variant.get('drugs', []),
                                'clinical_actionability': variant.get('clinical_actionability', ''),
                                'url': format_pmid_url(clean_pmid)
                            })
                            processed_pmids.add(clean_pmid)
        
        self.logger.info(f"Extracted {len(publications)} publication references from PharmGKB data")
        return publications

    def update_transcript_pharmgkb_data(self, 
                                      gene_annotation_mapping: Dict[str, List[Dict[str, Any]]],
                                      vip_mapping: Optional[Dict[str, Dict[str, Any]]] = None,
                                      pathway_mapping: Optional[Dict[str, Dict[str, Any]]] = None,
                                      variant_mapping: Optional[Dict[str, List[Dict[str, Any]]]] = None) -> None:
        """Update transcript records with PharmGKB pharmacogenomic data.
        
        Args:
            gene_annotation_mapping: Dictionary mapping gene symbols to clinical annotations
            vip_mapping: Optional dictionary mapping gene symbols to VIP data
            pathway_mapping: Optional dictionary mapping gene symbols to pathway data
            variant_mapping: Optional dictionary mapping gene symbols to variant annotations
            
        Raises:
            DatabaseError: If database operations fail
        """
        if not self.ensure_connection():
            raise DatabaseError("Database connection failed")
        
        try:
            self.logger.info("Updating transcript records with PharmGKB pharmacogenomic data")
            
            # Get all genes in database
            if not self.db_manager.cursor:
                raise DatabaseError("No database cursor available")
            
            # Find genes in database that match our PharmGKB data
            db_genes = set()
            self.db_manager.cursor.execute("""
                SELECT DISTINCT gene_symbol 
                FROM cancer_transcript_base 
                WHERE gene_symbol IS NOT NULL
            """)
            
            for row in self.db_manager.cursor.fetchall():
                db_genes.add(row[0])
            
            # Find intersection with PharmGKB targets
            annotation_genes = set(gene_annotation_mapping.keys())
            vip_genes = set(vip_mapping.keys()) if vip_mapping else set()
            pathway_genes = set(pathway_mapping.keys()) if pathway_mapping else set()
            variant_genes = set(variant_mapping.keys()) if variant_mapping else set()
            all_pharmgkb_genes = annotation_genes.union(vip_genes).union(pathway_genes).union(variant_genes)
            
            matching_genes = db_genes.intersection(all_pharmgkb_genes)
            
            self.logger.info(f"Found {len(matching_genes):,} genes in database that have PharmGKB data")
            self.logger.info(f"Database genes: {len(db_genes):,}, PharmGKB genes: {len(all_pharmgkb_genes):,}")
            
            if not matching_genes:
                self.logger.warning("No gene overlap found between database and PharmGKB")
                return
            
            # Process updates in batches
            update_data = []
            
            progress_bar = get_progress_bar(
                total=len(matching_genes),
                desc="Preparing PharmGKB updates",
                module_name="pharmgkb_annotations"
            )
            
            try:
                for gene_symbol in matching_genes:
                    pharmgkb_data = {}
                    
                    # Add clinical annotations
                    if gene_symbol in gene_annotation_mapping:
                        annotations = gene_annotation_mapping[gene_symbol]
                        pharmgkb_data['clinical_annotations'] = annotations
                        
                        # Calculate summary statistics
                        total_annotations = len(annotations)
                        max_evidence_score = max([ann['evidence_score'] for ann in annotations], default=0)
                        avg_score = sum([ann['score'] for ann in annotations]) / total_annotations if total_annotations > 0 else 0
                        total_pmids = sum([ann['pmid_count'] for ann in annotations])
                        total_evidence = sum([ann['evidence_count'] for ann in annotations])
                        
                        pharmgkb_data['annotation_summary'] = {
                            'total_annotations': total_annotations,
                            'max_evidence_score': max_evidence_score,
                            'avg_score': round(avg_score, 2),
                            'total_pmids': total_pmids,
                            'total_evidence': total_evidence,
                            'evidence_levels': list(set([ann['evidence_level'] for ann in annotations if ann['evidence_level']])),
                            'drugs_mentioned': list(set([ann['drug'] for ann in annotations if ann['drug']])),
                            'phenotype_categories': list(set([ann['phenotype_category'] for ann in annotations if ann['phenotype_category']])),
                            'level_modifiers': list(set([ann['level_modifiers'] for ann in annotations if ann['level_modifiers']]))
                        }
                    
                    # Add VIP information
                    if vip_mapping and gene_symbol in vip_mapping:
                        pharmgkb_data['vip_info'] = vip_mapping[gene_symbol]
                    
                    # Add pathway information
                    if pathway_mapping and gene_symbol in pathway_mapping:
                        pharmgkb_data['pathway_data'] = pathway_mapping[gene_symbol]
                        
                        # Calculate pathway summary statistics
                        pathway_stats = {
                            'total_pathways': len(pathway_mapping[gene_symbol]),
                            'cancer_relevant_pathways': sum(1 for p in pathway_mapping[gene_symbol].values() 
                                                          if p.get('clinical_relevance', {}).get('cancer_relevance', False)),
                            'enzyme_pathways': sum(1 for p in pathway_mapping[gene_symbol].values() 
                                                 if any(r.get('role') == 'enzyme' for r in p.get('gene_roles', {}).values())),
                            'total_reactions': sum(p.get('statistics', {}).get('total_reactions', 0) 
                                                 for p in pathway_mapping[gene_symbol].values()),
                            'total_pmids': sum(p.get('statistics', {}).get('pmid_count', 0) 
                                             for p in pathway_mapping[gene_symbol].values())
                        }
                        pharmgkb_data['pathway_summary'] = pathway_stats
                    
                    # Build comprehensive variant data for pharmgkb_variants column
                    if variant_mapping and gene_symbol in variant_mapping:
                        variants = variant_mapping[gene_symbol]
                        
                        # Build comprehensive pharmgkb_variants structure
                        variant_data = {
                            'summary': {
                                'total_variants': len(variants),
                                'high_impact_variants': sum(1 for v in variants if v.get('pharmacogenomic_score', 0) >= 70),
                                'clinical_actionable': sum(1 for v in variants if v.get('clinical_actionability') == 'high'),
                                'metabolizer_phenotypes': list(set([v.get('metabolizer_prediction', {}).get('phenotype', 'unknown') 
                                                                  for v in variants if v.get('metabolizer_prediction', {}).get('phenotype') != 'unknown'])),
                                'variant_types': list(set([v.get('variant_type', 'unknown') for v in variants])),
                                'drug_categories': list(set([v.get('phenotype_category', '') for v in variants if v.get('phenotype_category')])),
                                'evidence_levels': list(set([v.get('evidence_level', '') for v in variants if v.get('evidence_level')])),
                                'max_pharmacogenomic_score': max([v.get('pharmacogenomic_score', 0) for v in variants], default=0),
                                'avg_pharmacogenomic_score': round(sum([v.get('pharmacogenomic_score', 0) for v in variants]) / len(variants), 2) if variants else 0,
                                'pmid_count': sum(1 for v in variants if v.get('pmid') and v.get('pmid').strip()),
                                'drugs_affected': list(set([drug for v in variants for drug in v.get('drugs', [])])),
                                'specialty_populations': list(set([v.get('specialty_population', '') for v in variants 
                                                                 if v.get('specialty_population') and v.get('specialty_population').strip()]))
                            },
                            'high_impact_variants': [
                                {
                                    'variant_id': v.get('variant_identifier', ''),
                                    'variant_type': v.get('variant_type', 'unknown'),
                                    'drugs': v.get('drugs', []),
                                    'phenotype_category': v.get('phenotype_category', ''),
                                    'significance': v.get('significance', ''),
                                    'direction_of_effect': v.get('direction_of_effect', ''),
                                    'pharmacogenomic_score': v.get('pharmacogenomic_score', 0),
                                    'clinical_actionability': v.get('clinical_actionability', 'research_only'),
                                    'evidence_level': v.get('evidence_level', 'insufficient'),
                                    'metabolizer_prediction': v.get('metabolizer_prediction', {}),
                                    'pmid': v.get('pmid', ''),
                                    'clinical_sentence': v.get('clinical_sentence', '')[:200] + '...' if len(v.get('clinical_sentence', '')) > 200 else v.get('clinical_sentence', ''),  # Truncate long sentences
                                    'specialty_population': v.get('specialty_population', '')
                                }
                                for v in variants 
                                if (v.get('pharmacogenomic_score', 0) >= 70 or 
                                    v.get('clinical_actionability') == 'high' or 
                                    v.get('significance') == 'yes')
                            ],
                            'cyp450_variants': [
                                {
                                    'variant_id': v.get('variant_identifier', ''),
                                    'variant_type': v.get('variant_type', 'unknown'),
                                    'drugs': v.get('drugs', []),
                                    'phenotype_category': v.get('phenotype_category', ''),
                                    'metabolizer_prediction': v.get('metabolizer_prediction', {}),
                                    'pharmacogenomic_score': v.get('pharmacogenomic_score', 0),
                                    'clinical_actionability': v.get('clinical_actionability', 'research_only')
                                }
                                for v in variants 
                                if any(cyp in v.get('phenotype_category', '').lower() for cyp in ['cyp', 'metabolism'])
                            ],
                            'cancer_relevant_variants': [
                                {
                                    'variant_id': v.get('variant_identifier', ''),
                                    'drugs': v.get('drugs', []),
                                    'phenotype_category': v.get('phenotype_category', ''),
                                    'pharmacogenomic_score': v.get('pharmacogenomic_score', 0),
                                    'clinical_actionability': v.get('clinical_actionability', 'research_only'),
                                    'clinical_sentence': v.get('clinical_sentence', '')[:150] + '...' if len(v.get('clinical_sentence', '')) > 150 else v.get('clinical_sentence', '')
                                }
                                for v in variants 
                                if any(drug in ['tamoxifen', 'fluorouracil', 'methotrexate', 'doxorubicin', 'cyclophosphamide', 
                                              'paclitaxel', 'carboplatin', 'cisplatin', 'irinotecan', 'capecitabine',
                                              'trastuzumab', 'bevacizumab', 'rituximab', 'imatinib', 'gefitinib'] 
                                      for drug in [d.lower() for d in v.get('drugs', [])])
                            ]
                        }
                        
                        # Add basic variant summary to pharmgkb_data for backwards compatibility
                        pharmgkb_data['variant_summary'] = variant_data['summary']
                    
                    # Add source and processing metadata
                    pharmgkb_data['source'] = 'PharmGKB'
                    pharmgkb_data['processed_date'] = datetime.now().isoformat()
                    
                    # Prepare variant data for pharmgkb_variants column
                    if variant_mapping and gene_symbol in variant_mapping:
                        update_data.append((json.dumps(pharmgkb_data), json.dumps(variant_data), gene_symbol))
                    else:
                        update_data.append((json.dumps(pharmgkb_data), '{}', gene_symbol))
                    progress_bar.update(1)
                    
            finally:
                progress_bar.close()
            
            # Execute batch update
            self.logger.info(f"Updating {len(update_data):,} transcript records with PharmGKB data")
            
            try:
                # Add PharmGKB data to drugs field, pathway data to pharmgkb_pathways field, and variant data to pharmgkb_variants field
                self.db_manager.cursor.executemany("""
                    UPDATE cancer_transcript_base 
                    SET drugs = COALESCE(drugs, '{}'::jsonb) || jsonb_build_object('pharmgkb_data', %s::jsonb),
                        pharmgkb_pathways = CASE 
                            WHEN (%s::jsonb ? 'pathway_data') THEN (%s::jsonb->'pathway_data')
                            ELSE pharmgkb_pathways
                        END,
                        pharmgkb_variants = %s::jsonb
                    WHERE gene_symbol = %s
                """, [(json_data, json_data, json_data, variant_data, gene_symbol) for json_data, variant_data, gene_symbol in update_data])
                
                if self.db_manager.conn:
                    self.db_manager.conn.commit()
            except Exception as e:
                if self.db_manager.conn:
                    self.db_manager.conn.rollback()
                raise e
            
            # Verify updates
            self.db_manager.cursor.execute("""
                SELECT COUNT(*) 
                FROM cancer_transcript_base 
                WHERE drugs ? 'pharmgkb_data'
            """)
            
            updated_count = self.db_manager.cursor.fetchone()[0]
            
            # Check pathway updates
            self.db_manager.cursor.execute("""
                SELECT COUNT(*) 
                FROM cancer_transcript_base 
                WHERE pharmgkb_pathways != '{}'::jsonb
            """)
            
            pathway_count = self.db_manager.cursor.fetchone()[0]
            
            # Check variant updates
            self.db_manager.cursor.execute("""
                SELECT COUNT(*) 
                FROM cancer_transcript_base 
                WHERE pharmgkb_variants != '{}'::jsonb
            """)
            
            variant_count = self.db_manager.cursor.fetchone()[0]
            
            self.logger.info(f"Successfully updated {updated_count:,} records with PharmGKB clinical data")
            self.logger.info(f"Successfully updated {pathway_count:,} records with PharmGKB pathway data")
            self.logger.info(f"Successfully updated {variant_count:,} records with PharmGKB variant data")
            
        except Exception as e:
            raise DatabaseError(f"Failed to update transcript PharmGKB data: {e}")

    def calculate_pharmgkb_scores(self) -> None:
        """Calculate pharmacogenomic scores for genes with PharmGKB data.
        
        Raises:
            DatabaseError: If score calculation fails
        """
        if not self.ensure_connection():
            raise DatabaseError("Database connection failed")
        
        try:
            self.logger.info("Calculating PharmGKB pharmacogenomic scores")
            
            if not self.db_manager.cursor:
                raise DatabaseError("No database cursor available")
            
            # Get genes with PharmGKB data
            self.db_manager.cursor.execute("""
                SELECT gene_symbol, drugs->'pharmgkb_data' as pharmgkb_data
                FROM cancer_transcript_base 
                WHERE drugs ? 'pharmgkb_data'
            """)
            
            genes_with_pharmgkb = self.db_manager.cursor.fetchall()
            self.logger.info(f"Calculating scores for {len(genes_with_pharmgkb):,} genes with PharmGKB data")
            
            if not genes_with_pharmgkb:
                self.logger.warning("No genes found with PharmGKB data")
                return
            
            score_updates = []
            
            progress_bar = get_progress_bar(
                total=len(genes_with_pharmgkb),
                desc="Calculating PharmGKB scores",
                module_name="pharmgkb_annotations"
            )
            
            try:
                for gene_symbol, pharmgkb_data in genes_with_pharmgkb:
                    pharmgkb_scores = {}
                    
                    # Extract annotation summary if available
                    if 'annotation_summary' in pharmgkb_data:
                        summary = pharmgkb_data['annotation_summary']
                        
                        # Calculate comprehensive pharmacogenomic score
                        evidence_score = summary.get('max_evidence_score', 0)
                        annotation_count = summary.get('total_annotations', 0)
                        pmid_count = summary.get('total_pmids', 0)
                        avg_score = summary.get('avg_score', 0)
                        
                        # Overall pharmacogenomic score formula (updated for real data)
                        overall_score = (
                            evidence_score * 2.0 +           # Evidence level weight
                            avg_score * 1.0 +                # PharmGKB score weight
                            min(annotation_count * 0.3, 3.0) + # Annotation count bonus (capped)
                            min(pmid_count * 0.2, 2.0)       # Publication support bonus (capped)
                        )
                        
                        pharmgkb_scores = {
                            'evidence_score': evidence_score,
                            'avg_pharmgkb_score': avg_score,
                            'annotation_count': annotation_count,
                            'pmid_count': pmid_count,
                            'overall_pharmgkb_score': round(overall_score, 2)
                        }
                    
                    # VIP gene bonus
                    if 'vip_info' in pharmgkb_data:
                        pharmgkb_scores['is_vip_gene'] = True
                        pharmgkb_scores['overall_pharmgkb_score'] = pharmgkb_scores.get('overall_pharmgkb_score', 0) + 1.0
                    
                    if pharmgkb_scores:
                        score_updates.append((json.dumps(pharmgkb_scores), gene_symbol))
                    
                    progress_bar.update(1)
                    
            finally:
                progress_bar.close()
            
            # Update drug scores
            if score_updates:
                self.logger.info(f"Updating PharmGKB scores for {len(score_updates):,} genes")
                
                try:
                    self.db_manager.cursor.executemany("""
                        UPDATE cancer_transcript_base 
                        SET drug_scores = COALESCE(drug_scores, '{}'::jsonb) || %s::jsonb
                        WHERE gene_symbol = %s
                    """, score_updates)
                    
                    if self.db_manager.conn:
                        self.db_manager.conn.commit()
                except Exception as e:
                    if self.db_manager.conn:
                        self.db_manager.conn.rollback()
                    raise e
                
                self.logger.info("PharmGKB score calculation completed")
            
        except Exception as e:
            raise DatabaseError(f"Failed to calculate PharmGKB scores: {e}")

    def generate_pharmgkb_summary(self) -> None:
        """Generate summary statistics for PharmGKB integration."""
        try:
            if not self.ensure_connection() or not self.db_manager.cursor:
                return
            
            console = Console()
            
            # Get summary statistics
            self.db_manager.cursor.execute("""
                SELECT 
                    COUNT(*) as total_genes,
                    COUNT(*) FILTER (WHERE drugs ? 'pharmgkb_data') as genes_with_pharmgkb,
                    COUNT(*) FILTER (WHERE pharmgkb_pathways != '{}'::jsonb) as genes_with_pathways,
                    AVG((drug_scores->>'overall_pharmgkb_score')::float) FILTER (WHERE drug_scores ? 'overall_pharmgkb_score') as avg_pharmgkb_score,
                    COUNT(*) FILTER (WHERE drug_scores->>'is_vip_gene' = 'true') as vip_genes
                FROM cancer_transcript_base
            """)
            
            stats = self.db_manager.cursor.fetchone()
            
            # Create summary table
            table = Table(title="PharmGKB Integration Results")
            table.add_column("Metric", style="cyan")
            table.add_column("Count", style="green")
            table.add_column("Coverage", style="yellow")
            
            total_genes = stats[0]
            genes_with_pharmgkb = stats[1]
            genes_with_pathways = stats[2]
            avg_score = stats[3] if stats[3] else 0
            vip_genes = stats[4]
            
            coverage = (genes_with_pharmgkb / total_genes * 100) if total_genes > 0 else 0
            pathway_coverage = (genes_with_pathways / total_genes * 100) if total_genes > 0 else 0
            vip_coverage = (vip_genes / total_genes * 100) if total_genes > 0 else 0
            
            table.add_row("Total Genes", f"{total_genes:,}", "100.0%")
            table.add_row("With PharmGKB Data", f"{genes_with_pharmgkb:,}", f"{coverage:.1f}%")
            table.add_row("With Pathway Data", f"{genes_with_pathways:,}", f"{pathway_coverage:.1f}%")
            table.add_row("VIP Genes", f"{vip_genes:,}", f"{vip_coverage:.1f}%")
            table.add_row("Avg PharmGKB Score", f"{avg_score:.2f}", "-")
            
            console.print(table)
            
            # Log key statistics
            self.logger.info(f"PharmGKB integration statistics:")
            self.logger.info(f"  - Total genes: {total_genes:,}")
            self.logger.info(f"  - Genes with PharmGKB data: {genes_with_pharmgkb:,} ({coverage:.1f}%)")
            self.logger.info(f"  - Genes with pathway data: {genes_with_pathways:,} ({pathway_coverage:.1f}%)")
            self.logger.info(f"  - VIP genes: {vip_genes:,} ({vip_coverage:.1f}%)")
            self.logger.info(f"  - Average PharmGKB score: {avg_score:.2f}")
            
        except Exception as e:
            self.logger.warning(f"Failed to generate PharmGKB summary: {e}")

    def run(self) -> None:
        """Run the complete PharmGKB annotations processing pipeline.
        
        Steps:
        1. Download PharmGKB datasets (clinical annotations, VIP summaries)
        2. Process clinical annotations and VIP data
        3. Update transcript records with pharmacogenomic data
        4. Calculate pharmacogenomic scores
        5. Generate summary statistics
        
        Raises:
            Various ETLError subclasses based on failure point
        """
        try:
            self.logger.info("Starting PharmGKB annotations processing pipeline")
            
            # Ensure database connection and schema
            if not self.ensure_connection():
                raise DatabaseError("Database connection failed")
            
            if not self.ensure_schema_version(self.required_schema_version):
                raise DatabaseError(f"Incompatible database schema version")
            
            # Download PharmGKB data
            clinical_file, variant_file, vip_file, pathways_dir = self.download_pharmgkb_data()
            
            # Process clinical annotations
            gene_annotation_mapping = self.process_clinical_annotations(clinical_file)
            
            # Process VIP summaries if available
            vip_mapping = None
            if vip_file:
                vip_mapping = self.process_vip_summaries(vip_file)
            
            # Process variant annotations if available
            variant_mapping = None
            if variant_file:
                variant_mapping = self.process_variant_annotations(variant_file)
            
            # Process pathway data if available
            pathway_mapping = None
            if pathways_dir:
                pathway_mapping = self.process_pharmgkb_pathways(pathways_dir)
            
            # Extract publication references
            publications = self.extract_publication_references(gene_annotation_mapping, variant_mapping)
            
            # Process publications using the publications processor
            if publications:
                publications_processor = PublicationsProcessor(self.config)
                publications_processor.enrich_publications_bulk(publications)
            
            # Update transcript records
            self.update_transcript_pharmgkb_data(gene_annotation_mapping, vip_mapping, pathway_mapping, variant_mapping)
            
            # Calculate scores if not skipped
            if not self.skip_scores:
                self.calculate_pharmgkb_scores()
            
            # Generate summary
            self.generate_pharmgkb_summary()
            
            self.logger.info("PharmGKB annotations processing completed successfully")
            
        except Exception as e:
            self.logger.error(f"PharmGKB annotations processing failed: {e}")
            raise