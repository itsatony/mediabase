# Evidence Scoring Framework for MEDIABASE

## Overview

The Evidence Scoring Framework is a comprehensive system that transforms MEDIABASE from a data integration platform into an intelligent decision support system for cancer research. It integrates evidence from multiple pharmaceutical and genomic databases to generate confidence-based scores (0-100 scale) for drug-gene interactions, optimized for different research use cases.

## Motivation

Cancer research requires evidence-based prioritization of therapeutic targets, biomarkers, and drug repurposing candidates. Traditional approaches often rely on single data sources or manual literature review, leading to:

- **Incomplete evidence assessment**: Missing critical information from diverse sources
- **Subjective prioritization**: Inconsistent evaluation criteria across researchers
- **Scale limitations**: Manual review doesn't scale to genome-wide analysis
- **Use case misalignment**: Generic scores that don't match specific research goals

The Evidence Scoring Framework addresses these challenges by providing:
- **Multi-dimensional evidence integration** from clinical, mechanistic, genomic, and safety sources
- **Objective, reproducible scoring** with statistical confidence measures
- **Use case optimization** for drug repurposing, biomarker discovery, pathway analysis, and therapeutic targeting
- **Scalable automation** for genome-wide analysis

## Scoring Architecture

### Evidence Types and Weighting

The framework evaluates five types of evidence, weighted according to research use case:

#### 1. Clinical Evidence (0-30 points)
**Sources**: PharmGKB clinical annotations, PharmGKB variant annotations, ChEMBL trials, Drug Repurposing Hub phases

- **PharmGKB Clinical Annotations**:
  - 1A (High): 8.0 points + clinical significance bonus (0-2.0)
  - 1B (Moderate): 6.0 points + bonus
  - 2A (Moderate): 4.0 points + bonus
  - 2B (Weak): 2.0 points + bonus
  - 3 (Insufficient): 1.0 points + bonus
  - 4 (No effect): 0.0 points

- **PharmGKB Variant Annotations (Pharmacogenomics)**:
  - **High-Impact Variants** (score ≥ 70): Up to 8.0 points (0.5 × variant count)
  - **Clinical Actionable Variants**: Up to 6.0 points (1.0 × actionable count)
  - **Maximum Pharmacogenomic Score Bonus**:
    - Score ≥ 80: +4.0 points
    - Score ≥ 70: +2.0 points  
    - Score ≥ 60: +1.0 points
  - **CYP450 Variants**: Up to 3.0 points (0.3 × CYP450 variant count)
  - **Cancer-Relevant Variants**: Up to 5.0 points (0.8 × cancer variant count)

- **Clinical Trial Phases**:
  - Phase 4/Approved: 12-15 points
  - Phase 3: 8-10 points
  - Phase 2: 4-6 points
  - Phase 1: 2-3 points
  - Preclinical: 0.5-1.0 points

#### 2. Mechanistic Evidence (0-25 points)
**Sources**: PharmGKB pathways, Reactome pathways, DrugCentral targets
- **PharmGKB Pathways**: 2.0 points per pathway + cancer relevance bonus
- **Reactome Pathways**: 0.5 points per pathway
- **Drug-Target Interactions**: 1.5 points per validated interaction
- **Cancer Relevance Bonus**: Up to 5.0 points for cancer-specific pathways

#### 3. Publication Evidence (0-20 points)
**Sources**: Source-specific references, general publications
- **Source-weighted scoring**: Publication count × source reliability × 0.5
- **Source Reliability Weights**:
  - FDA: 0.95
  - ChEMBL: 0.90
  - PharmGKB: 0.85
  - DrugCentral: 0.80
  - PubMed: 0.75
- **Volume Bonus**: Additional points for high research interest (>20 publications)

#### 4. Genomic Evidence (0-15 points)
**Sources**: GO terms, gene features, molecular functions
- **GO Term Analysis**: 0.2 points per term by aspect (biological process, molecular function, cellular component)
- **Cancer Relevance Keywords**: Bonus for terms containing: apoptosis, cell cycle, DNA repair, tumor suppressor, oncogene, metastasis, etc.
- **Molecular Functions**: 0.4 points per function
- **Cancer Relevance Bonus**: Up to 4.0 points for cancer-related GO terms

