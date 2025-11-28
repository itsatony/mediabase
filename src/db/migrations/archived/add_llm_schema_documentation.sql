-- =============================================================================
-- LLM-Optimized Schema Documentation
-- =============================================================================
-- Purpose: Add comprehensive field documentation optimized for LLM-based
--          natural language → SQL query translation
-- Target: Enable intelligent query generation by oncology-focused AI agents
-- Date: 2025-01-17
--
-- Documentation Format (3-layer architecture):
-- 1. Biological Concept - What is this field?
-- 2. Clinical Interpretation - What does it mean for patient care?
-- 3. Query Patterns - How to translate natural language → SQL
--
-- Usage: This documentation will be included in LLM system prompts to enable
--        efficient translation of clinical questions into database queries
-- =============================================================================

BEGIN;

-- =============================================================================
-- PART 1: NORMALIZED SCHEMA - GENES TABLE
-- =============================================================================

COMMENT ON TABLE genes IS
'Core gene annotations from GENCODE. Each row represents a unique human gene locus.

TABLE PURPOSE:
- Central reference table for all gene-related data
- Links transcripts, pathways, drugs, GO terms, and publications
- PRIMARY JOIN KEY: gene_id (Ensembl stable identifier)

COMMON QUERY PATTERNS:
- "Find genes on chromosome 17" → WHERE chromosome = ''17''
- "Find protein-coding genes" → WHERE gene_type = ''protein_coding''
- "Look up gene by symbol" → WHERE gene_symbol = ''TP53''
- "Find genes in a region" → WHERE chromosome = ''X'' AND start_position BETWEEN 1000000 AND 2000000';

COMMENT ON COLUMN genes.gene_id IS
'Ensembl gene identifier (format: ENSG00000######). Stable unique identifier for genomic locus.

USAGE GUIDANCE:
- PRIMARY JOIN KEY: Use for all database joins (transcripts, pathways, drugs, GO terms)
- STABLE ACROSS VERSIONS: Gene IDs remain consistent across GENCODE releases
- SPECIES-SPECIFIC: Always ENSG prefix for human genes
- VERSION SUFFIXES: Some IDs have .version suffix (e.g., ENSG00000141510.16) - strip for joins

QUERY PATTERNS:
- Find gene by symbol: SELECT gene_id FROM genes WHERE gene_symbol = ''TP53''
- Join to expression: JOIN transcripts ON genes.gene_id = transcripts.gene_id
- External DB lookup: JOIN gene_cross_references ON genes.gene_id = gene_cross_references.gene_id';

COMMENT ON COLUMN genes.gene_symbol IS
'Official HGNC gene symbol (e.g., TP53, BRCA1, EGFR). Human-readable gene name.

USAGE GUIDANCE:
- DISPLAY NAME: Always use gene_symbol for user-facing results
- NON-UNIQUE: Rare cases where symbols change or are reused (use gene_id for joins)
- CASE-SENSITIVE: Conventionally uppercase (e.g., TP53 not tp53)
- ALIASES EXIST: Check gene_annotations.aliases for alternative names

QUERY PATTERNS:
- "tumor protein 53" / "p53" → WHERE gene_symbol = ''TP53''
- "breast cancer genes" → WHERE gene_symbol IN (''BRCA1'', ''BRCA2'')
- "EGFR" / "epidermal growth factor receptor" → WHERE gene_symbol = ''EGFR''';

COMMENT ON COLUMN genes.gene_type IS
'Gene biotype classification from GENCODE (protein_coding, lncRNA, miRNA, pseudogene, etc.).

BIOLOGICAL CONTEXT:
- protein_coding: Genes that produce proteins (highest druggability)
- lncRNA: Long non-coding RNAs (regulatory, biomarker potential)
- miRNA: MicroRNAs (regulatory, biomarker potential)
- pseudogene: Non-functional gene copies (usually low clinical relevance)
- IG_*: Immunoglobulin genes (immune system, specialized clinical use)
- TR_*: T-cell receptor genes (immune system, specialized clinical use)

CLINICAL DRUGGABILITY:
- protein_coding: HIGH - most drugs target proteins
- lncRNA: LOW-MODERATE - emerging therapeutic targets
- miRNA: MODERATE - biomarker and therapeutic potential
- pseudogene: VERY LOW - rarely therapeutically relevant

QUERY PATTERNS:
- "protein-coding genes" / "genes that make proteins" → WHERE gene_type = ''protein_coding''
- "druggable genes" → WHERE gene_type = ''protein_coding''
- "non-coding RNAs" → WHERE gene_type LIKE ''%RNA''';

