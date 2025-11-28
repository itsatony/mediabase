# MEDIABASE Database Schema Reference

**Version:** v1.0.1
**Database:** mbase
**PostgreSQL Version:** 12+
**Last Updated:** 2025-11-25

## Overview

MEDIABASE is a comprehensive cancer transcriptomics database system that integrates biological data from multiple authoritative sources into a unified PostgreSQL schema. The database supports both base research queries and patient-specific analysis through a sophisticated normalized architecture with extensive cross-referencing capabilities. The v0.6.0.2 release integrates 47+ million gene-publication links from PubTator Central, enabling evidence-based query filtering and literature support assessment for clinical decision-making.

### Data Sources
- **GENCODE** - Gene transcript annotations and genomic coordinates
- **UniProt** - Gene product classification and protein annotations
- **Gene Ontology** - Molecular function, biological process, and cellular component terms
- **Reactome** - Biological pathway data and gene roles
- **DrugCentral/ChEMBL** - Drug interactions and pharmacological data
- **PubTator Central** - Literature associations from PubMed
- **Open Targets Platform** - Disease associations, drug tractability, and clinical evidence

### Architecture Principles
1. **Normalized Core Tables** - Genes and transcripts as primary entities with separate annotation tables
2. **Extensive Indexing** - GIN, B-tree, and composite indexes for rapid querying
3. **JSONB for Complex Data** - Flexible storage for metadata and nested structures
4. **Cascade Deletion** - Foreign key constraints maintain referential integrity
5. **Patient Database Support** - Template structure for patient-specific fold-change data

---

## Quick Reference

| Table Name | Row Count | Primary Purpose |
|------------|-----------|-----------------|
| `genes` | 78,724 | Core gene entities with genomic coordinates |
| `transcripts` | 158,338 | Gene transcript isoforms with expression data |
| `gene_annotations` | 186,918 | Product types, functions, and cellular locations |
| `gene_cross_references` | 137,558 | External database ID mappings |
| `gene_pathways` | 113,417 | Reactome pathway associations |
| `gene_publications` | 47,391,210 | PubMed literature associations |
| `transcript_go_terms` | 1,263,052 | Gene Ontology term assignments |
| `gene_drug_interactions` | 0 | DrugCentral/ChEMBL drug data (to be populated) |
| `opentargets_diseases` | 28,327 | Disease ontology from Open Targets |
| `opentargets_gene_disease_associations` | 2,677 | Gene-disease evidence scores |
| `opentargets_known_drugs` | 130,374 | Clinical drugs and development phases |
| `opentargets_target_tractability` | 62,000 | Drug target tractability assessments |
| `cancer_transcript_base` | 0 | Patient database template (denormalized) |
| `evidence_scoring_metadata` | 0 | Evidence quality scoring (future use) |

---

## Core Tables

### 1. genes

**Purpose:** Primary gene entities with genomic coordinates and basic metadata from GENCODE.

**Columns:**

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `gene_id` | VARCHAR(50) | NOT NULL | Ensembl gene ID (primary identifier, e.g., ENSG00000141510) |
| `gene_symbol` | VARCHAR(100) | NOT NULL | HGNC gene symbol (e.g., TP53, BRCA1) |
| `gene_name` | VARCHAR(200) | NULL | Full gene name |
| `gene_type` | VARCHAR(100) | NULL | Gene biotype (protein_coding, lncRNA, pseudogene, etc.) |
| `chromosome` | VARCHAR(10) | NULL | Chromosome location (1-22, X, Y, MT) |
| `start_position` | INTEGER | NULL | Genomic start coordinate (1-based) |
| `end_position` | INTEGER | NULL | Genomic end coordinate (1-based, inclusive) |
| `strand` | INTEGER | NULL | Genomic strand: 1 for forward, -1 for reverse |
| `description` | TEXT | NULL | Gene description/function summary |
| `created_at` | TIMESTAMPTZ | NOT NULL | Record creation timestamp |
| `updated_at` | TIMESTAMPTZ | NOT NULL | Record last update timestamp |

**Primary Key:** `gene_id`

**Indexes:**
- `idx_genes_symbol` - Fast lookup by gene symbol (most common query pattern)
- `idx_genes_chromosome` - Chromosome-based filtering
- `idx_genes_position` - Composite index on (chromosome, start_position, end_position) for range queries
- `idx_genes_type` - Filter by gene biotype
- `idx_genes_created` - Audit trail queries

**Referenced By:**
- `transcripts.gene_id` - One-to-many relationship
- `gene_annotations.gene_id` - One-to-many annotations
- `gene_cross_references.gene_id` - One-to-many external IDs
- `gene_drug_interactions.gene_id` - One-to-many drug associations
- `gene_pathways.gene_id` - One-to-many pathway memberships
- `gene_publications.gene_id` - One-to-many literature citations

**Sample Query:**
```sql
-- Find all protein-coding genes on chromosome 17
SELECT gene_id, gene_symbol, gene_name, start_position, end_position
FROM genes
WHERE chromosome = '17'
  AND gene_type = 'protein_coding'
ORDER BY start_position;

-- Find genes in a genomic region (e.g., BRCA1 locus)
SELECT gene_id, gene_symbol, start_position, end_position
FROM genes
WHERE chromosome = '17'
  AND start_position <= 43125483
  AND end_position >= 43044295
ORDER BY start_position;
```

---

### 2. transcripts

**Purpose:** Gene transcript isoforms with patient-specific expression fold-change data. Each transcript represents an RNA sequence variant of a gene.

**Columns:**

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `transcript_id` | VARCHAR(50) | NOT NULL | - | Ensembl transcript ID (e.g., ENST00000269305) |
| `gene_id` | VARCHAR(50) | NOT NULL | - | Foreign key to genes table |
| `transcript_name` | VARCHAR(200) | NULL | - | Transcript name (e.g., TP53-201) |
| `transcript_type` | VARCHAR(100) | NULL | - | Transcript biotype (protein_coding, nonsense_mediated_decay, etc.) |
| `transcript_support_level` | INTEGER | NULL | 1 | TSL from GENCODE: 1 (best) to 5 (worst) |
| `expression_fold_change` | DOUBLE PRECISION | NULL | 1.0 | Patient-specific expression fold change (default 1.0 = no change) |
| `created_at` | TIMESTAMPTZ | NOT NULL | CURRENT_TIMESTAMP | Record creation timestamp |
| `updated_at` | TIMESTAMPTZ | NOT NULL | CURRENT_TIMESTAMP | Record last update timestamp |

**Primary Key:** `transcript_id`

**Foreign Keys:**
- `gene_id` REFERENCES `genes(gene_id)` ON DELETE CASCADE

**Indexes:**
- `idx_transcripts_gene` - Join with genes table
- `idx_transcripts_type` - Filter by transcript biotype
- `idx_transcripts_expression` - Sort/filter by fold-change values
- `idx_transcripts_created` - Audit trail queries

**Referenced By:**
- `transcript_go_terms.transcript_id` - Gene Ontology annotations

**Notes:**
- The `expression_fold_change` column is the key field for patient-specific analysis
- Values > 1.0 indicate upregulation, < 1.0 indicate downregulation
- In the base database, all values default to 1.0 (neutral expression)
- Patient database copies update this field with DESeq2 or similar analysis results

**Sample Query:**
```sql
-- Find all transcripts for TP53 with their support levels
SELECT t.transcript_id, t.transcript_name, t.transcript_type,
       t.transcript_support_level, t.expression_fold_change
FROM transcripts t
JOIN genes g ON t.gene_id = g.gene_id
WHERE g.gene_symbol = 'TP53'
ORDER BY t.transcript_support_level, t.transcript_name;

-- Find highly upregulated protein-coding transcripts (patient database)
SELECT t.transcript_id, g.gene_symbol, t.expression_fold_change
FROM transcripts t
JOIN genes g ON t.gene_id = g.gene_id
WHERE t.expression_fold_change > 5.0
  AND t.transcript_type = 'protein_coding'
ORDER BY t.expression_fold_change DESC
LIMIT 100;

-- Compare expression across transcript isoforms
SELECT g.gene_symbol,
       COUNT(*) as isoform_count,
       AVG(t.expression_fold_change) as avg_expression,
       MAX(t.expression_fold_change) as max_expression
FROM transcripts t
JOIN genes g ON t.gene_id = g.gene_id
WHERE t.expression_fold_change > 1.5
GROUP BY g.gene_symbol
HAVING COUNT(*) > 2
ORDER BY max_expression DESC;
```

---

### 3. gene_annotations

**Purpose:** Multi-source annotations including UniProt product types, molecular functions, and cellular locations. Denormalized for flexible querying.

**Columns:**

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | INTEGER | NOT NULL | AUTO | Synthetic primary key |
| `gene_id` | VARCHAR(50) | NOT NULL | - | Foreign key to genes table |
| `annotation_type` | VARCHAR(100) | NOT NULL | - | Type: product_type, molecular_function, cellular_location |
| `annotation_value` | TEXT | NOT NULL | - | The annotation text (e.g., "Enzyme", "Nucleus", "DNA binding") |
| `source` | VARCHAR(100) | NULL | 'UniProt' | Data source (UniProt, GO, etc.) |
| `created_at` | TIMESTAMPTZ | NOT NULL | CURRENT_TIMESTAMP | Record creation timestamp |

**Primary Key:** `id`

**Foreign Keys:**
- `gene_id` REFERENCES `genes(gene_id)` ON DELETE CASCADE

**Unique Constraint:**
- `(gene_id, annotation_type, annotation_value, source)` - Prevent duplicate annotations

**Indexes:**
- `idx_gene_annotations_gene` - Join with genes table
- `idx_gene_annotations_type` - Filter by annotation category
- `idx_gene_annotations_value` - Search by annotation text
- `idx_gene_annotations_source` - Filter by data source

**Annotation Types:**
- `product_type` - Protein classification (Enzyme, Receptor, Transcription factor, etc.)
- `molecular_function` - Biochemical activities (DNA binding, ATP binding, kinase activity, etc.)
- `cellular_location` - Subcellular compartments (Nucleus, Cytoplasm, Membrane, Secreted, etc.)

**Sample Query:**
```sql
-- Find all kinases
SELECT DISTINCT g.gene_symbol, g.gene_id
FROM genes g
JOIN gene_annotations ga ON g.gene_id = ga.gene_id
WHERE ga.annotation_type = 'molecular_function'
  AND ga.annotation_value ILIKE '%kinase%'
ORDER BY g.gene_symbol;

-- Get all annotations for a specific gene
SELECT ga.annotation_type, ga.annotation_value, ga.source
FROM gene_annotations ga
JOIN genes g ON ga.gene_id = g.gene_id
WHERE g.gene_symbol = 'EGFR'
ORDER BY ga.annotation_type, ga.annotation_value;

-- Find nuclear transcription factors
SELECT DISTINCT g.gene_symbol
FROM genes g
JOIN gene_annotations ga1 ON g.gene_id = ga1.gene_id
JOIN gene_annotations ga2 ON g.gene_id = ga2.gene_id
WHERE ga1.annotation_type = 'cellular_location' AND ga1.annotation_value = 'Nucleus'
  AND ga2.annotation_type = 'molecular_function' AND ga2.annotation_value ILIKE '%transcription%'
ORDER BY g.gene_symbol;
```

