# ETL Pipeline Improvement Plan

## Current State Analysis

### Critical Issues Identified

1. **ID Mapping Strategy** - Currently weak and happens too late
2. **Evidence/Reference Tracking** - Poor integration of publication data  
3. **Cross-Database Joins** - Limited ID matching between sources
4. **Data Source Gaps** - Missing key clinical and cancer-specific sources
5. **Joining Sequence** - Suboptimal order reduces data integration quality

## Recommended Data Sources & Schema

### 1. Comprehensive ID Mapping Sources

#### NCBI Gene2Ensembl (PRIORITY 1)
**URL:** `https://ftp.ncbi.nlm.nih.gov/gene/DATA/gene2ensembl.gz`
**Purpose:** Authoritative gene ID mapping
**Sample Record:**
```tsv
tax_id  GeneID  Ensembl_gene_identifier  RNA_nucleotide_accession.version  Ensembl_rna_identifier  protein_accession.version  Ensembl_protein_identifier
9606    1       ENSG00000121410          NM_130786.3                      ENST00000263100         NP_570602.2               ENSP00000263100
```
**Integration:** Join on `Ensembl_gene_identifier` = our `gene_id`

#### HGNC Complete Dataset (PRIORITY 1)  
**URL:** `https://www.genenames.org/cgi-bin/download/custom?col=gd_hgnc_id&col=gd_app_sym&col=gd_aliases&col=gd_pub_ensembl_id&status=Approved&hgnc_dbtag=on&order_by=gd_app_sym_sort&format=text&submit=submit`
**Purpose:** Official gene symbols and aliases
**Sample Record:**
```tsv
hgnc_id symbol  alias_symbol    ensembl_gene_id
HGNC:5  A1BG    A1B,ABG,GAB     ENSG00000121410
```

#### RefSeq Complete (PRIORITY 2)
**URL:** `https://ftp.ncbi.nlm.nih.gov/refseq/H_sapiens/annotation/GRCh38_latest/refseq_identifiers/GRCh38_latest_genomic.fna.gz`
**Purpose:** RefSeq to Ensembl mapping

### 2. Enhanced Evidence Sources

#### ChEMBL Database (PRIORITY 1)
**URL:** `https://ftp.ebi.ac.uk/pub/databases/chembl/ChEMBLdb/latest/`
**Purpose:** Comprehensive drug-target data with clinical phases
**Sample Record:**
```json
{
  "molecule_chembl_id": "CHEMBL25",
  "pref_name": "ASPIRIN", 
  "target_chembl_id": "CHEMBL204",
  "target_pref_name": "Cyclooxygenase-1",
  "mechanism_of_action": "Cyclooxygenase inhibitor",
  "max_phase": 4,
  "disease_efficacy": [{"disease": "Pain", "phase": 4}]
}
```

#### ClinicalTrials.gov API (PRIORITY 1)
**URL:** `https://clinicaltrials.gov/api/`
**Purpose:** Clinical evidence for drug-gene interactions
**Sample Record:**
```json
{
  "nct_id": "NCT00000001",
  "study_title": "Aspirin in Cardiovascular Disease",
  "intervention": ["Aspirin"],
  "condition": ["Cardiovascular Disease"],
  "phase": "Phase 4",
  "status": "Completed",
  "genes_mentioned": ["PTGS1", "PTGS2"]
}
```

#### PubMed Central Cancer Collection (PRIORITY 2)
**URL:** `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pmc&term=cancer[filter]`
**Purpose:** Cancer-specific literature with full text
**Focus:** Papers mentioning our genes + cancer terms

### 3. Cancer-Specific Sources

#### COSMIC Database (PRIORITY 2)
**URL:** `https://cancer.sanger.ac.uk/cosmic/download`
**Purpose:** Cancer mutations and clinical significance
**Sample Record:**
```tsv
Gene_name  Transcript  CDS_mutation  AA_mutation  Tissue  Histology  
TP53      ENST00000269305  c.524G>A     p.R175H     lung    carcinoma
```

#### TCGA Pan-Cancer Atlas (PRIORITY 3)  
**Purpose:** Expression patterns in cancer samples
**Integration:** Expression fold-change validation