COMMENT ON COLUMN genes.chromosome IS
'Chromosome location (1-22, X, Y, MT). Genomic coordinate reference.

USAGE GUIDANCE:
- VALUES: ''1'' through ''22'', ''X'', ''Y'', ''MT'' (mitochondrial)
- NUMERIC SORTING: Use CASE WHEN for proper ordering (1, 2, ..., 22, X, Y, MT)
- CYTOGENETIC BANDS: See gene_annotations.cytogenetic_band for detailed location

QUERY PATTERNS:
- "genes on chromosome 17" → WHERE chromosome = ''17''
- "X-linked genes" → WHERE chromosome = ''X''
- "mitochondrial genes" → WHERE chromosome = ''MT''';

COMMENT ON COLUMN genes.start_position IS
'Gene start coordinate on chromosome (GRCh38/hg38 assembly, 1-based).

USAGE GUIDANCE:
- ASSEMBLY: GRCh38 (hg38) coordinates
- COORDINATE SYSTEM: 1-based (first base = 1, not 0)
- RANGES: Use BETWEEN for genomic region queries
- STRAND: Check gene.strand for orientation (+ or -)

QUERY PATTERNS:
- "genes in region" → WHERE chromosome = ''17'' AND start_position BETWEEN 7000000 AND 8000000
- "genes near position" → WHERE chromosome = ''X'' AND ABS(start_position - 123456789) < 100000';

-- =============================================================================
-- PART 2: NORMALIZED SCHEMA - TRANSCRIPTS TABLE
-- =============================================================================

COMMENT ON TABLE transcripts IS
'Gene transcript isoforms with patient-specific expression data. Each row represents one transcript variant.

TABLE PURPOSE:
- Links genes to their RNA transcript variants
- Stores patient-specific expression fold changes
- Enables isoform-level analysis and splice variant queries

CLINICAL WORKFLOW:
1. Identify overexpressed transcripts (expression_fold_change > 2.0)
2. Map to genes via gene_id
3. Query druggability via gene_drug_interactions
4. Check pathway enrichment via gene_pathways

QUERY PATTERNS:
- "overexpressed transcripts" → WHERE expression_fold_change > 2.0
- "transcripts for gene TP53" → WHERE gene_id IN (SELECT gene_id FROM genes WHERE gene_symbol = ''TP53'')';

COMMENT ON COLUMN transcripts.expression_fold_change IS
'Patient-specific expression relative to normal tissue reference (1.0 = baseline, linear scale).

CLINICAL INTERPRETATION THRESHOLDS:
≥10.0: EXTREME overexpression - very high priority oncogene candidate
       Action: Immediate therapeutic targeting if druggable
≥5.0:  HIGH overexpression - strong therapeutic target candidate
       Action: Prioritize for drug matching and pathway analysis
≥3.0:  MODERATE overexpression - consider if druggable or pathway-enriched
       Action: Include in combination therapy strategies
≥2.0:  MILD overexpression - biomarker potential, pathway analysis
       Action: Monitor for multi-evidence support
0.8-1.2: NORMAL range - no significant change from reference
≤0.5:  SIGNIFICANT underexpression - tumor suppressor loss (HIGH RISK)
       Action: Check for known tumor suppressors (TP53, RB1, PTEN)
≤0.2:  SEVERE loss - critical tumor suppressor loss
       Action: Urgent clinical correlation required

ONCOGENE VS TUMOR SUPPRESSOR LOGIC:
- Overexpression (>2.0) suggests ONCOGENE → Target with INHIBITORS
- Underexpression (<0.5) suggests TUMOR SUPPRESSOR loss → Cannot directly drug (consider synthetic lethality)

QUERY PATTERNS:
- "overexpressed genes" / "upregulated" → WHERE expression_fold_change > 2.0
- "highly overexpressed" / "extreme expression" → WHERE expression_fold_change > 5.0
- "tumor suppressor loss" / "TS loss" → WHERE expression_fold_change < 0.5 AND gene_symbol IN (''TP53'', ''RB1'', ''PTEN'', ''BRCA1'', ''BRCA2'')
- "significantly changed" → WHERE expression_fold_change NOT BETWEEN 0.8 AND 1.2

DATA FORMAT:
- Linear fold change (NOT log2)
- Default value of 1.0 indicates no patient data loaded (reference database)
- DESeq2 log2FoldChange values automatically converted: linear = 2^log2FC
- Infinite values capped at 1000.0 for numerical stability';

-- =============================================================================
-- PART 3: NORMALIZED SCHEMA - GENE_DRUG_INTERACTIONS TABLE
-- =============================================================================

COMMENT ON TABLE gene_drug_interactions IS
'Drug-gene target interactions with clinical development status and pharmacological data.

TABLE PURPOSE:
- Links genes to therapeutic compounds
- Provides clinical phase and approval status
- Stores activity measurements (IC50, Ki, Kd values)
- Enables actionable therapy recommendations

CLINICAL WORKFLOW FOR ACTIONABILITY:
1. Find overexpressed genes (FROM transcripts WHERE expression_fold_change > 2.0)
2. Match to approved drugs (FROM this table WHERE is_approved = true)
3. Filter by interaction type (e.g., inhibitor for overexpressed genes)
4. Rank by evidence strength and clinical phase

COMMON QUERY PATTERNS:
- "approved drugs for overexpressed genes" →
  JOIN with transcripts on gene_id, WHERE expression_fold_change > 2.0 AND is_approved = true
- "drugs in clinical trials" → WHERE clinical_phase IN (''1'', ''2'', ''3'')
- "kinase inhibitors" → WHERE drug_class LIKE ''%kinase inhibitor%''';