---

### 4. gene_cross_references

**Purpose:** External database identifier mappings for interoperability with UniProt, NCBI, RefSeq, HGNC, PDB, and other biological databases.

**Columns:**

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | INTEGER | NOT NULL | AUTO | Synthetic primary key |
| `gene_id` | VARCHAR(50) | NOT NULL | - | Foreign key to genes table |
| `external_db` | VARCHAR(50) | NOT NULL | - | Database name: UniProt, NCBI, EntrezGene, RefSeq, HGNC, HAVANA, PDB |
| `external_id` | VARCHAR(100) | NOT NULL | - | External identifier in that database |
| `created_at` | TIMESTAMPTZ | NOT NULL | CURRENT_TIMESTAMP | Record creation timestamp |

**Primary Key:** `id`

**Foreign Keys:**
- `gene_id` REFERENCES `genes(gene_id)` ON DELETE CASCADE

**Unique Constraint:**
- `(gene_id, external_db, external_id)` - Prevent duplicate cross-references

**Indexes:**
- `idx_gene_xref_gene` - Join with genes table
- `idx_gene_xref_db` - Filter by database
- `idx_gene_xref_external_id` - Reverse lookup (external ID → gene_id)
- `idx_gene_xref_lookup` - Composite index on (external_db, external_id) for fast reverse mapping

**Common Database Types:**
- `UniProt` - UniProt/SwissProt accession (e.g., P04637 for TP53)
- `NCBI` / `EntrezGene` - NCBI Gene ID (e.g., 7157 for TP53)
- `RefSeq` - RefSeq transcript/protein accessions (e.g., NM_000546)
- `HGNC` - HGNC gene ID (e.g., HGNC:11998 for TP53)
- `PDB` - Protein Data Bank structure IDs (e.g., 1TUP)
- `HAVANA` - Havana manual annotation IDs

**Sample Query:**
```sql
-- Find Ensembl gene_id from UniProt accession
SELECT g.gene_id, g.gene_symbol, xr.external_id as uniprot_id
FROM gene_cross_references xr
JOIN genes g ON xr.gene_id = g.gene_id
WHERE xr.external_db = 'UniProt'
  AND xr.external_id = 'P04637';

-- Get all external IDs for a gene
SELECT xr.external_db, xr.external_id
FROM gene_cross_references xr
JOIN genes g ON xr.gene_id = g.gene_id
WHERE g.gene_symbol = 'BRCA1'
ORDER BY xr.external_db, xr.external_id;

-- Find genes with PDB structures
SELECT DISTINCT g.gene_symbol, xr.external_id as pdb_id
FROM genes g
JOIN gene_cross_references xr ON g.gene_id = xr.gene_id
WHERE xr.external_db = 'PDB'
ORDER BY g.gene_symbol;

-- Reverse lookup: EntrezGene ID to Ensembl
SELECT g.gene_id, g.gene_symbol
FROM gene_cross_references xr
JOIN genes g ON xr.gene_id = g.gene_id
WHERE xr.external_db = 'EntrezGene'
  AND xr.external_id = '7157';
```

---

### 5. gene_pathways

**Purpose:** Reactome biological pathway associations with hierarchical structure, confidence scoring, and literature support.

**Columns:**

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | INTEGER | NOT NULL | AUTO | Synthetic primary key |
| `gene_id` | VARCHAR(50) | NOT NULL | - | Foreign key to genes table |
| `pathway_id` | VARCHAR(100) | NOT NULL | - | Reactome pathway ID (e.g., R-HSA-162582) |
| `pathway_name` | TEXT | NOT NULL | - | Human-readable pathway name |
| `pathway_source` | VARCHAR(50) | NULL | 'Reactome' | Data source |
| `parent_pathway_id` | VARCHAR(100) | NULL | - | Parent pathway in hierarchy |
| `pathway_level` | INTEGER | NULL | 1 | Hierarchy level: 1=top-level, 2=sub-pathway, 3=detailed |
| `pathway_category` | VARCHAR(200) | NULL | - | High-level category (Signal Transduction, Metabolism, etc.) |
| `evidence_code` | VARCHAR(10) | NULL | 'IEA' | GO/ECO evidence code (IEA, IDA, IMP, TAS, etc.) |
| `confidence_score` | NUMERIC(3,2) | NULL | 0.80 | Data quality score 0.0-1.0 |
| `gene_role` | VARCHAR(100) | NULL | - | Gene role in pathway (member, regulator, target, catalyst, etc.) |
| `pmids` | TEXT[] | NULL | - | Array of PubMed IDs supporting this annotation |
| `created_at` | TIMESTAMPTZ | NOT NULL | CURRENT_TIMESTAMP | Record creation timestamp |

**Primary Key:** `id`

**Foreign Keys:**
- `gene_id` REFERENCES `genes(gene_id)` ON DELETE CASCADE

**Unique Constraint:**
- `(gene_id, pathway_id, pathway_source)` - Prevent duplicate pathway associations

**Indexes:**
- `idx_gene_pathways_gene` - Join with genes table
- `idx_gene_pathways_pathway` - Filter by pathway
- `idx_gene_pathways_category` - Filter by pathway category
- `idx_gene_pathways_level` - Filter by hierarchy level
- `idx_gene_pathways_parent` - Navigate pathway hierarchy
- `idx_gene_pathways_confidence` - Filter by data quality
- `idx_gene_pathways_evidence` - Filter by evidence code
- `idx_gene_pathways_role` - Filter by gene role
- `idx_gene_pathways_pmids` - GIN index for literature support queries

**Evidence Codes:**
- `IEA` - Inferred from Electronic Annotation (automatic)
- `IDA` - Inferred from Direct Assay (experimental)
- `IMP` - Inferred from Mutant Phenotype
- `TAS` - Traceable Author Statement
- `IC` - Inferred by Curator

**Sample Query:**
```sql
-- Find all pathways for a gene
SELECT gp.pathway_name, gp.pathway_category, gp.confidence_score,
       gp.gene_role, array_length(gp.pmids, 1) as pmid_count
FROM gene_pathways gp
JOIN genes g ON gp.gene_id = g.gene_id
WHERE g.gene_symbol = 'TP53'
ORDER BY gp.confidence_score DESC, gp.pathway_level;

-- Find genes in a specific pathway with literature evidence
SELECT DISTINCT g.gene_symbol, gp.gene_role, gp.confidence_score,
       COALESCE(COUNT(DISTINCT gp2.pmid), 0) as publication_count,
       CASE
           WHEN COUNT(DISTINCT gp2.pmid) >= 100000 THEN 'Extensively studied'
           WHEN COUNT(DISTINCT gp2.pmid) >= 10000 THEN 'Well-studied'
           WHEN COUNT(DISTINCT gp2.pmid) >= 1000 THEN 'Moderate evidence'
           ELSE 'Limited publications'
       END as evidence_level
FROM genes g
JOIN gene_pathways gp ON g.gene_id = gp.gene_id
LEFT JOIN gene_publications gp2 ON g.gene_id = gp2.gene_id
WHERE gp.pathway_name ILIKE '%DNA repair%'
  AND gp.confidence_score >= 0.8
GROUP BY g.gene_symbol, gp.gene_role, gp.confidence_score
ORDER BY publication_count DESC, g.gene_symbol;

-- Find highly confident pathway annotations with dual literature support
SELECT g.gene_symbol, gp.pathway_name, gp.confidence_score,
       array_length(gp.pmids, 1) as pathway_pmids,
       COALESCE(COUNT(DISTINCT gp2.pmid), 0) as total_publications,
       CASE
           WHEN COUNT(DISTINCT gp2.pmid) >= 100000 THEN 'Extensively studied'
           WHEN COUNT(DISTINCT gp2.pmid) >= 10000 THEN 'Well-studied'
           WHEN COUNT(DISTINCT gp2.pmid) >= 1000 THEN 'Moderate evidence'
           ELSE 'Limited publications'
       END as evidence_level
FROM gene_pathways gp
JOIN genes g ON gp.gene_id = g.gene_id
LEFT JOIN gene_publications gp2 ON g.gene_id = gp2.gene_id
WHERE gp.confidence_score >= 0.9
  AND array_length(gp.pmids, 1) >= 5
GROUP BY g.gene_symbol, gp.pathway_name, gp.confidence_score, gp.pmids
ORDER BY total_publications DESC, gp.confidence_score DESC
LIMIT 100;

-- Pathway hierarchy exploration
SELECT p1.pathway_name as parent_pathway,
       p2.pathway_name as sub_pathway,
       COUNT(DISTINCT p2.gene_id) as gene_count
FROM gene_pathways p1
JOIN gene_pathways p2 ON p1.pathway_id = p2.parent_pathway_id
GROUP BY p1.pathway_name, p2.pathway_name
ORDER BY gene_count DESC;
```

---

### 6. gene_drug_interactions

**Purpose:** Drug-gene interactions from DrugCentral and ChEMBL with clinical phase, pharmacological activity, and evidence quality.

**Columns:**

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | INTEGER | NOT NULL | AUTO | Synthetic primary key |
| `gene_id` | VARCHAR(50) | NOT NULL | - | Foreign key to genes table |
| `drug_name` | VARCHAR(500) | NOT NULL | - | Drug name (generic or trade name) |
| `drug_id` | VARCHAR(50) | NULL | - | DrugCentral drug identifier |
| `interaction_type` | VARCHAR(100) | NULL | - | Type of interaction (inhibitor, agonist, antagonist, etc.) |
| `evidence_level` | VARCHAR(50) | NULL | - | Evidence quality classification |
| `source` | VARCHAR(50) | NULL | 'DrugCentral' | Data source |
| `pmid` | TEXT | NULL | - | PubMed ID (deprecated - use pmids array) |
| `drug_chembl_id` | VARCHAR(50) | NULL | - | ChEMBL database identifier for cross-referencing |
| `drugbank_id` | VARCHAR(20) | NULL | - | DrugBank identifier |
| `clinical_phase` | VARCHAR(50) | NULL | - | Development phase: Preclinical, Phase I/II/III, Approved, Withdrawn |
| `approval_status` | VARCHAR(50) | NULL | - | Regulatory approval status |
| `activity_value` | NUMERIC(10,4) | NULL | - | Pharmacological activity value (IC50, Ki, Kd, EC50) |
| `activity_unit` | VARCHAR(20) | NULL | - | Unit of activity measurement (nM, uM, etc.) |
| `activity_type` | VARCHAR(50) | NULL | - | Type of activity measurement (IC50, Ki, Kd, EC50, etc.) |
| `drug_class` | VARCHAR(200) | NULL | - | Therapeutic or chemical class |
| `drug_type` | VARCHAR(50) | NULL | - | Small molecule, antibody, protein, etc. |
| `evidence_strength` | INTEGER | NULL | 1 | Evidence quality score 1-5 (1=low, 5=high) |
| `pmids` | TEXT[] | NULL | - | Array of PubMed IDs supporting this interaction |
| `created_at` | TIMESTAMPTZ | NOT NULL | CURRENT_TIMESTAMP | Record creation timestamp |

