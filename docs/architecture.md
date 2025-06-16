# MEDIABASE Architecture Documentation

## Overview

MEDIABASE is a comprehensive cancer transcriptomics database with advanced publication reference extraction and quality scoring capabilities. The architecture follows a modular ETL (Extract, Transform, Load) design with enhanced literature integration across all data sources.

## System Architecture

### High-Level Components

```
┌─────────────────────────────────────────────────────────────────┐
│                    MEDIABASE Architecture                      │
├─────────────────────────────────────────────────────────────────┤
│  API Layer          │  Clinical Interface  │  Analysis Tools   │
├─────────────────────────────────────────────────────────────────┤
│                Database Layer (PostgreSQL)                     │
│  ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐  │
│  │ cancer_transcript│ │ clinical_trials │ │ publications    │  │
│  │      _base       │ │     metadata    │ │    quality      │  │
│  └─────────────────┘ └─────────────────┘ └─────────────────┘  │
├─────────────────────────────────────────────────────────────────┤
│                     ETL Pipeline Layer                         │
│ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌─────────┐ │
│ │ Transcripts  │ │ Publications │ │ Clinical     │ │ Quality │ │
│ │ Processor    │ │ Extraction   │ │ Trials       │ │ Scoring │ │
│ └──────────────┘ └──────────────┘ └──────────────┘ └─────────┘ │
├─────────────────────────────────────────────────────────────────┤
│                   Data Sources Layer                           │
│ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────────┐ │
│ │GENCODE  │ │  GO     │ │Reactome │ │PharmGKB │ │ClinicalTrials│ │
│ │UniProt  │ │PubMed   │ │ChEMBL   │ │DrugHub  │ │     .gov    │ │
│ └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

## Enhanced Publication Reference Architecture

### Publication Enhancement System Components

#### 1. Multi-Source Publication Extraction
```
Data Sources → Publication Extractors → Quality Scoring → Database Integration

┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│ GO Evidence     │───→│ PMID Extractor  │───→│ Impact Scoring  │───→│ source_references│
│ Codes           │    │ (PMID:12345678) │    │ (0-100 scale)   │    │ JSONB Column    │
└─────────────────┘    └─────────────────┘    └─────────────────┘    └─────────────────┘

┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│ DrugCentral     │───→│ URL-based       │───→│ Relevance       │───→│ clinical_trials │
│ ACT_SOURCE_URL  │    │ PMID Extraction │    │ Assessment      │    │ JSONB Column    │
└─────────────────┘    └─────────────────┘    └─────────────────┘    └─────────────────┘

┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│ PharmGKB        │───→│ Clinical        │───→│ Quality Tier    │
│ Annotations     │    │ Evidence        │    │ Classification  │
└─────────────────┘    └─────────────────┘    └─────────────────┘

┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│ ClinicalTrials  │───→│ Trial Metadata  │───→│ Journal Impact  │
│ .gov API        │    │ & Publications  │    │ Factor Database │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

#### 2. Publication Quality Scoring System
```
Multi-Factor Scoring Algorithm (0-100 scale):

Base Score (10) +
Citation Score (0-35) +
Journal Impact (0-25) +
Recency Score (0-15) +
Evidence Type (0-15) +
Quality Indicators (0-10) = Total Impact Score

Context-Aware Relevance Assessment:
Gene Match (0-30) +
Disease Match (0-25) +
Drug Match (0-20) +
Evidence Type (0-15) +
Source Database (0-10) = Relevance Score
```

## ETL Pipeline Architecture

### Enhanced ETL Processors

#### 1. Base Processor Pattern
All ETL processors inherit from `BaseProcessor` with enhanced capabilities:

```python
class BaseProcessor:
    - Database connection management
    - Cache management with TTL
    - Download utilities with compression
    - Batch processing capabilities
    - Error handling with specialized exceptions
    - Publication reference extraction utilities
```

#### 2. Publication-Enhanced Processors

**GO Terms Processor** (`go_terms.py`)
- **Enhanced**: PMID extraction from evidence codes (`PMID:12345678`)
- Extracts 10,000+ literature references from GO annotations
- Integrates evidence-based publication linking
- Quality scoring for GO-based evidence