#### 5. Safety Evidence (0-10 points)
**Sources**: PharmGKB toxicity annotations, FDA approval status
- **Base Safety Score**: 5.0 (neutral)
- **FDA Approval Bonus**: +3.0 (indicates established safety profile)
- **Toxicity Penalty**: -0.5 per toxicity annotation (balanced with knowledge bonus)
- **Drug Interaction Risk**: Penalty for multiple drug interactions

### Use Case Optimization

Different research applications require different evidence priorities:

#### Drug Repurposing (Clinical Safety Focus)
```
Clinical Evidence: 35%    # Proven safety and efficacy
Safety Evidence: 25%      # Critical for repurposing
Mechanistic: 20%         # Understanding of action
Publication: 15%         # Literature support
Genomic: 5%             # Background information
```

#### Biomarker Discovery (Genomic Focus)
```
Genomic Evidence: 35%    # Gene function and cancer relevance
Clinical Evidence: 25%   # Clinical validation
Publication: 20%        # Research support
Mechanistic: 15%        # Biological rationale
Safety: 5%             # Less critical for biomarkers
```

#### Pathway Analysis (Mechanistic Focus)
```
Mechanistic: 40%        # Pathway involvement critical
Publication: 25%        # Literature support
Genomic: 20%           # Functional context
Clinical: 10%          # Clinical relevance
Safety: 5%             # Background information
```

#### Therapeutic Targeting (Balanced Approach)
```
Clinical Evidence: 30%   # Druggability evidence
Mechanistic: 25%        # Target validation
Genomic: 20%           # Biological rationale
Publication: 15%        # Literature support
Safety: 10%            # Safety considerations
```

## Statistical Framework

### Confidence Intervals

The framework calculates 95% confidence intervals using uncertainty propagation:

```python
# Uncertainty calculation
variance = Σ[(1 - confidence_i) × score_i × weight_i]²
std_error = √variance
margin = 1.96 × std_error
CI = [max(0, score - margin), min(100, score + margin)]
```

### Evidence Quality Metrics

Quality scores combine source reliability and confidence:

```python
quality = Σ(confidence_i × source_reliability_i × weight_i) / Σ(weight_i)
```

Where:
- `confidence_i`: Individual evidence confidence (0-1)
- `source_reliability_i`: Source-specific reliability weight
- `weight_i`: Evidence score (higher scores have more influence)

### Source Reliability Weights

Based on data quality, validation standards, and update frequency:

| Source | Weight | Rationale |
|--------|--------|-----------|
| FDA | 0.95 | Rigorous regulatory approval process |
| ClinicalTrials.gov | 0.90 | Structured clinical data |
| ChEMBL | 0.90 | Curated bioactivity database |
| PharmGKB | 0.85 | Expert-curated pharmacogenomics |
| DrugCentral | 0.80 | Comprehensive drug information |
| Drug Repurposing Hub | 0.75 | Systematic drug collection |
| PubMed | 0.75 | Peer-reviewed literature |
| Reactome | 0.70 | Expert-curated pathways |
| GO | 0.65 | Community annotation effort |
| UniProt | 0.60 | Protein database |

## Implementation Details

### Core Components

#### 1. EvidenceScoringProcessor
Main processor class that orchestrates scoring:
- Connects to database and retrieves gene/drug data
- Calculates individual evidence scores
- Computes composite scores for each use case
- Updates database with results

#### 2. Evidence Score Classes
- `EvidenceScore`: Individual evidence with confidence and metadata
- `CompositeScore`: Use case-specific aggregate with confidence intervals
- `UseCase` enum: Drug repurposing, biomarker discovery, pathway analysis, therapeutic targeting
- `EvidenceType` enum: Clinical, mechanistic, publication, genomic, safety

#### 3. Scoring Methods
Each evidence type has a dedicated calculation method:
- `calculate_clinical_evidence_score()`
- `calculate_mechanistic_evidence_score()`
- `calculate_publication_evidence_score()`
- `calculate_genomic_evidence_score()`
- `calculate_safety_evidence_score()`

### Database Schema

The enhanced `drug_scores` JSONB structure:

```json
{
  "use_case_scores": {
    "drug_repurposing": {
      "overall_score": 78.5,
      "confidence_interval": [72.1, 84.9],
      "component_scores": {
        "clinical": 25.2,
        "safety": 8.7,
        "mechanistic": 15.8,
        "publication": 12.3,
        "genomic": 6.1
      },
      "evidence_quality": 0.83
    },
    "biomarker_discovery": { ... },
    "pathway_analysis": { ... },
    "therapeutic_targeting": { ... }
  },
  "drug_specific_scores": {
    "drug_id_1": {
      "drug_name": "Tamoxifen",
      "score": 78.5,
      "source": "pharmgkb"
    }
  },
  "scoring_version": "1.0",
  "last_updated": "2025-01-16T16:29:51.123Z"
}
```

## Usage Examples

### Command Line Interface

```bash
# Test scoring with limited records
python scripts/run_evidence_scoring.py --test --limit 10

# Run full scoring for all genes
python scripts/run_evidence_scoring.py --full

# View results
cat evidence_scoring_results.json
```

### Database Queries

```sql
-- High-confidence drug repurposing candidates
SELECT 
    gene_symbol,
    drug_scores->'use_case_scores'->'drug_repurposing'->>'overall_score' as score,
    drug_scores->'use_case_scores'->'drug_repurposing'->>'evidence_quality' as quality
FROM cancer_transcript_base 
WHERE (drug_scores->'use_case_scores'->'drug_repurposing'->>'overall_score')::float > 70
ORDER BY (drug_scores->'use_case_scores'->'drug_repurposing'->>'overall_score')::float DESC;

-- Biomarker candidates with high genomic evidence
SELECT 
    gene_symbol,
    drug_scores->'use_case_scores'->'biomarker_discovery'->'component_scores'->>'genomic' as genomic_score,
    drug_scores->'use_case_scores'->'biomarker_discovery'->>'overall_score' as total_score
FROM cancer_transcript_base 
WHERE (drug_scores->'use_case_scores'->'biomarker_discovery'->'component_scores'->>'genomic')::float > 10
ORDER BY (drug_scores->'use_case_scores'->'biomarker_discovery'->>'overall_score')::float DESC;

-- Confidence interval analysis
SELECT 
    gene_symbol,
    drug_scores->'use_case_scores'->'therapeutic_targeting'->>'overall_score' as score,
    drug_scores->'use_case_scores'->'therapeutic_targeting'->'confidence_interval'->0 as ci_lower,
    drug_scores->'use_case_scores'->'therapeutic_targeting'->'confidence_interval'->1 as ci_upper
FROM cancer_transcript_base 
WHERE drug_scores ? 'use_case_scores'
ORDER BY (drug_scores->'use_case_scores'->'therapeutic_targeting'->>'overall_score')::float DESC;
```

### Programmatic Access

```python
from src.etl.evidence_scoring import EvidenceScoringProcessor, UseCase

# Initialize processor
config = {'cache_dir': '/tmp/cache'}
processor = EvidenceScoringProcessor(config)

# Calculate scores for specific gene data
gene_data = {
    'drugs': {...},
    'pharmgkb_pathways': {...},
    'go_terms': {...}
}

# Get individual evidence scores
clinical_score = processor.calculate_clinical_evidence_score(gene_data)
mechanistic_score = processor.calculate_mechanistic_evidence_score(gene_data)

# Calculate composite score for drug repurposing
evidence_scores = [clinical_score, mechanistic_score, ...]
composite = processor.calculate_composite_score(evidence_scores, UseCase.DRUG_REPURPOSING)

print(f"Overall score: {composite.overall_score}")
print(f"Confidence interval: {composite.confidence_interval}")
print(f"Evidence quality: {composite.evidence_quality}")
```

## Interpretation Guidelines

### Score Ranges

- **High Confidence (70-100)**: Strong evidence across multiple sources
  - Well-validated targets with clinical evidence
  - Suitable for prioritization and further investigation
  - Lower risk for drug development

- **Medium Confidence (40-69)**: Moderate evidence with some gaps
  - Promising targets requiring additional validation
  - Good candidates for exploratory research
  - Moderate risk profile