**Primary Key:** `id`

**Foreign Keys:**
- `gene_id` REFERENCES `genes(gene_id)` ON DELETE CASCADE

**Unique Constraint:**
- `(gene_id, drug_name, drug_id)` - Prevent duplicate drug interactions

**Indexes:**
- `idx_gene_drug_gene` - Join with genes table
- `idx_gene_drug_name` - Search by drug name
- `idx_gene_drug_drug_id` - Lookup by DrugCentral ID
- `idx_gene_drug_chembl` - ChEMBL cross-reference
- `idx_gene_drug_drugbank` - DrugBank cross-reference
- `idx_gene_drug_type` - Filter by interaction type
- `idx_gene_drug_clinical_phase` - Filter by development phase
- `idx_gene_drug_approval` - Filter by approval status
- `idx_gene_drug_class` - Filter by drug class
- `idx_gene_drug_drug_type` - Filter by drug type
- `idx_gene_drug_activity_type` - Filter by activity measurement
- `idx_gene_drug_evidence_strength` - Filter by evidence quality
- `idx_gene_drug_clinical_relevance` - Composite index on (clinical_phase, approval_status, evidence_strength)
- `idx_gene_drug_pmids` - GIN index for literature support

**Activity Types:**
- `IC50` - Half-maximal inhibitory concentration
- `Ki` - Inhibition constant
- `Kd` - Dissociation constant
- `EC50` - Half-maximal effective concentration

**Sample Query:**
```sql
-- Find approved drugs targeting a gene with literature evidence
SELECT gdi.drug_name, gdi.clinical_phase, gdi.activity_value,
       gdi.activity_unit, gdi.drug_class,
       COALESCE(COUNT(DISTINCT gp.pmid), 0) as publication_count,
       CASE
           WHEN COUNT(DISTINCT gp.pmid) >= 100000 THEN 'Extensively studied'
           WHEN COUNT(DISTINCT gp.pmid) >= 10000 THEN 'Well-studied'
           WHEN COUNT(DISTINCT gp.pmid) >= 1000 THEN 'Moderate evidence'
           ELSE 'Limited publications'
       END as evidence_level
FROM gene_drug_interactions gdi
JOIN genes g ON gdi.gene_id = g.gene_id
LEFT JOIN gene_publications gp ON g.gene_id = gp.gene_id
WHERE g.gene_symbol = 'EGFR'
  AND gdi.clinical_phase = 'Approved'
GROUP BY gdi.drug_name, gdi.clinical_phase, gdi.activity_value, gdi.activity_unit, gdi.drug_class
ORDER BY publication_count DESC, gdi.activity_value;

-- Find high-affinity inhibitors with research depth
SELECT g.gene_symbol, gdi.drug_name, gdi.activity_value,
       gdi.activity_unit, gdi.evidence_strength,
       COALESCE(COUNT(DISTINCT gp.pmid), 0) as publication_count,
       CASE
           WHEN COUNT(DISTINCT gp.pmid) >= 100000 THEN 'Extensively studied'
           WHEN COUNT(DISTINCT gp.pmid) >= 10000 THEN 'Well-studied'
           WHEN COUNT(DISTINCT gp.pmid) >= 1000 THEN 'Moderate evidence'
           ELSE 'Limited publications'
       END as evidence_level
FROM gene_drug_interactions gdi
JOIN genes g ON gdi.gene_id = g.gene_id
LEFT JOIN gene_publications gp ON g.gene_id = gp.gene_id
WHERE gdi.activity_type = 'IC50'
  AND gdi.activity_unit = 'nM'
  AND gdi.activity_value < 10
  AND gdi.evidence_strength >= 4
GROUP BY g.gene_symbol, gdi.drug_name, gdi.activity_value, gdi.activity_unit, gdi.evidence_strength
ORDER BY publication_count DESC, gdi.activity_value;

-- Drug repurposing candidates with evidence depth
SELECT DISTINCT gdi.drug_name, gdi.drug_class,
       COUNT(DISTINCT gdi.gene_id) as target_count,
       AVG(COALESCE(gp_stats.publication_count, 0)) as avg_target_publications,
       CASE
           WHEN AVG(COALESCE(gp_stats.publication_count, 0)) >= 100000 THEN 'Extensively studied targets'
           WHEN AVG(COALESCE(gp_stats.publication_count, 0)) >= 10000 THEN 'Well-studied targets'
           WHEN AVG(COALESCE(gp_stats.publication_count, 0)) >= 1000 THEN 'Moderate evidence'
           ELSE 'Limited publications'
       END as evidence_level
FROM gene_drug_interactions gdi
LEFT JOIN (
    SELECT gene_id, COUNT(DISTINCT pmid) as publication_count
    FROM gene_publications
    GROUP BY gene_id
) gp_stats ON gdi.gene_id = gp_stats.gene_id
WHERE gdi.approval_status = 'Approved'
  AND gdi.evidence_strength >= 3
GROUP BY gdi.drug_name, gdi.drug_class
HAVING COUNT(DISTINCT gdi.gene_id) > 2
ORDER BY avg_target_publications DESC, target_count DESC;
```

**Note:** This table is currently empty (row_count = 0) and will be populated in future ETL runs.

---

### 7. gene_publications

**Purpose:** Large-scale gene-literature associations from PubTator Central, linking 47+ million gene mentions to PubMed articles.

**Columns:**

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | INTEGER | NOT NULL | AUTO | Synthetic primary key |
| `gene_id` | VARCHAR(50) | NOT NULL | - | Foreign key to genes table. Links to gene_symbol, NCBI Gene ID, and transcript information |
| `pmid` | VARCHAR(20) | NOT NULL | - | PubMed ID uniquely identifying the publication. Use to fetch metadata from PubMed E-utilities |
| `mention_count` | INTEGER | NULL | 1 | Number of times gene is mentioned in the publication. Higher counts may indicate more central role in research |
| `first_seen_year` | INTEGER | NULL | - | Publication year (future enhancement). Currently NULL - will be populated from PubMed metadata |
| `created_at` | TIMESTAMPTZ | NOT NULL | CURRENT_TIMESTAMP | Record creation timestamp |
| `last_updated` | TIMESTAMPTZ | NOT NULL | CURRENT_TIMESTAMP | Timestamp of last data refresh. PubTator Central is updated monthly |

**Primary Key:** `id`

**Foreign Keys:**
- `gene_id` REFERENCES `genes(gene_id)` ON DELETE CASCADE

**Unique Constraint:**
- `(gene_id, pmid)` - Each gene-publication pair appears once

**Indexes:**
- `idx_gene_publications_gene_id` - Join with genes table
- `idx_gene_publications_pmid` - Lookup by PubMed ID
- `idx_gene_publications_mention_count` - Sort by relevance (DESC)
- `idx_gene_publications_gene_mentions` - Composite index on (gene_id, mention_count DESC)
- `idx_gene_publications_year` - Filter by publication year (when populated)

**Notes:**
- This is the largest table with 47.4 million rows
- `mention_count` extracted using GNormPlus gene normalization tool
- `first_seen_year` currently NULL - future enhancement for temporal analysis
- PubTator Central updates monthly - track via `last_updated`

**Sample Query:**
```sql
-- Find most-cited papers for a gene
SELECT gp.pmid, gp.mention_count
FROM gene_publications gp
JOIN genes g ON gp.gene_id = g.gene_id
WHERE g.gene_symbol = 'TP53'
ORDER BY gp.mention_count DESC
LIMIT 20;

-- Find genes with extensive literature support
SELECT g.gene_symbol, COUNT(*) as publication_count,
       SUM(gp.mention_count) as total_mentions
FROM genes g
JOIN gene_publications gp ON g.gene_id = gp.gene_id
GROUP BY g.gene_symbol
HAVING COUNT(*) > 1000
ORDER BY publication_count DESC;

-- Find publications mentioning multiple genes of interest
SELECT gp1.pmid,
       COUNT(DISTINCT gp1.gene_id) as gene_count,
       array_agg(DISTINCT g.gene_symbol) as genes_mentioned
FROM gene_publications gp1
JOIN genes g ON gp1.gene_id = g.gene_id
WHERE g.gene_symbol IN ('TP53', 'BRCA1', 'EGFR', 'MYC')
GROUP BY gp1.pmid
HAVING COUNT(DISTINCT gp1.gene_id) > 1
ORDER BY gene_count DESC
LIMIT 50;

-- Gene co-occurrence analysis
SELECT g1.gene_symbol as gene_1, g2.gene_symbol as gene_2,
       COUNT(*) as shared_publications
FROM gene_publications gp1
JOIN gene_publications gp2 ON gp1.pmid = gp2.pmid AND gp1.gene_id < gp2.gene_id
JOIN genes g1 ON gp1.gene_id = g1.gene_id
JOIN genes g2 ON gp2.gene_id = g2.gene_id
WHERE g1.gene_symbol = 'TP53'
GROUP BY g1.gene_symbol, g2.gene_symbol
ORDER BY shared_publications DESC
LIMIT 20;
```

---

### 8. transcript_go_terms

**Purpose:** Gene Ontology term assignments to transcripts, covering molecular function, biological process, and cellular component annotations.

**Columns:**

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | INTEGER | NOT NULL | AUTO | Synthetic primary key |
| `transcript_id` | VARCHAR(50) | NOT NULL | - | Foreign key to transcripts table |
| `go_id` | VARCHAR(20) | NOT NULL | - | Gene Ontology ID (e.g., GO:0005515) |
| `go_term` | TEXT | NOT NULL | - | GO term description (e.g., "protein binding") |
| `go_category` | VARCHAR(50) | NULL | - | GO aspect: molecular_function, biological_process, cellular_component |
| `evidence_code` | VARCHAR(10) | NULL | 'IEA' | GO evidence code (IEA, IDA, IMP, IGI, IEP, etc.) |
| `created_at` | TIMESTAMPTZ | NOT NULL | CURRENT_TIMESTAMP | Record creation timestamp |

**Primary Key:** `id`

**Foreign Keys:**
- `transcript_id` REFERENCES `transcripts(transcript_id)` ON DELETE CASCADE

**Unique Constraint:**
- `(transcript_id, go_id)` - Each GO term assigned once per transcript

**Indexes:**
- `idx_transcript_go_transcript` - Join with transcripts table
- `idx_transcript_go_id` - Lookup by GO ID
- `idx_transcript_go_category` - Filter by GO aspect
- `idx_transcript_go_evidence` - Filter by evidence code

**GO Categories:**
- `molecular_function` - Biochemical activities (e.g., "ATP binding", "protein kinase activity")
- `biological_process` - Biological programs (e.g., "cell cycle", "DNA repair", "apoptosis")
- `cellular_component` - Subcellular locations (e.g., "nucleus", "mitochondrion", "plasma membrane")