COMMENT ON COLUMN gene_drug_interactions.drug_name IS
'Therapeutic compound name (generic or brand name). May include drug class suffixes.

NAMING CONVENTIONS:
- Generic names preferred (e.g., "trastuzumab" over "Herceptin")
- May include suffixes like "-ib" (kinase inhibitors), "-mab" (monoclonal antibodies)
- Case varies (gemcitabine, Gemcitabine, GEMCITABINE) - use ILIKE for search

QUERY PATTERNS:
- "trastuzumab" / "Herceptin" → WHERE drug_name ILIKE ''%trastuzumab%''
- "kinase inhibitors" → WHERE drug_name LIKE ''%ib'' OR drug_class LIKE ''%kinase inhibitor%''
- "checkpoint inhibitors" → WHERE drug_name LIKE ''%mab'' AND drug_class LIKE ''%PD%'' OR drug_class LIKE ''%CTLA%''
- "all drugs for gene" → WHERE target_gene_id = (SELECT gene_id FROM genes WHERE gene_symbol = ''EGFR'')';

COMMENT ON COLUMN gene_drug_interactions.drug_chembl_id IS
'ChEMBL database identifier for cross-database lookups (format: CHEMBL#####).

USAGE GUIDANCE:
- PRIMARY EXTERNAL KEY: Use for linking to ChEMBL, PubChem, DrugBank
- FORMAT: CHEMBLdigits (e.g., CHEMBL1234567)
- STABILITY: ChEMBL IDs are stable across versions
- UNIQUE: One ChEMBL ID per molecular entity

