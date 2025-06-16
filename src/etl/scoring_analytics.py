"""Evidence Scoring Analytics and Validation Module for MEDIABASE.

This module provides comprehensive analytics and validation tools for the evidence
scoring system, including quality metrics, comparative analysis, and recommendations
for cancer research applications.
"""

import json
import statistics
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any, Union
from dataclasses import dataclass
from collections import defaultdict, Counter
import pandas as pd

from .base_processor import BaseProcessor, DatabaseError
from .evidence_scoring import UseCase, EvidenceType
from ..utils.logging import setup_logging


@dataclass
class ScoringAnalytics:
    """Analytics results for evidence scoring system."""
    gene_symbol: str
    total_evidence_items: int
    evidence_diversity_score: float
    clinical_strength: float
    mechanistic_depth: float
    publication_support: float
    genomic_relevance: float
    safety_profile: float
    cross_validation_score: float
    recommendation_confidence: float
    use_case_rankings: Dict[str, float]
    top_drugs: List[Dict[str, Any]]
    evidence_gaps: List[str]
    recommendations: List[str]


class ScoringAnalyticsProcessor(BaseProcessor):
    """Analytics processor for evidence scoring validation and insights."""
    
    def __init__(self, config: Dict[str, Any]) -> None:
        """Initialize scoring analytics processor."""
        super().__init__(config)
        
        # Set up logging
        self.logger = setup_logging(module_name=f"{__name__}.ScoringAnalyticsProcessor")
        
        # Configuration
        self.min_evidence_threshold = config.get('min_evidence_threshold', 3)
        self.high_confidence_threshold = config.get('high_confidence_threshold', 0.8)
        self.clinical_relevance_weight = config.get('clinical_relevance_weight', 0.4)
        
        # Cancer research priorities for recommendations
        self.cancer_research_priorities = {
            'immunotherapy_targets': ['CD19', 'CD20', 'CTLA4', 'PD1', 'PDL1', 'TIGIT'],
            'oncogenes': ['MYC', 'EGFR', 'HER2', 'RAS', 'PI3K', 'AKT', 'MTOR'],
            'tumor_suppressors': ['TP53', 'RB1', 'BRCA1', 'BRCA2', 'PTEN', 'APC'],
            'dna_repair': ['BRCA1', 'BRCA2', 'ATM', 'CHEK2', 'PALB2', 'RAD51'],
            'cell_cycle': ['CDK4', 'CDK6', 'CCND1', 'CCNE1', 'RB1', 'E2F1'],
            'apoptosis': ['BCL2', 'BAX', 'BAK1', 'CASP3', 'CASP9', 'APAF1'],
            'angiogenesis': ['VEGFA', 'VEGFR1', 'VEGFR2', 'FLT1', 'KDR', 'ANGPT1'],
            'metastasis': ['MMP9', 'MMP2', 'TIMP1', 'CDH1', 'SNAI1', 'TWIST1']
        }

    def analyze_gene_evidence_profile(self, gene_symbol: str) -> Optional[ScoringAnalytics]:
        """Analyze comprehensive evidence profile for a gene.
        
        Args:
            gene_symbol: Gene symbol to analyze
            
        Returns:
            ScoringAnalytics object with comprehensive analysis
        """
        if not self.ensure_connection() or not self.db_manager.cursor:
            return None
        
        try:
            # Get evidence scoring data
            self.db_manager.cursor.execute("""
                SELECT 
                    esm.evidence_score,
                    esm.evidence_count,
                    esm.evidence_quality,
                    esm.use_case,
                    esm.drug_id,
                    ctb.drugs,
                    ctb.pathways,
                    ctb.go_terms,
                    ctb.source_references
                FROM evidence_scoring_metadata esm
                JOIN cancer_transcript_base ctb ON esm.gene_symbol = ctb.gene_symbol
                WHERE esm.gene_symbol = %s
            """, (gene_symbol,))
            
            records = self.db_manager.cursor.fetchall()
            if not records:
                self.logger.warning(f"No evidence scoring data found for {gene_symbol}")
                return None
            
            # Aggregate data across use cases and drugs
            all_evidence_scores = []
            use_case_scores = {}
            drug_scores = defaultdict(list)
            total_evidence_items = 0
            
            for record in records:
                evidence_score, evidence_count, evidence_quality, use_case, drug_id = record[:5]
                drugs, pathways, go_terms, source_references = record[5:]
                
                all_evidence_scores.append(evidence_score)
                use_case_scores[use_case] = evidence_score.get('overall_score', 0)
                
                if drug_id:
                    drug_scores[drug_id].append(evidence_score.get('overall_score', 0))
                
                total_evidence_items = max(total_evidence_items, evidence_count or 0)
            
            # Calculate analytics metrics
            analytics = self._calculate_analytics_metrics(
                gene_symbol, all_evidence_scores, use_case_scores, 
                drug_scores, total_evidence_items, drugs, pathways, 
                go_terms, source_references
            )
            
            return analytics
            
        except Exception as e:
            self.logger.error(f"Error analyzing evidence profile for {gene_symbol}: {e}")
            return None

    def _calculate_analytics_metrics(
        self,
        gene_symbol: str,
        evidence_scores: List[Dict[str, Any]],
        use_case_scores: Dict[str, float],
        drug_scores: Dict[str, List[float]],
        total_evidence_items: int,
        drugs: Dict[str, Any],
        pathways: List[str],
        go_terms: Dict[str, Any],
        source_references: Dict[str, Any]
    ) -> ScoringAnalytics:
        """Calculate comprehensive analytics metrics."""
        
        # Evidence diversity score (0-1)
        evidence_sources = set()
        if drugs:
            evidence_sources.add('drugs')
        if pathways:
            evidence_sources.add('pathways')
        if go_terms:
            evidence_sources.add('go_terms')
        if source_references:
            evidence_sources.update(source_references.keys())
        
        evidence_diversity_score = min(len(evidence_sources) / 6.0, 1.0)  # Normalize to max 6 sources
        
        # Component strength scores from evidence data
        component_scores = {}
        for score_data in evidence_scores:
            components = score_data.get('component_scores', {})
            for component, value in components.items():
                if component not in component_scores:
                    component_scores[component] = []
                component_scores[component].append(value or 0)
        
        # Average component scores
        clinical_strength = statistics.mean(component_scores.get('clinical', [0])) / 30.0  # Normalize to 0-1
        mechanistic_depth = statistics.mean(component_scores.get('mechanistic', [0])) / 25.0
        publication_support = statistics.mean(component_scores.get('publication', [0])) / 20.0
        genomic_relevance = statistics.mean(component_scores.get('genomic', [0])) / 15.0
        safety_profile = statistics.mean(component_scores.get('safety', [0])) / 10.0
        
        # Cross-validation score based on consistency across evidence types
        all_scores = []
        for score_data in evidence_scores:
            all_scores.append(score_data.get('overall_score', 0))
        
        if len(all_scores) > 1:
            score_variance = statistics.variance(all_scores)
            cross_validation_score = max(0, 1.0 - (score_variance / 1000))  # Penalize high variance
        else:
            cross_validation_score = 0.5  # Neutral score for single evidence
        
        # Recommendation confidence based on multiple factors
        confidence_factors = [
            evidence_diversity_score,
            min(total_evidence_items / 10.0, 1.0),  # Evidence quantity
            clinical_strength,
            cross_validation_score
        ]
        recommendation_confidence = statistics.mean(confidence_factors)
        
        # Rank use cases by scores
        use_case_rankings = dict(sorted(use_case_scores.items(), key=lambda x: x[1], reverse=True))
        
        # Top drugs analysis
        top_drugs = []
        for drug_id, scores in drug_scores.items():
            avg_score = statistics.mean(scores)
            drug_info = drugs.get(drug_id, {}) if drugs else {}
            
            top_drugs.append({
                'drug_id': drug_id,
                'name': drug_info.get('name', 'Unknown'),
                'avg_score': round(avg_score, 2),
                'max_phase': drug_info.get('max_phase', 0),
                'mechanism': drug_info.get('mechanism', 'Unknown')
            })
        
        top_drugs.sort(key=lambda x: x['avg_score'], reverse=True)
        top_drugs = top_drugs[:5]  # Top 5 drugs
        
        # Identify evidence gaps
        evidence_gaps = self._identify_evidence_gaps(
            evidence_diversity_score, clinical_strength, mechanistic_depth,
            publication_support, genomic_relevance, safety_profile
        )
        
        # Generate recommendations
        recommendations = self._generate_recommendations(
            gene_symbol, use_case_rankings, evidence_gaps, 
            clinical_strength, recommendation_confidence
        )
        
        return ScoringAnalytics(
            gene_symbol=gene_symbol,
            total_evidence_items=total_evidence_items,
            evidence_diversity_score=round(evidence_diversity_score, 3),
            clinical_strength=round(clinical_strength, 3),
            mechanistic_depth=round(mechanistic_depth, 3),
            publication_support=round(publication_support, 3),
            genomic_relevance=round(genomic_relevance, 3),
            safety_profile=round(safety_profile, 3),
            cross_validation_score=round(cross_validation_score, 3),
            recommendation_confidence=round(recommendation_confidence, 3),
            use_case_rankings=use_case_rankings,
            top_drugs=top_drugs,
            evidence_gaps=evidence_gaps,
            recommendations=recommendations
        )

    def _identify_evidence_gaps(
        self,
        diversity: float,
        clinical: float,
        mechanistic: float,
        publication: float,
        genomic: float,
        safety: float
    ) -> List[str]:
        """Identify gaps in evidence coverage."""
        gaps = []
        
        if diversity < 0.5:
            gaps.append("Limited evidence source diversity - consider additional databases")
        
        if clinical < 0.3:
            gaps.append("Weak clinical evidence - search for clinical trials and FDA approvals")
        
        if mechanistic < 0.4:
            gaps.append("Limited mechanistic understanding - investigate pathway involvement")
        
        if publication < 0.3:
            gaps.append("Low publication support - expand literature search")
        
        if genomic < 0.2:
            gaps.append("Minimal genomic evidence - explore mutation and biomarker associations")
        
        if safety < 0.3:
            gaps.append("Limited safety data - investigate drug interaction profiles")
        
        return gaps

    def _generate_recommendations(
        self,
        gene_symbol: str,
        use_case_rankings: Dict[str, float],
        evidence_gaps: List[str],
        clinical_strength: float,
        confidence: float
    ) -> List[str]:
        """Generate research and therapeutic recommendations."""
        recommendations = []
        
        # Determine priority research area
        priority_areas = []
        for area, genes in self.cancer_research_priorities.items():
            if gene_symbol in genes:
                priority_areas.append(area)
        
        if priority_areas:
            recommendations.append(f"High priority for {', '.join(priority_areas)} research")
        
        # Best use case recommendation
        if use_case_rankings:
            best_use_case = max(use_case_rankings.items(), key=lambda x: x[1])
            if best_use_case[1] >= 60:
                recommendations.append(f"Strongly recommended for {best_use_case[0].replace('_', ' ')} (score: {best_use_case[1]:.1f})")
            elif best_use_case[1] >= 40:
                recommendations.append(f"Consider for {best_use_case[0].replace('_', ' ')} with additional validation")
        
        # Clinical development recommendations
        if clinical_strength >= 0.7:
            recommendations.append("Ready for clinical development - strong evidence base")
        elif clinical_strength >= 0.4:
            recommendations.append("Suitable for preclinical development - gather more clinical evidence")
        else:
            recommendations.append("Requires significant preclinical work before clinical development")
        
        # Research priority recommendations
        if confidence >= 0.8:
            recommendations.append("High confidence target - prioritize for resource allocation")
        elif confidence >= 0.6:
            recommendations.append("Moderate confidence - validate with additional evidence")
        else:
            recommendations.append("Low confidence - extensive validation required")
        
        # Evidence gap-specific recommendations
        if len(evidence_gaps) <= 2:
            recommendations.append("Well-characterized target with comprehensive evidence")
        elif len(evidence_gaps) <= 4:
            recommendations.append("Good evidence base - address specific gaps identified")
        else:
            recommendations.append("Requires comprehensive evidence gathering across multiple dimensions")
        
        return recommendations

    def generate_comparative_analysis(self, gene_list: List[str]) -> Dict[str, Any]:
        """Generate comparative analysis across multiple genes.
        
        Args:
            gene_list: List of gene symbols to compare
            
        Returns:
            Comprehensive comparative analysis
        """
        try:
            gene_analytics = {}
            
            # Analyze each gene
            for gene_symbol in gene_list:
                analytics = self.analyze_gene_evidence_profile(gene_symbol)
                if analytics:
                    gene_analytics[gene_symbol] = analytics
            
            if not gene_analytics:
                return {'error': 'No valid analytics data found for provided genes'}
            
            # Comparative metrics
            comparison = {
                'total_genes_analyzed': len(gene_analytics),
                'analysis_date': datetime.now().isoformat(),
                'gene_rankings': self._rank_genes_by_metrics(gene_analytics),
                'use_case_comparison': self._compare_use_cases(gene_analytics),
                'evidence_quality_distribution': self._analyze_evidence_quality(gene_analytics),
                'clinical_readiness_assessment': self._assess_clinical_readiness(gene_analytics),
                'research_priorities': self._prioritize_research_opportunities(gene_analytics),
                'portfolio_recommendations': self._generate_portfolio_recommendations(gene_analytics)
            }
            
            return comparison
            
        except Exception as e:
            self.logger.error(f"Error generating comparative analysis: {e}")
            return {'error': str(e)}

    def _rank_genes_by_metrics(self, gene_analytics: Dict[str, ScoringAnalytics]) -> Dict[str, List[Dict[str, Any]]]:
        """Rank genes by various metrics."""
        rankings = {}
        
        # Overall confidence ranking
        confidence_ranking = sorted(
            gene_analytics.items(),
            key=lambda x: x[1].recommendation_confidence,
            reverse=True
        )
        rankings['by_confidence'] = [
            {
                'gene': gene,
                'confidence': analytics.recommendation_confidence,
                'evidence_items': analytics.total_evidence_items
            }
            for gene, analytics in confidence_ranking[:20]  # Top 20
        ]
        
        # Clinical strength ranking
        clinical_ranking = sorted(
            gene_analytics.items(),
            key=lambda x: x[1].clinical_strength,
            reverse=True
        )
        rankings['by_clinical_strength'] = [
            {
                'gene': gene,
                'clinical_strength': analytics.clinical_strength,
                'top_drugs_count': len(analytics.top_drugs)
            }
            for gene, analytics in clinical_ranking[:20]
        ]
        
        # Evidence diversity ranking
        diversity_ranking = sorted(
            gene_analytics.items(),
            key=lambda x: x[1].evidence_diversity_score,
            reverse=True
        )
        rankings['by_evidence_diversity'] = [
            {
                'gene': gene,
                'diversity_score': analytics.evidence_diversity_score,
                'evidence_gaps_count': len(analytics.evidence_gaps)
            }
            for gene, analytics in diversity_ranking[:20]
        ]
        
        return rankings

    def _compare_use_cases(self, gene_analytics: Dict[str, ScoringAnalytics]) -> Dict[str, Any]:
        """Compare performance across different use cases."""
        use_case_data = defaultdict(list)
        
        for gene, analytics in gene_analytics.items():
            for use_case, score in analytics.use_case_rankings.items():
                use_case_data[use_case].append({
                    'gene': gene,
                    'score': score,
                    'confidence': analytics.recommendation_confidence
                })
        
        comparison = {}
        for use_case, data in use_case_data.items():
            # Sort by score
            sorted_data = sorted(data, key=lambda x: x['score'], reverse=True)
            
            scores = [item['score'] for item in data]
            comparison[use_case] = {
                'gene_count': len(data),
                'avg_score': round(statistics.mean(scores), 2),
                'std_score': round(statistics.stdev(scores) if len(scores) > 1 else 0, 2),
                'top_genes': sorted_data[:10],
                'score_distribution': {
                    'high (>70)': len([s for s in scores if s > 70]),
                    'medium (50-70)': len([s for s in scores if 50 <= s <= 70]),
                    'low (<50)': len([s for s in scores if s < 50])
                }
            }
        
        return comparison

    def _analyze_evidence_quality(self, gene_analytics: Dict[str, ScoringAnalytics]) -> Dict[str, Any]:
        """Analyze evidence quality distribution."""
        confidence_scores = [analytics.recommendation_confidence for analytics in gene_analytics.values()]
        diversity_scores = [analytics.evidence_diversity_score for analytics in gene_analytics.values()]
        evidence_counts = [analytics.total_evidence_items for analytics in gene_analytics.values()]
        
        return {
            'confidence_distribution': {
                'mean': round(statistics.mean(confidence_scores), 3),
                'median': round(statistics.median(confidence_scores), 3),
                'std': round(statistics.stdev(confidence_scores) if len(confidence_scores) > 1 else 0, 3),
                'high_confidence_count': len([c for c in confidence_scores if c >= 0.8]),
                'medium_confidence_count': len([c for c in confidence_scores if 0.5 <= c < 0.8]),
                'low_confidence_count': len([c for c in confidence_scores if c < 0.5])
            },
            'diversity_distribution': {
                'mean': round(statistics.mean(diversity_scores), 3),
                'median': round(statistics.median(diversity_scores), 3),
                'high_diversity_count': len([d for d in diversity_scores if d >= 0.7])
            },
            'evidence_volume': {
                'mean_evidence_items': round(statistics.mean(evidence_counts), 1),
                'median_evidence_items': round(statistics.median(evidence_counts), 1),
                'well_evidenced_count': len([e for e in evidence_counts if e >= 5])
            }
        }

    def _assess_clinical_readiness(self, gene_analytics: Dict[str, ScoringAnalytics]) -> Dict[str, List[str]]:
        """Assess clinical development readiness."""
        readiness_categories = {
            'ready_for_clinical': [],
            'ready_for_preclinical': [],
            'requires_basic_research': [],
            'insufficient_evidence': []
        }
        
        for gene, analytics in gene_analytics.items():
            clinical_score = analytics.clinical_strength
            confidence = analytics.recommendation_confidence
            evidence_count = analytics.total_evidence_items
            
            if clinical_score >= 0.7 and confidence >= 0.8 and evidence_count >= 5:
                readiness_categories['ready_for_clinical'].append(gene)
            elif clinical_score >= 0.4 and confidence >= 0.6 and evidence_count >= 3:
                readiness_categories['ready_for_preclinical'].append(gene)
            elif evidence_count >= 2:
                readiness_categories['requires_basic_research'].append(gene)
            else:
                readiness_categories['insufficient_evidence'].append(gene)
        
        return readiness_categories

    def _prioritize_research_opportunities(self, gene_analytics: Dict[str, ScoringAnalytics]) -> List[Dict[str, Any]]:
        """Identify and prioritize research opportunities."""
        opportunities = []
        
        for gene, analytics in gene_analytics.items():
            # Calculate opportunity score based on potential and evidence gaps
            potential_score = max(analytics.use_case_rankings.values()) if analytics.use_case_rankings else 0
            evidence_gap_penalty = len(analytics.evidence_gaps) * 5
            
            opportunity_score = potential_score - evidence_gap_penalty
            
            # Determine research type needed
            research_types = []
            if analytics.clinical_strength < 0.3:
                research_types.append('clinical_trials')
            if analytics.mechanistic_depth < 0.4:
                research_types.append('mechanism_studies')
            if analytics.publication_support < 0.3:
                research_types.append('literature_validation')
            if analytics.safety_profile < 0.3:
                research_types.append('safety_assessment')
            
            opportunities.append({
                'gene': gene,
                'opportunity_score': round(opportunity_score, 1),
                'research_types_needed': research_types,
                'evidence_gaps_count': len(analytics.evidence_gaps),
                'confidence': analytics.recommendation_confidence,
                'priority_areas': [area for area, genes in self.cancer_research_priorities.items() if gene in genes]
            })
        
        # Sort by opportunity score
        opportunities.sort(key=lambda x: x['opportunity_score'], reverse=True)
        
        return opportunities[:25]  # Top 25 opportunities

    def _generate_portfolio_recommendations(self, gene_analytics: Dict[str, ScoringAnalytics]) -> List[str]:
        """Generate overall portfolio recommendations."""
        recommendations = []
        
        total_genes = len(gene_analytics)
        high_confidence_genes = len([a for a in gene_analytics.values() if a.recommendation_confidence >= 0.8])
        clinical_ready_genes = len([a for a in gene_analytics.values() if a.clinical_strength >= 0.7])
        
        # Portfolio composition recommendations
        if high_confidence_genes / total_genes >= 0.3:
            recommendations.append("Strong portfolio with high proportion of confident targets")
        else:
            recommendations.append("Portfolio needs more high-confidence targets - focus on evidence gathering")
        
        if clinical_ready_genes / total_genes >= 0.2:
            recommendations.append("Good clinical pipeline potential - prioritize clinical development")
        else:
            recommendations.append("Limited clinical readiness - invest in preclinical development")
        
        # Use case balance recommendations
        use_case_strengths = defaultdict(int)
        for analytics in gene_analytics.values():
            if analytics.use_case_rankings:
                best_use_case = max(analytics.use_case_rankings.items(), key=lambda x: x[1])[0]
                use_case_strengths[best_use_case] += 1
        
        dominant_use_case = max(use_case_strengths.items(), key=lambda x: x[1]) if use_case_strengths else None
        if dominant_use_case and dominant_use_case[1] / total_genes > 0.5:
            recommendations.append(f"Portfolio heavily weighted toward {dominant_use_case[0]} - consider diversification")
        else:
            recommendations.append("Well-balanced portfolio across use cases")
        
        # Research priority recommendations
        priority_gene_count = len([
            gene for gene, analytics in gene_analytics.items()
            if any(gene in genes for genes in self.cancer_research_priorities.values())
        ])
        
        if priority_gene_count / total_genes >= 0.4:
            recommendations.append("Strong alignment with cancer research priorities")
        else:
            recommendations.append("Consider including more high-priority cancer research targets")
        
        return recommendations

    def export_analytics_report(self, gene_list: List[str], output_file: str) -> bool:
        """Export comprehensive analytics report."""
        try:
            # Generate comparative analysis
            analysis = self.generate_comparative_analysis(gene_list)
            
            if 'error' in analysis:
                self.logger.error(f"Analysis failed: {analysis['error']}")
                return False
            
            # Create comprehensive report
            report = {
                'report_metadata': {
                    'generated_date': datetime.now().isoformat(),
                    'gene_count': len(gene_list),
                    'genes_analyzed': gene_list,
                    'scoring_system_version': '1.0'
                },
                'executive_summary': {
                    'total_genes_analyzed': analysis['total_genes_analyzed'],
                    'clinical_readiness': analysis['clinical_readiness_assessment'],
                    'top_priorities': analysis['research_priorities'][:10],
                    'portfolio_recommendations': analysis['portfolio_recommendations']
                },
                'detailed_analysis': analysis,
                'individual_gene_profiles': {}
            }
            
            # Add individual gene profiles
            for gene_symbol in gene_list:
                gene_analytics = self.analyze_gene_evidence_profile(gene_symbol)
                if gene_analytics:
                    report['individual_gene_profiles'][gene_symbol] = {
                        'summary_metrics': {
                            'confidence': gene_analytics.recommendation_confidence,
                            'clinical_strength': gene_analytics.clinical_strength,
                            'evidence_diversity': gene_analytics.evidence_diversity_score,
                            'total_evidence': gene_analytics.total_evidence_items
                        },
                        'use_case_rankings': gene_analytics.use_case_rankings,
                        'top_drugs': gene_analytics.top_drugs,
                        'evidence_gaps': gene_analytics.evidence_gaps,
                        'recommendations': gene_analytics.recommendations
                    }
            
            # Write report to file
            with open(output_file, 'w') as f:
                json.dump(report, f, indent=2, default=str)
            
            self.logger.info(f"Analytics report exported to {output_file}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to export analytics report: {e}")
            return False