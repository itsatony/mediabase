#!/usr/bin/env python3
"""
SOTA (Standard Oncological Analysis) Auto-Analysis Script

This script performs comprehensive automated analysis of cancer transcriptome data
to generate clinically relevant insights for oncologists and researchers.

Analysis Categories:
1. Drug-Gene Interaction Analysis - Therapeutic targeting opportunities
2. Pathway Enrichment Analysis - Biological process perturbations  
3. Functional Classification Analysis - Molecular function distributions
4. Chromosomal Distribution Analysis - Positional clustering patterns
5. Multi-modal Integration Analysis - Cross-domain associations
6. Clinical Biomarker Discovery - Potential diagnostic/prognostic markers
"""

import argparse
import json
import logging
import os
import sys
from collections import defaultdict, Counter
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
import statistics

# Add project root to Python path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from src.db.database import get_db_manager
from src.utils.logging import setup_logging, get_progress_bar, console

# Setup logging
logger = setup_logging(
    module_name=__name__,
    log_file="sota_analysis.log"
)

class SOTAAnalyzer:
    """Comprehensive SOTA analysis engine for cancer transcriptome data."""
    
    def __init__(self, db_config: Dict[str, Any]):
        """Initialize analyzer with database configuration."""
        self.db_manager = get_db_manager(db_config)
        self.analysis_results = {}
        self.timestamp = datetime.now().isoformat()
        
    def get_all_transcripts(self, patient_db: Optional[str] = None) -> List[Dict]:
        """
        Retrieve all transcript data for analysis.
        
        Args:
            patient_db: Optional patient database name for patient-specific analysis
            
        Returns:
            List of transcript records with all enrichment data
        """
        # Connect to the appropriate database
        if patient_db:
            self.db_manager.connect(patient_db)
        else:
            self.db_manager.connect()
        
        if not self.db_manager.ensure_connection():
            logger.error("Failed to establish database connection")
            return []
        
        try:
            cursor = self.db_manager.cursor
            cursor.execute("""
                SELECT 
                    transcript_id, gene_symbol, gene_id, gene_type, chromosome,
                    coordinates, product_type, go_terms, pathways, drugs,
                    molecular_functions, cellular_location, expression_fold_change
                FROM cancer_transcript_base
            """)
            
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error retrieving transcript data: {e}")
            return []
    
    def analyze_drug_gene_interactions(self, transcripts: List[Dict]) -> Dict[str, Any]:
        """
        SOTA Query 1: Drug-Gene Interaction Analysis
        
        Clinical Rationale:
        - Identifies genes with existing drug interactions for therapeutic targeting
        - Prioritizes high-scoring drug-gene pairs for precision medicine
        - Maps drug mechanisms to understand intervention strategies
        
        Returns comprehensive drug interaction landscape with therapeutic potential scores.
        """
        logger.info("Running SOTA Query 1: Drug-Gene Interaction Analysis")
        
        drug_interactions = []
        mechanism_counts = Counter()
        high_score_targets = []
        druggable_genes = set()
        
        for transcript in transcripts:
            if transcript['drugs'] and transcript['drugs'] != {}:
                gene_symbol = transcript['gene_symbol']
                drugs = transcript['drugs']
                
                for drug_id, drug_info in drugs.items():
                    interaction = {
                        'gene_symbol': gene_symbol,
                        'transcript_id': transcript['transcript_id'],
                        'drug_id': drug_id,
                        'drug_name': drug_info.get('name', 'Unknown'),
                        'score': drug_info.get('score', 0),
                        'mechanism': drug_info.get('mechanism', 'unknown'),
                        'chromosome': transcript['chromosome']
                    }
                    
                    drug_interactions.append(interaction)
                    mechanism_counts[drug_info.get('mechanism', 'unknown')] += 1
                    druggable_genes.add(gene_symbol)
                    
                    # High therapeutic potential (score > 100)
                    if drug_info.get('score', 0) > 100:
                        high_score_targets.append(interaction)
        
        # Calculate drug interaction statistics
        if drug_interactions:
            scores = [d['score'] for d in drug_interactions if d['score'] > 0]
            score_stats = {
                'mean': statistics.mean(scores) if scores else 0,
                'median': statistics.median(scores) if scores else 0,
                'max': max(scores) if scores else 0,
                'min': min(scores) if scores else 0
            }
        else:
            score_stats = {'mean': 0, 'median': 0, 'max': 0, 'min': 0}
        
        return {
            'total_drug_interactions': len(drug_interactions),
            'druggable_genes_count': len(druggable_genes),
            'high_score_targets': len(high_score_targets),
            'mechanism_distribution': dict(mechanism_counts),
            'score_statistics': score_stats,
            'top_drug_targets': sorted(high_score_targets, key=lambda x: x['score'], reverse=True)[:10],
            'clinical_summary': self._generate_drug_clinical_summary(drug_interactions, high_score_targets)
        }
    
    def analyze_pathway_enrichment(self, transcripts: List[Dict]) -> Dict[str, Any]:
        """
        SOTA Query 2: Pathway Enrichment Analysis
        
        Clinical Rationale:
        - Identifies perturbed biological pathways in cancer
        - Maps pathway co-occurrence patterns for systems-level understanding
        - Prioritizes pathway-targeted therapeutic strategies
        
        Returns pathway landscape with enrichment scores and co-occurrence networks.
        """
        logger.info("Running SOTA Query 2: Pathway Enrichment Analysis")
        
        pathway_counts = Counter()
        pathway_gene_map = defaultdict(list)
        pathway_cooccurrence = defaultdict(lambda: defaultdict(int))
        
        for transcript in transcripts:
            if transcript['pathways']:
                gene_symbol = transcript['gene_symbol']
                pathways = transcript['pathways']
                
                for pathway in pathways:
                    pathway_counts[pathway] += 1
                    pathway_gene_map[pathway].append(gene_symbol)
                
                # Pathway co-occurrence analysis
                for i, pathway1 in enumerate(pathways):
                    for pathway2 in pathways[i+1:]:
                        pathway_cooccurrence[pathway1][pathway2] += 1
                        pathway_cooccurrence[pathway2][pathway1] += 1
        
        # Calculate enrichment scores (frequency-based)
        total_genes = len(transcripts)
        enrichment_analysis = []
        
        for pathway, count in pathway_counts.most_common():
            enrichment_score = (count / total_genes) * 100  # Percentage enrichment
            enrichment_analysis.append({
                'pathway': pathway,
                'gene_count': count,
                'enrichment_score': enrichment_score,
                'genes': pathway_gene_map[pathway]
            })
        
        # Top co-occurring pathway pairs
        cooccurrence_pairs = []
        for pathway1, partners in pathway_cooccurrence.items():
            for pathway2, count in partners.items():
                if count >= 2:  # Minimum co-occurrence threshold
                    cooccurrence_pairs.append({
                        'pathway1': pathway1,
                        'pathway2': pathway2,
                        'cooccurrence_count': count
                    })
        
        cooccurrence_pairs.sort(key=lambda x: x['cooccurrence_count'], reverse=True)
        
        return {
            'total_pathways': len(pathway_counts),
            'enriched_pathways': enrichment_analysis[:20],  # Top 20 enriched
            'pathway_cooccurrence_network': cooccurrence_pairs[:15],  # Top 15 pairs
            'pathway_statistics': {
                'mean_genes_per_pathway': statistics.mean(pathway_counts.values()) if pathway_counts else 0,
                'max_pathway_size': max(pathway_counts.values()) if pathway_counts else 0
            },
            'clinical_summary': self._generate_pathway_clinical_summary(enrichment_analysis[:10])
        }
    
    def analyze_functional_classification(self, transcripts: List[Dict]) -> Dict[str, Any]:
        """
        SOTA Query 3: Functional Classification Analysis
        
        Clinical Rationale:
        - Maps molecular function landscape alterations in cancer
        - Identifies functional domains for targeted intervention
        - Provides systems-level view of cellular process perturbations
        
        Returns functional classification patterns with clinical relevance scoring.
        """
        logger.info("Running SOTA Query 3: Functional Classification Analysis")
        
        function_counts = Counter()
        location_counts = Counter()
        product_type_counts = Counter()
        go_function_counts = Counter()
        
        function_location_map = defaultdict(lambda: defaultdict(int))
        
        for transcript in transcripts:
            # Molecular functions analysis
            if transcript['molecular_functions']:
                for func in transcript['molecular_functions']:
                    function_counts[func] += 1
                    
                    # Cross-reference with cellular location
                    if transcript['cellular_location']:
                        for location in transcript['cellular_location']:
                            function_location_map[func][location] += 1
            
            # Cellular location analysis
            if transcript['cellular_location']:
                for location in transcript['cellular_location']:
                    location_counts[location] += 1
            
            # Product type analysis
            if transcript['product_type']:
                for ptype in transcript['product_type']:
                    product_type_counts[ptype] += 1
            
            # GO terms molecular function analysis
            if transcript['go_terms'] and 'molecular_function' in transcript['go_terms']:
                for go_func in transcript['go_terms']['molecular_function']:
                    go_function_counts[go_func] += 1
        
        # Generate functional profiles
        functional_profiles = []
        for func, count in function_counts.most_common(15):
            profile = {
                'molecular_function': func,
                'gene_count': count,
                'primary_locations': dict(Counter(function_location_map[func]).most_common(3)),
                'frequency_score': (count / len(transcripts)) * 100
            }
            functional_profiles.append(profile)
        
        return {
            'molecular_function_landscape': {
                'total_functions': len(function_counts),
                'top_functions': dict(function_counts.most_common(10)),
                'functional_profiles': functional_profiles
            },
            'cellular_location_distribution': dict(location_counts.most_common(10)),
            'product_type_classification': dict(product_type_counts.most_common()),
            'go_molecular_functions': dict(go_function_counts.most_common(10)),
            'clinical_summary': self._generate_functional_clinical_summary(functional_profiles[:5])
        }
    
    def analyze_chromosomal_distribution(self, transcripts: List[Dict]) -> Dict[str, Any]:
        """
        SOTA Query 4: Chromosomal Distribution Analysis
        
        Clinical Rationale:
        - Identifies chromosomal regions with high gene alteration density
        - Maps potential chromosomal instability patterns
        - Guides cytogenetic analysis and chromosomal therapy targets
        
        Returns chromosomal landscape with hotspot identification.
        """
        logger.info("Running SOTA Query 4: Chromosomal Distribution Analysis")
        
        chromosome_counts = Counter()
        chromosome_density = defaultdict(list)
        chromosomal_drug_targets = defaultdict(int)
        
        for transcript in transcripts:
            chromosome = transcript['chromosome']
            chromosome_counts[chromosome] += 1
            
            # Extract chromosomal coordinates if available
            if transcript['coordinates']:
                coords = transcript['coordinates']
                if isinstance(coords, dict) and 'start' in coords:
                    chromosome_density[chromosome].append(coords['start'])
            
            # Map drug targets by chromosome
            if transcript['drugs'] and transcript['drugs'] != {}:
                chromosomal_drug_targets[chromosome] += len(transcript['drugs'])
        
        # Calculate chromosomal statistics
        chromosome_stats = []
        for chrom, count in chromosome_counts.most_common():
            stats = {
                'chromosome': chrom,
                'gene_count': count,
                'drug_targets': chromosomal_drug_targets[chrom],
                'density_score': count / len(transcripts) * 100
            }
            
            # Add positional clustering analysis if coordinates available
            if chromosome_density[chrom]:
                positions = chromosome_density[chrom]
                stats['position_range'] = {
                    'start': min(positions),
                    'end': max(positions),
                    'span': max(positions) - min(positions)
                }
            
            chromosome_stats.append(stats)
        
        # Identify chromosomal hotspots (top 25% by density)
        density_scores = [s['density_score'] for s in chromosome_stats]
        if density_scores:
            # Sort and find 75th percentile manually
            sorted_scores = sorted(density_scores)
            n = len(sorted_scores)
            index = int(0.75 * (n - 1))
            hotspot_threshold = sorted_scores[index]
        else:
            hotspot_threshold = 0
        hotspots = [s for s in chromosome_stats if s['density_score'] >= hotspot_threshold]
        
        return {
            'chromosomal_distribution': chromosome_stats,
            'hotspot_chromosomes': hotspots,
            'drug_target_chromosomes': sorted(chromosomal_drug_targets.items(), 
                                            key=lambda x: x[1], reverse=True)[:5],
            'distribution_statistics': {
                'total_chromosomes': len(chromosome_counts),
                'mean_genes_per_chromosome': statistics.mean(chromosome_counts.values()) if chromosome_counts else 0,
                'hotspot_threshold': hotspot_threshold
            },
            'clinical_summary': self._generate_chromosomal_clinical_summary(hotspots, chromosome_stats)
        }
    
    def analyze_multimodal_integration(self, transcripts: List[Dict]) -> Dict[str, Any]:
        """
        SOTA Query 5: Multi-modal Integration Analysis
        
        Clinical Rationale:
        - Integrates drug, pathway, and functional data for comprehensive insights
        - Identifies multi-target therapeutic opportunities
        - Maps systems-level intervention strategies
        
        Returns integrated analysis with cross-domain associations and therapeutic profiles.
        """
        logger.info("Running SOTA Query 5: Multi-modal Integration Analysis")
        
        integrated_profiles = []
        pathway_drug_associations = defaultdict(lambda: defaultdict(int))
        function_drug_associations = defaultdict(lambda: defaultdict(int))
        
        for transcript in transcripts:
            gene_symbol = transcript['gene_symbol']
            
            # Create integrated gene profile
            profile = {
                'gene_symbol': gene_symbol,
                'transcript_id': transcript['transcript_id'],
                'chromosome': transcript['chromosome'],
                'has_drugs': bool(transcript['drugs'] and transcript['drugs'] != {}),
                'drug_count': len(transcript['drugs']) if transcript['drugs'] else 0,
                'pathway_count': len(transcript['pathways']) if transcript['pathways'] else 0,
                'function_count': len(transcript['molecular_functions']) if transcript['molecular_functions'] else 0,
                'multimodal_score': 0
            }
            
            # Calculate multimodal score (integration complexity)
            if profile['has_drugs']:
                profile['multimodal_score'] += profile['drug_count'] * 3  # Drug interactions weighted heavily
            profile['multimodal_score'] += profile['pathway_count'] * 2  # Pathway involvement
            profile['multimodal_score'] += profile['function_count']  # Functional diversity
            
            integrated_profiles.append(profile)
            
            # Cross-domain association analysis
            if transcript['drugs'] and transcript['pathways']:
                for pathway in transcript['pathways']:
                    for drug_id in transcript['drugs'].keys():
                        pathway_drug_associations[pathway][drug_id] += 1
            
            if transcript['drugs'] and transcript['molecular_functions']:
                for function in transcript['molecular_functions']:
                    for drug_id in transcript['drugs'].keys():
                        function_drug_associations[function][drug_id] += 1
        
        # Sort by multimodal complexity
        integrated_profiles.sort(key=lambda x: x['multimodal_score'], reverse=True)
        
        # Generate cross-domain association networks
        pathway_drug_network = []
        for pathway, drugs in pathway_drug_associations.items():
            for drug_id, count in drugs.items():
                if count >= 1:  # Minimum association threshold
                    pathway_drug_network.append({
                        'pathway': pathway,
                        'drug_id': drug_id,
                        'association_strength': count
                    })
        
        function_drug_network = []
        for function, drugs in function_drug_associations.items():
            for drug_id, count in drugs.items():
                if count >= 1:
                    function_drug_network.append({
                        'molecular_function': function,
                        'drug_id': drug_id,
                        'association_strength': count
                    })
        
        return {
            'integrated_gene_profiles': integrated_profiles[:20],  # Top 20 complex genes
            'multimodal_statistics': {
                'mean_multimodal_score': statistics.mean([p['multimodal_score'] for p in integrated_profiles]),
                'highly_integrated_genes': len([p for p in integrated_profiles if p['multimodal_score'] >= 10])
            },
            'pathway_drug_associations': sorted(pathway_drug_network, 
                                              key=lambda x: x['association_strength'], reverse=True)[:15],
            'function_drug_associations': sorted(function_drug_network,
                                               key=lambda x: x['association_strength'], reverse=True)[:15],
            'clinical_summary': self._generate_multimodal_clinical_summary(integrated_profiles[:10])
        }
    
    def analyze_clinical_biomarkers(self, transcripts: List[Dict]) -> Dict[str, Any]:
        """
        SOTA Query 6: Clinical Biomarker Discovery Analysis
        
        Clinical Rationale:
        - Identifies potential diagnostic and prognostic biomarkers
        - Maps biomarker expression patterns and drug responsiveness
        - Prioritizes genes for clinical validation studies
        
        Returns biomarker candidates with clinical utility scores.
        """
        logger.info("Running SOTA Query 6: Clinical Biomarker Discovery Analysis")
        
        biomarker_candidates = []
        
        for transcript in transcripts:
            gene_symbol = transcript['gene_symbol']
            
            # Calculate biomarker potential score
            biomarker_score = 0
            characteristics = []
            
            # Drug targetability (high clinical utility)
            if transcript['drugs'] and transcript['drugs'] != {}:
                drug_scores = [d.get('score', 0) for d in transcript['drugs'].values()]
                if drug_scores:
                    biomarker_score += max(drug_scores) * 0.4  # 40% weight for druggability
                    characteristics.append('drug_targetable')
            
            # Pathway involvement (systems relevance)
            if transcript['pathways']:
                pathway_count = len(transcript['pathways'])
                biomarker_score += min(pathway_count * 10, 50)  # Cap at 50 points
                if pathway_count >= 3:
                    characteristics.append('multi_pathway')
            
            # Functional diversity (biological importance)
            if transcript['molecular_functions']:
                function_count = len(transcript['molecular_functions'])
                biomarker_score += min(function_count * 5, 25)  # Cap at 25 points
                if function_count >= 3:
                    characteristics.append('multi_functional')
            
            # Expression level consideration (if available)
            if transcript.get('expression_fold_change'):
                fold_change = abs(transcript['expression_fold_change'])
                if fold_change >= 2.0:
                    biomarker_score += 20
                    characteristics.append('high_expression_change')
                elif fold_change >= 1.5:
                    biomarker_score += 10
                    characteristics.append('moderate_expression_change')
            
            # Chromosomal location consideration (stability)
            chromosome = transcript['chromosome']
            if chromosome not in ['chrX', 'chrY']:  # Autosomal chromosomes more stable
                biomarker_score += 5
                characteristics.append('autosomal')
            
            biomarker_candidates.append({
                'gene_symbol': gene_symbol,
                'transcript_id': transcript['transcript_id'],
                'biomarker_score': biomarker_score,
                'characteristics': characteristics,
                'chromosome': chromosome,
                'drug_count': len(transcript['drugs']) if transcript['drugs'] else 0,
                'pathway_count': len(transcript['pathways']) if transcript['pathways'] else 0,
                'function_count': len(transcript['molecular_functions']) if transcript['molecular_functions'] else 0
            })
        
        # Sort by biomarker potential
        biomarker_candidates.sort(key=lambda x: x['biomarker_score'], reverse=True)
        
        # Categorize biomarkers
        high_potential = [b for b in biomarker_candidates if b['biomarker_score'] >= 75]
        moderate_potential = [b for b in biomarker_candidates if 50 <= b['biomarker_score'] < 75]
        emerging_biomarkers = [b for b in biomarker_candidates if 25 <= b['biomarker_score'] < 50]
        
        return {
            'biomarker_candidates': biomarker_candidates[:25],  # Top 25 candidates
            'biomarker_categories': {
                'high_potential': len(high_potential),
                'moderate_potential': len(moderate_potential),
                'emerging_biomarkers': len(emerging_biomarkers)
            },
            'top_biomarkers': high_potential[:10],
            'biomarker_statistics': {
                'mean_biomarker_score': statistics.mean([b['biomarker_score'] for b in biomarker_candidates]),
                'score_distribution': {
                    'high': len(high_potential),
                    'moderate': len(moderate_potential),
                    'emerging': len(emerging_biomarkers)
                }
            },
            'clinical_summary': self._generate_biomarker_clinical_summary(high_potential[:5])
        }
    
    def _generate_drug_clinical_summary(self, interactions: List[Dict], high_score: List[Dict]) -> str:
        """Generate clinical summary for drug interaction analysis."""
        if not interactions:
            return "No drug interactions found in the dataset."
        
        summary = f"Analysis identified {len(interactions)} drug-gene interactions across multiple therapeutic modalities. "
        
        if high_score:
            top_target = max(high_score, key=lambda x: x['score'])
            summary += f"Highest therapeutic potential: {top_target['gene_symbol']} (score: {top_target['score']:.1f}). "
        
        summary += "These interactions represent immediate opportunities for precision medicine approaches."
        return summary
    
    def _generate_pathway_clinical_summary(self, enriched: List[Dict]) -> str:
        """Generate clinical summary for pathway analysis."""
        if not enriched:
            return "No enriched pathways identified."
        
        top_pathway = enriched[0]
        summary = f"Primary pathway alteration: {top_pathway['pathway']} ({top_pathway['gene_count']} genes, "
        summary += f"{top_pathway['enrichment_score']:.1f}% enrichment). "
        summary += "Pathway-targeted therapies should be prioritized for clinical intervention."
        return summary
    
    def _generate_functional_clinical_summary(self, profiles: List[Dict]) -> str:
        """Generate clinical summary for functional analysis."""
        if not profiles:
            return "No functional alterations detected."
        
        top_function = profiles[0]
        summary = f"Dominant functional alteration: {top_function['molecular_function']} "
        summary += f"({top_function['gene_count']} genes affected). "
        summary += "Functional targeting strategies should focus on this domain."
        return summary
    
    def _generate_chromosomal_clinical_summary(self, hotspots: List[Dict], all_stats: List[Dict]) -> str:
        """Generate clinical summary for chromosomal analysis."""
        if not hotspots:
            return "No chromosomal hotspots identified."
        
        top_hotspot = max(hotspots, key=lambda x: x['density_score'])
        summary = f"Primary chromosomal hotspot: {top_hotspot['chromosome']} "
        summary += f"({top_hotspot['gene_count']} genes, {top_hotspot['density_score']:.1f}% density). "
        summary += "Cytogenetic analysis and chromosomal stability assessment recommended."
        return summary
    
    def _generate_multimodal_clinical_summary(self, profiles: List[Dict]) -> str:
        """Generate clinical summary for multimodal analysis."""
        if not profiles:
            return "No integrated gene profiles available."
        
        top_gene = profiles[0]
        summary = f"Most complex therapeutic target: {top_gene['gene_symbol']} "
        summary += f"(multimodal score: {top_gene['multimodal_score']}). "
        summary += "Multi-target therapeutic strategies recommended for high-complexity genes."
        return summary
    
    def _generate_biomarker_clinical_summary(self, biomarkers: List[Dict]) -> str:
        """Generate clinical summary for biomarker analysis."""
        if not biomarkers:
            return "No biomarker candidates identified."
        
        top_biomarker = biomarkers[0]
        summary = f"Top biomarker candidate: {top_biomarker['gene_symbol']} "
        summary += f"(score: {top_biomarker['biomarker_score']:.1f}). "
        summary += "Immediate clinical validation studies recommended for high-scoring candidates."
        return summary
    
    def run_complete_analysis(self, patient_db: Optional[str] = None) -> Dict[str, Any]:
        """
        Run complete SOTA analysis pipeline.
        
        Args:
            patient_db: Optional patient database for patient-specific analysis
            
        Returns:
            Complete analysis results with all SOTA queries
        """
        logger.info("Starting comprehensive SOTA analysis pipeline")
        
        # Retrieve transcript data
        transcripts = self.get_all_transcripts(patient_db)
        
        if not transcripts:
            logger.warning("No transcript data found for analysis")
            return {
                'status': 'no_data',
                'message': 'No transcript data available for analysis',
                'timestamp': self.timestamp
            }
        
        logger.info(f"Analyzing {len(transcripts)} transcripts")
        
        # Progress tracking
        progress_bar = get_progress_bar(
            total=6,
            desc="Running SOTA analyses",
            module_name="sota_analysis"
        )
        
        try:
            # Run all SOTA analyses
            self.analysis_results = {
                'analysis_metadata': {
                    'timestamp': self.timestamp,
                    'database': patient_db or 'mediabase',
                    'transcript_count': len(transcripts),
                    'analysis_version': 'v1.0.0'
                }
            }
            
            # SOTA Query 1: Drug-Gene Interactions
            self.analysis_results['drug_gene_interactions'] = self.analyze_drug_gene_interactions(transcripts)
            progress_bar.update(1)
            
            # SOTA Query 2: Pathway Enrichment
            self.analysis_results['pathway_enrichment'] = self.analyze_pathway_enrichment(transcripts)
            progress_bar.update(1)
            
            # SOTA Query 3: Functional Classification
            self.analysis_results['functional_classification'] = self.analyze_functional_classification(transcripts)
            progress_bar.update(1)
            
            # SOTA Query 4: Chromosomal Distribution
            self.analysis_results['chromosomal_distribution'] = self.analyze_chromosomal_distribution(transcripts)
            progress_bar.update(1)
            
            # SOTA Query 5: Multi-modal Integration
            self.analysis_results['multimodal_integration'] = self.analyze_multimodal_integration(transcripts)
            progress_bar.update(1)
            
            # SOTA Query 6: Clinical Biomarkers
            self.analysis_results['clinical_biomarkers'] = self.analyze_clinical_biomarkers(transcripts)
            progress_bar.update(1)
            
            # Generate executive summary
            self.analysis_results['executive_summary'] = self._generate_executive_summary()
            
            logger.info("SOTA analysis pipeline completed successfully")
            return self.analysis_results
            
        finally:
            progress_bar.close()
    
    def _generate_executive_summary(self) -> Dict[str, Any]:
        """Generate executive summary of all analyses."""
        summary = {
            'key_findings': [],
            'clinical_priorities': [],
            'therapeutic_opportunities': [],
            'recommended_actions': []
        }
        
        # Extract key findings from each analysis
        if 'drug_gene_interactions' in self.analysis_results:
            drug_analysis = self.analysis_results['drug_gene_interactions']
            if drug_analysis['high_score_targets'] > 0:
                summary['key_findings'].append(f"{drug_analysis['high_score_targets']} high-priority drug targets identified")
                summary['therapeutic_opportunities'].append("Precision medicine targeting of high-score drug-gene interactions")
        
        if 'pathway_enrichment' in self.analysis_results:
            pathway_analysis = self.analysis_results['pathway_enrichment']
            if pathway_analysis['total_pathways'] > 0:
                summary['key_findings'].append(f"{pathway_analysis['total_pathways']} altered pathways detected")
                summary['clinical_priorities'].append("Pathway-targeted therapeutic intervention")
        
        if 'clinical_biomarkers' in self.analysis_results:
            biomarker_analysis = self.analysis_results['clinical_biomarkers']
            high_potential = biomarker_analysis['biomarker_categories']['high_potential']
            if high_potential > 0:
                summary['key_findings'].append(f"{high_potential} high-potential biomarker candidates")
                summary['recommended_actions'].append("Initiate clinical validation studies for top biomarker candidates")
        
        # Default recommendations
        if not summary['recommended_actions']:
            summary['recommended_actions'] = [
                "Expand transcript dataset for more comprehensive analysis",
                "Implement targeted sequencing for identified genes",
                "Consider multi-omics integration for enhanced insights"
            ]
        
        return summary
    
    def save_report(self, output_path: Path, format: str = 'json') -> None:
        """
        Save analysis report to file.
        
        Args:
            output_path: Path to save report
            format: Output format ('json' or 'txt')
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        if format == 'json':
            with open(output_path, 'w') as f:
                json.dump(self.analysis_results, f, indent=2, default=str)
        elif format == 'txt':
            self._generate_text_report(output_path)
        
        logger.info(f"Report saved to {output_path}")
    
    def _generate_text_report(self, output_path: Path) -> None:
        """Generate human-readable text report."""
        with open(output_path, 'w') as f:
            f.write("MEDIABASE SOTA ANALYSIS REPORT\n")
            f.write("=" * 50 + "\n\n")
            
            # Write metadata
            metadata = self.analysis_results.get('analysis_metadata', {})
            f.write(f"Analysis Date: {metadata.get('timestamp', 'Unknown')}\n")
            f.write(f"Database: {metadata.get('database', 'Unknown')}\n")
            f.write(f"Transcripts Analyzed: {metadata.get('transcript_count', 0)}\n\n")
            
            # Write executive summary
            if 'executive_summary' in self.analysis_results:
                summary = self.analysis_results['executive_summary']
                f.write("EXECUTIVE SUMMARY\n")
                f.write("-" * 20 + "\n")
                
                f.write("\nKey Findings:\n")
                for finding in summary.get('key_findings', []):
                    f.write(f"• {finding}\n")
                
                f.write("\nTherapeutic Opportunities:\n")
                for opportunity in summary.get('therapeutic_opportunities', []):
                    f.write(f"• {opportunity}\n")
                
                f.write("\nRecommended Actions:\n")
                for action in summary.get('recommended_actions', []):
                    f.write(f"• {action}\n")
                
                f.write("\n" + "=" * 50 + "\n")


def main():
    """Main entry point for SOTA analysis."""
    parser = argparse.ArgumentParser(description="Run SOTA analysis on cancer transcriptome data")
    
    parser.add_argument(
        '--patient-db',
        type=str,
        help='Patient database name for patient-specific analysis'
    )
    parser.add_argument(
        '--output',
        type=str,
        default='reports/sota_analysis',
        help='Output file path (without extension)'
    )
    parser.add_argument(
        '--format',
        choices=['json', 'txt', 'both'],
        default='both',
        help='Output format'
    )
    parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        default='INFO',
        help='Logging level'
    )
    
    args = parser.parse_args()
    
    # Setup logging
    logging.getLogger().setLevel(getattr(logging, args.log_level))
    
    # Database configuration
    db_config = {
        'host': os.getenv('MB_POSTGRES_HOST', 'localhost'),
        'port': int(os.getenv('MB_POSTGRES_PORT', '5435')),
        'dbname': 'mediabase',
        'user': os.getenv('MB_POSTGRES_USER', 'mbase_user'),
        'password': os.getenv('MB_POSTGRES_PASSWORD', 'mbase_secret')
    }
    
    try:
        # Initialize analyzer
        analyzer = SOTAAnalyzer(db_config)
        
        # Run analysis
        results = analyzer.run_complete_analysis(args.patient_db)
        
        # Save reports
        output_path = Path(args.output)
        
        if args.format in ['json', 'both']:
            analyzer.save_report(output_path.with_suffix('.json'), 'json')
        
        if args.format in ['txt', 'both']:
            analyzer.save_report(output_path.with_suffix('.txt'), 'txt')
        
        console.print("\n[bold green]SOTA analysis completed successfully![/bold green]")
        console.print(f"Reports saved to: {output_path}")
        
    except Exception as e:
        logger.error(f"SOTA analysis failed: {e}", exc_info=True)
        console.print(f"[bold red]Error:[/bold red] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()