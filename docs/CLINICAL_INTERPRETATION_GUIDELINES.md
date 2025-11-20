# Clinical Interpretation Guidelines for MEDIABASE

**Version:** 0.4.1
**Purpose:** Guide for interpreting gene expression, drug, and disease association data in clinical oncology contexts

---

## Overview

MEDIABASE integrates transcriptomic data with drug targets, disease associations, and biological pathways. This guide provides evidence-based thresholds and interpretation frameworks for translating database queries into clinical insights.

**Critical Disclaimer:** All recommendations generated using MEDIABASE must be reviewed by qualified oncologists before any patient care decisions. This database is a clinical decision support tool, not a replacement for clinical judgment.

---

## 1. Gene Expression Interpretation

### 1.1 Fold-Change Thresholds

Expression fold-change values in `cancer_transcript_base.expression_fold_change` represent the ratio of cancer tissue expression to normal tissue expression.

| Fold-Change Range | Clinical Significance | Priority | Clinical Action |
|-------------------|----------------------|----------|----------------|
| **> 5.0** | Strong overexpression | **HIGH** | Priority target - consider targeted therapy |
| **2.0 - 5.0** | Moderate overexpression | **MEDIUM** | Actionable target - evaluate drug availability |
| **1.2 - 2.0** | Mild overexpression | **LOW** | Monitor - may be relevant in combination |
| **0.8 - 1.2** | Baseline expression | N/A | No differential expression detected |
| **0.5 - 0.8** | Mild underexpression | **LOW** | Potential tumor suppressor loss |
| **0.2 - 0.5** | Moderate underexpression | **MEDIUM** | Investigate tumor suppressor function |
| **< 0.2** | Strong underexpression | **HIGH** | Significant loss - check for biallelic inactivation |

### 1.2 Interpreting DESeq2-Derived Data

MEDIABASE automatically converts DESeq2 `log2FoldChange` values to linear fold-change:

- **log2FoldChange = 2.0** → fold-change = 4.0 (4-fold overexpression)
- **log2FoldChange = -2.0** → fold-change = 0.25 (4-fold underexpression)

**Conversion formula:** `fold_change = 2^(log2FoldChange)`

**Important:** Always verify the source data format. If your input already contains linear fold-change values (not log2), do not apply additional conversion.

### 1.3 Clinical Context Considerations

- **Overexpression (>2.0):** Potential therapeutic targets, biomarkers for diagnosis
- **Underexpression (<0.5):** Tumor suppressor loss, resistance mechanisms
- **Housekeeping genes:** Fold-change near 1.0 is expected and not clinically actionable
- **Tissue specificity:** Some genes have naturally high expression in certain tissues

---

## 2. Drug Target Evaluation

### 2.1 Clinical Phase Classification

MEDIABASE integrates OpenTargets drug data with clinical phase information in `opentargets_known_drugs.clinical_phase_label`:

| Phase | Label | Clinical Availability | Recommendation |
|-------|-------|----------------------|----------------|
| **Phase IV** | FDA-approved | **Immediate use** | Prescribe per indication and tumor profile |
| **Phase III** | Late-stage trials | Clinical trial enrollment | Strong evidence - seek trial enrollment |
| **Phase II** | Mid-stage trials | Clinical trial enrollment | Moderate evidence - consider for refractory cases |
| **Phase I** | Early safety trials | Clinical trial enrollment | Limited evidence - salvage therapy only |
| **Preclinical** | Research stage | Not available | Research interest only - not for patient care |

### 2.2 Approved Drug Prioritization

**Query pattern for FDA-approved drugs:**
```sql
SELECT
    g.gene_symbol,
    ctb.expression_fold_change,
    okd.molecule_name,
    okd.mechanism_of_action,
    okd.clinical_phase_label
FROM cancer_transcript_base ctb
JOIN genes g ON ctb.gene_symbol = g.gene_symbol
JOIN opentargets_known_drugs okd ON g.gene_id = okd.target_gene_id
WHERE ctb.expression_fold_change > 2.0
  AND okd.is_approved = true
ORDER BY ctb.expression_fold_change DESC;
```