**Evidence Codes:**
- `IEA` - Inferred from Electronic Annotation (automatic)
- `IDA` - Inferred from Direct Assay (experimental)
- `IMP` - Inferred from Mutant Phenotype
- `IGI` - Inferred from Genetic Interaction
- `IEP` - Inferred from Expression Pattern
- `TAS` - Traceable Author Statement
- `NAS` - Non-traceable Author Statement

**Sample Query:**
```sql
-- Find all GO terms for a gene (via transcripts)
SELECT DISTINCT tg.go_category, tg.go_id, tg.go_term, tg.evidence_code
FROM transcript_go_terms tg
JOIN transcripts t ON tg.transcript_id = t.transcript_id
JOIN genes g ON t.gene_id = g.gene_id
WHERE g.gene_symbol = 'TP53'
ORDER BY tg.go_category, tg.go_term;

-- Find genes with specific molecular function
SELECT DISTINCT g.gene_symbol
FROM genes g
JOIN transcripts t ON g.gene_id = t.gene_id
JOIN transcript_go_terms tg ON t.transcript_id = tg.transcript_id
WHERE tg.go_category = 'molecular_function'
  AND tg.go_term ILIKE '%kinase%'
ORDER BY g.gene_symbol;

-- GO term enrichment by category
SELECT tg.go_category, tg.go_term, COUNT(DISTINCT tg.transcript_id) as transcript_count
FROM transcript_go_terms tg
GROUP BY tg.go_category, tg.go_term
HAVING COUNT(DISTINCT tg.transcript_id) > 100
ORDER BY transcript_count DESC
LIMIT 50;

-- High-confidence experimental annotations only
SELECT g.gene_symbol, tg.go_category, tg.go_term
FROM transcript_go_terms tg
JOIN transcripts t ON tg.transcript_id = t.transcript_id
JOIN genes g ON t.gene_id = g.gene_id
WHERE tg.evidence_code IN ('IDA', 'IMP', 'IGI', 'IEP')
  AND g.gene_symbol IN ('TP53', 'BRCA1', 'EGFR')
ORDER BY g.gene_symbol, tg.go_category;
```

---

### 9. schema_version

**Purpose:** Track schema version and migration history for database management.

**Columns:**

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `version_name` | VARCHAR(20) | NOT NULL | - | Semantic version identifier (e.g., v1.0.0_baseline) |
| `description` | TEXT | NULL | - | Human-readable description of schema changes |
| `applied_at` | TIMESTAMPTZ | NOT NULL | CURRENT_TIMESTAMP | Timestamp when version was applied |

**Primary Key:** `version_name`

**Current Version:** `v1.0.0_baseline`

**Version History:**
```
v1.0.0_baseline - Complete flattened baseline schema with normalized tables,
                  PubTator Central literature, Open Targets Platform integration,
                  schema cleanup, and comprehensive LLM documentation.
                  No migrations required - single-step initialization.
```

**Sample Query:**
```sql
-- View schema history
SELECT version_name, description, applied_at
FROM schema_version
ORDER BY applied_at DESC;
```

---

## Open Targets Platform Integration Tables

The Open Targets Platform provides comprehensive disease associations, drug tractability, and clinical evidence for therapeutic target prioritization.

### 10. opentargets_diseases

**Purpose:** Disease ontology from Open Targets with hierarchical relationships and therapeutic area classifications.

**Columns:**

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `disease_id` | TEXT | NOT NULL | - | EFO, MONDO, or other ontology identifier (e.g., EFO_0000616 for neoplasm) |
| `disease_name` | TEXT | NOT NULL | - | Human-readable disease name |
| `disease_description` | TEXT | NULL | - | Disease definition and characteristics |
| `therapeutic_areas` | TEXT[] | NULL | - | Array of therapeutic area names (e.g., "oncology", "hematology") |
| `ontology_source` | TEXT | NULL | - | Source ontology (EFO, MONDO, etc.) |
| `is_cancer` | BOOLEAN | NULL | FALSE | Boolean flag: true if disease is classified under neoplasm/cancer |
| `parent_disease_ids` | TEXT[] | NULL | - | Array of parent disease IDs in ontology hierarchy |
| `metadata` | JSONB | NULL | - | Additional disease metadata |
| `ot_version` | TEXT | NOT NULL | - | Open Targets Platform release version |
| `created_at` | TIMESTAMP | NOT NULL | NOW() | Record creation timestamp |
| `updated_at` | TIMESTAMP | NOT NULL | NOW() | Record last update timestamp |

**Primary Key:** `disease_id`

**Indexes:**
- `idx_ot_diseases_cancer` - Partial index for cancer diseases (WHERE is_cancer = true)
- `idx_ot_diseases_therapeutic_areas` - GIN index for therapeutic area queries
- `idx_ot_diseases_name` - Full-text search on disease name

**Referenced By:**
- `opentargets_gene_disease_associations.disease_id`
- `opentargets_known_drugs.disease_id`

**Notes:**
- `parent_disease_ids` enables hierarchical queries (e.g., HER2+ breast cancer → breast cancer → carcinoma → neoplasm)
- `is_cancer` flag allows rapid filtering for oncology queries
- Therapeutic areas useful for grouping diseases by treatment approach

**Sample Query:**
```sql
-- Find all cancer diseases
SELECT disease_id, disease_name, therapeutic_areas
FROM opentargets_diseases
WHERE is_cancer = true
ORDER BY disease_name;

-- Explore disease hierarchy
SELECT d1.disease_name as parent_disease,
       d2.disease_name as child_disease
FROM opentargets_diseases d1
JOIN opentargets_diseases d2 ON d1.disease_id = ANY(d2.parent_disease_ids)
WHERE d1.disease_name ILIKE '%breast cancer%'
ORDER BY d2.disease_name;

-- Find diseases in a therapeutic area
SELECT disease_name, disease_description
FROM opentargets_diseases
WHERE 'oncology' = ANY(therapeutic_areas)
ORDER BY disease_name
LIMIT 20;
```

---

### 11. opentargets_gene_disease_associations

**Purpose:** Evidence-based gene-disease associations with multiple scoring dimensions from Open Targets Platform.

**Columns:**

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `association_id` | INTEGER | NOT NULL | AUTO | Synthetic primary key |
| `gene_id` | TEXT | NOT NULL | - | Ensembl gene ID |
| `disease_id` | TEXT | NOT NULL | - | Disease ontology ID |
| `overall_score` | NUMERIC(5,4) | NOT NULL | - | Combined evidence score 0-1. Thresholds: ≥0.5 moderate, ≥0.7 strong, ≥0.85 very strong |
| `genetic_association_score` | NUMERIC(5,4) | NULL | - | Evidence from GWAS and genetic studies |
| `somatic_mutation_score` | NUMERIC(5,4) | NULL | - | Evidence from cancer somatic mutations (CGC, COSMIC, IntOGen). Range 0-1, ≥0.7 = strong driver |
| `known_drug_score` | NUMERIC(5,4) | NULL | - | Evidence from approved/clinical drugs targeting gene for disease. Range 0-1, ≥0.5 = clinical development |
| `literature_score` | NUMERIC(5,4) | NULL | - | Evidence from text mining (Europe PMC). Range 0-1, higher = extensive research |
| `rna_expression_score` | NUMERIC(5,4) | NULL | - | Evidence from RNA expression data |
| `pathways_systems_biology_score` | NUMERIC(5,4) | NULL | - | Evidence from pathway and systems biology analyses |
| `animal_model_score` | NUMERIC(5,4) | NULL | - | Evidence from animal models |
| `is_direct` | BOOLEAN | NULL | TRUE | True if direct gene-disease association (vs inferred) |
| `evidence_count` | INTEGER | NULL | - | Total number of evidence items |
| `datasource_count` | INTEGER | NULL | - | Number of distinct data sources |
| `tractability_clinical_precedence` | BOOLEAN | NULL | - | True if gene target has drugs in clinical development or approved |
| `tractability_discovery_precedence` | BOOLEAN | NULL | - | True if gene has discovery-stage tractability evidence |
| `metadata` | JSONB | NULL | - | Additional evidence metadata |
| `ot_version` | TEXT | NOT NULL | - | Open Targets Platform release version |
| `created_at` | TIMESTAMP | NOT NULL | NOW() | Record creation timestamp |
| `updated_at` | TIMESTAMP | NOT NULL | NOW() | Record last update timestamp |

**Primary Key:** `association_id`

**Foreign Keys:**
- `disease_id` REFERENCES `opentargets_diseases(disease_id)`

**Unique Constraint:**
- `(gene_id, disease_id, ot_version)` - One association per gene-disease-version

**Indexes:**
- `idx_ot_assoc_gene` - Lookup by gene
- `idx_ot_assoc_disease` - Lookup by disease
- `idx_ot_assoc_score` - Sort by overall score (DESC)
- `idx_ot_assoc_gene_score` - Composite on (gene_id, overall_score DESC)
- `idx_ot_assoc_strong_evidence` - Partial index WHERE overall_score >= 0.7
- `idx_ot_assoc_somatic` - Partial index on (gene_id, somatic_mutation_score DESC) WHERE >= 0.5
- `idx_ot_assoc_cancer_genes` - Partial index on (gene_id, overall_score) WHERE >= 0.5

**Score Interpretation:**
- **overall_score**: Primary filter for clinical relevance
  - 0.0-0.49: Weak evidence
  - 0.5-0.69: Moderate evidence
  - 0.7-0.84: Strong evidence
  - 0.85-1.0: Very strong evidence
- **somatic_mutation_score** ≥ 0.7: Well-established cancer driver genes
- **known_drug_score** ≥ 0.5: Drugs in clinical development