- **Low Confidence (0-39)**: Limited or conflicting evidence
  - Early-stage targets requiring extensive validation
  - May indicate data gaps rather than poor targets
  - Higher risk but potentially high reward

### Evidence Quality Thresholds

- **High Quality (>0.8)**: Multiple high-reliability sources
- **Good Quality (0.6-0.8)**: Mix of reliable sources
- **Moderate Quality (0.4-0.6)**: Some reliable evidence
- **Low Quality (<0.4)**: Primarily low-reliability sources

### Confidence Interval Width

- **Narrow (<10 points)**: Consistent evidence across sources
- **Moderate (10-20 points)**: Some uncertainty in evidence
- **Wide (>20 points)**: High uncertainty, conflicting evidence

## Validation and Quality Control

### Cross-Validation

The framework includes several validation mechanisms:

1. **Source Consistency**: Compare scores across overlapping sources
2. **Evidence Triangulation**: Verify findings across evidence types
3. **Known Target Validation**: Test against established drug-target pairs
4. **Literature Validation**: Compare with expert curation

### Quality Metrics

- **Evidence Count**: Number of supporting evidence pieces
- **Source Diversity**: Number of different data sources
- **Clinical Evidence Ratio**: Proportion of clinical vs. preclinical evidence
- **Publication Support Ratio**: Literature coverage relative to clinical evidence

### Limitations and Considerations

1. **Data Completeness**: Scores reflect available data, not absolute target quality
2. **Source Bias**: Some databases may have therapeutic area biases
3. **Temporal Factors**: Evidence may be outdated or emerging
4. **Context Specificity**: Cancer type and patient population matter
5. **False Negatives**: Novel targets may score low due to limited data

## Future Enhancements

### Planned Improvements

1. **Dynamic Weighting**: Machine learning-based weight optimization
2. **Temporal Modeling**: Evidence age and trajectory analysis
3. **Cancer Type Specificity**: Subtype-specific scoring models
4. **Network Effects**: Protein-protein interaction influence
5. **Clinical Outcome Integration**: Real-world evidence incorporation

### Data Source Expansion

- **ClinVar**: Genetic variant clinical significance
- **COSMIC**: Cancer mutation database
- **TCGA**: Tumor genomics and outcomes
- **GDSC**: Drug sensitivity screening
- **DepMap**: Genetic dependency mapping

### Advanced Analytics

- **Ensemble Methods**: Multiple scoring algorithm combination
- **Uncertainty Quantification**: Bayesian confidence estimation
- **Causal Inference**: Evidence causality assessment
- **Bias Detection**: Systematic bias identification and correction

## Technical Reference

### Configuration Options

```python
config = {
    'cache_dir': '/tmp/mediabase/cache',
    'skip_scores': False,                    # Skip existing scores
    'force_download': False,                 # Force data re-download
    'evidence_half_life_days': 365 * 3,     # Evidence decay time
    'min_confidence_threshold': 0.1,        # Minimum confidence
    'max_scores': {                         # Score ceilings
        'clinical': 30.0,
        'mechanistic': 25.0,
        'publication': 20.0,
        'genomic': 15.0,
        'safety': 10.0
    }
}
```

### Performance Considerations

- **Database Indexing**: GIN indexes on JSONB columns for fast queries
- **Batch Processing**: Bulk updates for improved performance
- **Memory Management**: Streaming for large datasets
- **Caching**: Intermediate results caching for repeated analysis

### Error Handling

- **Data Validation**: Input data type and range checking
- **Missing Data**: Graceful handling of incomplete records
- **Database Errors**: Transaction rollback and retry logic
- **Logging**: Comprehensive logging for debugging and monitoring

## Contributing

### Adding New Evidence Types

1. Extend `EvidenceType` enum
2. Implement calculation method following naming convention
3. Update use case weights
4. Add unit tests and validation
5. Update documentation

### Modifying Scoring Algorithms

1. Create feature branch
2. Implement algorithm changes
3. Run validation against known targets
4. Document changes and rationale
5. Submit pull request with test results

### Data Source Integration

1. Assess data quality and reliability
2. Implement data processing pipeline
3. Determine evidence type classification
4. Calculate source reliability weight
5. Integrate into scoring framework

For questions or contributions, please refer to the main MEDIABASE documentation and contributing guidelines.