**Drug Processor** (`drugs.py`)
- **Enhanced**: URL-based PMID extraction from DrugCentral
- Fixed column mapping for ACT_SOURCE_URL and MOA_SOURCE_URL
- ChEMBL publications integration
- Literature support for drug-target interactions

**PharmGKB Processor** (`pharmgkb_annotations.py`)
- **Enhanced**: Clinical annotation PMID integration
- Variant annotation literature references
- Evidence-level publication linking (1A-4 scoring)
- Clinical significance categorization

**Clinical Trials Processor** (`clinical_trials.py`) - **NEW**
- ClinicalTrials.gov API integration
- Rate-limited API access (1 req/sec)
- Trial metadata extraction (phases, status, sponsors)
- Publication reference extraction from trial documentation
- Cancer-focused filtering

**Publications Processor** (`publications.py`)
- **Enhanced**: Multi-factor quality scoring system
- Context-aware relevance assessment
- Journal impact factor integration (21+ journals)
- Quality tier classification (exceptional → minimal)
- Intelligent publication ranking

### Publication Reference Data Flow

```
┌─────────────────┐
│ Data Source     │
│ (GO, Drugs,     │
│ PharmGKB, etc.) │
└─────────┬───────┘
          │
          v
┌─────────────────┐
│ Pattern         │
│ Recognition     │
│ (PMIDs, DOIs,   │
│ Trial IDs)      │
└─────────┬───────┘
          │
          v
┌─────────────────┐
│ Reference       │
│ Extraction      │
│ & Validation    │
└─────────┬───────┘
          │
          v
┌─────────────────┐
│ Quality         │
│ Scoring &       │
│ Enhancement     │
└─────────┬───────┘
          │
          v
┌─────────────────┐
│ Database        │
│ Integration     │
│ (source_        │
│ references)     │
└─────────────────┘
```

## Database Architecture

### Enhanced Schema Design

#### Core Table: `cancer_transcript_base`
- **27 columns** with comprehensive publication integration
- **clinical_trials** JSONB column for trial metadata
- **source_references** JSONB column with quality scoring
- Optimized GIN indexes for publication queries

#### Publication Reference Schema
```json
{
  "source_references": {
    "publications": [
      {
        "pmid": "33961781",
        "title": "Study title",
        "journal": "Nature",
        "year": 2023,
        "impact_score": 85.2,
        "relevance_score": 78.9,
        "quality_tier": "exceptional",
        "quality_indicators": ["high_impact_journal", "recent", "highly_cited"]
      }
    ],
    "go_terms": [...],
    "drugs": [...],
    "pharmgkb": [...],
    "clinical_trials": [...]
  }
}
```

#### Clinical Trials Schema
```json
{
  "clinical_trials": {
    "summary": {
      "total_trials": 5,
      "phases": ["Phase 1", "Phase 2"],
      "statuses": ["COMPLETED", "ACTIVE"],
      "recent_trials": 3,
      "active_trials": 2
    },
    "trials": [
      {
        "nct_id": "NCT03123456",
        "title": "Trial title",
        "phase": "Phase 2",
        "status": "COMPLETED",
        "conditions": ["Cancer"],
        "start_date": "2020-03-15",
        "lead_sponsor": "Institution"
      }
    ]
  }
}
```

### Database Indexes for Publication Queries
```sql
-- Publication-focused indexes
CREATE INDEX idx_source_references ON cancer_transcript_base USING GIN(source_references);
CREATE INDEX idx_clinical_trials ON cancer_transcript_base USING GIN(clinical_trials);
CREATE INDEX idx_pmid_extraction ON cancer_transcript_base USING GIN((source_references->'publications'));
CREATE INDEX idx_clinical_trial_pmids ON cancer_transcript_base USING GIN((source_references->'clinical_trials'));
```

## Publication Quality Scoring System

### Multi-Factor Impact Scoring Algorithm