**Sample Query:**
```sql
-- Find high-confidence cancer gene associations with publication support
SELECT g.gene_symbol, od.disease_name,
       ogda.overall_score, ogda.somatic_mutation_score, ogda.known_drug_score,
       COALESCE(COUNT(DISTINCT gp.pmid), 0) as publication_count,
       CASE
           WHEN COUNT(DISTINCT gp.pmid) >= 100000 THEN 'Extensively studied'
           WHEN COUNT(DISTINCT gp.pmid) >= 10000 THEN 'Well-studied'
           WHEN COUNT(DISTINCT gp.pmid) >= 1000 THEN 'Moderate evidence'
           ELSE 'Limited publications'
       END as evidence_level
FROM opentargets_gene_disease_associations ogda
JOIN genes g ON ogda.gene_id = g.gene_id
JOIN opentargets_diseases od ON ogda.disease_id = od.disease_id
LEFT JOIN gene_publications gp ON g.gene_id = gp.gene_id
WHERE od.is_cancer = true
  AND ogda.overall_score >= 0.7
GROUP BY g.gene_symbol, od.disease_name, ogda.overall_score, ogda.somatic_mutation_score, ogda.known_drug_score
ORDER BY publication_count DESC, ogda.overall_score DESC
LIMIT 50;

-- Find actionable targets (high score + drug precedence)
SELECT g.gene_symbol, od.disease_name, ogda.overall_score
FROM opentargets_gene_disease_associations ogda
JOIN genes g ON ogda.gene_id = g.gene_id
JOIN opentargets_diseases od ON ogda.disease_id = od.disease_id
WHERE ogda.overall_score >= 0.7
  AND ogda.tractability_clinical_precedence = true
ORDER BY ogda.overall_score DESC;

-- Top cancer driver genes with research support
SELECT g.gene_symbol, COUNT(DISTINCT ogda.disease_id) as disease_count,
       AVG(ogda.somatic_mutation_score) as avg_mutation_score,
       COALESCE(COUNT(DISTINCT gp.pmid), 0) as publication_count,
       CASE
           WHEN COUNT(DISTINCT gp.pmid) >= 100000 THEN 'Extensively studied'
           WHEN COUNT(DISTINCT gp.pmid) >= 10000 THEN 'Well-studied'
           WHEN COUNT(DISTINCT gp.pmid) >= 1000 THEN 'Moderate evidence'
           ELSE 'Limited publications'
       END as evidence_level
FROM opentargets_gene_disease_associations ogda
JOIN genes g ON ogda.gene_id = g.gene_id
JOIN opentargets_diseases od ON ogda.disease_id = od.disease_id
LEFT JOIN gene_publications gp ON g.gene_id = gp.gene_id
WHERE od.is_cancer = true
  AND ogda.somatic_mutation_score >= 0.7
GROUP BY g.gene_symbol
ORDER BY publication_count DESC, avg_mutation_score DESC
LIMIT 30;
```

---

### 12. opentargets_known_drugs

**Purpose:** Clinical drugs and their target-disease associations with development phase and mechanism of action from Open Targets.

**Columns:**

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `drug_id` | INTEGER | NOT NULL | AUTO | Synthetic primary key |
| `molecule_chembl_id` | TEXT | NULL | - | ChEMBL identifier (e.g., CHEMBL1743070 for afatinib) |
| `molecule_name` | TEXT | NOT NULL | - | Drug name (generic or trade) |
| `molecule_type` | TEXT | NULL | - | Chemical type (Small molecule, Antibody, Protein, etc.) |
| `target_gene_id` | TEXT | NULL | - | Target gene Ensembl ID |
| `disease_id` | TEXT | NULL | - | Disease ontology ID |
| `clinical_phase` | NUMERIC(3,1) | NULL | - | Development phase: 0=preclinical, 1-3=trials, 4=approved, NULL=withdrawn |
| `clinical_phase_label` | TEXT | NULL | - | Human-readable phase label |
| `clinical_status` | TEXT | NULL | - | Current development status |
| `mechanism_of_action` | TEXT | NULL | - | How the drug works (e.g., "ERBB2 receptor antagonist") |
| `action_type` | TEXT | NULL | - | Type of action (inhibitor, agonist, etc.) |
| `drug_type` | TEXT | NULL | - | Therapeutic class |
| `is_approved` | BOOLEAN | NULL | - | True if drug is approved for any indication (may differ from this specific disease) |
| `approval_year` | INTEGER | NULL | - | Year of first approval |
| `clinical_trial_ids` | TEXT[] | NULL | - | Array of clinical trial identifiers |
| `metadata` | JSONB | NULL | - | Additional drug metadata |
| `ot_version` | TEXT | NOT NULL | - | Open Targets Platform release version |
| `created_at` | TIMESTAMP | NOT NULL | NOW() | Record creation timestamp |
| `updated_at` | TIMESTAMP | NOT NULL | NOW() | Record last update timestamp |

**Primary Key:** `drug_id`

**Foreign Keys:**
- `disease_id` REFERENCES `opentargets_diseases(disease_id)`

**Indexes:**
- `idx_ot_drugs_target` - Lookup by gene target
- `idx_ot_drugs_disease` - Lookup by disease
- `idx_ot_drugs_chembl` - ChEMBL cross-reference (partial WHERE NOT NULL)
- `idx_ot_drugs_name` - Full-text search on drug name
- `idx_ot_drugs_approved` - Filter by approval status and phase
- `idx_ot_drugs_clinical` - Composite on (target_gene_id, clinical_phase, is_approved) WHERE phase >= 2

**Clinical Phases:**
- 0.0: Preclinical
- 1.0: Phase I clinical trials
- 2.0: Phase II clinical trials
- 3.0: Phase III clinical trials
- 4.0: Approved for use
- NULL: Withdrawn or terminated

**Sample Query:**
```sql
-- Find approved drugs for a gene target with evidence depth
SELECT okd.molecule_name, okd.mechanism_of_action,
       okd.clinical_phase, od.disease_name,
       COALESCE(COUNT(DISTINCT gp.pmid), 0) as publication_count,
       CASE
           WHEN COUNT(DISTINCT gp.pmid) >= 100000 THEN 'Extensively studied'
           WHEN COUNT(DISTINCT gp.pmid) >= 10000 THEN 'Well-studied'
           WHEN COUNT(DISTINCT gp.pmid) >= 1000 THEN 'Moderate evidence'
           ELSE 'Limited publications'
       END as evidence_level
FROM opentargets_known_drugs okd
JOIN genes g ON okd.target_gene_id = g.gene_id
JOIN opentargets_diseases od ON okd.disease_id = od.disease_id
LEFT JOIN gene_publications gp ON g.gene_id = gp.gene_id
WHERE g.gene_symbol = 'EGFR'
  AND okd.clinical_phase = 4.0
GROUP BY okd.molecule_name, okd.mechanism_of_action, okd.clinical_phase, od.disease_name
ORDER BY publication_count DESC, okd.molecule_name;

-- Drug repurposing candidates (approved, multiple targets)
SELECT okd.molecule_name, okd.molecule_type, okd.approval_year,
       COUNT(DISTINCT okd.target_gene_id) as target_count,
       COUNT(DISTINCT okd.disease_id) as disease_count
FROM opentargets_known_drugs okd
WHERE okd.is_approved = true
GROUP BY okd.molecule_name, okd.molecule_type, okd.approval_year
HAVING COUNT(DISTINCT okd.target_gene_id) > 2
ORDER BY target_count DESC, approval_year DESC;

-- Drugs in late-stage development for cancer with research backing
SELECT okd.molecule_name, g.gene_symbol, od.disease_name,
       okd.clinical_phase, okd.mechanism_of_action,
       COALESCE(COUNT(DISTINCT gp.pmid), 0) as publication_count,
       CASE
           WHEN COUNT(DISTINCT gp.pmid) >= 100000 THEN 'Extensively studied'
           WHEN COUNT(DISTINCT gp.pmid) >= 10000 THEN 'Well-studied'
           WHEN COUNT(DISTINCT gp.pmid) >= 1000 THEN 'Moderate evidence'
           ELSE 'Limited publications'
       END as evidence_level
FROM opentargets_known_drugs okd
JOIN genes g ON okd.target_gene_id = g.gene_id
JOIN opentargets_diseases od ON okd.disease_id = od.disease_id
LEFT JOIN gene_publications gp ON g.gene_id = gp.gene_id
WHERE od.is_cancer = true
  AND okd.clinical_phase >= 2.0
  AND okd.clinical_phase < 4.0
GROUP BY okd.molecule_name, g.gene_symbol, od.disease_name, okd.clinical_phase, okd.mechanism_of_action
ORDER BY publication_count DESC, okd.clinical_phase DESC;
```

---

### 13. opentargets_target_tractability

**Purpose:** Target druggability assessments indicating likelihood of successful drug development for small molecules and antibodies.

**Columns:**

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `gene_id` | TEXT | NOT NULL | - | Ensembl gene ID (primary key) |
| `sm_clinical_precedence` | BOOLEAN | NULL | - | Small molecule clinical precedence: drugs exist for target or family |
| `sm_discovery_precedence` | BOOLEAN | NULL | - | Small molecule discovery precedence: tractable structures/assays available |
| `sm_predicted_tractable` | BOOLEAN | NULL | - | Computational prediction of small molecule tractability (structure-based) |
| `sm_top_bucket` | TEXT | NULL | - | Overall small molecule tractability category |
| `ab_clinical_precedence` | BOOLEAN | NULL | - | Antibody clinical precedence: antibody drugs exist for this target |
| `ab_predicted_tractable` | BOOLEAN | NULL | - | Predicted tractability for antibody therapeutics |
| `ab_top_bucket` | TEXT | NULL | - | Overall antibody tractability category |
| `other_modality_tractable` | BOOLEAN | NULL | - | Tractable by other modalities (enzyme replacement, etc.) |
| `tractability_summary` | TEXT | NULL | - | Human-readable tractability summary |
| `metadata` | JSONB | NULL | - | Additional tractability data |
| `ot_version` | TEXT | NOT NULL | - | Open Targets Platform release version |
| `created_at` | TIMESTAMP | NOT NULL | NOW() | Record creation timestamp |
| `updated_at` | TIMESTAMP | NOT NULL | NOW() | Record last update timestamp |

**Primary Key:** `gene_id`

**Indexes:**
- `idx_ot_tract_clinical` - Partial index WHERE sm_clinical_precedence OR ab_clinical_precedence = true
- `idx_ot_tract_sm` - Partial index WHERE sm_clinical_precedence OR sm_predicted_tractable = true
- `idx_ot_tract_ab` - Partial index WHERE ab_clinical_precedence OR ab_predicted_tractable = true

**Tractability Interpretation:**
- **sm_clinical_precedence = true**: Highest confidence for small molecule development (drugs exist for target/family)
- **sm_predicted_tractable = true**: Computational prediction based on structure (binding pockets, physicochemical properties)
- **ab_clinical_precedence = true**: Antibody drugs exist, target is accessible to large molecules
- Combination of flags indicates most promising drug development strategy

**Sample Query:**
```sql
-- Find targets with highest druggability (clinical precedence)
SELECT g.gene_symbol,
       ott.sm_clinical_precedence,
       ott.ab_clinical_precedence,
       ott.tractability_summary
FROM opentargets_target_tractability ott
JOIN genes g ON ott.gene_id = g.gene_id
WHERE ott.sm_clinical_precedence = true
   OR ott.ab_clinical_precedence = true
ORDER BY g.gene_symbol;

-- Find tractable targets for a disease
SELECT g.gene_symbol, ott.sm_clinical_precedence, ott.sm_predicted_tractable,
       ogda.overall_score, ogda.somatic_mutation_score
FROM opentargets_target_tractability ott
JOIN opentargets_gene_disease_associations ogda ON ott.gene_id = ogda.gene_id
JOIN genes g ON ott.gene_id = g.gene_id
JOIN opentargets_diseases od ON ogda.disease_id = od.disease_id
WHERE od.disease_name ILIKE '%lung cancer%'
  AND ogda.overall_score >= 0.5
  AND (ott.sm_clinical_precedence = true OR ott.sm_predicted_tractable = true)
ORDER BY ogda.overall_score DESC;

-- Compare small molecule vs antibody tractability
SELECT
  COUNT(*) FILTER (WHERE sm_clinical_precedence = true) as sm_clinical,
  COUNT(*) FILTER (WHERE sm_predicted_tractable = true) as sm_predicted,
  COUNT(*) FILTER (WHERE ab_clinical_precedence = true) as ab_clinical,
  COUNT(*) FILTER (WHERE ab_predicted_tractable = true) as ab_predicted,
  COUNT(*) FILTER (WHERE sm_clinical_precedence = true AND ab_clinical_precedence = true) as both_clinical
FROM opentargets_target_tractability;
```