QUERY PATTERNS:
- Cross-database lookup: WHERE drug_chembl_id = ''CHEMBL25''
- Find all records for a compound: WHERE drug_chembl_id IN (list_of_ids)';

COMMENT ON COLUMN gene_drug_interactions.clinical_phase IS
'Clinical development phase (0-4 scale). Indicates regulatory progress and treatment availability.

CLINICAL PHASE MEANINGS:
0 = Preclinical: Laboratory/animal studies only - NOT available for patients
    Interpretation: Experimental, years away from clinical use
1 = Phase I: First human trials, safety/dosing focus (20-100 patients)
    Interpretation: Investigational, may be available in phase I trials
2 = Phase II: Efficacy testing in target disease (100-300 patients)
    Interpretation: Promising but unproven, may be available in trials
3 = Phase III: Large confirmatory trials (300-3000+ patients)
    Interpretation: Strong evidence, likely to be approved soon
4 = Approved: FDA/EMA approved for clinical use
    Interpretation: ACTIONABLE - can be prescribed to patients

TREATMENT DECISION LOGIC:
- Phase 4 (Approved): Direct prescription possible
- Phase 3: Strong evidence, consider compassionate use or trial enrollment
- Phase 2: Moderate evidence, trial enrollment if available
- Phase 1: Weak evidence, only if no other options
- Phase 0: Not clinically relevant for patient treatment

QUERY PATTERNS:
- "approved drugs" / "FDA approved" → WHERE clinical_phase = ''4'' OR is_approved = true
- "drugs in trials" → WHERE clinical_phase IN (''1'', ''2'', ''3'')
- "actionable drugs" → WHERE clinical_phase = ''4''
- "experimental drugs" → WHERE clinical_phase IN (''0'', ''1'')';

COMMENT ON COLUMN gene_drug_interactions.interaction_type IS
'Mechanism of drug-gene interaction (inhibitor, agonist, antagonist, substrate, etc.).

MECHANISM TYPES & CLINICAL IMPLICATIONS:
- inhibitor/antagonist: BLOCKS gene/protein activity → Use for OVEREXPRESSED genes
- agonist: ACTIVATES gene/protein activity → Use for UNDEREXPRESSED genes (rare in cancer)
- substrate: Drug is metabolized by gene product → Pharmacokinetic concern, not therapeutic
- modulator: Alters activity without complete block/activation
- binder: Physical interaction without clear functional effect

THERAPEUTIC PAIRING LOGIC:
- Overexpressed oncogene (fold_change > 2.0) + inhibitor = ACTIONABLE MATCH
- Overexpressed oncogene + agonist = CONTRAINDICATED (would worsen cancer)
- Underexpressed tumor suppressor + inhibitor = CONTRAINDICATED (would worsen loss)

QUERY PATTERNS:
- "inhibitors for overexpressed genes" →
  WHERE interaction_type IN (''inhibitor'', ''antagonist'')
  AND gene_id IN (SELECT gene_id FROM transcripts WHERE expression_fold_change > 2.0)
- "drugs that block activity" → WHERE interaction_type IN (''inhibitor'', ''antagonist'')';

COMMENT ON COLUMN gene_drug_interactions.activity_value IS
'Pharmacological potency measurement (IC50, Ki, Kd) in numeric form.

ACTIVITY METRICS:
- IC50: Concentration causing 50% inhibition (lower = more potent)
- Ki: Inhibition constant (lower = stronger binding)
- Kd: Dissociation constant (lower = tighter binding)
- EC50: Effective concentration for 50% activation (agonists)

POTENCY INTERPRETATION (typically in nM or µM range):
<1 nM:       VERY HIGH potency - excellent drug candidate
1-10 nM:     HIGH potency - strong drug candidate
10-100 nM:   MODERATE potency - acceptable for clinical use
100-1000 nM: LOW potency - may require high doses
>1000 nM (>1 µM): VERY LOW potency - limited clinical utility