#### Impact Score Components (0-100 scale)
1. **Base Score**: 10 points (for having a publication)
2. **Citation Score**: 0-35 points (logarithmic scaling of citation count)
3. **Journal Impact**: 0-25 points (based on impact factor database)
4. **Recency Score**: 0-15 points (newer publications favored)
5. **Evidence Type**: 0-15 points (clinical trials > experimental > reviews)
6. **Quality Indicators**: 0-10 points (high-impact journal bonus)

#### Context-Aware Relevance Assessment
1. **Gene Symbol Match**: 0-30 points (title > abstract > keywords)
2. **Disease Relevance**: 0-25 points (cancer context matching)
3. **Drug Relevance**: 0-20 points (therapeutic context)
4. **Evidence Type**: 0-15 points (clinical > experimental)
5. **Source Database**: 0-10 points (ClinicalTrials.gov > ChEMBL > PharmGKB)

#### Quality Tier Classification
- **Exceptional** (80-100): High-impact, recent, highly cited
- **High** (60-79): Strong evidence with good impact
- **Moderate** (40-59): Reasonable quality evidence
- **Basic** (20-39): Limited but valid evidence
- **Minimal** (0-19): Weak evidence

### Journal Impact Factor Database
Integrated impact factors for 21+ major journals:
- Nature: 42.8
- NEJM: 70.7
- Science: 41.8
- Cell: 38.0
- Lancet: 60.4
- And 16+ more journals

## API and Query Architecture

### Publication-Enhanced Query Capabilities

#### New Query Types
1. **Clinical Trial Queries**: Find trials relevant to upregulated genes
2. **Evidence Strength Assessment**: Multi-source publication convergence
3. **Quality-Filtered Literature**: High-impact publication filtering
4. **Multi-Source Convergence**: Cross-database evidence correlation

#### Performance Optimizations
- GIN indexes for JSONB publication data
- Batch processing for quality scoring
- Efficient pattern matching for identifier extraction
- Smart caching for publication metadata

## Patient Copy Architecture

### Database Duplication for Patient Analysis
- **Complete schema preservation** with all publication enhancements
- **Patient-specific expression** overlay on reference database
- **Publication context** maintained for personalized analysis
- **Clinical trial relevance** assessment for patient genes

## Error Handling and Monitoring

### Publication-Specific Error Handling
- **API Rate Limiting**: Handles ClinicalTrials.gov rate limits
- **Pattern Validation**: Ensures extracted PMIDs are valid
- **Quality Score Validation**: Prevents invalid scoring data
- **Cross-Reference Validation**: Maintains referential integrity

### Monitoring and Logging
- **Publication Extraction Statistics**: Track success rates per data source
- **Quality Score Distribution**: Monitor scoring algorithm performance
- **API Usage Tracking**: Monitor external API consumption
- **Database Performance**: Track query performance for publication data

## Scalability and Performance

### Publication System Scalability
- **Batch Processing**: Process publications in configurable batch sizes
- **Caching Strategy**: Smart caching for publication metadata
- **Index Optimization**: GIN indexes for efficient JSON queries
- **API Management**: Rate limiting for sustainable external API usage

### Performance Metrics
- **10,000+ GO literature references** processed efficiently
- **90%+ improvement** in publication reference extraction
- **Multi-database integration** with consistent performance
- **Quality scoring** for 100+ publications per second

## Future Architecture Considerations

### Planned Enhancements
1. **Real-time Publication Updates**: Live feeds from PubMed
2. **Advanced NLP**: Semantic analysis of publication content
3. **Citation Network Analysis**: Publication relationship mapping
4. **Clinical Decision Support**: AI-powered publication recommendations

### Integration Points
- **LLM Integration**: JSON output optimized for AI processing
- **Clinical Workflow**: Integration with EHR systems
- **Research Tools**: API endpoints for external research platforms
- **Visualization**: Publication network and quality visualization tools

## Security and Data Privacy

### Publication Data Security
- **No Personal Data**: Only public scientific literature
- **API Key Management**: Secure storage of external API credentials
- **Rate Limiting**: Prevents abuse of external APIs
- **Data Validation**: Ensures data integrity throughout pipeline

This architecture supports MEDIABASE's mission to become a **literature-driven cancer research platform** with comprehensive publication integration, quality assessment, and clinical trial correlation capabilities.