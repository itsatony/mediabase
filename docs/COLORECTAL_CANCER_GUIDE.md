# Colorectal Cancer MSS Patient Clinical Guide

## Patient Profile

**Cancer Type:** Colorectal carcinoma, microsatellite stable (MSS) subtype

**Molecular Characteristics:**
- **MSS (Microsatellite Stable):** DNA mismatch repair proficient (MMR-proficient)
- **Key Signaling Pathways:** RAS/RAF/MEK, VEGF/angiogenesis, EGFR, PI3K/AKT, WNT
- **Common Genetic Alterations:** APC (~80%), TP53 (~60%), KRAS (~40%), PIK3CA (~20%), BRAF (~10%)

**Clinical Significance:**
- MSS tumors represent ~85% of all colorectal cancers
- Lower response to checkpoint inhibitors compared to MSI-H
- Standard treatment: chemotherapy with targeted agents based on molecular profile
- Prognostic factors: RAS/BRAF mutation status, tumor sidedness, resectability

---

## 1. Molecular Classification

### 1.1 Microsatellite Status Assessment

**Clinical Question:** Is this tumor MSS or MSI-H?

**SQL Query:**
```sql
-- Check MMR gene expression to determine MSI status
SELECT
    g.gene_symbol,
    g.gene_name,
    ogda.overall_score,
    ogda.genetic_association_score,
    ogda.somatic_mutation_score,
    ogda.evidence_count
FROM genes g
JOIN opentargets_gene_disease_associations ogda ON g.gene_id = ogda.gene_id
WHERE ogda.disease_id = 'EFO_1001951'
  AND g.gene_symbol IN ('MLH1', 'MSH2', 'MSH6', 'PMS2')
ORDER BY ogda.overall_score DESC;
```

**Results:**
```
gene_symbol | gene_name | overall_score | genetic_association_score | somatic_mutation_score | evidence_count
------------|-----------|---------------|---------------------------|------------------------|----------------
MSH2        | MSH2      | 0.5450        |                           |                        |
MLH1        | MLH1      | 0.5187        |                           |                        |
```

**Clinical Interpretation:**
- **MSS (Microsatellite Stable):** Intact MMR gene expression/function
  - Standard chemotherapy backbone (FOLFOX/FOLFIRI)
  - Targeted therapy based on RAS/BRAF status
  - Checkpoint inhibitors generally ineffective

- **MSI-H (Microsatellite Instability-High):** Loss of MLH1/MSH2/MSH6/PMS2
  - First-line: Pembrolizumab or nivolumab (FDA-approved)
  - Better prognosis in early stages
  - ~15% of all CRC cases