**Interpretation:**
- **Fold-change > 5.0 + Phase IV:** Immediate consideration for treatment
- **Fold-change 2.0-5.0 + Phase IV:** Secondary treatment option
- **Fold-change > 2.0 + Phase III:** Clinical trial enrollment recommended
- **Multiple drugs available:** Consider mechanism of action, side effect profile, drug interactions

### 2.3 Drug Mechanism of Action

`opentargets_known_drugs.mechanism_of_action` describes how drugs interact with targets:

| Mechanism Type | Example | Clinical Interpretation |
|----------------|---------|------------------------|
| **Inhibitor** | EGFR inhibitor | Blocks protein function - use for overexpressed targets |
| **Antagonist** | HER2 antagonist | Blocks receptor signaling - use for overexpressed receptors |
| **Antibody** | Anti-PD-1 antibody | Immune checkpoint blockade - consider TMB/PD-L1 status |
| **Modulator** | PARP modulator | Alters protein activity - check for DNA repair deficiency |
| **Agonist** | Rarely used in cancer | Activates target - limited oncology applications |

---

## 3. Disease Association Scoring

### 3.1 OpenTargets Association Scores

MEDIABASE includes gene-disease associations from OpenTargets in `opentargets_gene_disease_associations.overall_score`:

| Overall Score Range | Association Strength | Clinical Confidence | Action |
|---------------------|---------------------|---------------------|--------|
| **> 0.8** | Very strong | **High** | Definitive target - prioritize for treatment planning |
| **0.5 - 0.8** | Strong | **Medium-High** | Validated target - include in treatment options |
| **0.2 - 0.5** | Moderate | **Medium** | Secondary target - consider if primary targets unavailable |
| **< 0.2** | Weak | **Low** | Exploratory only - deprioritize for active treatment |

### 3.2 Evidence Type Interpretation

OpenTargets provides multiple evidence streams (see `OPENTARGETS_PLATFORM_GUIDE.md` for full details):

| Evidence Type | Column | Interpretation |
|---------------|--------|----------------|
| **Somatic mutations** | `somatic_mutation_score` | Driver mutations - high confidence for causality |
| **Literature** | `literature_score` | Publication support - breadth of research |
| **Drugs** | `drug_evidence_score` | Clinical validation - drugs targeting this association |
| **Overall** | `overall_score` | Composite score - use as primary confidence metric |

**Important:** In the current MEDIABASE integration (v0.4.1), some evidence streams like `somatic_mutation_score` and `literature_score` may be NULL. Use `overall_score` as the primary confidence metric.

### 3.3 Disease Specificity

**Query for cancer-specific associations:**
```sql
SELECT
    g.gene_symbol,
    ctb.expression_fold_change,
    ogda.disease_name,
    ogda.overall_score
FROM cancer_transcript_base ctb
JOIN genes g ON ctb.gene_symbol = g.gene_symbol
JOIN opentargets_gene_disease_associations ogda ON g.gene_id = ogda.gene_id
WHERE ctb.expression_fold_change > 2.0
  AND ogda.disease_name ILIKE '%cancer%'
  AND ogda.overall_score > 0.5
ORDER BY ogda.overall_score DESC;
```

**Interpretation tips:**
- **Broad terms (e.g., "cancer"):** General associations - consider tissue-specific evidence
- **Specific terms (e.g., "colorectal cancer"):** High relevance - prioritize for matching tumor types
- **Multiple diseases:** Gene may be involved in multiple pathways - check for overlap

---

## 4. Actionability Scoring Framework

### 4.1 Composite Actionability Score

Combine multiple data sources to calculate an **Actionability Score (0-100)**:

| Component | Weight | Source |
|-----------|--------|--------|
| **Expression Level** | 30 points | `expression_fold_change` |
| **Drug Availability** | 25 points | `opentargets_known_drugs.clinical_phase_label` |
| **Disease Association** | 20 points | `opentargets_gene_disease_associations.overall_score` |
| **Literature Support** | 15 points | `gene_publications` count |
| **Pathway Membership** | 10 points | `gene_pathways` count |

### 4.2 Scoring Algorithm

**Expression Level (0-30 points):**
- Fold-change > 10.0: **30 points**
- Fold-change 5.0-10.0: **25 points**
- Fold-change 2.0-5.0: **15 points**
- Fold-change < 2.0: **0 points**

**Drug Availability (0-25 points):**
- Phase IV (FDA-approved): **25 points**
- Phase III: **18 points**
- Phase II: **10 points**
- Phase I: **5 points**
- No drug available: **0 points**

**Disease Association (0-20 points):**
- Overall score > 0.8: **20 points**
- Overall score 0.5-0.8: **15 points**
- Overall score 0.2-0.5: **8 points**
- Overall score < 0.2: **0 points**

**Literature Support (0-15 points):**
- Publications > 1000: **15 points**
- Publications 500-1000: **12 points**
- Publications 100-500: **8 points**
- Publications 10-100: **4 points**
- Publications < 10: **0 points**

**Pathway Membership (0-10 points):**
- Pathways > 10: **10 points**
- Pathways 5-10: **8 points**
- Pathways 1-5: **5 points**
- No pathways: **0 points**

### 4.3 Actionability Tiers

| Score Range | Tier | Clinical Priority | Recommendation |
|-------------|------|-------------------|----------------|
| **80-100** | Tier 1 | **Immediate** | FDA-approved drugs + strong evidence - prioritize for treatment |
| **60-79** | Tier 2 | **High** | Clinical trial options or off-label use - discuss with tumor board |
| **40-59** | Tier 3 | **Medium** | Emerging targets - consider if Tier 1/2 options exhausted |
| **20-39** | Tier 4 | **Low** | Exploratory - monitor for new drug development |
| **< 20** | Non-actionable | N/A | Research interest only - not for active treatment planning |

### 4.4 Example Actionability Calculation

**Gene:** ERBB2 (HER2)
**Expression:** 8.5-fold overexpression
**Drug:** Trastuzumab (FDA-approved, Phase IV)
**Disease Association:** 0.85 (breast cancer)
**Publications:** 5,200 publications
**Pathways:** 14 pathways

**Calculation:**
- Expression (8.5-fold): **25 points**
- Drug (Phase IV): **25 points**
- Disease (0.85): **20 points**
- Literature (5,200): **15 points**
- Pathways (14): **10 points**
- **Total: 95/100** → **Tier 1 (Immediate priority)**

---

## 5. Clinical Decision-Making Workflow

### 5.1 Step-by-Step Query Workflow

**Step 1: Identify overexpressed genes**
```sql
SELECT gene_symbol, expression_fold_change
FROM cancer_transcript_base
WHERE expression_fold_change > 2.0
ORDER BY expression_fold_change DESC;
```

**Step 2: Find FDA-approved drugs for top genes**
```sql
SELECT
    ctb.gene_symbol,
    ctb.expression_fold_change,
    okd.molecule_name,
    okd.mechanism_of_action
FROM cancer_transcript_base ctb
JOIN genes g ON ctb.gene_symbol = g.gene_symbol
JOIN opentargets_known_drugs okd ON g.gene_id = okd.target_gene_id
WHERE ctb.expression_fold_change > 2.0
  AND okd.is_approved = true;
```