## Improved Pipeline Sequence

### Phase 1: Foundation & ID Mapping
1. **transcripts** (GENCODE GTF) - Base data
2. **comprehensive_id_mapping** (NEW) - Multi-source ID enrichment
   - NCBI Gene2Ensembl 
   - HGNC complete
   - RefSeq mapping
   - UniProt (existing)
3. **validation** (NEW) - Verify ID mapping coverage

### Phase 2: Functional Enrichment  
4. **go_terms** (Enhanced) - Leverage comprehensive IDs
5. **pathways** (Enhanced) - Cross-reference with GO terms
6. **products** (Enhanced) - Use GO molecular functions

### Phase 3: Clinical & Drug Data
7. **chembl_drugs** (Enhanced existing) - Clinical phases & mechanisms
8. **drugcentral_legacy** (Keep existing for compatibility)
9. **clinical_trials** (NEW) - ClinicalTrials.gov API integration

### Phase 4: Evidence & References
10. **publications** (Enhanced) - Target cancer literature 
11. **cosmic_variants** (NEW) - Cancer-specific mutations
12. **evidence_integration** (NEW) - Cross-module evidence scoring

## Implementation Priority

### Week 1: Critical ID Mapping
- [ ] Implement comprehensive_id_mapping module
- [ ] Add NCBI Gene2Ensembl source
- [ ] Add HGNC complete source  
- [ ] Enhance existing modules to use comprehensive IDs

### Week 2: Enhanced Evidence
- [ ] Upgrade ChEMBL integration with clinical phases
- [ ] Add ClinicalTrials.gov API module
- [ ] Enhance publications with cancer-focused searches

### Week 3: Cross-Module Integration
- [ ] Add evidence scoring across modules
- [ ] Implement pathway-drug association scoring
- [ ] Add GO term evidence quality integration

### Week 4: Documentation & Validation
- [ ] Document all data sources with schemas
- [ ] Add sample records to README
- [ ] Create data lineage documentation
- [ ] Validate SOTA analysis improvements

## Success Metrics

### ID Mapping Improvement
- **Target:** >95% gene symbol match rate (vs current ~60-70%)
- **Measure:** ID coverage across all modules

### Evidence Quality
- **Target:** >80% of drugs have clinical trial references
- **Measure:** References per drug/pathway/GO term

### Clinical Utility
- **Target:** SOTA analyses include clinical evidence scores
- **Measure:** Clinical recommendation confidence levels

## Technical Implementation Notes

### New Module Template
```python
class ComprehensiveIDMappingProcessor(BaseProcessor):
    """Multi-source ID mapping for optimal database joins."""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.sources = [
            NCBIGene2EnsemblSource(),
            HGNCCompleteSource(), 
            RefSeqMappingSource(),
            UniProtSource()  # existing
        ]
    
    def run(self):
        # Download all sources
        # Create comprehensive mapping table
        # Update all transcript records
        # Generate mapping quality report
```

### Evidence Integration Pattern
```python
class EvidenceIntegrator:
    """Cross-module evidence scoring and integration."""
    
    def calculate_evidence_score(self, gene_symbol: str) -> Dict[str, float]:
        return {
            'clinical_trials': self.count_clinical_evidence(gene_symbol),
            'pathway_evidence': self.score_pathway_evidence(gene_symbol),
            'go_evidence': self.score_go_evidence(gene_symbol),
            'drug_evidence': self.score_drug_evidence(gene_symbol)
        }
```

## Schema Documentation Requirements

For each data source, document in README:

### Data Source Template
```markdown
#### [Source Name]
- **URL:** [download_url]
- **Update Frequency:** [daily/weekly/monthly]
- **Coverage:** [human genes/drugs/pathways]
- **Key IDs:** [primary identifiers]
- **Sample Record:** [JSON/TSV example]
- **Integration Point:** [how we join with existing data]
- **Evidence Type:** [experimental/computational/clinical]
```

This systematic approach will dramatically improve our data integration quality and provide the robust evidence base needed for clinical decision support.