---

### 14. opentargets_metadata

**Purpose:** Track Open Targets Platform data version and validation for reproducibility.

**Columns:**

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `version` | TEXT | NOT NULL | - | Open Targets release version (e.g., "24.09") |
| `release_date` | DATE | NULL | - | Official release date from Open Targets |
| `loaded_date` | TIMESTAMP | NOT NULL | NOW() | When data was loaded into MEDIABASE |
| `record_counts` | JSONB | NULL | - | Count of records loaded per table |
| `validation_results` | JSONB | NULL | - | Data quality validation results |
| `notes` | TEXT | NULL | - | Additional notes about this version |

**Primary Key:** `version`

**Sample Query:**
```sql
-- View Open Targets data version and statistics
SELECT version, release_date, loaded_date, record_counts
FROM opentargets_metadata
ORDER BY loaded_date DESC;
```

---

## Special Purpose Tables

### 15. cancer_transcript_base

**Purpose:** Denormalized template table for patient-specific database copies. Combines all transcript information into a single wide table optimized for AI agent queries. This table serves as the foundation for patient databases.

**Structure:** Denormalized wide table with JSONB columns for complex nested data

**Key Columns:**
- `transcript_id` (TEXT, PRIMARY KEY) - Ensembl transcript ID
- `gene_symbol` (TEXT) - HGNC gene symbol
- `gene_id` (TEXT) - Ensembl gene ID
- `gene_type` (TEXT) - Gene biotype
- `chromosome` (TEXT) - Chromosome location
- `coordinates` (JSONB) - Genomic position with start/end/strand
- `product_type` (TEXT[]) - Array of protein classifications
- `go_terms` (JSONB) - Nested GO annotations by category
- `pathways` (TEXT[]) - Array of pathway names
- `drugs` (JSONB) - Drug interaction data with scores
- `expression_fold_change` (DOUBLE PRECISION) - Patient-specific expression (default 1.0)
- `features` (JSONB) - Transcript features and metadata
- `molecular_functions` (TEXT[]) - Array of molecular functions
- `cellular_location` (TEXT[]) - Array of cellular locations
- `drug_scores` (JSONB) - Detailed drug scoring data
- `alt_transcript_ids` (JSONB) - Alternative transcript identifiers
- `alt_gene_ids` (JSONB) - Alternative gene identifiers
- `uniprot_ids` (TEXT[]) - UniProt accessions
- `ncbi_ids` (TEXT[]) - NCBI Gene IDs
- `refseq_ids` (TEXT[]) - RefSeq accessions
- `pdb_ids` (TEXT[]) - PDB structure IDs
- `source_references` (JSONB) - References to source data with PMIDs
- `evidence_quality_metrics` (JSONB) - Data quality scores and metadata

**Indexes:** Extensive GIN and B-tree indexes on all query-relevant columns

**Row Count:** 0 (template table, populated when creating patient databases)

**Usage Pattern:**
1. Base database maintains this table as empty template
2. When creating patient database: `CREATE DATABASE patient_xyz WITH TEMPLATE mbase`
3. Patient-specific fold-change data loaded via CSV
4. AI agents query single table instead of complex joins

**Sample Query (in patient database):**
```sql
-- Find upregulated genes with drug interactions
SELECT transcript_id, gene_symbol, expression_fold_change,
       drugs, pathways, molecular_functions
FROM cancer_transcript_base
WHERE expression_fold_change > 2.0
  AND drugs IS NOT NULL AND drugs != '{}'::jsonb
ORDER BY expression_fold_change DESC
LIMIT 50;

-- Search by molecular function with fold-change
SELECT gene_symbol, molecular_functions, expression_fold_change
FROM cancer_transcript_base
WHERE 'kinase activity' = ANY(molecular_functions)
  AND expression_fold_change > 1.5
ORDER BY expression_fold_change DESC;

-- Cross-reference lookup by UniProt ID
SELECT transcript_id, gene_symbol, uniprot_ids, expression_fold_change
FROM cancer_transcript_base
WHERE 'P04637' = ANY(uniprot_ids);  -- TP53 UniProt ID
```

---

### 16. evidence_scoring_metadata

**Purpose:** Store evidence quality scores and confidence intervals for gene-drug associations. Currently unused, reserved for future evidence scoring system.

**Columns:**
- `id` (INTEGER, PRIMARY KEY) - Synthetic primary key
- `gene_symbol` (TEXT, NOT NULL) - Gene symbol
- `drug_id` (TEXT) - Drug identifier
- `evidence_score` (JSONB, NOT NULL) - Structured evidence scoring data
- `use_case` (TEXT, DEFAULT 'therapeutic_target') - Scoring context
- `confidence_lower` (DOUBLE PRECISION) - Lower confidence bound
- `confidence_upper` (DOUBLE PRECISION) - Upper confidence bound
- `evidence_count` (INTEGER) - Number of evidence items
- `evidence_quality` (DOUBLE PRECISION) - Overall quality score
- `last_updated` (TIMESTAMPTZ, DEFAULT CURRENT_TIMESTAMP) - Update timestamp
- `scoring_version` (TEXT, DEFAULT '1.0') - Scoring algorithm version

**Indexes:** Gene symbol, drug ID, quality, use case, JSONB scoring data (GIN)

**Row Count:** 0 (future use)

**Unique Constraint:** `(gene_symbol, drug_id, use_case)`

---

## Analytical Views

### drug_interaction_coverage

**Purpose:** Summary statistics on drug interaction data coverage across the database.

**Columns:**
- `total_genes` (BIGINT) - Total number of genes in database
- `genes_with_drugs` (BIGINT) - Genes with at least one drug interaction
- `drug_coverage_percentage` (NUMERIC) - Percentage of genes with drug data
- `unique_drugs` (BIGINT) - Number of distinct drugs
- `total_drug_interactions` (BIGINT) - Total interaction records
- `avg_evidence_strength` (NUMERIC) - Average evidence quality score
- `clinical_stage_interactions` (BIGINT) - Interactions in Approved or Phase III
- `high_confidence_interactions` (BIGINT) - Interactions with evidence_strength >= 4

**Sample Query:**
```sql
SELECT * FROM drug_interaction_coverage;
```

---

### pathway_annotation_coverage

**Purpose:** Summary statistics on pathway annotation coverage.

**Columns:**
- `total_genes` (BIGINT) - Total number of genes
- `genes_with_pathways` (BIGINT) - Genes with pathway annotations
- `pathway_coverage_percentage` (NUMERIC) - Coverage percentage
- `unique_pathways` (BIGINT) - Number of distinct pathways
- `total_pathway_annotations` (BIGINT) - Total pathway-gene associations
- `avg_confidence_score` (NUMERIC) - Average pathway confidence score

**Sample Query:**
```sql
SELECT * FROM pathway_annotation_coverage;
```

---

### publication_coverage

**Purpose:** Summary statistics on literature coverage and gene research activity.

**Columns:**
- `total_genes` (BIGINT) - Total number of genes
- `genes_with_publications` (BIGINT) - Genes with literature associations
- `publication_coverage_percentage` (NUMERIC) - Coverage percentage
- `unique_publications` (BIGINT) - Number of distinct PubMed articles
- `total_gene_publication_associations` (BIGINT) - Total gene-paper links
- `avg_papers_per_gene` (NUMERIC) - Average publications per gene
- `max_papers_for_gene` (BIGINT) - Most publications for any single gene
- `highly_studied_genes` (BIGINT) - Genes with >= 100 publications
- `actively_researched_genes` (BIGINT) - Genes with >= 10 recent papers (5yr)

**Note:** This view references `gene_literature_summary` which may not exist in current schema. View may need adjustment.

**Sample Query:**
```sql
SELECT * FROM publication_coverage;
```

---

### gene_id_lookup

**Purpose:** Simplified view for cross-database ID lookups from cancer_transcript_base.

**Columns:**
- `transcript_id` (TEXT) - Ensembl transcript ID
- `gene_symbol` (TEXT) - Gene symbol
- `gene_id` (TEXT) - Ensembl gene ID
- `uniprot_ids` (TEXT[]) - UniProt accessions
- `ncbi_ids` (TEXT[]) - NCBI Gene IDs
- `refseq_ids` (TEXT[]) - RefSeq accessions
- `alt_gene_ids` (JSONB) - Alternative gene IDs
- `alt_transcript_ids` (JSONB) - Alternative transcript IDs

**Sample Query:**
```sql
-- Lookup by gene symbol
SELECT * FROM gene_id_lookup WHERE gene_symbol = 'TP53';

-- Reverse lookup by UniProt ID
SELECT transcript_id, gene_symbol
FROM gene_id_lookup
WHERE 'P04637' = ANY(uniprot_ids);
```

---

## Entity Relationship Diagram

```
┌─────────────────┐
│     genes       │◄──────────┬─────────────────────────────────────┐
│  - gene_id (PK) │           │                                     │
│  - gene_symbol  │           │                                     │
│  - chromosome   │           │                                     │
│  - coordinates  │           │                                     │
└────────┬────────┘           │                                     │
         │                    │                                     │
         │ 1:N                │ 1:N                                 │
         │                    │                                     │
┌────────▼────────┐  ┌────────┴─────────────┐  ┌──────────────────┴──────┐
│  transcripts    │  │ gene_annotations     │  │ gene_cross_references   │
│- transcript_id  │  │ - id (PK)            │  │ - id (PK)               │
│- gene_id (FK)   │  │ - gene_id (FK)       │  │ - gene_id (FK)          │
│- expression_    │  │ - annotation_type    │  │ - external_db           │
│  fold_change    │  │ - annotation_value   │  │ - external_id           │
└────────┬────────┘  └──────────────────────┘  └─────────────────────────┘
         │
         │ 1:N
         │
┌────────▼────────────┐
│ transcript_go_terms │
│ - id (PK)           │       ┌──────────────────────┐
│ - transcript_id (FK)│       │ gene_pathways        │
│ - go_id             │       │ - id (PK)            │
│ - go_term           │       │ - gene_id (FK)       │
│ - go_category       │       │ - pathway_id         │
└─────────────────────┘       │ - pathway_name       │
                              │ - confidence_score   │
                              │ - pmids[]            │
┌──────────────────────┐      └──────────────────────┘
│ gene_publications    │               │
│ - id (PK)            │               │ 1:N
│ - gene_id (FK)       │               │
│ - pmid               │      ┌────────┴──────────────────┐
│ - mention_count      │      │ gene_drug_interactions    │
└──────────────────────┘      │ - id (PK)                 │
                              │ - gene_id (FK)            │
                              │ - drug_name               │
┌───────────────────────────┐ │ - clinical_phase          │
│ opentargets_diseases      │ │ - activity_value          │
│ - disease_id (PK)         │ │ - evidence_strength       │
│ - disease_name            │ └───────────────────────────┘
│ - is_cancer               │
│ - therapeutic_areas[]     │
└──────┬────────────────────┘
       │
       │ 1:N
       │
┌──────▼─────────────────────────────┐
│ opentargets_gene_disease_          │
│ associations                       │
│ - association_id (PK)              │
│ - gene_id                          │
│ - disease_id (FK)                  │
│ - overall_score                    │
│ - somatic_mutation_score           │
│ - known_drug_score                 │
└────────────────────────────────────┘

┌──────▼─────────────────────────────┐
│ opentargets_known_drugs            │
│ - drug_id (PK)                     │
│ - molecule_name                    │
│ - disease_id (FK)                  │
│ - target_gene_id                   │
│ - clinical_phase                   │
│ - mechanism_of_action              │
└────────────────────────────────────┘

┌────────────────────────────────────┐
│ opentargets_target_tractability    │
│ - gene_id (PK)                     │
│ - sm_clinical_precedence           │
│ - ab_clinical_precedence           │
│ - tractability_summary             │
└────────────────────────────────────┘

┌────────────────────────────────────┐
│ cancer_transcript_base             │
│ (Denormalized patient database)    │
│ - transcript_id (PK)               │
│ - gene_symbol                      │
│ - expression_fold_change           │
│ - drugs (JSONB)                    │
│ - pathways (TEXT[])                │
│ - go_terms (JSONB)                 │
│ - cross_reference_ids (arrays)     │
└────────────────────────────────────┘
```