IMPORTANT: Always check activity_unit column to interpret values correctly.

QUERY PATTERNS:
- "highly potent drugs" → WHERE activity_value < 10 AND activity_unit = ''nM''
- "drugs with IC50 < 100nM" → WHERE activity_type = ''IC50'' AND activity_value < 100 AND activity_unit = ''nM''';

COMMENT ON COLUMN gene_drug_interactions.drug_class IS
'Therapeutic drug classification (e.g., "kinase inhibitor", "monoclonal antibody", "checkpoint inhibitor").

COMMON DRUG CLASSES IN ONCOLOGY:
- "kinase inhibitor" / "tyrosine kinase inhibitor": Small molecules targeting kinases (EGFR, ALK, etc.)
- "monoclonal antibody": Large molecules targeting surface proteins (trastuzumab, pembrolizumab)
- "checkpoint inhibitor": Immune checkpoint blockers (anti-PD-1, anti-PD-L1, anti-CTLA-4)
- "chemotherapy": Traditional cytotoxic agents
- "hormone therapy": Endocrine therapies (tamoxifen, aromatase inhibitors)
- "PARP inhibitor": Synthetic lethality for BRCA-mutant cancers

QUERY PATTERNS:
- "kinase inhibitors" / "TKIs" → WHERE drug_class LIKE ''%kinase inhibitor%''
- "checkpoint inhibitors" → WHERE drug_class LIKE ''%checkpoint%''
- "antibodies" → WHERE drug_class LIKE ''%antibody%''
- "targeted therapy" → WHERE drug_class NOT LIKE ''%chemotherapy%''';

-- =============================================================================
-- PART 4: NORMALIZED SCHEMA - GENE_PATHWAYS TABLE
-- =============================================================================

COMMENT ON TABLE gene_pathways IS
'Gene-pathway associations from Reactome with hierarchical organization and evidence codes.

TABLE PURPOSE:
- Links genes to biological pathways
- Enables pathway enrichment analysis
- Provides hierarchical pathway organization (parent-child relationships)
- Includes evidence quality metrics

CLINICAL APPLICATIONS:
- Pathway enrichment: Find pathways with multiple overexpressed genes
- Druggability assessment: Pathways with more druggable genes are better targets
- Mechanism of action: Understand how genes work together biologically

QUERY PATTERNS:
- "pathways for overexpressed genes" →
  WHERE gene_id IN (SELECT gene_id FROM transcripts WHERE expression_fold_change > 2.0)
- "enriched pathways" →
  GROUP BY pathway_id HAVING COUNT(*) > threshold';

COMMENT ON COLUMN gene_pathways.evidence_code IS
'Gene Ontology evidence code indicating data source quality and experimental validation level.

EVIDENCE HIERARCHY (highest to lowest confidence):
1. EXPERIMENTAL (direct evidence, gold-standard):
   - IDA: Inferred from Direct Assay (e.g., enzyme activity measured in lab)
   - IPI: Inferred from Physical Interaction (e.g., co-immunoprecipitation, yeast two-hybrid)
   - IMP: Inferred from Mutant Phenotype (e.g., knockout studies showing function loss)
   - IGI: Inferred from Genetic Interaction (e.g., synthetic lethality experiments)
   - IEP: Inferred from Expression Pattern (e.g., immunofluorescence localization)

2. COMPUTATIONAL (predicted but validated):
   - ISS: Inferred from Sequence/Structural Similarity (ortholog transfer with validation)
   - ISO: Inferred from Sequence Orthology (one-to-one ortholog mapping)
   - ISA: Inferred from Sequence Alignment (sequence motif identification)
   - ISM: Inferred from Sequence Model (protein domain match)

3. AUTHOR STATEMENT (literature-derived):
   - TAS: Traceable Author Statement (published experimental assertion)
   - NAS: Non-traceable Author Statement (review article claim)

