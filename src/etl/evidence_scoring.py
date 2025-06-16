"""Evidence Scoring Framework for MEDIABASE.

This module provides a comprehensive evidence scoring system that integrates
multiple data sources to generate confidence-based scores for drug-gene interactions,
biomarker discovery, and therapeutic targeting in cancer research.
"""

import json
import logging
import math
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any, Set
from dataclasses import dataclass
from enum import Enum

import numpy as np
from scipy import stats

from .base_processor import BaseProcessor
from ..utils.logging import get_progress_bar


class EvidenceType(Enum):
    """Types of evidence supported by the scoring system."""
    CLINICAL = "clinical"
    MECHANISTIC = "mechanistic"
    PUBLICATION = "publication"
    GENOMIC = "genomic"
    SAFETY = "safety"


class UseCase(Enum):
    """Use cases for evidence scoring optimization."""
    DRUG_REPURPOSING = "drug_repurposing"
    BIOMARKER_DISCOVERY = "biomarker_discovery"
    PATHWAY_ANALYSIS = "pathway_analysis"
    THERAPEUTIC_TARGETING = "therapeutic_targeting"


@dataclass
class EvidenceScore:
    """Individual evidence score with metadata."""
    score: float
    confidence: float
    source: str
    evidence_type: EvidenceType
    timestamp: datetime
    metadata: Dict[str, Any]


@dataclass
class CompositeScore:
    """Composite evidence score with breakdown."""
    overall_score: float
    component_scores: Dict[str, float]
    confidence_interval: Tuple[float, float]
    evidence_quality: float
    use_case: UseCase
    scoring_version: str