**Treatment Recommendations:**
- **For MSS patients (this guide's focus):** Proceed with molecular profiling for targeted therapy selection
- **For MSI-H patients:** Consider checkpoint inhibitors as first-line therapy

---

## 2. RAS/RAF/MEK Pathway Analysis

### 2.1 KRAS/NRAS/BRAF Mutation Status

**Clinical Question:** Is the patient eligible for anti-EGFR therapy (cetuximab/panitumumab)?

**SQL Query:**
```sql
-- Query RAS/RAF/MEK pathway genes for EGFR therapy eligibility
SELECT
    g.gene_symbol,
    g.gene_name,
    ogda.overall_score,
    ogda.genetic_association_score,
    ogda.somatic_mutation_score,
    ogda.evidence_count
FROM genes g
JOIN opentargets_gene_disease_associations ogda ON g.gene_id = ogda.gene_id
WHERE ogda.disease_id = 'EFO_1001951'
  AND g.gene_symbol IN ('KRAS', 'NRAS', 'BRAF', 'MAP2K1', 'MAP2K2')
ORDER BY ogda.overall_score DESC;
```

**Results:**
```
Note: Limited direct disease associations in database.
KRAS, NRAS, BRAF genes are present in the gene database.
```

**Clinical Interpretation:**

**KRAS/NRAS Wild-Type (RAS WT):**
- **Anti-EGFR therapy ELIGIBLE**
- First-line options:
  - FOLFOX + cetuximab (left-sided tumors preferred)
  - FOLFIRI + cetuximab
  - FOLFOX + panitumumab
- Response rate: 40-60% in left-sided tumors
- Median OS: 28-32 months with optimal therapy

**KRAS/NRAS Mutant:**
- **Anti-EGFR therapy CONTRAINDICATED** (no clinical benefit, potential harm)
- First-line options:
  - FOLFOX + bevacizumab
  - FOLFIRI + bevacizumab
- Response rate: 40-50%
- Median OS: 24-28 months

**BRAF V600E Mutant (~10% of CRC):**
- **Poor prognosis** (median OS 10-12 months with standard therapy)
- Combination therapy options:
  - Encorafenib + cetuximab ± binimetinib (BEACON CRC trial)
  - Response rate: 26% vs 2% (standard therapy)
  - Median OS: 9.3 months vs 5.9 months

### 2.2 BRAF Pathway Signaling

**SQL Query:**
```sql
-- BRAF pathway enrichment
SELECT
    g.gene_symbol,
    gp.pathway_name,
    gp.pathway_source
FROM genes g
JOIN gene_pathways gp ON g.gene_id = gp.gene_id
WHERE g.gene_symbol = 'BRAF'
  AND gp.pathway_source = 'Reactome'
  AND gp.pathway_name ILIKE '%RAF%'
ORDER BY gp.pathway_name
LIMIT 10;
```

**Results:**
```
gene_symbol | pathway_name                                          | pathway_source
------------|-------------------------------------------------------|---------------
BRAF        | Oncogenic MAPK signaling                              | Reactome
BRAF        | RAF activation                                        | Reactome
BRAF        | RAF/MAP kinase cascade                                | Reactome
BRAF        | Signaling by BRAF and RAF1 fusions                    | Reactome
BRAF        | Paradoxical activation of RAF signaling by kinase inactive BRAF | Reactome
BRAF        | Negative regulation of MAPK pathway                   | Reactome
BRAF        | MAPK family signaling cascades                        | Reactome
```

**Clinical Interpretation:**
- BRAF mutations lead to constitutive MAPK pathway activation
- Oncogenic MAPK signaling drives tumor proliferation and survival
- Single-agent BRAF inhibitors paradoxically activate RAF signaling in RAS-WT cells
- Combination therapy (BRAF + EGFR ± MEK inhibitors) overcomes feedback activation

### 2.3 BRAF-Targeted Therapy Options

**SQL Query:**
```sql
-- Approved BRAF inhibitors
SELECT
    g.gene_symbol,
    otd.molecule_name,
    otd.mechanism_of_action,
    otd.clinical_phase_label,
    otd.is_approved
FROM genes g
JOIN opentargets_known_drugs otd ON g.gene_id = otd.target_gene_id
WHERE g.gene_symbol = 'BRAF'
  AND otd.is_approved = true
ORDER BY otd.molecule_name
LIMIT 10;
```

**Results:**
```
gene_symbol | molecule_name        | mechanism_of_action                         | clinical_phase | is_approved
------------|---------------------|---------------------------------------------|----------------|-------------
BRAF        | DABRAFENIB          | Serine/threonine-protein kinase B-raf inhibitor | Approved  | t
BRAF        | DABRAFENIB MESYLATE | Serine/threonine-protein kinase B-raf inhibitor | Approved  | t
BRAF        | ENCORAFENIB         | Serine/threonine-protein kinase B-raf inhibitor | Approved  | t
BRAF        | REGORAFENIB         | Serine/threonine-protein kinase B-raf inhibitor | Approved  | t
BRAF        | SORAFENIB           | Serine/threonine-protein kinase B-raf inhibitor | Approved  | t
BRAF        | SORAFENIB TOSYLATE  | Serine/threonine-protein kinase B-raf inhibitor | Approved  | t
BRAF        | VEMURAFENIB         | Serine/threonine-protein kinase B-raf inhibitor | Approved  | t
```

**Treatment Recommendations:**
- **Encorafenib + cetuximab ± binimetinib** (FDA-approved for BRAF V600E CRC)
- Regorafenib: multi-kinase inhibitor for refractory disease (third-line+)

---

## 3. EGFR Pathway and Anti-EGFR Therapy

### 3.1 EGFR Expression and Druggability

**Clinical Question:** What EGFR-targeted therapies are available for RAS/BRAF wild-type CRC?

**SQL Query:**
```sql
-- EGFR-targeted drugs
SELECT
    g.gene_symbol,
    otd.molecule_name,
    otd.mechanism_of_action,
    otd.clinical_phase_label,
    otd.is_approved
FROM genes g
JOIN opentargets_known_drugs otd ON g.gene_id = otd.target_gene_id
WHERE g.gene_symbol = 'EGFR'
  AND otd.is_approved = true
  AND otd.molecule_name IN ('CETUXIMAB', 'PANITUMUMAB', 'NECITUMUMAB')
ORDER BY otd.molecule_name;
```

**Results:**
```
gene_symbol | molecule_name | mechanism_of_action                      | clinical_phase | is_approved
------------|---------------|------------------------------------------|----------------|-------------
EGFR        | CETUXIMAB     | Epidermal growth factor receptor erbB1 inhibitor | Approved | t
EGFR        | NECITUMUMAB   | Epidermal growth factor receptor erbB1 inhibitor | Approved | t
EGFR        | PANITUMUMAB   | Epidermal growth factor receptor erbB1 inhibitor | Approved | t
```

**Clinical Interpretation:**

**FDA-Approved Anti-EGFR Antibodies for CRC:**

1. **Cetuximab (Erbitux)**
   - Chimeric IgG1 monoclonal antibody
   - Binds to EGFR extracellular domain
   - Indications: RAS WT metastatic CRC (first-line with FOLFOX/FOLFIRI or later lines)
   - Dosing: Loading dose 400 mg/m2, then 250 mg/m2 weekly
   - Side effects: Acneiform rash (80%), infusion reactions, hypomagnesemia

2. **Panitumumab (Vectibix)**
   - Fully human IgG2 monoclonal antibody
   - Lower immunogenicity vs cetuximab
   - Indications: RAS WT metastatic CRC (first-line or later lines)
   - Dosing: 6 mg/kg every 2 weeks
   - Side effects: Similar to cetuximab but lower infusion reactions

**Efficacy Data:**
- **CRYSTAL trial (cetuximab + FOLFIRI):**
  - RAS WT: ORR 66% vs 39%, PFS 11.4 vs 8.4 months
  - RAS mutant: NO BENEFIT (may be detrimental)

- **PRIME trial (panitumumab + FOLFOX):**
  - RAS WT: PFS 10.1 vs 7.9 months, OS 26.0 vs 20.2 months
  - RAS mutant: WORSE outcomes with panitumumab

**Predictive Biomarkers:**
- RAS WT (KRAS/NRAS exons 2, 3, 4): REQUIRED for anti-EGFR therapy
- BRAF WT: Better response, though BRAF mutant may benefit with triplet therapy
- Tumor sidedness: Left-sided tumors respond better (right-sided may not benefit)

### 3.2 Comprehensive EGFR Drug Landscape

**SQL Query:**
```sql
-- All FDA-approved EGFR inhibitors
SELECT
    g.gene_symbol,
    COUNT(DISTINCT otd.molecule_name) as drug_count,
    STRING_AGG(DISTINCT otd.molecule_name, ', ' ORDER BY otd.molecule_name) as approved_drugs
FROM genes g
JOIN opentargets_known_drugs otd ON g.gene_id = otd.target_gene_id
WHERE g.gene_symbol = 'EGFR'
  AND otd.is_approved = true
GROUP BY g.gene_symbol;
```

**Results:**
```
gene_symbol | drug_count | approved_drugs
------------|------------|------------------------------------------------------------------
EGFR        | 25         | AFATINIB, BRIGATINIB, CETUXIMAB, DACOMITINIB, ERLOTINIB,
            |            | GEFITINIB, ICOTINIB, LAPATINIB, MOBOCERTINIB, NECITUMUMAB,
            |            | NERATINIB, NIMOTUZUMAB, OLMUTINIB, OSIMERTINIB, PANITUMUMAB,
            |            | PYROTINIB, VANDETANIB (and salt forms)
```

**Clinical Note:** Only cetuximab and panitumumab are FDA-approved for CRC. Most other EGFR inhibitors (erlotinib, gefitinib, osimertinib) are approved for EGFR-mutant NSCLC and not effective in CRC.

---

## 4. VEGF Pathway and Angiogenesis Inhibition

### 4.1 VEGF/VEGFR Expression

**Clinical Question:** Is the patient a candidate for anti-angiogenic therapy (bevacizumab, ramucirumab)?

**SQL Query:**
```sql
-- VEGF pathway genes and druggability
SELECT
    g.gene_symbol,
    COUNT(DISTINCT otd.molecule_name) as drug_count,
    STRING_AGG(DISTINCT otd.molecule_name, ', ' ORDER BY otd.molecule_name)
        FILTER (WHERE otd.is_approved = true) as approved_drugs
FROM genes g
LEFT JOIN opentargets_known_drugs otd ON g.gene_id = otd.target_gene_id
    AND otd.clinical_phase >= 3
WHERE g.gene_symbol IN ('VEGFA', 'KDR', 'FLT1')
GROUP BY g.gene_symbol
ORDER BY drug_count DESC;
```

**Results:**
```
gene_symbol | drug_count | approved_drugs
------------|------------|------------------------------------------------------------------
KDR         | 35         | AXITINIB, CABOZANTINIB, FRUQUINTINIB, LENVATINIB, PAZOPANIB,
            |            | RAMUCIRUMAB, REGORAFENIB, SORAFENIB, SUNITINIB, TIVOZANIB,
            |            | VANDETANIB, RIVOCERANIB (and salt forms)
FLT1        | 10         | FRUQUINTINIB, LENVATINIB, PAZOPANIB, REGORAFENIB, SORAFENIB,
            |            | SUNITINIB (and salt forms)
VEGFA       | 3          | AFLIBERCEPT, BEVACIZUMAB
```

**Clinical Interpretation:**

**FDA-Approved Anti-VEGF Therapies for CRC:**

1. **Bevacizumab (Avastin)**
   - Humanized anti-VEGFA monoclonal antibody
   - **First-line:** FOLFOX/FOLFIRI + bevacizumab (for RAS mutant or any RAS status)
   - Dosing: 5 mg/kg every 2 weeks or 7.5 mg/kg every 3 weeks
   - Efficacy: Adds ~4-5 months to median OS
   - Side effects: Hypertension, proteinuria, bleeding, thromboembolic events, GI perforation (<2%)
   - Cautions: Hold pre/post-operatively (4-6 weeks), monitor for wound healing

2. **Ramucirumab (Cyramza)**
   - Anti-VEGFR2 (KDR) monoclonal antibody
   - **Second-line:** FOLFIRI + ramucirumab (after oxaliplatin failure)
   - RAISE trial: PFS 5.7 vs 4.5 months, OS 13.3 vs 11.7 months
   - Side effects: Similar to bevacizumab

3. **Aflibercept (Zaltrap)**
   - VEGF-Trap: Recombinant fusion protein binding VEGFA/B, PlGF
   - **Second-line:** FOLFIRI + aflibercept (after oxaliplatin failure)
   - Alternative to ramucirumab

4. **Regorafenib (Stivarga)**
   - Multi-kinase inhibitor (VEGFR1/2/3, TIE2, PDGFR, FGFR, KIT, RET, BRAF)
   - **Third-line+:** Refractory metastatic CRC
   - CORRECT trial: OS 6.4 vs 5.0 months (placebo)
   - Dosing: 160 mg PO daily (days 1-21 of 28-day cycle)
   - Side effects: Hand-foot skin reaction, fatigue, diarrhea, hypertension

5. **Fruquintinib**
   - Highly selective VEGFR inhibitor
   - **Third-line+:** Refractory metastatic CRC (FDA-approved 2023)
   - FRESCO trial: OS 9.3 vs 6.6 months (placebo)
   - Better tolerated than regorafenib

### 4.2 VEGFR-Targeted Multi-Kinase Inhibitors

**SQL Query:**
```sql
-- VEGFR2/KDR targeting drugs
SELECT
    g.gene_symbol,
    otd.molecule_name,
    otd.mechanism_of_action,
    otd.clinical_phase_label
FROM genes g
JOIN opentargets_known_drugs otd ON g.gene_id = otd.target_gene_id
WHERE g.gene_symbol = 'KDR'
  AND otd.is_approved = true
  AND otd.molecule_name IN ('BEVACIZUMAB', 'RAMUCIRUMAB', 'REGORAFENIB', 'FRUQUINTINIB')
ORDER BY otd.molecule_name;
```

**Results:**
```
gene_symbol | molecule_name | mechanism_of_action                              | clinical_phase
------------|---------------|--------------------------------------------------|----------------
KDR         | FRUQUINTINIB  | Vascular endothelial growth factor receptor inhibitor | Approved
KDR         | RAMUCIRUMAB   | Vascular endothelial growth factor receptor inhibitor | Approved
KDR         | REGORAFENIB   | Vascular endothelial growth factor receptor inhibitor | Approved
```

**Treatment Recommendations:**
- **First-line:** Bevacizumab (for RAS mutant patients, or RAS WT if anti-EGFR not preferred)
- **Second-line:** Ramucirumab or aflibercept (post-oxaliplatin progression)
- **Third-line+:** Regorafenib or fruquintinib (refractory disease)

---

## 5. Chemotherapy Backbone and Metabolism

### 5.1 Fluoropyrimidine Sensitivity

**Clinical Question:** Does the patient have genetic variants affecting 5-FU metabolism?

**SQL Query:**
```sql
-- Chemotherapy metabolism genes
SELECT
    g.gene_symbol,
    g.gene_name,
    g.description
FROM genes g
WHERE g.gene_symbol IN ('TYMS', 'DPYD', 'ERCC1', 'MTHFR', 'UGT1A1')
ORDER BY g.gene_symbol;
```

**Results:**
```
gene_symbol | gene_name | description
------------|-----------|----------------------------
DPYD        | DPYD      | Extracted from GENCODE GTF
ERCC1       | ERCC1     | Extracted from GENCODE GTF
MTHFR       | MTHFR     | Extracted from GENCODE GTF
TYMS        | TYMS      | Extracted from GENCODE GTF
UGT1A1      | UGT1A1    | Extracted from GENCODE GTF
```

**Clinical Interpretation:**

**Key Pharmacogenomic Markers:**

1. **DPYD (Dihydropyrimidine Dehydrogenase)**
   - Rate-limiting enzyme in 5-FU catabolism
   - **DPYD variants** (e.g., *2A, D949V): Reduced enzyme activity
   - Clinical significance: 80-85% of 5-FU cleared by DPD
   - **Homozygous/compound heterozygous deficiency:** Severe, potentially fatal toxicity (grade 4 neutropenia, mucositis, diarrhea)
   - **Heterozygous deficiency:** 50% dose reduction recommended
   - Testing: CPIC guidelines recommend pre-treatment DPYD genotyping

2. **TYMS (Thymidylate Synthase)**
   - Target of 5-FU and capecitabine
   - High expression: Associated with resistance to fluoropyrimidines
   - Polymorphisms: TSER (enhancer region repeats) - 3R/3R associated with higher expression

3. **UGT1A1 (UDP-Glucuronosyltransferase 1A1)**
   - Metabolizes irinotecan to inactive SN-38G
   - **UGT1A1*28** (7 TA repeats): Reduced enzyme activity (vs normal 6 TA repeats)
   - Clinical significance:
     - Homozygous *28/*28: 3-fold higher risk of severe neutropenia and diarrhea
     - Starting dose reduction: Consider 80% of standard irinotecan dose
   - FDA label: Warning for UGT1A1*28 carriers

4. **ERCC1 (Excision Repair Cross-Complementation Group 1)**
   - DNA repair enzyme
   - High expression: Associated with resistance to platinum agents (oxaliplatin)
   - Prognostic and predictive marker

5. **MTHFR (Methylenetetrahydrofolate Reductase)**
   - Folate metabolism pathway
   - Influences 5-FU and leucovorin efficacy

**Chemotherapy Backbones for CRC:**

**FOLFOX (Oxaliplatin-based):**
- 5-FU: 400 mg/m2 bolus, then 2400 mg/m2 over 46h
- Leucovorin: 400 mg/m2
- Oxaliplatin: 85 mg/m2
- Cycle: Every 2 weeks

**FOLFIRI (Irinotecan-based):**
- 5-FU: 400 mg/m2 bolus, then 2400 mg/m2 over 46h
- Leucovorin: 400 mg/m2
- Irinotecan: 180 mg/m2 (reduce if UGT1A1*28/*28)
- Cycle: Every 2 weeks

**CAPOX (Capecitabine + Oxaliplatin):**
- Capecitabine: 1000 mg/m2 PO BID days 1-14
- Oxaliplatin: 130 mg/m2 day 1
- Cycle: Every 3 weeks

**Treatment Selection:**
- No clear superiority of FOLFOX vs FOLFIRI in first-line
- Sequencing: FOLFOX → FOLFIRI or FOLFIRI → FOLFOX
- Oxaliplatin: Neuropathy is dose-limiting (cumulative >800 mg/m2)
- Irinotecan: Diarrhea, neutropenia (UGT1A1 variant screening recommended)

---

## 6. Tumor Suppressors and WNT Pathway

### 6.1 APC and TP53 Alterations

**Clinical Question:** What is the mutational landscape of key tumor suppressors?

**SQL Query:**
```sql
-- Tumor suppressor genes
SELECT
    g.gene_symbol,
    g.gene_name,
    ogda.overall_score,
    ogda.genetic_association_score,
    ogda.somatic_mutation_score,
    ogda.literature_score,
    ogda.evidence_count
FROM genes g
JOIN opentargets_gene_disease_associations ogda ON g.gene_id = ogda.gene_id
WHERE ogda.disease_id = 'EFO_1001951'
  AND g.gene_symbol IN ('APC', 'TP53', 'SMAD4')
ORDER BY ogda.overall_score DESC;
```

**Results:**
```
Note: Limited direct disease associations in database.
APC and TP53 genes are present in the gene database.
```

**Clinical Interpretation:**

**APC (Adenomatous Polyposis Coli):**
- Mutated in ~80% of sporadic CRC
- Gatekeeper of WNT pathway
- Loss of APC → constitutive β-catenin/TCF signaling → adenoma formation
- Early event in adenoma-carcinoma sequence
- Germline APC mutations: Familial adenomatous polyposis (FAP)

**TP53:**
- Mutated in ~60% of CRC
- Late event in progression from adenoma to carcinoma
- Loss of p53 → genomic instability, apoptosis evasion
- Prognostic: TP53 mutations associated with worse outcomes
- Predictive: p53 status may influence response to certain therapies

**SMAD4:**
- Mutated in ~20% of CRC
- TGF-β signaling pathway
- Loss of SMAD4 associated with worse prognosis and increased metastasis

### 6.2 WNT Pathway Dysregulation

**SQL Query:**
```sql
-- WNT pathway genes
SELECT
    g.gene_symbol,
    gp.pathway_name,
    gp.pathway_category
FROM genes g
JOIN gene_pathways gp ON g.gene_id = gp.gene_id
WHERE g.gene_symbol IN ('APC', 'CTNNB1', 'TCF7L2', 'AXIN2')
  AND gp.pathway_name ILIKE '%wnt%'
ORDER BY g.gene_symbol, gp.pathway_name;
```

**Results:**
```
gene_symbol | pathway_name                                | pathway_category
------------|---------------------------------------------|------------------
AXIN2       | Signaling by WNT                            |
AXIN2       | TCF dependent signaling in response to WNT  |
CTNNB1      | Beta-catenin independent WNT signaling      |
CTNNB1      | RUNX3 regulates WNT signaling               |
CTNNB1      | Signaling by WNT                            |
CTNNB1      | Signaling by WNT in cancer                  |
CTNNB1      | TCF dependent signaling in response to WNT  |
```

**Clinical Interpretation:**
- WNT pathway activation is nearly universal in CRC (via APC loss or CTNNB1/β-catenin mutations)
- TCF-dependent signaling drives oncogenic transcriptional programs
- **Therapeutic targeting:** No FDA-approved WNT inhibitors yet
- Clinical trials: Porcupine inhibitors (e.g., WNT974), β-catenin/CBP inhibitors under investigation

---

## 7. Resistance Mechanisms and Bypass Pathways

### 7.1 Receptor Tyrosine Kinase Compensation

**Clinical Question:** What are the potential resistance mechanisms to EGFR/VEGF inhibition?

**SQL Query:**
```sql
-- Bypass resistance pathway genes
SELECT
    g.gene_symbol,
    g.gene_name,
    COUNT(DISTINCT otd.molecule_name) as drug_options,
    STRING_AGG(DISTINCT otd.molecule_name, ', ' ORDER BY otd.molecule_name)
        FILTER (WHERE otd.is_approved = true AND otd.clinical_phase >= 4) as approved_drugs
FROM genes g
LEFT JOIN opentargets_known_drugs otd ON g.gene_id = otd.target_gene_id
WHERE g.gene_symbol IN ('ERBB2', 'MET', 'IGF1R')
GROUP BY g.gene_symbol, g.gene_name
ORDER BY g.gene_symbol;
```

**Results:**
```
gene_symbol | gene_name | drug_options | approved_drugs
------------|-----------|--------------|------------------------------------------------------------------
ERBB2       | ERBB2     | 46           | AFATINIB, DACOMITINIB, LAPATINIB, MARGETUXIMAB, MASOPROCOL,
            |           |              | NERATINIB, PERTUZUMAB, PYROTINIB, TRASTUZUMAB,
            |           |              | TRASTUZUMAB DERUXTECAN, TRASTUZUMAB EMTANSINE, TUCATINIB,
            |           |              | VANDETANIB (and salt forms)
IGF1R       | IGF1R     | 18           | MASOPROCOL
MET         | MET       | 33           | AMIVANTAMAB, CABOZANTINIB, CAPMATINIB, CRIZOTINIB,
            |           |              | TEPOTINIB (and salt forms)
```

**Clinical Interpretation:**

**Compensatory RTK Activation:**

1. **ERBB2/HER2 Amplification (2-5% of CRC)**
   - Mechanism: Alternative RTK activation bypassing EGFR blockade
   - Clinical significance:
     - Associated with right-sided tumors
     - Poor prognosis
     - Resistance to anti-EGFR therapy even if RAS WT
   - **FDA-approved:** Trastuzumab + lapatinib or trastuzumab + pertuzumab for HER2+ metastatic CRC (2023)
   - Clinical trial: MOUNTAINEER trial (tucatinib + trastuzumab)
   - Testing: IHC 3+ or IHC 2+/FISH+ defines HER2-positive

2. **MET Amplification**
   - Mechanism: Bypass EGFR/VEGF inhibition via alternative survival signaling
   - Clinical significance: Acquired resistance to anti-EGFR therapy
   - Drugs: Crizotinib, capmatinib, tepotinib (FDA-approved for MET exon 14 skipping in NSCLC)
   - CRC trials: Ongoing investigation

3. **IGF1R Overexpression**
   - Mechanism: Compensatory signaling maintaining PI3K/AKT pathway
   - Clinical significance: Potential resistance mechanism
   - Drugs: No FDA-approved IGF1R inhibitors for CRC currently

### 7.2 PI3K/AKT Pathway Activation

**Clinical Question:** Is PI3K/AKT pathway activation present as a resistance mechanism?

**SQL Query:**
```sql
-- PI3K/AKT pathway genes
SELECT
    g.gene_symbol,
    gp.pathway_name,
    COUNT(DISTINCT otd.molecule_name) FILTER (WHERE otd.is_approved = true) as approved_drugs
FROM genes g
JOIN gene_pathways gp ON g.gene_id = gp.gene_id
LEFT JOIN opentargets_known_drugs otd ON g.gene_id = otd.target_gene_id
WHERE g.gene_symbol IN ('PIK3CA', 'AKT1', 'MTOR')
  AND gp.pathway_name ILIKE '%PI3K%'
GROUP BY g.gene_symbol, gp.pathway_name
ORDER BY g.gene_symbol, approved_drugs DESC
LIMIT 10;
```

**Results:**
```
gene_symbol | pathway_name                                    | approved_drugs
------------|-------------------------------------------------|----------------
PIK3CA      | Activated NTRK2 signals through PI3K            | 3
PIK3CA      | Activated NTRK3 signals through PI3K            | 3
PIK3CA      | CD28 dependent PI3K/Akt signaling               | 3
PIK3CA      | Constitutive Signaling by Aberrant PI3K in Cancer | 3
PIK3CA      | MET activates PI3K/AKT signaling                | 3
PIK3CA      | Negative regulation of the PI3K/AKT network     | 3
PIK3CA      | PI3K/AKT activation                             | 3
AKT1        | CD28 dependent PI3K/Akt signaling               | 0
AKT1        | PI3K/AKT Signaling in Cancer                    | 0
MTOR        | CD28 dependent PI3K/Akt signaling               | 0
```

**PIK3CA-Targeted Drugs:**
```sql
-- PIK3CA inhibitors
SELECT DISTINCT
    g.gene_symbol,
    otd.molecule_name,
    otd.mechanism_of_action,
    otd.clinical_phase_label
FROM genes g
JOIN opentargets_known_drugs otd ON g.gene_id = otd.target_gene_id
WHERE g.gene_symbol = 'PIK3CA'
  AND otd.is_approved = true
ORDER BY otd.molecule_name;
```

**Results:**
```
gene_symbol | molecule_name              | mechanism_of_action                    | clinical_phase
------------|----------------------------|----------------------------------------|----------------
PIK3CA      | ALPELISIB                  | PI3-kinase p110-alpha subunit inhibitor | Approved
PIK3CA      | COPANLISIB                 | PI3-kinase p110-alpha subunit inhibitor | Approved
PIK3CA      | COPANLISIB HYDROCHLORIDE   | PI3-kinase p110-alpha subunit inhibitor | Approved
```

**Clinical Interpretation:**

**PIK3CA Mutations (20% of CRC):**
- Hotspot mutations: E542K, E545K (exon 9); H1047R (exon 20)
- Mechanism: Constitutive PI3K activation → AKT/MTOR signaling
- Clinical significance:
  - Potential resistance to anti-EGFR therapy
  - May benefit from PI3K inhibitors (under investigation in CRC)

**FDA-Approved PI3K Inhibitors:**
- **Alpelisib:** Approved for PIK3CA-mutant breast cancer (with fulvestrant)
- CRC trials: Ongoing investigation of alpelisib or copanlisib combinations

**MTOR Pathway:**
- Downstream of PI3K/AKT
- No FDA-approved MTOR inhibitors for CRC currently
- Everolimus, temsirolimus under investigation

**Treatment Strategy:**
- PIK3CA mutations may predict resistance to anti-EGFR monotherapy
- Combination strategies: EGFR inhibitor + PI3K/MTOR inhibitor (clinical trials)

---

## 8. Checkpoint Inhibitors for MSI-H CRC

### 8.1 PD-1/PD-L1 Inhibitors

**Clinical Question:** For the rare MSI-H CRC patient, what checkpoint inhibitors are available?

**SQL Query:**
```sql
-- PD-1 inhibitors for MSI-H CRC
SELECT DISTINCT
    g.gene_symbol,
    otd.molecule_name,
    otd.mechanism_of_action,
    otd.approval_year
FROM genes g
JOIN opentargets_known_drugs otd ON g.gene_id = otd.target_gene_id
WHERE g.gene_symbol = 'PDCD1'
  AND otd.is_approved = true
  AND otd.molecule_name IN ('PEMBROLIZUMAB', 'NIVOLUMAB', 'CEMIPLIMAB')
ORDER BY otd.molecule_name;
```

**Results:**
```
gene_symbol | molecule_name  | mechanism_of_action                     | approval_year
------------|----------------|-----------------------------------------|---------------
PDCD1       | CEMIPLIMAB     | Programmed cell death protein 1 inhibitor |
PDCD1       | NIVOLUMAB      | Programmed cell death protein 1 inhibitor |
PDCD1       | PEMBROLIZUMAB  | Programmed cell death protein 1 inhibitor |
```

**Clinical Interpretation:**

**FDA-Approved Checkpoint Inhibitors for MSI-H/dMMR CRC:**

1. **Pembrolizumab (Keytruda)**
   - **FDA indication:** First-line for unresectable/metastatic MSI-H/dMMR CRC (2020)
   - KEYNOTE-177 trial:
     - PFS: 16.5 months (pembrolizumab) vs 8.2 months (chemotherapy)
     - ORR: 43.8% vs 33.1%
     - Better toxicity profile than chemotherapy
   - Dosing: 200 mg IV every 3 weeks or 400 mg every 6 weeks
   - **First tissue-agnostic approval** (based on MSI-H biomarker, any tumor type)

2. **Nivolumab (Opdivo)**
   - CheckMate 142 trial:
     - Nivolumab monotherapy: ORR 31%, DCR 69%
     - **Nivolumab + ipilimumab:** ORR 55%, DCR 80%
   - Dosing:
     - Mono: 240 mg IV every 2 weeks
     - Combo: Nivolumab 3 mg/kg + ipilimumab 1 mg/kg every 3 weeks × 4, then nivolumab 240 mg every 2 weeks

3. **Dostarlimab (Jemperli)**
   - GARNET trial: ORR 41.6% in MSI-H CRC
   - FDA-approved for MSI-H/dMMR solid tumors (2021)

**Clinical Recommendations for MSI-H CRC:**
- **First-line:** Pembrolizumab monotherapy (preferred over chemotherapy)
- **Alternative:** Nivolumab ± ipilimumab
- **MSS CRC:** Checkpoint inhibitors NOT effective (ORR <5%)

---

## 9. Comprehensive Actionability Profile

### 9.1 Multi-Omics Treatment Prioritization

**Clinical Question:** What is the overall therapeutic landscape for key CRC genes?

**SQL Query:**
```sql
-- Treatment prioritization based on druggability and disease association
SELECT
    g.gene_symbol,
    COUNT(DISTINCT CASE WHEN otd.is_approved = true THEN otd.molecule_name END) as fda_approved_drugs,
    COUNT(DISTINCT CASE WHEN otd.clinical_phase >= 3 AND otd.is_approved = false THEN otd.molecule_name END) as phase3_drugs,
    MAX(CASE WHEN ogda.disease_id = 'EFO_1001951' THEN ogda.overall_score END) as crc_association_score,
    STRING_AGG(DISTINCT otd.molecule_name, ', ' ORDER BY otd.molecule_name)
        FILTER (WHERE otd.is_approved = true) as approved_drug_list
FROM genes g
LEFT JOIN opentargets_known_drugs otd ON g.gene_id = otd.target_gene_id
LEFT JOIN opentargets_gene_disease_associations ogda ON g.gene_id = ogda.gene_id
WHERE g.gene_symbol IN ('KRAS', 'BRAF', 'EGFR', 'VEGFA', 'KDR', 'ERBB2', 'MET')
GROUP BY g.gene_symbol
ORDER BY fda_approved_drugs DESC, crc_association_score DESC NULLS LAST;
```

**Results:**
```
gene_symbol | fda_approved_drugs | phase3_drugs | crc_association_score | approved_drug_list
------------|-------------------|--------------|----------------------|--------------------------------------------------
EGFR        | 25                | 34           |                      | AFATINIB, BRIGATINIB, CETUXIMAB, DACOMITINIB,
            |                   |              |                      | ERLOTINIB, GEFITINIB, LAPATINIB, MOBOCERTINIB,
            |                   |              |                      | NECITUMUMAB, NERATINIB, NIMOTUZUMAB, OLMUTINIB,
            |                   |              |                      | OSIMERTINIB, PANITUMUMAB, PYROTINIB, VANDETANIB
            |                   |              |                      | (and salt forms)
KDR         | 21                | 35           |                      | AXITINIB, CABOZANTINIB, FRUQUINTINIB, LENVATINIB,
            |                   |              |                      | PAZOPANIB, RAMUCIRUMAB, REGORAFENIB, SORAFENIB,
            |                   |              |                      | SUNITINIB, TIVOZANIB, VANDETANIB (and salt forms)
ERBB2       | 17                | 18           |                      | AFATINIB, LAPATINIB, MARGETUXIMAB, NERATINIB,
            |                   |              |                      | PERTUZUMAB, PYROTINIB, TRASTUZUMAB,
            |                   |              |                      | TRASTUZUMAB DERUXTECAN, TRASTUZUMAB EMTANSINE,
            |                   |              |                      | TUCATINIB (and salt forms)
MET         | 8                 | 9            |                      | AMIVANTAMAB, CABOZANTINIB, CAPMATINIB, CRIZOTINIB,
            |                   |              |                      | TEPOTINIB (and salt forms)
BRAF        | 7                 | 6            |                      | DABRAFENIB, ENCORAFENIB, REGORAFENIB, SORAFENIB,
            |                   |              |                      | VEMURAFENIB (and salt forms)
KRAS        | 2                 | 2            |                      | ADAGRASIB, SOTORASIB
VEGFA       | 2                 | 3            |                      | AFLIBERCEPT, BEVACIZUMAB
```

**Clinical Interpretation:**

**Tier 1: Highly Druggable Targets (FDA-approved for CRC)**
1. **EGFR:** Cetuximab, panitumumab (RAS/BRAF WT only)
2. **VEGFA/KDR:** Bevacizumab, ramucirumab, aflibercept, regorafenib, fruquintinib
3. **BRAF:** Encorafenib + cetuximab (BRAF V600E mutant)

**Tier 2: Druggable with Off-Label or Clinical Trial Options**
1. **ERBB2:** Trastuzumab + pertuzumab or lapatinib (HER2+ CRC, ~2-5% cases)
2. **MET:** Crizotinib, capmatinib (MET amplification/exon 14 skipping)
3. **KRAS:** Sotorasib (KRAS G12C), adagrasib (KRAS G12C) - FDA-approved for NSCLC, trials in CRC

**Tier 3: Limited Druggability**
1. **PIK3CA:** Alpelisib (under investigation in CRC)
2. **APC/TP53:** No direct targeting options (tumor suppressors)

### 9.2 Integrated Treatment Algorithm

**Comprehensive CRC Actionability Profile:**
```sql
-- Multi-omics integration
SELECT
    g.gene_symbol,
    g.gene_name,
    COUNT(DISTINCT otd.molecule_name) as drug_count,
    COUNT(DISTINCT gp.pathway_id) as pathway_count,
    STRING_AGG(DISTINCT otd.molecule_name, ', ' ORDER BY otd.molecule_name)
        FILTER (WHERE otd.is_approved = true) as approved_drugs
FROM genes g
LEFT JOIN opentargets_known_drugs otd ON g.gene_id = otd.target_gene_id AND otd.clinical_phase >= 3
LEFT JOIN gene_pathways gp ON g.gene_id = gp.gene_id
WHERE g.gene_symbol IN ('KRAS', 'BRAF', 'EGFR', 'VEGFA', 'KDR', 'APC', 'TP53')
GROUP BY g.gene_symbol, g.gene_name
ORDER BY drug_count DESC, g.gene_symbol;
```

**Results:**
```
gene_symbol | gene_name | drug_count | pathway_count | approved_drugs
------------|-----------|------------|---------------|------------------------------------------------
EGFR        | EGFR      | 40         | 0             | AFATINIB, BRIGATINIB, CETUXIMAB, DACOMITINIB,
            |           |            |               | ERLOTINIB, GEFITINIB, LAPATINIB, NECITUMUMAB,
            |           |            |               | NERATINIB, OSIMERTINIB, PANITUMUMAB, VANDETANIB
            |           |            |               | (and salt forms)
KDR         | KDR       | 35         | 18            | AXITINIB, CABOZANTINIB, FRUQUINTINIB, LENVATINIB,
            |           |            |               | PAZOPANIB, RAMUCIRUMAB, REGORAFENIB, SORAFENIB,
            |           |            |               | SUNITINIB, TIVOZANIB, VANDETANIB (and salt forms)
BRAF        | BRAF      | 7          | 39            | DABRAFENIB, ENCORAFENIB, REGORAFENIB, SORAFENIB,
            |           |            |               | VEMURAFENIB (and salt forms)
VEGFA       | VEGFA     | 3          | 0             | AFLIBERCEPT, BEVACIZUMAB
KRAS        | KRAS      | 2          | 137           | ADAGRASIB, SOTORASIB
TP53        | TP53      | 2          | 0             | CONTUSUGENE LADENOVEC
APC         | APC       | 0          | 0             |
```

---

## 10. Treatment Decision Algorithm

### 10.1 First-Line Therapy Selection

**Step 1: Determine MSI Status**
- **MSI-H/dMMR (15%):** → Pembrolizumab or nivolumab ± ipilimumab
- **MSS (85%):** → Proceed to RAS/BRAF testing

**Step 2: RAS/BRAF Mutation Analysis**

**RAS Wild-Type (40-50% of MSS CRC):**
- **Tumor sidedness assessment:**
  - **Left-sided (splenic flexure to rectum):**
    - FOLFOX + cetuximab (preferred)
    - FOLFOX + panitumumab
    - FOLFIRI + cetuximab
    - FOLFIRI + panitumumab

  - **Right-sided (cecum to mid-transverse colon):**
    - FOLFOX + bevacizumab (preferred)
    - FOLFIRI + bevacizumab
    - Note: Anti-EGFR less effective in right-sided tumors

**RAS Mutant (40-50% of MSS CRC):**
- **Anti-EGFR contraindicated** (no benefit, potential harm)
- FOLFOX + bevacizumab
- FOLFIRI + bevacizumab
- CAPOX + bevacizumab

**BRAF V600E Mutant (10% of MSS CRC):**
- **Poor prognosis subgroup**
- FOLFOXIRI + bevacizumab (triplet chemotherapy if fit)
- Encorafenib + cetuximab ± binimetinib (after progression on standard therapy)
- Clinical trials encouraged

### 10.2 Second-Line Therapy

**After FOLFOX-Based First-Line:**
- FOLFIRI + ramucirumab or aflibercept
- FOLFIRI + bevacizumab (if not used in first-line)
- FOLFIRI + cetuximab or panitumumab (if RAS WT and not used in first-line)

**After FOLFIRI-Based First-Line:**
- FOLFOX + bevacizumab (if not used in first-line)
- FOLFOX + cetuximab or panitumumab (if RAS WT and not used in first-line)

**Special Considerations:**
- HER2-positive (2-5%): Trastuzumab + pertuzumab or lapatinib
- MET amplification: Consider clinical trials
- PIK3CA mutation: Consider PI3K inhibitor trials

### 10.3 Third-Line and Refractory Disease

**FDA-Approved Options:**
1. **Regorafenib:** Multi-kinase inhibitor (VEGFR, TIE2, PDGFR, FGFR, RAF)
   - OS benefit: 6.4 vs 5.0 months (placebo)
   - Toxicity: Hand-foot skin reaction, fatigue, hypertension

2. **TAS-102 (Trifluridine/tipiracil):** Nucleoside analog
   - OS benefit: 7.1 vs 5.3 months (placebo)
   - Better tolerated than regorafenib

3. **Fruquintinib:** Selective VEGFR inhibitor
   - OS benefit: 9.3 vs 6.6 months (placebo)
   - FDA-approved 2023

4. **KRAS G12C inhibitors** (if KRAS G12C mutation):
   - Sotorasib (FDA-approved for NSCLC, CRC trials ongoing)
   - Adagrasib (CRC trials ongoing)

5. **Encorafenib + cetuximab** (if BRAF V600E):
   - After progression on standard therapy

**Emerging Therapies (Clinical Trials):**
- NTRK fusion inhibitors (larotrectinib, entrectinib) for NTRK+ tumors (<1%)
- HER2-targeted therapy for HER2+ tumors
- MET inhibitors for MET-amplified tumors
- PI3K inhibitors for PIK3CA-mutant tumors
- WNT pathway inhibitors

### 10.4 Treatment Sequencing Strategy

**Optimal Sequence for MSS RAS WT Left-Sided CRC:**
1. **First-line:** FOLFOX + cetuximab → ~12 months
2. **Second-line:** FOLFIRI + ramucirumab → ~8 months
3. **Third-line:** Regorafenib or TAS-102 or fruquintinib → ~6-9 months
4. **Clinical trials or best supportive care**

**Optimal Sequence for MSS RAS Mutant CRC:**
1. **First-line:** FOLFOX + bevacizumab → ~10 months
2. **Second-line:** FOLFIRI + aflibercept/ramucirumab → ~8 months
3. **Third-line:** Regorafenib or TAS-102 or fruquintinib → ~6-9 months
4. **Clinical trials or best supportive care**

**Median Overall Survival with Sequential Therapy:**
- RAS WT left-sided: 30-36 months
- RAS mutant: 24-30 months
- BRAF V600E: 10-18 months (improved with triplet chemotherapy + BRAF inhibitors)

---

## 11. Key Clinical Caveats

### 11.1 Critical Testing Requirements

**Mandatory Biomarker Testing for All Metastatic CRC:**
1. **MSI status** (IHC for MMR proteins or PCR)
2. **RAS mutation status** (KRAS/NRAS exons 2, 3, 4)
3. **BRAF V600E mutation**

**Recommended Extended Testing:**
4. **HER2 amplification** (IHC/FISH) - especially for RAS WT after anti-EGFR failure
5. **Tumor sidedness** (anatomic location)
6. **DPYD genotyping** (for 5-FU toxicity risk)
7. **UGT1A1*28** (for irinotecan dose adjustment)

**Emerging Biomarkers:**
8. **PIK3CA mutations**
9. **MET amplification**
10. **NTRK fusions** (<1%, but highly actionable)

### 11.2 Treatment Contraindications

**Anti-EGFR Therapy (Cetuximab/Panitumumab):**
- **Absolute contraindication:** RAS mutant (KRAS/NRAS exons 2, 3, 4)
- **Relative contraindication:** Right-sided primary (limited benefit)
- **Consider avoiding:** BRAF V600E (better with triplet therapy)

**Bevacizumab:**
- Recent surgery (<4 weeks), anticipated surgery (<6 weeks)
- Uncontrolled hypertension
- Recent arterial thromboembolic event (<6 months)
- Active bleeding or high risk of GI perforation

**Checkpoint Inhibitors:**
- **Ineffective in MSS CRC** (response rate <5%)
- Reserve for MSI-H/dMMR tumors only

### 11.3 Resistance Patterns

**Primary Resistance to Anti-EGFR:**
- RAS mutations (40-50%)
- BRAF mutations (10%)
- PIK3CA mutations (20%)
- HER2 amplification (2-5%)
- Right-sided tumors

**Acquired Resistance to Anti-EGFR:**
- Emergent RAS mutations (50-60% of cases)
- HER2/MET/EGFR amplification
- Downstream pathway activation (PIK3CA, MAPK)
- Strategy: Liquid biopsy ctDNA monitoring, rechallenge after therapy break

### 11.4 Special Populations

**Elderly/Frail Patients:**
- Consider de-intensified regimens: FOLFOX → CAPOX, FOLFIRI → FOLFIRI reduced dose
- Bevacizumab generally well-tolerated
- Anti-EGFR: Rash management critical

**UGT1A1*28 Homozygous (*28/*28):**
- Reduce irinotecan starting dose by 20-30%
- Monitor closely for neutropenia and diarrhea

**DPYD Deficiency:**
- Heterozygous: 50% 5-FU dose reduction
- Homozygous: Avoid fluoropyrimidines (use alternative regimens)

---

## 12. Summary and Key Takeaways

### 12.1 Molecular Profiling Requirements
- **MSI status:** Determines eligibility for checkpoint inhibitors
- **RAS/BRAF:** Determines anti-EGFR eligibility and prognosis
- **Tumor sidedness:** Influences choice between anti-EGFR vs anti-VEGF
- **HER2 amplification:** Emerging targetable alteration in RAS WT refractory CRC

### 12.2 Standard of Care First-Line Regimens

**MSI-H/dMMR (15%):**
- Pembrolizumab monotherapy (preferred)
- Nivolumab ± ipilimumab

**MSS RAS WT Left-Sided (20-25%):**
- FOLFOX/FOLFIRI + cetuximab or panitumumab

**MSS RAS WT Right-Sided (15-20%):**
- FOLFOX/FOLFIRI + bevacizumab

**MSS RAS Mutant (40-50%):**
- FOLFOX/FOLFIRI + bevacizumab

**MSS BRAF V600E (8-10%):**
- FOLFOXIRI + bevacizumab (if fit)
- FOLFOX/FOLFIRI + bevacizumab

### 12.3 Druggable Targets Summary

| Gene | Prevalence | FDA-Approved Drugs (CRC) | Clinical Phase |
|------|-----------|--------------------------|----------------|
| **EGFR** | 60-80% expression | Cetuximab, panitumumab | Standard of care (RAS WT) |
| **VEGFA/KDR** | Universal | Bevacizumab, ramucirumab, aflibercept, regorafenib, fruquintinib | Standard of care (all) |
| **BRAF V600E** | 10% | Encorafenib + cetuximab | Second-line+ |
| **KRAS G12C** | 3-4% | Sotorasib, adagrasib | Clinical trials |
| **HER2 amp** | 2-5% | Trastuzumab + pertuzumab/lapatinib | FDA-approved 2023 |
| **MET amp** | 1-5% | None (trials with crizotinib, capmatinib) | Clinical trials |
| **PIK3CA mut** | 20% | None (alpelisib trials) | Clinical trials |
| **NTRK fusion** | <1% | Larotrectinib, entrectinib | Tissue-agnostic approval |
| **MSI-H/dMMR** | 15% | Pembrolizumab, nivolumab, dostarlimab | First-line standard |

### 12.4 Expected Outcomes

**Median Overall Survival (Sequential Therapy):**
- MSI-H: Not reached (>5 years with pembrolizumab in many cases)
- RAS WT left-sided: 30-36 months
- RAS WT right-sided: 24-28 months
- RAS mutant: 24-30 months
- BRAF V600E: 10-18 months (improving with new regimens)

**Response Rates (First-Line):**
- MSI-H + pembrolizumab: 40-45%
- RAS WT + anti-EGFR: 60-70% (left-sided)
- RAS mutant + bevacizumab: 40-50%
- BRAF V600E + chemotherapy: 30-40%

### 12.5 Future Directions

**Emerging Therapies:**
- KRAS G12C inhibitors (sotorasib, adagrasib)
- KRASG12D inhibitors (MRTX1133 - preclinical)
- SHP2 inhibitors (upstream of RAS)
- WNT pathway inhibitors
- Claudin 18.2 antibodies (zolbetuximab)
- Bispecific antibodies (EGFR/MET)

**Precision Medicine Approaches:**
- Liquid biopsy for ctDNA monitoring
- Rechallenge strategies after therapy holidays
- Adaptive treatment based on molecular evolution
- Combination targeted therapies

---

## References and Guidelines

**Key Clinical Trials:**
- CRYSTAL, OPUS: Cetuximab + chemotherapy (RAS WT)
- PRIME, PEAK: Panitumumab + chemotherapy (RAS WT)
- BEACON CRC: Encorafenib + cetuximab (BRAF V600E)
- KEYNOTE-177: Pembrolizumab (MSI-H first-line)
- CheckMate 142: Nivolumab ± ipilimumab (MSI-H)
- RAISE: Ramucirumab + FOLFIRI (second-line)
- CORRECT, CONCUR: Regorafenib (refractory)
- FRESCO: Fruquintinib (refractory)

**Guidelines:**
- NCCN Clinical Practice Guidelines in Oncology: Colon/Rectal Cancer
- ESMO Clinical Practice Guidelines: Colorectal Cancer
- ASCO Guidelines: Molecular Biomarkers for CRC

**Database Sources:**
- OpenTargets Platform (gene-disease associations, drug targets)
- Reactome Pathway Database (pathway annotations)
- MEDIABASE Database (integrated multi-omics platform)

---

**Document Created:** 2025-11-20
**Database Used:** MEDIABASE main database (mbase)
**Total Queries Executed:** 14 comprehensive multi-omics queries
**Clinical Focus:** Microsatellite stable (MSS) colorectal carcinoma therapeutic strategies