**Step 3: Check disease relevance**
```sql
SELECT
    ctb.gene_symbol,
    ogda.disease_name,
    ogda.overall_score
FROM cancer_transcript_base ctb
JOIN genes g ON ctb.gene_symbol = g.gene_symbol
JOIN opentargets_gene_disease_associations ogda ON g.gene_id = ogda.gene_id
WHERE ctb.expression_fold_change > 2.0
  AND ogda.disease_name ILIKE '%<cancer_type>%'
  AND ogda.overall_score > 0.5;
```

**Step 4: Calculate actionability scores** (see Section 4.2)

**Step 5: Rank targets by actionability tier** (see Section 4.3)

### 5.2 Interpretation Checklist

Before making clinical recommendations based on MEDIABASE queries:

- [ ] **Expression validation:** Verify fold-change thresholds are appropriate for tissue type
- [ ] **Drug indication:** Confirm FDA-approved drugs are indicated for this cancer type
- [ ] **Disease relevance:** Check that disease associations match patient's tumor type
- [ ] **Mechanism of action:** Ensure drug mechanism is appropriate for overexpressed target
- [ ] **Literature support:** Review publication count for target validation
- [ ] **Pathway context:** Consider dysregulated pathways for combination therapy
- [ ] **Contraindications:** Check patient comorbidities and drug interactions (external to MEDIABASE)
- [ ] **Tumor board review:** Discuss findings with multidisciplinary team

### 5.3 Common Query Patterns

See `MEDIABASE_QUERY_LIBRARY.md` for 25 validated production queries covering:
- FDA-approved drug recommendations
- Pathway enrichment analysis
- Disease association profiling
- Drug repurposing opportunities
- Combination therapy identification
- Biomarker panel generation

---

## 6. Biological Context Integration

### 6.1 GO Terms and Pathway Analysis

**GO Term Enrichment:**
- Use `transcript_go_terms` to identify biological processes enriched in overexpressed genes
- High GO term count (>20) suggests pleiotropic effects - use caution
- Focus on GO terms related to cancer hallmarks (proliferation, apoptosis resistance, angiogenesis)

**Reactome Pathway Analysis:**
- Use `gene_pathways` to identify dysregulated signaling cascades
- Multiple genes in same pathway → consider pathway inhibitors
- Pathway crosstalk → potential for combination therapy

**Example query:**
```sql
SELECT
    gp.pathway_name,
    COUNT(DISTINCT ctb.gene_id) as dysregulated_genes
FROM cancer_transcript_base ctb
JOIN genes g ON ctb.gene_symbol = g.gene_symbol
JOIN gene_pathways gp ON g.gene_id = gp.gene_id
WHERE ctb.expression_fold_change > 2.0 OR ctb.expression_fold_change < 0.5
GROUP BY gp.pathway_name
ORDER BY dysregulated_genes DESC
LIMIT 10;
```

### 6.2 Literature Evidence Evaluation

**Publication Count Interpretation:**
- **> 1,000 publications:** Well-studied target - high confidence in mechanism
- **100-1,000:** Moderate evidence - review key publications
- **< 100:** Emerging target - may lack clinical validation

**Query for literature-supported targets:**
```sql
SELECT
    g.gene_symbol,
    COUNT(gp.pmid) as publication_count
FROM cancer_transcript_base ctb
JOIN genes g ON ctb.gene_symbol = g.gene_symbol
JOIN gene_publications gp ON g.gene_id = gp.gene_id
WHERE ctb.expression_fold_change > 2.0
GROUP BY g.gene_symbol
HAVING COUNT(gp.pmid) > 100
ORDER BY publication_count DESC;
```

### 6.3 Target Tractability Assessment

MEDIABASE includes OpenTargets tractability data in `opentargets_target_tractability`:

| Tractability Category | Description | Clinical Implication |
|----------------------|-------------|---------------------|
| **Small molecule** | Druggable with small molecules | Oral therapy possible - better patient compliance |
| **Antibody** | Druggable with antibodies | Infusion required - high specificity |
| **Clinical precedence** | Similar targets successfully drugged | High confidence in druggability |
| **Discovery precedence** | Preclinical evidence | Lower confidence - monitor for new drugs |