4. CURATOR JUDGMENT:
   - IC: Inferred by Curator (expert manual review)
   - ND: No biological Data available (placeholder annotation)

5. AUTOMATIC (lowest confidence):
   - IEA: Inferred from Electronic Annotation (automated computational pipeline)

CONFIDENCE RANKING FOR CLINICAL DECISIONS:
- HIGH CONFIDENCE: IDA, IPI, IMP, IGI, IEP, TAS
- MODERATE CONFIDENCE: ISS, ISO, ISA, ISM, IC
- LOW CONFIDENCE: IEA, NAS, ND

QUERY PATTERNS:
- "experimentally validated pathways" →
  WHERE evidence_code IN (''IDA'', ''IPI'', ''IMP'', ''IGI'', ''IEP'')
- "high confidence pathways" →
  WHERE evidence_code NOT IN (''IEA'', ''ND'')
- "exclude low confidence" →
  WHERE evidence_code <> ''IEA''';

COMMENT ON COLUMN gene_pathways.confidence_score IS
'Data quality/confidence score (0.0-1.0 range). Composite metric of evidence strength.

SCORE INTERPRETATION:
≥0.9: VERY HIGH confidence - multiple lines of experimental evidence
≥0.7: HIGH confidence - strong experimental or multiple computational lines
≥0.5: MODERATE confidence - single computational or weak experimental evidence
≥0.3: LOW confidence - weak computational evidence
<0.3: VERY LOW confidence - automated annotation only

CLINICAL USE:
- For therapeutic decisions: Use confidence_score >= 0.7
- For hypothesis generation: Use confidence_score >= 0.5
- For comprehensive analysis: Include all but flag low scores

QUERY PATTERNS:
- "high confidence pathways" → WHERE confidence_score >= 0.7
- "validated pathways" → WHERE confidence_score >= 0.5';

-- =============================================================================
-- PART 5: NORMALIZED SCHEMA - TRANSCRIPT_GO_TERMS TABLE
-- =============================================================================

COMMENT ON TABLE transcript_go_terms IS
'Gene Ontology annotations linking transcripts to molecular functions, biological processes, and cellular components.

TABLE PURPOSE:
- Describes what proteins do (molecular function)
- Describes what processes they participate in (biological process)
- Describes where they are located (cellular component)

GO ASPECTS:
- F (molecular_function): What the protein DOES (e.g., "kinase activity", "DNA binding")
- P (biological_process): What the protein is INVOLVED IN (e.g., "cell cycle", "apoptosis")
- C (cellular_component): WHERE the protein IS FOUND (e.g., "nucleus", "membrane")

QUERY PATTERNS:
- "kinases" → WHERE go_name LIKE ''%kinase activity%'' AND aspect = ''F''
- "nuclear proteins" → WHERE go_name LIKE ''%nucleus%'' AND aspect = ''C''';

COMMIT;

-- =============================================================================
-- NOTE: Open Targets table documentation (opentargets_disease_associations,
-- opentargets_known_drugs) will be added via a separate migration after
-- the Open Targets ETL module has created those tables.
-- =============================================================================

-- =============================================================================
-- Verification: Extract schema documentation for LLM prompts
-- =============================================================================

-- To export documentation for LLM system prompts, run:
--
-- SELECT
--   table_name,
--   column_name,
--   obj_description((table_schema||''.''||table_name)::regclass, ''pg_class'') as table_description,
--   col_description((table_schema||''.''||table_name)::regclass, ordinal_position) as column_description
-- FROM information_schema.columns
-- WHERE table_schema = ''public''
--   AND table_name IN (''genes'', ''transcripts'', ''gene_pathways'', ''gene_drug_interactions'',
--                       ''transcript_go_terms'', ''opentargets_disease_associations'', ''opentargets_known_drugs'')
-- ORDER BY table_name, ordinal_position;