---

## Common Query Patterns

### 1. Gene Lookup and Basic Information

```sql
-- Lookup gene by symbol
SELECT * FROM genes WHERE gene_symbol = 'TP53';

-- Find genes by partial name match
SELECT gene_id, gene_symbol, gene_name
FROM genes
WHERE gene_symbol ILIKE '%BRCA%'
ORDER BY gene_symbol;

-- Get all information for a gene
SELECT g.*,
       (SELECT COUNT(*) FROM transcripts t WHERE t.gene_id = g.gene_id) as transcript_count,
       (SELECT COUNT(*) FROM gene_pathways gp WHERE gp.gene_id = g.gene_id) as pathway_count,
       (SELECT COUNT(*) FROM gene_publications gpub WHERE gpub.gene_id = g.gene_id) as publication_count
FROM genes g
WHERE g.gene_symbol = 'EGFR';
```

### 2. Transcript and Expression Queries

```sql
-- Find highly expressed transcripts (patient database)
SELECT t.transcript_id, g.gene_symbol, t.expression_fold_change
FROM transcripts t
JOIN genes g ON t.gene_id = g.gene_id
WHERE t.expression_fold_change > 5.0
ORDER BY t.expression_fold_change DESC
LIMIT 100;

-- Compare isoform expression for a gene
SELECT t.transcript_id, t.transcript_name, t.transcript_type,
       t.transcript_support_level, t.expression_fold_change
FROM transcripts t
JOIN genes g ON t.gene_id = g.gene_id
WHERE g.gene_symbol = 'BRCA1'
ORDER BY t.expression_fold_change DESC;
```

### 3. Annotation Queries

```sql
-- Find all kinases
SELECT DISTINCT g.gene_symbol, g.gene_id
FROM genes g
JOIN gene_annotations ga ON g.gene_id = ga.gene_id
WHERE ga.annotation_type = 'molecular_function'
  AND ga.annotation_value ILIKE '%kinase%'
ORDER BY g.gene_symbol;

-- Find nuclear transcription factors
SELECT DISTINCT g.gene_symbol
FROM genes g
JOIN gene_annotations ga1 ON g.gene_id = ga1.gene_id
JOIN gene_annotations ga2 ON g.gene_id = ga2.gene_id
WHERE ga1.annotation_type = 'cellular_location'
  AND ga1.annotation_value = 'Nucleus'
  AND ga2.annotation_type = 'molecular_function'
  AND ga2.annotation_value ILIKE '%transcription%'
ORDER BY g.gene_symbol;
```

### 4. Pathway Analysis

```sql
-- Find genes in DNA repair pathways
SELECT g.gene_symbol, gp.pathway_name, gp.confidence_score
FROM genes g
JOIN gene_pathways gp ON g.gene_id = gp.gene_id
WHERE gp.pathway_name ILIKE '%DNA repair%'
  AND gp.confidence_score >= 0.8
ORDER BY gp.confidence_score DESC;

-- Pathway enrichment for upregulated genes
SELECT gp.pathway_name, COUNT(DISTINCT gp.gene_id) as gene_count,
       AVG(t.expression_fold_change) as avg_fold_change
FROM gene_pathways gp
JOIN genes g ON gp.gene_id = g.gene_id
JOIN transcripts t ON g.gene_id = t.gene_id
WHERE t.expression_fold_change > 2.0
GROUP BY gp.pathway_name
HAVING COUNT(DISTINCT gp.gene_id) >= 5
ORDER BY gene_count DESC, avg_fold_change DESC;
```

### 5. Drug Discovery Queries

```sql
-- Find approved drugs for a target with literature support
SELECT gdi.drug_name, gdi.clinical_phase, gdi.activity_value,
       gdi.activity_unit, gdi.mechanism_of_action,
       COALESCE(COUNT(DISTINCT gp.pmid), 0) as publication_count,
       CASE
           WHEN COUNT(DISTINCT gp.pmid) >= 100000 THEN 'Extensively studied'
           WHEN COUNT(DISTINCT gp.pmid) >= 10000 THEN 'Well-studied'
           WHEN COUNT(DISTINCT gp.pmid) >= 1000 THEN 'Moderate evidence'
           ELSE 'Limited publications'
       END as evidence_level
FROM gene_drug_interactions gdi
JOIN genes g ON gdi.gene_id = g.gene_id
LEFT JOIN gene_publications gp ON g.gene_id = gp.gene_id
WHERE g.gene_symbol = 'EGFR'
  AND gdi.clinical_phase = 'Approved'
GROUP BY gdi.drug_name, gdi.clinical_phase, gdi.activity_value, gdi.activity_unit, gdi.mechanism_of_action
ORDER BY publication_count DESC, gdi.activity_value;

-- High-affinity drug candidates with research depth
SELECT g.gene_symbol, gdi.drug_name, gdi.activity_value,
       gdi.activity_type, gdi.evidence_strength,
       COALESCE(COUNT(DISTINCT gp.pmid), 0) as publication_count,
       CASE
           WHEN COUNT(DISTINCT gp.pmid) >= 100000 THEN 'Extensively studied'
           WHEN COUNT(DISTINCT gp.pmid) >= 10000 THEN 'Well-studied'
           WHEN COUNT(DISTINCT gp.pmid) >= 1000 THEN 'Moderate evidence'
           ELSE 'Limited publications'
       END as evidence_level
FROM gene_drug_interactions gdi
JOIN genes g ON gdi.gene_id = g.gene_id
LEFT JOIN gene_publications gp ON g.gene_id = gp.gene_id
WHERE gdi.activity_type = 'IC50'
  AND gdi.activity_unit = 'nM'
  AND gdi.activity_value < 10
  AND gdi.evidence_strength >= 4
GROUP BY g.gene_symbol, gdi.drug_name, gdi.activity_value, gdi.activity_type, gdi.evidence_strength
ORDER BY publication_count DESC, gdi.activity_value;
```

### 6. Open Targets Integration Queries

```sql
-- Find cancer driver genes with drug tractability and evidence
SELECT g.gene_symbol, od.disease_name,
       ogda.overall_score, ogda.somatic_mutation_score,
       ott.sm_clinical_precedence, ott.ab_clinical_precedence,
       COALESCE(COUNT(DISTINCT gp.pmid), 0) as publication_count,
       CASE
           WHEN COUNT(DISTINCT gp.pmid) >= 100000 THEN 'Extensively studied'
           WHEN COUNT(DISTINCT gp.pmid) >= 10000 THEN 'Well-studied'
           WHEN COUNT(DISTINCT gp.pmid) >= 1000 THEN 'Moderate evidence'
           ELSE 'Limited publications'
       END as evidence_level
FROM opentargets_gene_disease_associations ogda
JOIN genes g ON ogda.gene_id = g.gene_id
JOIN opentargets_diseases od ON ogda.disease_id = od.disease_id
JOIN opentargets_target_tractability ott ON g.gene_id = ott.gene_id
LEFT JOIN gene_publications gp ON g.gene_id = gp.gene_id
WHERE od.is_cancer = true
  AND ogda.overall_score >= 0.7
  AND (ott.sm_clinical_precedence = true OR ott.ab_clinical_precedence = true)
GROUP BY g.gene_symbol, od.disease_name, ogda.overall_score, ogda.somatic_mutation_score,
         ott.sm_clinical_precedence, ott.ab_clinical_precedence
ORDER BY publication_count DESC, ogda.overall_score DESC;

-- Find drugs in clinical development with target research depth
SELECT okd.molecule_name, g.gene_symbol,
       okd.clinical_phase, okd.mechanism_of_action,
       COALESCE(COUNT(DISTINCT gp.pmid), 0) as publication_count,
       CASE
           WHEN COUNT(DISTINCT gp.pmid) >= 100000 THEN 'Extensively studied'
           WHEN COUNT(DISTINCT gp.pmid) >= 10000 THEN 'Well-studied'
           WHEN COUNT(DISTINCT gp.pmid) >= 1000 THEN 'Moderate evidence'
           ELSE 'Limited publications'
       END as evidence_level
FROM opentargets_known_drugs okd
JOIN genes g ON okd.target_gene_id = g.gene_id
JOIN opentargets_diseases od ON okd.disease_id = od.disease_id
LEFT JOIN gene_publications gp ON g.gene_id = gp.gene_id
WHERE od.disease_name ILIKE '%breast cancer%'
  AND okd.clinical_phase >= 2.0
GROUP BY okd.molecule_name, g.gene_symbol, okd.clinical_phase, okd.mechanism_of_action
ORDER BY publication_count DESC, okd.clinical_phase DESC;
```

### 7. Literature Mining

```sql
-- Find most-studied genes
SELECT g.gene_symbol, COUNT(*) as publication_count
FROM genes g
JOIN gene_publications gp ON g.gene_id = gp.gene_id
GROUP BY g.gene_symbol
ORDER BY publication_count DESC
LIMIT 50;

-- Gene co-occurrence in literature
SELECT g1.gene_symbol as gene_1, g2.gene_symbol as gene_2,
       COUNT(*) as shared_publications
FROM gene_publications gp1
JOIN gene_publications gp2 ON gp1.pmid = gp2.pmid AND gp1.gene_id < gp2.gene_id
JOIN genes g1 ON gp1.gene_id = g1.gene_id
JOIN genes g2 ON gp2.gene_id = g2.gene_id
WHERE g1.gene_symbol = 'TP53'
GROUP BY g1.gene_symbol, g2.gene_symbol
ORDER BY shared_publications DESC
LIMIT 20;
```