**Query for tractable targets:**
```sql
SELECT
    g.gene_symbol,
    ctb.expression_fold_change,
    ott.small_molecule,
    ott.antibody,
    ott.clinical_precedence
FROM cancer_transcript_base ctb
JOIN genes g ON ctb.gene_symbol = g.gene_symbol
JOIN opentargets_target_tractability ott ON g.gene_id = ott.gene_id
WHERE ctb.expression_fold_change > 2.0
  AND (ott.small_molecule = true OR ott.antibody = true)
ORDER BY ctb.expression_fold_change DESC;
```

---

## 7. Special Considerations

### 7.1 Tumor Suppressor Genes

For underexpressed genes (fold-change < 0.5):
- **Biallelic inactivation:** Check for homozygous deletion or mutation + LOH
- **Haploinsufficiency:** Single copy loss may be sufficient for loss of function
- **Synthetic lethality:** Identify dependencies that can be therapeutically exploited

**Common tumor suppressors to monitor:**
- TP53 (p53 pathway)
- PTEN (PI3K/AKT pathway)
- RB1 (cell cycle regulation)
- BRCA1/BRCA2 (DNA repair)
- CDKN2A (p16/INK4a)

### 7.2 Drug Resistance Mechanisms

Check for known resistance genes:
- **KRAS/NRAS mutations:** Resistance to EGFR inhibitors
- **MET amplification:** Resistance to EGFR/ALK inhibitors
- **PIK3CA mutations:** Resistance to HER2 inhibitors
- **BRAF mutations:** Resistance to EGFR inhibitors in colorectal cancer

### 7.3 Combination Therapy Opportunities

Identify multiple actionable targets for combination therapy:
- **Parallel pathways:** Target redundant signaling (e.g., EGFR + MET)
- **Sequential pathway:** Target upstream + downstream (e.g., RAS + MAPK)
- **Immune + targeted:** Combine checkpoint inhibitors with targeted therapy

---

## 8. Clinical Case Examples

### 8.1 HER2+ Breast Cancer

**Patient profile:** ER-/PR-/HER2+ breast cancer
**Top findings:** ERBB2 fold-change = 12.5

**Interpretation:**
- Expression: 12.5-fold → **30 points** (Tier 1)
- Drug availability: Trastuzumab (Phase IV) → **25 points**
- Disease association: 0.85 → **20 points**
- Literature: 5,200 publications → **15 points**
- **Total: 90/100 → Tier 1 (Immediate priority)**

**Clinical recommendation:** Trastuzumab-based therapy (first-line standard of care)

See `BREAST_CANCER_HER2_GUIDE.md` for complete workflow.

### 8.2 MSS Colorectal Cancer

**Patient profile:** Microsatellite stable (MSS) colorectal cancer
**Top findings:** KRAS fold-change = 6.2, BRAF fold-change = 0.8

**Interpretation:**
- KRAS overexpression + no EGFR inhibitor response expected
- Check MEK inhibitors (downstream of KRAS)
- Evaluate multi-kinase inhibitors (regorafenib, TAS-102)

See `COLORECTAL_CANCER_GUIDE.md` for complete workflow.

---

## 9. Quality Control and Validation

### 9.1 Data Quality Checks

Before interpreting results:
- [ ] Verify patient database was created correctly (see `create_patient_copy.py`)
- [ ] Check that fold-change values are reasonable (not all near 1.0 or all extreme)
- [ ] Confirm gene symbol mapping success rate >95%
- [ ] Validate that cancer_transcript_base has >100 genes with fold-change data

### 9.2 Biological Plausibility