class EvidenceScoringProcessor(BaseProcessor):
    """Process and calculate evidence-based scores for genes and drugs."""

    def __init__(self, config: Dict[str, Any]) -> None:
        """Initialize the evidence scoring processor."""
        super().__init__(config)
        
        # Evidence type weights for different use cases
        self.use_case_weights = {
            UseCase.DRUG_REPURPOSING: {
                EvidenceType.CLINICAL: 0.35,
                EvidenceType.SAFETY: 0.25,
                EvidenceType.MECHANISTIC: 0.20,
                EvidenceType.PUBLICATION: 0.15,
                EvidenceType.GENOMIC: 0.05
            },
            UseCase.BIOMARKER_DISCOVERY: {
                EvidenceType.GENOMIC: 0.35,
                EvidenceType.CLINICAL: 0.25,
                EvidenceType.PUBLICATION: 0.20,
                EvidenceType.MECHANISTIC: 0.15,
                EvidenceType.SAFETY: 0.05
            },
            UseCase.PATHWAY_ANALYSIS: {
                EvidenceType.MECHANISTIC: 0.40,
                EvidenceType.PUBLICATION: 0.25,
                EvidenceType.GENOMIC: 0.20,
                EvidenceType.CLINICAL: 0.10,
                EvidenceType.SAFETY: 0.05
            },
            UseCase.THERAPEUTIC_TARGETING: {
                EvidenceType.CLINICAL: 0.30,
                EvidenceType.MECHANISTIC: 0.25,
                EvidenceType.GENOMIC: 0.20,
                EvidenceType.PUBLICATION: 0.15,
                EvidenceType.SAFETY: 0.10
            }
        }
        
        # Source reliability weights
        self.source_weights = {
            'fda': 0.95,
            'clinicaltrials_gov': 0.90,
            'chembl': 0.90,
            'pharmgkb': 0.85,
            'drugcentral': 0.80,
            'pubmed': 0.75,
            'drug_repurposing_hub': 0.75,
            'reactome': 0.70,
            'go': 0.65,
            'uniprot': 0.60
        }
        
        # Evidence decay parameters (3-year linear decay)
        self.evidence_half_life_days = 365 * 3
        
        # Score normalization parameters
        self.max_scores = {
            EvidenceType.CLINICAL: 30.0,
            EvidenceType.MECHANISTIC: 25.0,
            EvidenceType.PUBLICATION: 20.0,
            EvidenceType.GENOMIC: 15.0,
            EvidenceType.SAFETY: 10.0
        }
        
        # Required schema version
        self.required_schema_version = "0.1.8"

    def calculate_clinical_evidence_score(self, gene_data: Dict[str, Any]) -> EvidenceScore:
        """Calculate clinical evidence score from drug trials and approvals."""
        score = 0.0
        evidence_count = 0
        metadata = {"components": []}
        
        # PharmGKB clinical annotations
        pharmgkb_data = gene_data.get('drugs', {}).get('pharmgkb_data', {})
        if pharmgkb_data:
            clinical_annotations = pharmgkb_data.get('clinical_annotations', [])
            for annotation in clinical_annotations:
                evidence_level = annotation.get('evidence_level', '4')
                level_score = {
                    '1A': 8.0, '1B': 6.0, '2A': 4.0, 
                    '2B': 2.0, '3': 1.0, '4': 0.0
                }.get(evidence_level, 0.0)
                
                # Clinical significance bonus
                significance = annotation.get('clinical_significance', 'Unknown')
                significance_bonus = {
                    'High': 2.0, 'Moderate': 1.0, 'Low': 0.5, 'Unknown': 0.0
                }.get(significance, 0.0)
                
                annotation_score = level_score + significance_bonus
                score += annotation_score
                evidence_count += 1
                
                metadata["components"].append({
                    "type": "pharmgkb_clinical",
                    "score": annotation_score,
                    "evidence_level": evidence_level,
                    "significance": significance
                })
        
        # ChEMBL clinical phases
        chembl_data = gene_data.get('drugs', {}).get('chembl_data', {})
        if chembl_data:
            trials = chembl_data.get('clinical_trials', [])
            for trial in trials:
                phase = trial.get('phase', 0)
                phase_score = {4: 12.0, 3: 8.0, 2: 4.0, 1: 2.0, 0: 0.5}.get(phase, 0.0)
                score += phase_score
                evidence_count += 1
                
                metadata["components"].append({
                    "type": "chembl_trial",
                    "score": phase_score,
                    "phase": phase
                })
        
        # Drug Repurposing Hub clinical phases
        repurposing_data = gene_data.get('drugs', {}).get('repurposing_hub', {})
        if repurposing_data:
            phase = repurposing_data.get('clinical_phase', 'Preclinical')
            phase_score = {
                'Approved': 15.0, 'Phase 3': 10.0, 'Phase 2': 6.0,
                'Phase 1': 3.0, 'Preclinical': 1.0
            }.get(phase, 0.0)
            score += phase_score
            evidence_count += 1
            
            metadata["components"].append({
                "type": "repurposing_hub",
                "score": phase_score,
                "phase": phase
            })
        
        # PharmGKB Variant Annotations (Pharmacogenomics)
        pharmgkb_variants = gene_data.get('pharmgkb_variants', {})
        if pharmgkb_variants:
            variant_summary = pharmgkb_variants.get('summary', {})
            
            # High-impact variants with clinical actionability
            high_impact_variants = variant_summary.get('high_impact_variants', 0)
            clinical_actionable = variant_summary.get('clinical_actionable', 0)
            max_pharmgkb_score = variant_summary.get('max_pharmacogenomic_score', 0)
            
            # Calculate pharmacogenomic evidence score
            pharmacogenomic_score = 0.0
            
            # High-impact variants contribute to clinical evidence
            if high_impact_variants > 0:
                impact_score = min(8.0, high_impact_variants * 0.5)
                pharmacogenomic_score += impact_score
                evidence_count += high_impact_variants
            
            # Clinical actionability bonus
            if clinical_actionable > 0:
                actionability_score = min(6.0, clinical_actionable * 1.0)
                pharmacogenomic_score += actionability_score
                evidence_count += clinical_actionable
            
            # Maximum PharmGKB score bonus (indicates strong pharmacogenomic evidence)
            if max_pharmgkb_score >= 80:
                max_score_bonus = 4.0
            elif max_pharmgkb_score >= 70:
                max_score_bonus = 2.0
            elif max_pharmgkb_score >= 60:
                max_score_bonus = 1.0
            else:
                max_score_bonus = 0.0
            
            pharmacogenomic_score += max_score_bonus
            
            # CYP450 variants (important for drug metabolism)
            cyp450_variants = len(pharmgkb_variants.get('cyp450_variants', []))
            if cyp450_variants > 0:
                cyp_score = min(3.0, cyp450_variants * 0.3)
                pharmacogenomic_score += cyp_score
                evidence_count += cyp450_variants
            
            # Cancer-relevant variants
            cancer_variants = len(pharmgkb_variants.get('cancer_relevant_variants', []))
            if cancer_variants > 0:
                cancer_score = min(5.0, cancer_variants * 0.8)
                pharmacogenomic_score += cancer_score
                evidence_count += cancer_variants
            
            score += pharmacogenomic_score
            
            metadata["components"].append({
                "type": "pharmgkb_variants",
                "score": pharmacogenomic_score,
                "high_impact_variants": high_impact_variants,
                "clinical_actionable": clinical_actionable,
                "max_pharmgkb_score": max_pharmgkb_score,
                "cyp450_variants": cyp450_variants,
                "cancer_variants": cancer_variants
            })
        
        # Normalize to max score
        if evidence_count > 0:
            score = min(score, self.max_scores[EvidenceType.CLINICAL])
        
        confidence = min(0.9, evidence_count * 0.2) if evidence_count > 0 else 0.0
        
        return EvidenceScore(
            score=score,
            confidence=confidence,
            source="multiple_clinical",
            evidence_type=EvidenceType.CLINICAL,
            timestamp=datetime.now(),
            metadata=metadata
        )

    def calculate_mechanistic_evidence_score(self, gene_data: Dict[str, Any]) -> EvidenceScore:
        """Calculate mechanistic evidence score from pathway and target data."""
        score = 0.0
        evidence_count = 0
        metadata = {"components": []}
        
        # PharmGKB pathway involvement
        pharmgkb_pathways = gene_data.get('pharmgkb_pathways', {})
        if pharmgkb_pathways:
            pathway_count = len(pharmgkb_pathways)
            pathway_score = min(15.0, pathway_count * 2.0)
            score += pathway_score
            evidence_count += pathway_count
            
            # Cancer relevance bonus
            cancer_relevant_pathways = sum(
                1 for pathway in pharmgkb_pathways.values()
                if pathway.get('clinical_relevance', {}).get('cancer_relevance', False)
            )
            cancer_bonus = min(5.0, cancer_relevant_pathways * 1.0)
            score += cancer_bonus
            
            metadata["components"].append({
                "type": "pharmgkb_pathways",
                "score": pathway_score + cancer_bonus,
                "pathway_count": pathway_count,
                "cancer_relevant": cancer_relevant_pathways
            })
        
        # Reactome pathways
        pathways = gene_data.get('pathways', [])
        if pathways:
            pathway_score = min(8.0, len(pathways) * 0.5)
            score += pathway_score
            evidence_count += len(pathways)
            
            metadata["components"].append({
                "type": "reactome_pathways",
                "score": pathway_score,
                "pathway_count": len(pathways)
            })
        
        # DrugCentral target interactions
        drugs = gene_data.get('drugs', {})
        target_interactions = 0
        for drug_key, drug_data in drugs.items():
            if isinstance(drug_data, dict) and drug_data.get('source') == 'drugcentral':
                target_interactions += 1
        
        if target_interactions > 0:
            target_score = min(7.0, target_interactions * 1.5)
            score += target_score
            evidence_count += target_interactions
            
            metadata["components"].append({
                "type": "drugcentral_targets",
                "score": target_score,
                "interaction_count": target_interactions
            })
        
        # Normalize to max score
        score = min(score, self.max_scores[EvidenceType.MECHANISTIC])
        confidence = min(0.9, evidence_count * 0.15) if evidence_count > 0 else 0.0
        
        return EvidenceScore(
            score=score,
            confidence=confidence,
            source="multiple_mechanistic",
            evidence_type=EvidenceType.MECHANISTIC,
            timestamp=datetime.now(),
            metadata=metadata
        )

    def calculate_publication_evidence_score(self, gene_data: Dict[str, Any]) -> EvidenceScore:
        """Calculate publication evidence score from literature references."""
        score = 0.0
        evidence_count = 0
        metadata = {"components": []}
        
        # Source-specific publication references
        source_refs = gene_data.get('source_references', {})
        total_publications = 0
        
        for source, refs in source_refs.items():
            if refs and isinstance(refs, list):
                pub_count = len(refs)
                total_publications += pub_count
                
                # Weight by source reliability
                source_weight = self.source_weights.get(source, 0.5)
                weighted_score = pub_count * source_weight * 0.5
                score += weighted_score
                evidence_count += pub_count
                
                metadata["components"].append({
                    "type": f"{source}_publications",
                    "score": weighted_score,
                    "publication_count": pub_count,
                    "source_weight": source_weight
                })
        
        # General publications
        publications = gene_data.get('publications', [])
        if publications:
            pub_score = min(8.0, len(publications) * 0.3)
            score += pub_score
            evidence_count += len(publications)
            
            metadata["components"].append({
                "type": "general_publications",
                "score": pub_score,
                "publication_count": len(publications)
            })
        
        # Publication volume bonus (research interest indicator)
        if total_publications > 20:
            volume_bonus = min(3.0, (total_publications - 20) * 0.1)
            score += volume_bonus
            metadata["volume_bonus"] = volume_bonus
        
        # Normalize to max score
        score = min(score, self.max_scores[EvidenceType.PUBLICATION])
        confidence = min(0.8, evidence_count * 0.1) if evidence_count > 0 else 0.0
        
        return EvidenceScore(
            score=score,
            confidence=confidence,
            source="multiple_publications",
            evidence_type=EvidenceType.PUBLICATION,
            timestamp=datetime.now(),
            metadata=metadata
        )

    def calculate_genomic_evidence_score(self, gene_data: Dict[str, Any]) -> EvidenceScore:
        """Calculate genomic evidence score from GO terms and gene features."""
        score = 0.0
        evidence_count = 0
        metadata = {"components": []}
        
        # GO terms analysis
        go_terms = gene_data.get('go_terms', {})
        cancer_relevant_terms = 0
        
        # Cancer-relevant GO term keywords
        cancer_keywords = {
            'apoptosis', 'cell death', 'tumor', 'cancer', 'oncogene', 'tumor suppressor',
            'cell cycle', 'DNA repair', 'metastasis', 'proliferation', 'growth factor',
            'angiogenesis', 'invasion', 'migration', 'transformation'
        }
        
        # Group GO terms by aspect
        go_by_aspect = defaultdict(list)
        for go_id, go_data in go_terms.items():
            if isinstance(go_data, dict):
                aspect = go_data.get('aspect', 'unknown')
                go_by_aspect[aspect].append(go_data)
        
        for aspect, terms in go_by_aspect.items():
            if terms:
                aspect_score = min(3.0, len(terms) * 0.2)
                score += aspect_score
                evidence_count += len(terms)
                
                # Cancer relevance bonus
                for term_data in terms:
                    term_name = term_data.get('term', '').lower()
                    if any(keyword in term_name for keyword in cancer_keywords):
                        cancer_relevant_terms += 1
                        score += 0.5
                
                metadata["components"].append({
                    "type": f"go_{aspect}",
                    "score": aspect_score,
                    "term_count": len(terms)
                })
        
        # Cancer relevance bonus
        if cancer_relevant_terms > 0:
            cancer_bonus = min(4.0, cancer_relevant_terms * 0.8)
            score += cancer_bonus
            metadata["cancer_relevance_bonus"] = cancer_bonus
        
        # Gene features
        features = gene_data.get('features', {})
        if features:
            feature_score = min(2.0, len(features) * 0.3)
            score += feature_score
            evidence_count += len(features)
            
            metadata["components"].append({
                "type": "gene_features",
                "score": feature_score,
                "feature_count": len(features)
            })
        
        # Molecular functions
        mol_functions = gene_data.get('molecular_functions', [])
        if mol_functions:
            function_score = min(2.0, len(mol_functions) * 0.4)
            score += function_score
            evidence_count += len(mol_functions)
            
            metadata["components"].append({
                "type": "molecular_functions",
                "score": function_score,
                "function_count": len(mol_functions)
            })
        
        # Normalize to max score
        score = min(score, self.max_scores[EvidenceType.GENOMIC])
        confidence = min(0.8, evidence_count * 0.05) if evidence_count > 0 else 0.0
        
        return EvidenceScore(
            score=score,
            confidence=confidence,
            source="multiple_genomic",
            evidence_type=EvidenceType.GENOMIC,
            timestamp=datetime.now(),
            metadata=metadata
        )

    def calculate_safety_evidence_score(self, gene_data: Dict[str, Any]) -> EvidenceScore:
        """Calculate safety evidence score from adverse events and interactions."""
        score = 5.0  # Start with neutral safety score
        evidence_count = 0
        metadata = {"components": []}
        
        # PharmGKB toxicity annotations
        pharmgkb_data = gene_data.get('drugs', {}).get('pharmgkb_data', {})
        if pharmgkb_data:
            clinical_annotations = pharmgkb_data.get('clinical_annotations', [])
            toxicity_annotations = [
                ann for ann in clinical_annotations
                if 'toxicity' in ann.get('phenotype_category', '').lower()
            ]
            
            if toxicity_annotations:
                # Penalize for toxicity but give credit for known safety profile
                toxicity_penalty = len(toxicity_annotations) * 0.5
                safety_knowledge = len(toxicity_annotations) * 0.3
                score = score - toxicity_penalty + safety_knowledge
                evidence_count += len(toxicity_annotations)
                
                metadata["components"].append({
                    "type": "pharmgkb_toxicity",
                    "penalty": toxicity_penalty,
                    "knowledge_bonus": safety_knowledge,
                    "annotation_count": len(toxicity_annotations)
                })
        
        # FDA approval status (indicates safety profile)
        repurposing_data = gene_data.get('drugs', {}).get('repurposing_hub', {})
        if repurposing_data:
            phase = repurposing_data.get('clinical_phase', 'Preclinical')
            if phase == 'Approved':
                score += 3.0  # FDA approval indicates good safety profile
                evidence_count += 1
                metadata["fda_approval_bonus"] = 3.0
        
        # Drug interaction indicators
        drugs = gene_data.get('drugs', {})
        drug_count = len([d for d in drugs.values() if isinstance(d, dict)])
        if drug_count > 1:
            # Multiple drug interactions could indicate interaction risks
            interaction_risk = min(2.0, (drug_count - 1) * 0.2)
            score -= interaction_risk
            metadata["interaction_risk_penalty"] = interaction_risk
        
        # Ensure score stays within bounds
        score = max(0.0, min(score, self.max_scores[EvidenceType.SAFETY]))
        confidence = min(0.7, evidence_count * 0.3) if evidence_count > 0 else 0.3
        
        return EvidenceScore(
            score=score,
            confidence=confidence,
            source="multiple_safety",
            evidence_type=EvidenceType.SAFETY,
            timestamp=datetime.now(),
            metadata=metadata
        )

    def calculate_composite_score(self, evidence_scores: List[EvidenceScore], 
                                use_case: UseCase) -> CompositeScore:
        """Calculate composite score for a specific use case."""
        weights = self.use_case_weights[use_case]
        
        # Calculate weighted score
        total_score = 0.0
        component_scores = {}
        total_confidence = 0.0
        
        for evidence in evidence_scores:
            weight = weights.get(evidence.evidence_type, 0.0)
            weighted_score = evidence.score * weight
            total_score += weighted_score
            component_scores[evidence.evidence_type.value] = evidence.score
            total_confidence += evidence.confidence * weight
        
        # Calculate confidence interval using bootstrap method
        ci_lower, ci_upper = self._calculate_confidence_interval(
            evidence_scores, weights, total_score
        )
        
        # Calculate evidence quality
        evidence_quality = self._calculate_evidence_quality(evidence_scores)
        
        return CompositeScore(
            overall_score=round(total_score, 2),
            component_scores=component_scores,
            confidence_interval=(round(ci_lower, 2), round(ci_upper, 2)),
            evidence_quality=round(evidence_quality, 3),
            use_case=use_case,
            scoring_version="1.0"
        )

    def _calculate_confidence_interval(self, evidence_scores: List[EvidenceScore],
                                     weights: Dict[EvidenceType, float],
                                     base_score: float) -> Tuple[float, float]:
        """Calculate confidence interval using uncertainty propagation."""
        if not evidence_scores:
            return (0.0, 0.0)
        
        # Estimate uncertainty based on confidence levels
        variance = 0.0
        for evidence in evidence_scores:
            weight = weights.get(evidence.evidence_type, 0.0)
            # Uncertainty increases as confidence decreases
            uncertainty = (1.0 - evidence.confidence) * evidence.score * weight
            variance += uncertainty ** 2
        
        std_error = math.sqrt(variance)
        
        # 95% confidence interval (1.96 * standard error)
        margin = 1.96 * std_error
        
        ci_lower = max(0.0, base_score - margin)
        ci_upper = min(100.0, base_score + margin)
        
        return (ci_lower, ci_upper)

    def _calculate_evidence_quality(self, evidence_scores: List[EvidenceScore]) -> float:
        """Calculate overall evidence quality score."""
        if not evidence_scores:
            return 0.0
        
        # Weight by confidence and source reliability
        total_quality = 0.0
        total_weight = 0.0
        
        for evidence in evidence_scores:
            source_reliability = self.source_weights.get(
                evidence.source.split('_')[0], 0.5
            )
            quality = evidence.confidence * source_reliability
            weight = evidence.score if evidence.score > 0 else 0.1
            
            total_quality += quality * weight
            total_weight += weight
        
        return total_quality / total_weight if total_weight > 0 else 0.0

    def process_evidence_scoring(self, limit_records: Optional[int] = None) -> Dict[str, Any]:
        """Process evidence scoring for all genes in the database."""
        self.logger.info("Starting evidence scoring processing")
        
        # Get all genes with drug data
        query = """
        SELECT transcript_id, gene_symbol, drugs, pharmgkb_pathways, go_terms,
               pathways, source_references, features, molecular_functions, pharmgkb_variants
        FROM cancer_transcript_base 
        WHERE drugs IS NOT NULL AND drugs != '{}'
        """
        
        if limit_records:
            query += f" LIMIT {limit_records}"
        
        cursor = self.connection.cursor()
        cursor.execute(query)
        records = cursor.fetchall()
        
        self.logger.info(f"Processing evidence scores for {len(records)} genes")
        
        score_updates = []
        use_cases = [UseCase.DRUG_REPURPOSING, UseCase.BIOMARKER_DISCOVERY, 
                    UseCase.PATHWAY_ANALYSIS, UseCase.THERAPEUTIC_TARGETING]
        
        progress_bar = get_progress_bar(
            total=len(records),
            desc="Calculating evidence scores",
            module_name="evidence_scoring"
        )
        
        try:
            for record in records:
                progress_bar.update()
                
                transcript_id, gene_symbol, drugs, pharmgkb_pathways, go_terms, \
                pathways, source_references, features, molecular_functions, pharmgkb_variants = record
                
                # Prepare gene data structure
                gene_data = {
                    'drugs': drugs or {},
                    'pharmgkb_pathways': pharmgkb_pathways or {},
                    'go_terms': go_terms or {},
                    'pathways': pathways or [],
                    'publications': [],  # Publications not available in current schema
                    'source_references': source_references or {},
                    'features': features or {},
                    'molecular_functions': molecular_functions or [],
                    'pharmgkb_variants': pharmgkb_variants or {}
                }
                
                # Calculate individual evidence scores
                evidence_scores = [
                    self.calculate_clinical_evidence_score(gene_data),
                    self.calculate_mechanistic_evidence_score(gene_data),
                    self.calculate_publication_evidence_score(gene_data),
                    self.calculate_genomic_evidence_score(gene_data),
                    self.calculate_safety_evidence_score(gene_data)
                ]
                
                # Calculate composite scores for each use case
                use_case_scores = {}
                for use_case in use_cases:
                    composite = self.calculate_composite_score(evidence_scores, use_case)
                    use_case_scores[use_case.value] = {
                        'overall_score': composite.overall_score,
                        'component_scores': composite.component_scores,
                        'confidence_interval': composite.confidence_interval,
                        'evidence_quality': composite.evidence_quality
                    }
                
                # Prepare drug-specific scores
                drug_specific_scores = {}
                for drug_key, drug_data in gene_data['drugs'].items():
                    if isinstance(drug_data, dict):
                        drug_name = drug_data.get('name', drug_key)
                        # Use therapeutic targeting as default for drug-specific scoring
                        score = use_case_scores[UseCase.THERAPEUTIC_TARGETING.value]['overall_score']
                        drug_specific_scores[drug_key] = {
                            'drug_name': drug_name,
                            'score': score,
                            'source': drug_data.get('source', 'unknown')
                        }
                
                # Build comprehensive drug_scores structure
                new_drug_scores = {
                    'use_case_scores': use_case_scores,
                    'drug_specific_scores': drug_specific_scores,
                    'scoring_version': '1.0',
                    'last_updated': datetime.now().isoformat()
                }
                
                score_updates.append((transcript_id, json.dumps(new_drug_scores)))
        
        finally:
            progress_bar.close()
        
        # Batch update database
        self.logger.info(f"Updating drug scores for {len(score_updates)} genes")
        
        update_query = """
        UPDATE cancer_transcript_base 
        SET drug_scores = %s::jsonb
        WHERE transcript_id = %s
        """
        
        cursor.executemany(update_query, [(scores, tid) for tid, scores in score_updates])
        self.connection.commit()
        
        # Generate summary statistics
        stats = self._generate_scoring_statistics(score_updates)
        
        self.logger.info("Evidence scoring processing completed successfully")
        return stats

    def _generate_scoring_statistics(self, score_updates: List[Tuple[str, str]]) -> Dict[str, Any]:
        """Generate summary statistics for the scoring results."""
        if not score_updates:
            return {}
        
        all_scores = []
        use_case_stats = defaultdict(list)
        
        for _, scores_json in score_updates:
            scores = json.loads(scores_json)
            use_case_scores = scores.get('use_case_scores', {})
            
            for use_case, score_data in use_case_scores.items():
                overall_score = score_data.get('overall_score', 0)
                all_scores.append(overall_score)
                use_case_stats[use_case].append(overall_score)
        
        stats = {
            'total_genes_scored': len(score_updates),
            'overall_statistics': {
                'mean_score': np.mean(all_scores) if all_scores else 0,
                'median_score': np.median(all_scores) if all_scores else 0,
                'std_score': np.std(all_scores) if all_scores else 0,
                'min_score': np.min(all_scores) if all_scores else 0,
                'max_score': np.max(all_scores) if all_scores else 0
            },
            'use_case_statistics': {}
        }
        
        for use_case, scores in use_case_stats.items():
            if scores:
                stats['use_case_statistics'][use_case] = {
                    'mean_score': np.mean(scores),
                    'median_score': np.median(scores),
                    'high_confidence_genes': len([s for s in scores if s > 70]),
                    'medium_confidence_genes': len([s for s in scores if 40 <= s <= 70]),
                    'low_confidence_genes': len([s for s in scores if s < 40])
                }
        
        return stats

    def get_required_schema_version(self) -> str:
        """Return required schema version."""
        return self.required_schema_version

    def run(self):
        """Main processing method for ETL pipeline integration."""
        try:
            self.logger.info("Starting evidence scoring processing")
            
            # Connect to database if not already connected
            if not hasattr(self, 'connection') or not self.connection:
                from ..db.database import get_db_manager
                db_config = {
                    'host': self.config.get('host', 'localhost'),
                    'port': self.config.get('port', 5432),
                    'dbname': self.config.get('dbname', 'mediabase'),
                    'user': self.config.get('user', 'postgres'),
                    'password': self.config.get('password', 'postgres')
                }
                
                db_manager = get_db_manager(db_config)
                if not db_manager.connect():
                    raise Exception("Failed to connect to database")
                
                self.connection = db_manager.conn
            
            # Process evidence scoring for all genes
            stats = self.process_evidence_scoring()
            
            # Log results summary
            if stats:
                total_genes = stats.get('total_genes_scored', 0)
                overall_stats = stats.get('overall_statistics', {})
                mean_score = overall_stats.get('mean_score', 0)
                
                self.logger.info(f"Evidence scoring completed successfully:")
                self.logger.info(f"  - Total genes scored: {total_genes:,}")
                self.logger.info(f"  - Mean evidence score: {mean_score:.2f}")
                
                # Log use case statistics
                use_case_stats = stats.get('use_case_statistics', {})
                for use_case, case_stats in use_case_stats.items():
                    mean_score = case_stats.get('mean_score', 0)
                    high_conf = case_stats.get('high_confidence_genes', 0)
                    self.logger.info(f"  - {use_case}: mean={mean_score:.1f}, high_confidence={high_conf}")
            
        except Exception as e:
            self.logger.error(f"Evidence scoring failed: {e}")
            raise