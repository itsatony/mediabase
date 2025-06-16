# Comprehensive Evidence Scoring Framework for MEDIABASE

## Overview

The Evidence Scoring Framework provides a unified, multi-dimensional approach to evaluating drug-gene interactions for cancer research. It integrates evidence from multiple data sources and generates interpretable scores (0-100 scale) with confidence intervals and quality metrics.

## Table of Contents

1. [Framework Architecture](#framework-architecture)
2. [Evidence Types and Sources](#evidence-types-and-sources)
3. [Scoring Methodology](#scoring-methodology)
4. [Use Case Optimization](#use-case-optimization)
5. [Quality Metrics](#quality-metrics)
6. [Implementation Guide](#implementation-guide)
7. [API Reference](#api-reference)
8. [Validation and Analytics](#validation-and-analytics)

## Framework Architecture

### Core Components

```
┌─────────────────────────────────────────────────────────┐
│                Evidence Collection                       │
├─────────────────────────────────────────────────────────┤
│ • DrugCentral    • ChEMBL           • PharmGKB         │
│ • Drug Repurpos. • ClinicalTrials   • Publications     │
│ • GO Terms       • Pathways         • Safety Data      │
└─────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────┐
│               Evidence Processing                        │
├─────────────────────────────────────────────────────────┤
│ • Source reliability weighting                          │
│ • Evidence age decay factors                            │
│ • Cross-validation between sources                      │
│ • Quality assessment metrics                            │
└─────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────┐
│              Multi-Dimensional Scoring                  │
├─────────────────────────────────────────────────────────┤
│ Clinical (0-30)  │ Mechanistic (0-25) │ Publication (0-20)│
│ Genomic (0-15)   │ Safety (0-10)      │                  │
└─────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────┐
│               Use Case Optimization                      │
├─────────────────────────────────────────────────────────┤
│ • Drug Repurposing    • Biomarker Discovery            │
│ • Pathway Analysis    • Therapeutic Targeting          │
└─────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────┐
│           Final Score + Confidence Intervals            │
├─────────────────────────────────────────────────────────┤
│ Overall Score: 0-100                                    │
│ Confidence: [Lower, Upper]                              │
│ Quality Metrics + Recommendations                       │
└─────────────────────────────────────────────────────────┘
```

### Data Flow

1. **Evidence Extraction**: Systematically extract evidence from existing MEDIABASE data
2. **Source Weighting**: Apply reliability weights based on data source quality
3. **Age Decay**: Apply temporal decay factors for evidence recency
4. **Component Scoring**: Calculate scores for each evidence dimension
5. **Use Case Weighting**: Optimize scores for specific research applications
6. **Confidence Calculation**: Generate confidence intervals and quality metrics
7. **Recommendation Generation**: Provide actionable research recommendations

## Evidence Types and Sources

### 1. Clinical Evidence (0-30 points)

**Sources:**
- FDA/EMA drug approvals
- Clinical trial phases (ClinicalTrials.gov)
- Drug Repurposing Hub clinical data
- PharmGKB clinical annotations

**Scoring Factors:**
- Clinical trial phase (Phase 4: 90, Phase 3: 75, Phase 2: 60, Phase 1: 45)
- FDA approval status (+20 bonus)
- Number of completed trials
- Trial success rates
- Real-world evidence

**Example:**
```json
{
  "drug_id": "CHEMBL25",
  "clinical_evidence": {
    "max_phase": 4,
    "fda_approved": true,
    "completed_trials": 150,
    "score": 28.5
  }
}
```

### 2. Mechanistic Evidence (0-25 points)

**Sources:**
- Reactome pathway involvement
- PharmGKB pharmacokinetic/pharmacodynamic pathways
- Drug mechanism of action data
- Protein-protein interaction networks

**Scoring Factors:**
- Pathway participation breadth
- Mechanism of action clarity
- Protein interaction confidence
- Metabolic pathway involvement
- Cancer-relevant pathway bonus

**Example:**
```json
{
  "mechanistic_evidence": {
    "pathway_count": 12,
    "cancer_pathways": 8,
    "moa_clarity": "high",
    "protein_interactions": 45,
    "score": 22.3
  }
}
```

### 3. Publication Support (0-20 points)

**Sources:**
- PubMed literature
- Source-specific publication references
- Citation networks
- Review article mentions

**Scoring Factors:**
- Publication volume
- Citation quality and recency
- Review article inclusion
- Journal impact factors
- Cancer-specific literature bonus

**Example:**
```json
{
  "publication_evidence": {
    "total_publications": 234,
    "high_impact_publications": 45,
    "recent_publications": 78,
    "review_mentions": 12,
    "score": 18.7
  }
}
```

### 4. Genomic Evidence (0-15 points)

**Sources:**
- GO term annotations
- Genetic variant associations
- Cancer mutation databases
- Biomarker validation studies

**Scoring Factors:**
- GO term richness and cancer relevance
- Mutation association strength
- Biomarker validation status
- Functional annotation depth
- Cancer hallmark involvement

**Example:**
```json
{
  "genomic_evidence": {
    "go_terms": 67,
    "cancer_go_terms": 23,
    "mutation_associations": 8,
    "biomarker_status": "validated",
    "score": 13.2
  }
}
```

### 5. Safety Evidence (0-10 points)

**Sources:**
- Drug safety databases
- Adverse event reports
- Drug interaction databases
- Contraindication data

**Scoring Factors:**
- Approved drug safety profile
- Adverse event severity and frequency
- Drug-drug interaction potential
- Contraindication scope
- Black box warning penalties

**Example:**
```json
{
  "safety_evidence": {
    "approved_drugs": 3,
    "safety_warnings": 1,
    "interaction_potential": "moderate",
    "adverse_events": "mild",
    "score": 8.4
  }
}
```

## Scoring Methodology

### Component Score Calculation

Each evidence type is scored independently using domain-specific algorithms:

#### Clinical Evidence Scoring
```python
def score_clinical_evidence(evidence_items):
    base_score = map_clinical_phase_to_score(max_phase)
    approval_bonus = 20 if fda_approved else 0
    trial_bonus = min(completed_trials * 0.5, 10)
    
    return min(base_score + approval_bonus + trial_bonus, 30)
```

#### Mechanistic Evidence Scoring
```python
def score_mechanistic_evidence(evidence_items):
    pathway_score = min(pathway_count * 2, 15)
    cancer_bonus = cancer_pathway_count * 1.5
    clarity_bonus = moa_clarity_score * 5
    
    return min(pathway_score + cancer_bonus + clarity_bonus, 25)
```

### Overall Score Calculation

The overall score is calculated using use-case-specific weights:

```python
overall_score = sum(
    component_scores[component] * weights[use_case][component]
    for component in ['clinical', 'mechanistic', 'publication', 'genomic', 'safety']
)
```

### Confidence Interval Calculation

Confidence intervals account for:
- Evidence source reliability
- Sample size (number of evidence items)
- Cross-source consistency
- Evidence age and quality

```python
def calculate_confidence_interval(evidence_items, overall_score):
    base_margin = (1 - mean_confidence) * overall_score * 0.5
    variance_margin = confidence_variance * overall_score * 0.3
    sample_margin = (1 - sample_adjustment) * overall_score * 0.2
    
    total_margin = base_margin + variance_margin + sample_margin
    
    return (
        max(overall_score - total_margin, 0),
        min(overall_score + total_margin, 100)
    )
```

## Use Case Optimization

### Drug Repurposing (Clinical Focus)

**Weights:**
- Clinical Evidence: 40%
- Safety Evidence: 25%
- Mechanistic Evidence: 20%
- Publication Support: 10%
- Genomic Evidence: 5%

**Rationale:** Prioritizes existing clinical data and safety profiles for faster development.

**Example Output:**
```json
{
  "use_case": "drug_repurposing",
  "overall_score": 78.5,
  "confidence_interval": [72.1, 84.9],
  "component_breakdown": {
    "clinical": 28.5,
    "safety": 8.4,
    "mechanistic": 15.2,
    "publication": 4.3,
    "genomic": 2.1
  }
}
```

### Biomarker Discovery (Genomic Focus)

**Weights:**
- Genomic Evidence: 35%
- Clinical Evidence: 25%
- Publication Support: 20%
- Mechanistic Evidence: 15%
- Safety Evidence: 5%

**Rationale:** Emphasizes genomic associations and validation for biomarker development.

### Pathway Analysis (Mechanistic Focus)

**Weights:**
- Mechanistic Evidence: 40%
- Publication Support: 25%
- Genomic Evidence: 20%
- Clinical Evidence: 10%
- Safety Evidence: 5%

**Rationale:** Focuses on biological mechanisms and literature support for pathway studies.

### Therapeutic Targeting (Balanced Approach)

**Weights:**
- Clinical Evidence: 30%
- Mechanistic Evidence: 25%
- Genomic Evidence: 20%
- Publication Support: 15%
- Safety Evidence: 10%

**Rationale:** Balanced weighting for comprehensive therapeutic target evaluation.

## Quality Metrics

### Evidence Quality Assessment

**Metrics Calculated:**
- **Evidence Diversity Score**: Source variety (0-1)
- **Cross-Validation Score**: Inter-source consistency (0-1)
- **Temporal Relevance**: Evidence recency factor (0-1)
- **Confidence Level**: Overall reliability (0-1)

**Quality Indicators:**
- **High Quality** (≥0.8): Well-validated with diverse, consistent evidence
- **Medium Quality** (0.6-0.8): Good evidence base with minor gaps
- **Low Quality** (0.4-0.6): Limited evidence requiring validation
- **Very Low Quality** (<0.4): Insufficient evidence for confidence

### Age Decay Factors

Evidence is weighted by recency using linear decay:

```python
def calculate_age_factor(date_added, decay_days=1095):
    days_old = (datetime.now() - date_added).days
    return max(1.0 - (days_old / decay_days), 0.1)
```

## Implementation Guide

### 1. Database Schema Updates

Run the v0.1.8 migration to add evidence scoring support:

```bash
python scripts/manage_db.py --migrate v0.1.8
```

### 2. Configuration

Configure evidence scoring in `config/evidence_scoring.yml`:

```yaml
scoring:
  max_evidence_score: 100.0
  confidence_threshold: 0.3
  evidence_decay_days: 1095
  
use_case_weights:
  drug_repurposing:
    clinical: 0.40
    safety: 0.25
    # ... etc
```

### 3. Running Evidence Scoring

```bash
# Score all genes
python scripts/run_evidence_scoring.py

# Score specific genes
python scripts/run_evidence_scoring.py --genes EGFR,TP53,BRCA1

# Score for specific use case
python scripts/run_evidence_scoring.py --use-case drug_repurposing

# Force recalculation
python scripts/run_evidence_scoring.py --force

# Validate results
python scripts/run_evidence_scoring.py --validate

# Export results
python scripts/run_evidence_scoring.py --export json --output results.json
```

### 4. Integration with ETL Pipeline

Evidence scoring runs automatically after all data sources are processed:

```python
from etl.evidence_scoring import EvidenceScoringProcessor

# Initialize processor
config = load_config('config/evidence_scoring.yml')
processor = EvidenceScoringProcessor(config)

# Run scoring for all genes
processor.run()

# Score specific gene
score = processor.calculate_evidence_score('EGFR', use_case=UseCase.DRUG_REPURPOSING)
```

## API Reference

### Core Classes

#### EvidenceScoringProcessor

**Methods:**
- `calculate_evidence_score(gene_symbol, drug_id=None, use_case=UseCase.THERAPEUTIC_TARGET)`: Calculate comprehensive score
- `extract_evidence_from_existing_data(gene_symbol)`: Extract evidence items from database
- `update_evidence_scores_for_gene(gene_symbol)`: Update database with new scores
- `run()`: Process all genes in database

#### EvidenceItem

**Properties:**
- `source`: Data source name
- `evidence_type`: Type of evidence (clinical, mechanistic, etc.)
- `score`: Raw evidence score
- `confidence`: Source confidence level
- `weight`: Source reliability weight
- `metadata`: Additional evidence details

#### EvidenceScore

**Properties:**
- `overall_score`: Final weighted score (0-100)
- `confidence_interval`: Lower and upper bounds
- `component_scores`: Scores by evidence type
- `evidence_count`: Number of evidence items
- `evidence_quality`: Overall quality metric
- `use_case_scores`: Scores optimized for different use cases

### Database Schema

#### evidence_scoring_metadata Table

```sql
CREATE TABLE evidence_scoring_metadata (
    id SERIAL PRIMARY KEY,
    gene_symbol TEXT NOT NULL,
    drug_id TEXT,
    evidence_score JSONB NOT NULL,
    use_case TEXT NOT NULL DEFAULT 'therapeutic_target',
    confidence_lower FLOAT,
    confidence_upper FLOAT,
    evidence_count INTEGER,
    evidence_quality FLOAT,
    last_updated TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    scoring_version TEXT DEFAULT '1.0',
    UNIQUE(gene_symbol, drug_id, use_case)
);
```

#### Evidence Quality Metrics

```sql
ALTER TABLE cancer_transcript_base
ADD COLUMN evidence_quality_metrics JSONB DEFAULT jsonb_build_object(
    'overall_confidence', 0.0,
    'evidence_count', 0,
    'source_diversity', 0,
    'clinical_evidence_ratio', 0.0,
    'publication_support_ratio', 0.0,
    'last_assessment', CURRENT_TIMESTAMP
);
```

### Materialized Views

#### High-Confidence Drug Targets
```sql
SELECT * FROM high_confidence_drug_targets 
WHERE evidence_quality >= 0.7 
  AND overall_score >= 60.0
ORDER BY overall_score DESC;
```

#### Drug Repurposing Candidates
```sql
SELECT * FROM drug_repurposing_candidates 
WHERE repurposing_score >= 65.0
ORDER BY repurposing_score DESC;
```

#### Biomarker Discovery Targets
```sql
SELECT * FROM biomarker_discovery_targets 
WHERE biomarker_score >= 60.0
ORDER BY biomarker_score DESC;
```

### Utility Functions

#### Get Gene Evidence Summary
```sql
SELECT * FROM get_gene_evidence_summary('EGFR');
```

#### Compare Drugs for Gene
```sql
SELECT * FROM compare_drugs_for_gene('EGFR');
```

#### Refresh Analytics
```sql
SELECT refresh_evidence_scoring_analytics();
```

## Validation and Analytics

### Scoring Analytics Module

The `ScoringAnalyticsProcessor` provides comprehensive validation and analysis:

```python
from etl.scoring_analytics import ScoringAnalyticsProcessor

# Initialize analytics processor
analytics = ScoringAnalyticsProcessor(config)

# Analyze individual gene
gene_analysis = analytics.analyze_gene_evidence_profile('EGFR')

# Comparative analysis across genes
comparison = analytics.generate_comparative_analysis(['EGFR', 'TP53', 'BRCA1'])

# Export comprehensive report
analytics.export_analytics_report(gene_list, 'report.json')
```

### Quality Validation

**Validation Checks:**
- Evidence score consistency across use cases
- Confidence interval validity
- Source diversity requirements
- Temporal relevance assessment
- Cross-validation between data sources

**Quality Metrics:**
- **Evidence Coverage**: Percentage of genes with comprehensive evidence
- **Scoring Consistency**: Variance in scores across use cases
- **Source Reliability**: Weighted average of source confidence
- **Temporal Currency**: Average age of evidence items

### Performance Monitoring

**Key Performance Indicators:**
- Scoring completion rate
- Average evidence quality score
- High-confidence target identification rate
- Clinical readiness assessment accuracy
- Use case optimization effectiveness

## Best Practices

### 1. Data Quality Assurance

- Validate source data completeness before scoring
- Monitor evidence age distribution
- Track source reliability changes
- Implement cross-validation checks

### 2. Score Interpretation

- Always consider confidence intervals
- Review component score breakdown
- Assess evidence quality metrics
- Validate with domain expertise

### 3. Use Case Selection

- **Drug Repurposing**: Focus on clinical and safety evidence
- **Biomarker Discovery**: Emphasize genomic and validation data
- **Pathway Analysis**: Prioritize mechanistic understanding
- **Therapeutic Targeting**: Use balanced approach

### 4. Continuous Improvement

- Regular validation against known positive/negative controls
- Periodic weight optimization based on outcomes
- Integration of new evidence sources
- User feedback incorporation

## Troubleshooting

### Common Issues

**Low Evidence Scores:**
- Check data source completeness
- Verify gene symbol matching
- Review evidence extraction logic
- Validate source reference integrity

**High Score Variance:**
- Investigate evidence source conflicts
- Check temporal consistency
- Review cross-validation logic
- Assess source reliability weights

**Performance Issues:**
- Optimize database queries
- Implement batch processing
- Use appropriate indexes
- Monitor memory usage

### Debugging Tools

```python
# Debug evidence extraction
evidence_items = processor.extract_evidence_from_existing_data('EGFR')
for item in evidence_items:
    print(f"{item.source}: {item.score} (confidence: {item.confidence})")

# Debug component scoring
score = processor.calculate_evidence_score('EGFR')
print(f"Component scores: {score.component_scores}")
print(f"Confidence interval: {score.confidence_interval}")
```

## Future Enhancements

### Planned Features

1. **Machine Learning Integration**
   - Predictive scoring models
   - Evidence weight optimization
   - Outcome-based validation

2. **Real-Time Updates**
   - Streaming evidence integration
   - Dynamic score recalculation
   - Alert systems for score changes

3. **Advanced Analytics**
   - Network-based scoring
   - Multi-gene interaction effects
   - Combination therapy optimization

4. **External Data Integration**
   - Electronic health records
   - Real-world evidence databases
   - Patent and regulatory data

### Research Applications

The evidence scoring framework supports various cancer research applications:

- **Drug Discovery**: Prioritize targets and compounds
- **Clinical Trial Design**: Select biomarkers and endpoints
- **Personalized Medicine**: Identify patient-specific targets
- **Research Portfolio Management**: Optimize resource allocation
- **Regulatory Submissions**: Support evidence packages

---

*For additional support or questions about the evidence scoring framework, please refer to the MEDIABASE documentation or contact the development team.*