Red flags that suggest data quality issues:
- **All genes overexpressed:** Possible normalization error
- **Housekeeping genes dysregulated:** Check reference sample quality
- **No known oncogenes/suppressors:** Incomplete data or wrong tissue comparison
- **Contradictory findings:** ERBB2 underexpressed in HER2+ tumor → data error

### 9.3 External Validation

Complement MEDIABASE findings with:
- **IHC/FISH validation:** Protein-level confirmation for key targets
- **Genomic profiling:** Mutation and copy number analysis
- **Clinical guidelines:** NCCN, ESMO, ASCO recommendations
- **Tumor board consensus:** Multidisciplinary review

---

## 10. Limitations and Caveats

### 10.1 Database Limitations

**OpenTargets integration (v0.4.1):**
- Some evidence scores (e.g., `somatic_mutation_score`) may be NULL
- Use `overall_score` as primary confidence metric
- Drug-target mappings use `target_gene_id` (TEXT), not `gene_id` (INTEGER)

**Gene symbol mapping:**
- Some transcripts may have ambiguous gene symbols
- Alternative transcripts may have different expression levels
- Use `GENCODE_REFERENCE.md` for transcript ID disambiguation

**Literature data:**
- Publication counts do not include full abstracts
- Mention counts may include false positives
- Bias toward well-studied genes

### 10.2 Clinical Interpretation Caveats

**Fold-change thresholds:**
- Tissue-specific expression patterns may require adjusted thresholds
- Technical batch effects can introduce false positives
- Single-patient data lacks statistical significance testing

**Drug recommendations:**
- FDA approval does not guarantee efficacy in all cancer types
- Off-label use requires careful justification
- Drug interactions and contraindications not captured in MEDIABASE

**Disease associations:**
- Scores reflect population-level evidence, not individual patient applicability
- Rare tumor subtypes may lack adequate representation
- Molecular subtyping (e.g., HER2+, MSI-H) not automatically inferred

---

## 11. Resources and Further Reading

### MEDIABASE Documentation
- **[Schema Reference](MEDIABASE_SCHEMA_REFERENCE.md)** - Complete database schema
- **[Query Library](MEDIABASE_QUERY_LIBRARY.md)** - 25 production-ready queries
- **[OpenTargets Guide](OPENTARGETS_PLATFORM_GUIDE.md)** - Drug and disease association details
- **[AI Agent Integration](AI_AGENT_INTEGRATION_GUIDE.md)** - LLM integration patterns

### Clinical Guidelines
- **[Breast Cancer HER2 Guide](BREAST_CANCER_HER2_GUIDE.md)** - HER2+ workflow
- **[Colorectal Cancer Guide](COLORECTAL_CANCER_GUIDE.md)** - MSS CRC workflow

### External Resources
- **OpenTargets Platform:** [https://www.targetvalidation.org/](https://www.targetvalidation.org/)
- **NCCN Guidelines:** [https://www.nccn.org/professionals/physician_gls/](https://www.nccn.org/professionals/physician_gls/)
- **ClinicalTrials.gov:** [https://clinicaltrials.gov/](https://clinicaltrials.gov/)
- **My Cancer Genome:** [https://www.mycancergenome.org/](https://www.mycancergenome.org/)

---

## 12. Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.4.1 | 2025-01-20 | Initial clinical interpretation guidelines with OpenTargets integration |

---

## 13. Contact and Support

For questions about clinical interpretation:
- Review example queries in `MEDIABASE_QUERY_LIBRARY.md`
- Consult disease-specific guides (HER2+ breast, MSS CRC)
- Check OpenTargets documentation for scoring details

For technical issues:
- See `CLAUDE.md` for development guidelines
- GitHub issues: [https://github.com/itsatony/mediabase/issues](https://github.com/itsatony/mediabase/issues)

---

**Important:** All clinical recommendations must be reviewed by qualified oncologists. MEDIABASE is a research and clinical decision support tool, not a substitute for clinical expertise.

*Generated with [Claude Code](https://claude.com/claude-code)*