### 8. Cross-Reference Lookups

```sql
-- Find gene by UniProt accession
SELECT g.gene_id, g.gene_symbol
FROM gene_cross_references xr
JOIN genes g ON xr.gene_id = g.gene_id
WHERE xr.external_db = 'UniProt'
  AND xr.external_id = 'P04637';

-- Get all external IDs for a gene
SELECT xr.external_db, xr.external_id
FROM gene_cross_references xr
JOIN genes g ON xr.gene_id = g.gene_id
WHERE g.gene_symbol = 'BRCA1'
ORDER BY xr.external_db, xr.external_id;
```

### 9. Patient Database Queries (cancer_transcript_base)

```sql
-- Find actionable targets (upregulated + drugs available)
SELECT transcript_id, gene_symbol, expression_fold_change,
       drugs, drug_scores
FROM cancer_transcript_base
WHERE expression_fold_change > 2.0
  AND drugs IS NOT NULL
  AND jsonb_array_length(drugs) > 0
ORDER BY expression_fold_change DESC
LIMIT 50;

-- Enriched pathways in patient
SELECT unnest(pathways) as pathway_name,
       COUNT(*) as gene_count,
       AVG(expression_fold_change) as avg_expression
FROM cancer_transcript_base
WHERE expression_fold_change > 2.0
GROUP BY pathway_name
HAVING COUNT(*) >= 3
ORDER BY gene_count DESC, avg_expression DESC;
```

---

## Performance Optimization Tips

### Index Usage

1. **Always use indexed columns in WHERE clauses**:
   - `gene_symbol` for genes table
   - `transcript_id` for transcripts
   - `pmid` for publications
   - `pathway_id` for pathways

2. **Use EXPLAIN ANALYZE** to verify index usage:
```sql
EXPLAIN ANALYZE
SELECT * FROM genes WHERE gene_symbol = 'TP53';
```

3. **GIN indexes** are used for array and JSONB columns:
   - `pathways` arrays
   - `pmids` arrays
   - JSONB columns in cancer_transcript_base

### Query Optimization

1. **Use EXISTS instead of IN for large subqueries**:
```sql
-- Better
SELECT g.* FROM genes g
WHERE EXISTS (
  SELECT 1 FROM gene_pathways gp
  WHERE gp.gene_id = g.gene_id
    AND gp.pathway_name ILIKE '%DNA repair%'
);

-- Avoid for large result sets
SELECT g.* FROM genes g
WHERE g.gene_id IN (
  SELECT gene_id FROM gene_pathways
  WHERE pathway_name ILIKE '%DNA repair%'
);
```

2. **Use JOINs instead of nested queries** when possible

3. **Limit result sets** for exploratory queries:
```sql
SELECT * FROM gene_publications LIMIT 1000;
```

4. **Use partial indexes** for common filter patterns:
   - Cancer-only queries: `WHERE is_cancer = true`
   - High-confidence associations: `WHERE overall_score >= 0.7`

### Connection String for psql

```bash
psql -h localhost -p 5435 -U mbase_user -d mbase
```

Environment variable:
```bash
export PGPASSWORD=mbase_secret
```

---

## AI Agent Integration Guidelines

### Best Practices for LLM Queries

1. **Start with cancer_transcript_base for patient databases** - Single table contains all information

2. **Use specific gene symbols** when possible - Indexed and fast:
```sql
WHERE gene_symbol = 'TP53'  -- Good
WHERE gene_symbol ILIKE '%TP53%'  -- Slower
```

3. **Filter by confidence/quality scores** to reduce noise:
```sql
WHERE confidence_score >= 0.8
WHERE overall_score >= 0.7
WHERE evidence_strength >= 4
```

4. **Limit result sets** for large tables (especially gene_publications):
```sql
LIMIT 100  -- Add to exploratory queries
```

5. **Use JSONB operators** for complex queries on cancer_transcript_base:
```sql
-- Check if drugs exist
WHERE drugs IS NOT NULL AND drugs != '{}'::jsonb

-- Query nested JSONB
WHERE go_terms->>'molecular_function' IS NOT NULL

-- Array membership
WHERE 'kinase activity' = ANY(molecular_functions)
```

### Common AI Agent Query Templates

**Template 1: Find therapeutic targets in patient data with evidence**
```sql
SELECT ctb.transcript_id, ctb.gene_symbol, ctb.expression_fold_change,
       ctb.drugs, ctb.pathways, ctb.molecular_functions,
       COALESCE(COUNT(DISTINCT gp.pmid), 0) as publication_count,
       CASE
           WHEN COUNT(DISTINCT gp.pmid) >= 100000 THEN 'Extensively studied'
           WHEN COUNT(DISTINCT gp.pmid) >= 10000 THEN 'Well-studied'
           WHEN COUNT(DISTINCT gp.pmid) >= 1000 THEN 'Moderate evidence'
           ELSE 'Limited publications'
       END as evidence_level
FROM cancer_transcript_base ctb
JOIN genes g ON ctb.gene_id = g.gene_id
LEFT JOIN gene_publications gp ON g.gene_id = gp.gene_id
WHERE ctb.expression_fold_change > {THRESHOLD}
  AND ctb.drugs IS NOT NULL
GROUP BY ctb.transcript_id, ctb.gene_symbol, ctb.gene_id, ctb.expression_fold_change,
         ctb.drugs, ctb.pathways, ctb.molecular_functions
ORDER BY publication_count DESC, ctb.expression_fold_change DESC
LIMIT {LIMIT};
```

**Template 2: Gene function lookup**
```sql
SELECT g.gene_symbol, g.gene_name,
       array_agg(DISTINCT ga.annotation_value) FILTER (WHERE ga.annotation_type = 'molecular_function') as functions,
       array_agg(DISTINCT ga.annotation_value) FILTER (WHERE ga.annotation_type = 'cellular_location') as locations
FROM genes g
JOIN gene_annotations ga ON g.gene_id = ga.gene_id
WHERE g.gene_symbol = '{GENE_SYMBOL}'
GROUP BY g.gene_symbol, g.gene_name;
```

**Template 3: Pathway enrichment**
```sql
SELECT gp.pathway_name, COUNT(DISTINCT gp.gene_id) as gene_count
FROM gene_pathways gp
JOIN genes g ON gp.gene_id = g.gene_id
WHERE g.gene_symbol IN ({GENE_LIST})
GROUP BY gp.pathway_name
ORDER BY gene_count DESC;
```

**Template 4: Drug discovery for upregulated genes with evidence**
```sql
SELECT g.gene_symbol, t.expression_fold_change,
       gdi.drug_name, gdi.clinical_phase, gdi.mechanism_of_action,
       COALESCE(COUNT(DISTINCT gp.pmid), 0) as publication_count,
       CASE
           WHEN COUNT(DISTINCT gp.pmid) >= 100000 THEN 'Extensively studied'
           WHEN COUNT(DISTINCT gp.pmid) >= 10000 THEN 'Well-studied'
           WHEN COUNT(DISTINCT gp.pmid) >= 1000 THEN 'Moderate evidence'
           ELSE 'Limited publications'
       END as evidence_level
FROM transcripts t
JOIN genes g ON t.gene_id = g.gene_id
JOIN gene_drug_interactions gdi ON g.gene_id = gdi.gene_id
LEFT JOIN gene_publications gp ON g.gene_id = gp.gene_id
WHERE t.expression_fold_change > {THRESHOLD}
  AND gdi.clinical_phase IN ('Approved', 'Phase III')
GROUP BY g.gene_symbol, t.expression_fold_change, gdi.drug_name, gdi.clinical_phase, gdi.mechanism_of_action
ORDER BY publication_count DESC, t.expression_fold_change DESC;
```

### Error Handling

Common errors and solutions:

1. **"relation does not exist"**: Check table name spelling and case
2. **"column does not exist"**: Verify column name in schema
3. **"syntax error at or near"**: Check SQL syntax, especially quotes
4. **Slow query**: Add LIMIT, use indexed columns, check EXPLAIN ANALYZE

### Schema Discovery Queries

```sql
-- List all tables
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public' ORDER BY table_name;

-- Get column details for a table
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name = 'genes'
ORDER BY ordinal_position;

-- View table row counts
SELECT schemaname, relname, n_live_tup as row_count
FROM pg_stat_user_tables
WHERE schemaname = 'public'
ORDER BY n_live_tup DESC;
```

---

## Appendix: Data Source Documentation

### GENCODE
- **Website**: https://www.gencodegenes.org/
- **Version**: Human release (check schema_version for specific version)
- **Content**: Gene and transcript annotations, genomic coordinates

### UniProt
- **Website**: https://www.uniprot.org/
- **Content**: Protein function, product types, cellular locations
- **ID Format**: Accession (e.g., P04637 for TP53)

### Gene Ontology
- **Website**: http://geneontology.org/
- **Content**: Molecular functions, biological processes, cellular components
- **ID Format**: GO:xxxxxxx (e.g., GO:0005515)

### Reactome
- **Website**: https://reactome.org/
- **Content**: Biological pathways and reactions
- **ID Format**: R-HSA-xxxxxx (e.g., R-HSA-162582)

### DrugCentral
- **Website**: https://drugcentral.org/
- **Content**: Drug-target interactions, clinical phases, pharmacology

### ChEMBL
- **Website**: https://www.ebi.ac.uk/chembl/
- **Content**: Bioactive molecules, drug discovery data
- **ID Format**: CHEMBL followed by numbers

### PubTator Central
- **Website**: https://www.ncbi.nlm.nih.gov/research/pubtator/
- **Content**: Gene-literature associations from PubMed
- **Update Frequency**: Monthly

### Open Targets Platform
- **Website**: https://platform.opentargets.org/
- **Content**: Disease associations, drug tractability, clinical evidence
- **Version**: Check opentargets_metadata table

---

## Version History

### v1.0.1 (2025-11-25)
- Updated sample queries with v0.6.0.2 PMID evidence integration
- Added publication_count and evidence_level columns to clinical queries
- Enhanced drug discovery and disease association query examples
- Maintained backward compatibility with existing schema
- Updated 17 queries across 7 sections with literature evidence patterns
- Added evidence-level categorization (Extensively studied, Well-studied, Moderate evidence, Limited publications)

### v1.0.0_baseline (2025-11-19)
- Complete flattened baseline schema
- Normalized tables (genes, transcripts, annotations)
- PubTator Central literature integration (47M+ records)
- Open Targets Platform integration (diseases, associations, drugs, tractability)
- Schema cleanup and optimization
- Comprehensive LLM documentation
- No migrations required - single-step initialization

---

## Contact and Support

For questions about this schema or MEDIABASE:
- Check project README.md
- Review CLAUDE.md for development guidelines
- See ETL documentation in src/etl/
- Database connection: localhost:5435, database: mbase

---

**End of Schema Reference**
