# Colorectal Cancer MSS/MSI-H Patient Guide
## Clinical Decision Support for Colorectal Cancer

**Patient Database:** Main MEDIABASE Database (patient-specific copies can be created)
**Analysis Date:** 2025-11-25
**MEDIABASE Version:** 0.6.0.2
**Validation Status:** 100% Query Success Rate (10/10 queries validated)

---

## Executive Summary

This guide provides comprehensive molecular profiling and therapeutic decision support for colorectal cancer (CRC) patients. The guide covers both major CRC subtypes:

**MSS (Microsatellite Stable) - 85% of CRC:**
- Proficient DNA mismatch repair (pMMR)
- Treatment selection based on RAS/BRAF mutation status
- Anti-EGFR therapy for RAS wild-type tumors
- Anti-VEGF therapy for RAS mutant or any molecular subtype
- Targeted BRAF inhibition for BRAF V600E mutations

**MSI-H (Microsatellite Instability-High) - 15% of CRC:**
- Deficient DNA mismatch repair (dMMR)
- First-line checkpoint inhibitor therapy (pembrolizumab, nivolumab)
- Superior response rates and long-term survival
- Limited benefit from chemotherapy alone

**Key Molecular Biomarkers:**
1. MSI status (MLH1, MSH2, MSH6, PMS2 expression)
2. RAS mutation status (KRAS, NRAS) - determines anti-EGFR eligibility
3. BRAF V600E mutation - poor prognosis marker, targetable alteration
4. Tumor sidedness - left vs. right-sided tumors (predictive for anti-EGFR response)
5. HER2 amplification (2-5% of RAS wild-type CRC)

---

## Patient Profile

### Colorectal Cancer Molecular Subtypes

Colorectal cancer is a heterogeneous disease with distinct molecular subtypes that dictate treatment strategy. The primary classification is based on microsatellite instability status, with secondary stratification by oncogenic driver mutations.

### Key Clinical Characteristics

**Microsatellite Stable (MSS) - 85% of CRC:**
- Chromosomally unstable tumors
- Frequent mutations in APC, TP53, KRAS, PIK3CA, BRAF
- Standard chemotherapy backbone (FOLFOX/FOLFIRI)
- Targeted therapy selection based on molecular profile
- Checkpoint inhibitors generally ineffective

**Microsatellite Instability-High (MSI-H) - 15% of CRC:**
- Defective DNA mismatch repair system
- High tumor mutational burden (TMB)
- Excellent response to immune checkpoint inhibitors
- Better prognosis in early-stage disease
- Associated with Lynch syndrome (germline MMR mutations) or sporadic MLH1 methylation

**RAS Wild-Type (40-50% of MSS CRC):**
- Eligible for anti-EGFR therapy (cetuximab, panitumumab)
- Higher response rates in left-sided tumors
- Median overall survival: 28-32 months with optimal therapy

**RAS Mutant (40-50% of MSS CRC):**
- Anti-EGFR therapy contraindicated (no benefit, potential harm)
- Anti-VEGF therapy recommended (bevacizumab, ramucirumab)
- Median overall survival: 24-28 months

**BRAF V600E Mutant (~10% of MSS CRC):**
- Poor prognosis subgroup
- Median overall survival: 10-12 months with standard therapy
- Benefit from BRAF + EGFR + MEK inhibitor combinations
- Median overall survival improved to 15-18 months with triplet targeted therapy

---

## Query 1: Microsatellite Instability Status Assessment

### Clinical Question
Is this patient's tumor MSS (microsatellite stable) or MSI-H (microsatellite instability-high)? This determines first-line treatment strategy.

### SQL Query

```sql
-- Query 1: Microsatellite Instability Genes (MMR pathway)
-- Main Database Query (for gene discovery and reference data)
SELECT
    g.gene_symbol,
    g.gene_name,
    COALESCE(array_length(gp_agg.pathways, 1), 0) as pathway_count,
    COALESCE(COUNT(DISTINCT pub.pmid), 0) as publication_count,
    CASE
        WHEN COUNT(DISTINCT pub.pmid) >= 100000 THEN 'Extensively studied (>100k publications)'
        WHEN COUNT(DISTINCT pub.pmid) >= 10000 THEN 'Well-studied (10k-100k publications)'
        WHEN COUNT(DISTINCT pub.pmid) >= 1000 THEN 'Moderate evidence (1k-10k publications)'
        ELSE 'Limited publications (<1k)'
    END as evidence_level
FROM genes g
LEFT JOIN (
    SELECT gene_id, array_agg(DISTINCT pathway_id) as pathways
    FROM gene_pathways
    GROUP BY gene_id
) gp_agg ON g.gene_id = gp_agg.gene_id
LEFT JOIN gene_publications pub ON g.gene_id = pub.gene_id
WHERE g.gene_symbol IN ('MLH1', 'MSH2', 'MSH6', 'PMS2')
GROUP BY g.gene_symbol, g.gene_name, gp_agg.pathways
ORDER BY publication_count DESC;
```

### Expected Results (Main Database)

```
 gene_symbol | gene_name | pathway_count | publication_count |            evidence_level
-------------+-----------+---------------+-------------------+--------------------------------------
 MLH1        | MLH1      |            18 |             20343 | Well-studied (10k-100k publications)
 MSH2        | MSH2      |            15 |             17530 | Well-studied (10k-100k publications)
 MSH6        | MSH6      |             8 |             12870 | Well-studied (10k-100k publications)
 PMS2        | PMS2      |            14 |             10046 | Well-studied (10k-100k publications)
```

### Patient-Specific Query

For patient-specific databases with expression data:

```sql
-- Patient Database Query: MMR Gene Expression Levels
SELECT
    ctb.gene_symbol,
    ROUND(ctb.expression_fold_change::numeric, 3) as fold_change,
    COALESCE(array_length(ctb.pathways, 1), 0) as pathway_count,
    COALESCE(COUNT(DISTINCT gp.pmid), 0) as publication_count,
    CASE
        WHEN ctb.expression_fold_change < 0.3 THEN 'Severe loss (MSI-H likely)'
        WHEN ctb.expression_fold_change < 0.7 THEN 'Partial loss (investigate further)'
        WHEN ctb.expression_fold_change >= 0.7 AND ctb.expression_fold_change <= 1.3 THEN 'Normal expression (MSS likely)'
        ELSE 'Overexpressed'
    END as msi_interpretation
FROM cancer_transcript_base ctb
LEFT JOIN public.genes g ON ctb.gene_symbol = g.gene_symbol
LEFT JOIN public.gene_publications gp ON g.gene_id = gp.gene_id
WHERE ctb.gene_symbol IN ('MLH1', 'MSH2', 'MSH6', 'PMS2')
GROUP BY ctb.gene_symbol, ctb.expression_fold_change, ctb.pathways
ORDER BY ctb.expression_fold_change ASC;
```

### Clinical Interpretation

**MSS (Microsatellite Stable) - Normal MMR Expression:**
- MLH1, MSH2, MSH6, PMS2 all expressed normally (fold_change 0.7-1.3)
- DNA mismatch repair system intact
- Low tumor mutational burden
- **Treatment Strategy:**
  - Standard chemotherapy backbone (FOLFOX/FOLFIRI)
  - Targeted therapy based on RAS/BRAF status
  - Checkpoint inhibitors NOT effective (<5% response rate)

**MSI-H (Microsatellite Instability-High) - Loss of MMR Protein:**
- Loss of one or more MMR proteins (fold_change < 0.5)
- Most commonly MLH1 loss (sporadic) or MSH2 loss (Lynch syndrome)
- High tumor mutational burden (>20 mutations/Mb)
- **Treatment Strategy:**
  - **First-line:** Pembrolizumab or nivolumab +/- ipilimumab (FDA-approved)
  - Response rate: 40-55%
  - Progression-free survival: 16.5 months vs 8.2 months (chemotherapy)
  - Duration of response: Often durable (>2 years)

**Testing Recommendations:**
- IHC for MMR proteins (MLH1, MSH2, MSH6, PMS2)
- PCR-based MSI testing (gold standard)
- NGS panel with tumor mutational burden (TMB) assessment

**Key References:**
- KEYNOTE-177 trial (Pembrolizumab MSI-H first-line): PMID 32846927
- CheckMate 142 trial (Nivolumab +/- ipilimumab MSI-H): PMID 29355075

---

## Query 2: RAS/BRAF Mutation Status and Anti-EGFR Eligibility

### Clinical Question
Is the patient eligible for anti-EGFR therapy (cetuximab/panitumumab)? This requires RAS wild-type status and is most effective in left-sided tumors.

### SQL Query

```sql
-- Query 2: RAS/BRAF Pathway Analysis
-- Main Database Query (gene discovery and publication evidence)
SELECT
    g.gene_symbol,
    g.gene_name,
    COALESCE(array_length(gp_agg.pathways, 1), 0) as pathway_count,
    COALESCE(COUNT(DISTINCT pub.pmid), 0) as publication_count,
    CASE
        WHEN COUNT(DISTINCT pub.pmid) >= 100000 THEN 'Extensively studied'
        WHEN COUNT(DISTINCT pub.pmid) >= 10000 THEN 'Well-studied'
        WHEN COUNT(DISTINCT pub.pmid) >= 1000 THEN 'Moderate evidence'
        ELSE 'Limited publications'
    END as evidence_level
FROM genes g
LEFT JOIN (
    SELECT gene_id, array_agg(DISTINCT pathway_id) as pathways
    FROM gene_pathways
    GROUP BY gene_id
) gp_agg ON g.gene_id = gp_agg.gene_id
LEFT JOIN gene_publications pub ON g.gene_id = pub.gene_id
WHERE g.gene_symbol IN ('KRAS', 'NRAS', 'BRAF', 'MAP2K1', 'MAP2K2')
GROUP BY g.gene_symbol, g.gene_name, gp_agg.pathways
ORDER BY publication_count DESC;
```

### Expected Results (Main Database)

```
 gene_symbol | gene_name | pathway_count | publication_count |  evidence_level
-------------+-----------+---------------+-------------------+-------------------
 KRAS        | KRAS      |           137 |             97567 | Well-studied
 BRAF        | BRAF      |            39 |             71598 | Well-studied
 NRAS        | NRAS      |           141 |             27748 | Well-studied
 MAP2K1      | MAP2K1    |            61 |             15301 | Well-studied
 MAP2K2      | MAP2K2    |            36 |              6233 | Moderate evidence
```

### Patient-Specific Query

For patient-specific databases with mutation/expression data:

```sql
-- Patient Database Query: RAS/BRAF Expression and Mutation Status
SELECT
    ctb.gene_symbol,
    ROUND(ctb.expression_fold_change::numeric, 3) as fold_change,
    COALESCE(array_length(ctb.pathways, 1), 0) as pathway_count,
    COALESCE(COUNT(DISTINCT gp.pmid), 0) as publication_count,
    CASE
        WHEN ctb.gene_symbol = 'KRAS' AND ctb.expression_fold_change > 2.0 THEN 'Likely activating mutation - Anti-EGFR CONTRAINDICATED'
        WHEN ctb.gene_symbol = 'NRAS' AND ctb.expression_fold_change > 2.0 THEN 'Likely activating mutation - Anti-EGFR CONTRAINDICATED'
        WHEN ctb.gene_symbol = 'BRAF' AND ctb.expression_fold_change > 2.5 THEN 'Possible BRAF V600E - Consider BRAF inhibitor'
        ELSE 'Normal expression - RAS WT candidate if confirmed by NGS'
    END as anti_egfr_eligibility
FROM cancer_transcript_base ctb
LEFT JOIN public.genes g ON ctb.gene_symbol = g.gene_symbol
LEFT JOIN public.gene_publications gp ON g.gene_id = gp.gene_id
WHERE ctb.gene_symbol IN ('KRAS', 'NRAS', 'BRAF', 'MAP2K1', 'MAP2K2')
GROUP BY ctb.gene_symbol, ctb.expression_fold_change, ctb.pathways
ORDER BY ctb.expression_fold_change DESC;
```

### Clinical Interpretation

**RAS Wild-Type (KRAS/NRAS WT) - 40-50% of MSS CRC:**
- **Anti-EGFR therapy ELIGIBLE**
- First-line options (left-sided tumors):
  - FOLFOX + cetuximab (CRYSTAL trial: ORR 66% vs 39%)
  - FOLFOX + panitumumab (PRIME trial: PFS 10.1 vs 7.9 months)
  - FOLFIRI + cetuximab
  - FOLFIRI + panitumumab
- Median overall survival: 28-32 months (left-sided)
- **Tumor sidedness critical:** Right-sided tumors have limited benefit from anti-EGFR therapy

**RAS Mutant (KRAS/NRAS exons 2, 3, 4) - 40-50% of MSS CRC:**
- **Anti-EGFR therapy CONTRAINDICATED** (no benefit, potential harm)
- First-line options:
  - FOLFOX + bevacizumab
  - FOLFIRI + bevacizumab
  - CAPOX + bevacizumab
- Response rate: 40-50%
- Median overall survival: 24-28 months

**BRAF V600E Mutant - ~10% of MSS CRC:**
- **Poor prognosis marker**
- Median overall survival with standard therapy: 10-12 months
- **FDA-approved targeted therapy:** Encorafenib + cetuximab +/- binimetinib
- BEACON CRC trial results:
  - Triplet therapy: ORR 26%, OS 9.3 months
  - Chemotherapy alone: ORR 2%, OS 5.9 months
- Consider intensive chemotherapy (FOLFOXIRI + bevacizumab) if fit

**KRAS G12C Mutation - 3-4% of CRC:**
- **Emerging targeted therapy:** Sotorasib, adagrasib (FDA-approved for NSCLC)
- CRC clinical trials ongoing
- Response rates: 7-10% monotherapy, higher with combination therapy

**Testing Recommendations:**
- NGS panel covering KRAS exons 2, 3, 4 (codons 12, 13, 59, 61, 117, 146)
- NRAS exons 2, 3, 4 (codons 12, 13, 59, 61)
- BRAF V600E mutation
- Consider extended RAS panel testing before anti-EGFR therapy

**Key References:**
- CRYSTAL trial (cetuximab + FOLFIRI RAS WT): PMID 19949011
- PRIME trial (panitumumab + FOLFOX RAS WT): PMID 24024839
- BEACON CRC trial (encorafenib + cetuximab BRAF V600E): PMID 31566309

---

## Query 3: FDA-Approved Anti-EGFR Therapies for RAS Wild-Type CRC

### Clinical Question
What anti-EGFR monoclonal antibodies are FDA-approved for RAS wild-type colorectal cancer?

### SQL Query

```sql
-- Query 3: FDA-Approved Anti-EGFR Therapies
SELECT
    g.gene_symbol,
    otd.molecule_name,
    otd.mechanism_of_action,
    otd.clinical_phase_label,
    COALESCE(COUNT(DISTINCT pub.pmid), 0) as gene_publication_count
FROM genes g
JOIN opentargets_known_drugs otd ON g.gene_id = otd.target_gene_id
LEFT JOIN gene_publications pub ON g.gene_id = pub.gene_id
WHERE g.gene_symbol = 'EGFR'
    AND otd.is_approved = true
    AND otd.molecule_name IN ('CETUXIMAB', 'PANITUMUMAB')
GROUP BY g.gene_symbol, otd.molecule_name, otd.mechanism_of_action, otd.clinical_phase_label
ORDER BY otd.molecule_name;
```

### Expected Results

```
 gene_symbol | molecule_name |               mechanism_of_action                | clinical_phase_label | gene_publication_count
-------------+---------------+--------------------------------------------------+----------------------+------------------------
 EGFR        | CETUXIMAB     | Epidermal growth factor receptor erbB1 inhibitor | Approved             |                 219621
 EGFR        | PANITUMUMAB   | Epidermal growth factor receptor erbB1 inhibitor | Approved             |                 219621
```

### Clinical Interpretation

**FDA-Approved Anti-EGFR Monoclonal Antibodies for CRC:**

**1. Cetuximab (Erbitux)**
- **Structure:** Chimeric IgG1 monoclonal antibody
- **Mechanism:** Binds EGFR extracellular domain, blocks ligand binding
- **Indications:** RAS WT metastatic CRC (first-line with FOLFOX/FOLFIRI or later lines)
- **Dosing:** Loading dose 400 mg/m2, then 250 mg/m2 IV weekly
- **Efficacy (CRYSTAL trial - RAS WT):**
  - FOLFIRI + cetuximab vs. FOLFIRI alone
  - ORR: 66% vs 39% (p<0.001)
  - PFS: 11.4 vs 8.4 months
  - OS: 28.4 vs 20.2 months (left-sided)
- **Side Effects:**
  - Acneiform rash (80% of patients) - correlates with efficacy
  - Infusion reactions (15-20%, premedicate with antihistamines)
  - Hypomagnesemia (monitor magnesium levels)
  - Diarrhea, fatigue

**2. Panitumumab (Vectibix)**
- **Structure:** Fully human IgG2 monoclonal antibody
- **Mechanism:** Binds EGFR extracellular domain with high affinity
- **Indications:** RAS WT metastatic CRC (first-line or later lines)
- **Dosing:** 6 mg/kg IV every 2 weeks
- **Efficacy (PRIME trial - RAS WT):**
  - FOLFOX + panitumumab vs. FOLFOX alone
  - PFS: 10.1 vs 7.9 months (HR 0.72, p=0.004)
  - OS: 26.0 vs 20.2 months (HR 0.78)
  - ORR: 57% vs 48%
- **Side Effects:**
  - Similar to cetuximab but lower infusion reaction rates (fully human)
  - Acneiform rash (90% of patients)
  - Hypomagnesemia, diarrhea, fatigue
  - Skin toxicity (paronychia, xerosis)

**Comparative Considerations:**
- No head-to-head trial demonstrating superiority of one over the other
- Panitumumab: Lower immunogenicity, less frequent infusion reactions
- Cetuximab: More established clinical experience
- Both effective when combined with appropriate chemotherapy backbone
- Choice often based on institutional preference and infusion schedule

**Predictive Biomarkers for Anti-EGFR Response:**
1. **RAS wild-type status (REQUIRED):** KRAS/NRAS exons 2, 3, 4
2. **Tumor sidedness:** Left-sided tumors respond better (cecum to rectum)
3. **BRAF wild-type:** Better response, though BRAF mutant may benefit with triplet therapy
4. **HER2 amplification:** Negative predictor (2-5% of RAS WT CRC) - consider HER2-targeted therapy

**Resistance Mechanisms:**
- Primary resistance: RAS/BRAF/PIK3CA mutations, HER2 amplification
- Acquired resistance: Emergent RAS mutations (50-60% of cases), EGFR amplification
- Strategy: Liquid biopsy ctDNA monitoring, rechallenge after treatment holiday

**Key References:**
- CRYSTAL trial: PMID 19949011
- PRIME trial: PMID 24024839
- Extended RAS analysis: PMID 23630200

---

## Query 4: Anti-VEGF/Angiogenesis Therapies for All Molecular Subtypes

### Clinical Question
What anti-angiogenic therapies are FDA-approved for colorectal cancer? These are effective across all molecular subtypes (RAS WT and RAS mutant).

### SQL Query

```sql
-- Query 4: Anti-VEGF/Angiogenesis Therapies
SELECT
    g.gene_symbol,
    otd.molecule_name,
    otd.mechanism_of_action,
    otd.clinical_phase_label
FROM genes g
JOIN opentargets_known_drugs otd ON g.gene_id = otd.target_gene_id
WHERE g.gene_symbol IN ('VEGFA', 'KDR')
    AND otd.is_approved = true
    AND otd.molecule_name IN ('BEVACIZUMAB', 'RAMUCIRUMAB', 'AFLIBERCEPT', 'REGORAFENIB', 'FRUQUINTINIB')
GROUP BY g.gene_symbol, otd.molecule_name, otd.mechanism_of_action, otd.clinical_phase_label
ORDER BY g.gene_symbol, otd.molecule_name;
```

### Expected Results

```
 gene_symbol | molecule_name |                   mechanism_of_action                   | clinical_phase_label
-------------+---------------+---------------------------------------------------------+----------------------
 KDR         | FRUQUINTINIB  | Vascular endothelial growth factor receptor inhibitor   | Approved
 KDR         | RAMUCIRUMAB   | Vascular endothelial growth factor receptor 2 inhibitor | Approved
 KDR         | REGORAFENIB   | Vascular endothelial growth factor receptor inhibitor   | Approved
 VEGFA       | AFLIBERCEPT   | Vascular endothelial growth factor A inhibitor          | Approved
 VEGFA       | BEVACIZUMAB   | Vascular endothelial growth factor A inhibitor          | Approved
```

### Clinical Interpretation

**FDA-Approved Anti-Angiogenic Therapies for CRC:**

**1. Bevacizumab (Avastin) - First-Line Therapy**
- **Mechanism:** Humanized anti-VEGFA monoclonal antibody
- **Indications:** First-line metastatic CRC (any RAS status)
- **Dosing:** 5 mg/kg IV every 2 weeks (with FOLFOX/FOLFIRI) or 7.5 mg/kg every 3 weeks (with CAPOX)
- **Efficacy:**
  - Adds 4-5 months to median overall survival
  - ORR: 45-50% (with chemotherapy)
  - PFS: 10-12 months (first-line with chemotherapy)
- **Side Effects:**
  - Hypertension (30% of patients, usually manageable)
  - Proteinuria (monitor urinalysis)
  - Bleeding (minor in most cases, <2% major bleeding)
  - Thromboembolic events (arterial and venous)
  - GI perforation (<2%, higher risk with bowel inflammation)
  - Wound healing complications (hold 4-6 weeks before/after surgery)
- **Clinical Use:** Standard first-line for RAS mutant CRC, alternative to anti-EGFR in RAS WT

**2. Ramucirumab (Cyramza) - Second-Line Therapy**
- **Mechanism:** Anti-VEGFR2 (KDR) monoclonal antibody
- **Indications:** Second-line with FOLFIRI (after oxaliplatin failure)
- **Dosing:** 8 mg/kg IV every 2 weeks (with FOLFIRI)
- **Efficacy (RAISE trial):**
  - FOLFIRI + ramucirumab vs. FOLFIRI alone
  - PFS: 5.7 vs 4.5 months (HR 0.79, p<0.0005)
  - OS: 13.3 vs 11.7 months (HR 0.84, p=0.022)
  - ORR: 13.4% vs 12.5%
- **Side Effects:** Similar to bevacizumab (hypertension, proteinuria, bleeding)
- **Clinical Use:** Standard second-line alternative to aflibercept

**3. Aflibercept (Zaltrap) - Second-Line Therapy**
- **Mechanism:** VEGF-Trap (recombinant fusion protein binding VEGFA, VEGFB, PlGF)
- **Indications:** Second-line with FOLFIRI (after oxaliplatin failure)
- **Dosing:** 4 mg/kg IV every 2 weeks (with FOLFIRI)
- **Efficacy (VELOUR trial):**
  - FOLFIRI + aflibercept vs. FOLFIRI alone
  - OS: 13.5 vs 12.1 months (HR 0.817, p=0.0032)
  - PFS: 6.9 vs 4.7 months
- **Side Effects:** Higher toxicity than bevacizumab (hypertension, diarrhea, neutropenia)
- **Clinical Use:** Second-line alternative to ramucirumab

**4. Regorafenib (Stivarga) - Third-Line+ Therapy**
- **Mechanism:** Multi-kinase inhibitor (VEGFR1/2/3, TIE2, PDGFR, FGFR, KIT, RET, BRAF)
- **Indications:** Refractory metastatic CRC (third-line or later)
- **Dosing:** 160 mg PO daily (days 1-21 of 28-day cycle)
- **Efficacy (CORRECT trial):**
  - Regorafenib vs. placebo + best supportive care
  - OS: 6.4 vs 5.0 months (HR 0.77, p=0.0052)
  - PFS: 1.9 vs 1.7 months
  - Disease control rate: 41% vs 15%
- **Side Effects:**
  - Hand-foot skin reaction (47%, dose-limiting)
  - Fatigue, diarrhea, hypertension, liver toxicity
  - Start at reduced dose (120 mg) to improve tolerability
- **Clinical Use:** Third-line standard of care for refractory disease

**5. Fruquintinib - Third-Line+ Therapy (FDA-Approved 2023)**
- **Mechanism:** Highly selective VEGFR1/2/3 tyrosine kinase inhibitor
- **Indications:** Refractory metastatic CRC (third-line or later)
- **Dosing:** 5 mg PO daily (days 1-21 of 28-day cycle)
- **Efficacy (FRESCO trial):**
  - Fruquintinib vs. placebo
  - OS: 9.3 vs 6.6 months (HR 0.65, p<0.001)
  - PFS: 3.7 vs 1.8 months
- **Side Effects:** Better tolerated than regorafenib (lower hand-foot skin reaction)
- **Clinical Use:** Preferred third-line option over regorafenib for many patients

**Treatment Sequencing:**
- **First-line:** Bevacizumab (RAS mutant or any subtype)
- **Second-line:** Ramucirumab or aflibercept (post-oxaliplatin progression)
- **Third-line+:** Fruquintinib (preferred) or regorafenib

**Key References:**
- Bevacizumab first-line: PMID 15383407
- RAISE trial (ramucirumab): PMID 25823737
- VELOUR trial (aflibercept): PMID 23177514
- CORRECT trial (regorafenib): PMID 23177514
- FRESCO trial (fruquintinib): PMID 30207593

---

## Query 5: BRAF-Targeted Therapies for BRAF V600E Mutant CRC

### Clinical Question
What BRAF-targeted therapies are available for patients with BRAF V600E mutant colorectal cancer?

### SQL Query

```sql
-- Query 5: BRAF-Targeted Therapies for V600E
SELECT
    g.gene_symbol,
    otd.molecule_name,
    otd.mechanism_of_action,
    otd.clinical_phase_label,
    COALESCE(COUNT(DISTINCT pub.pmid), 0) as gene_publication_count
FROM genes g
JOIN opentargets_known_drugs otd ON g.gene_id = otd.target_gene_id
LEFT JOIN gene_publications pub ON g.gene_id = pub.gene_id
WHERE g.gene_symbol = 'BRAF'
    AND otd.is_approved = true
    AND otd.molecule_name IN ('ENCORAFENIB', 'DABRAFENIB', 'VEMURAFENIB')
GROUP BY g.gene_symbol, otd.molecule_name, otd.mechanism_of_action, otd.clinical_phase_label
ORDER BY otd.molecule_name;
```

### Expected Results

```
 gene_symbol | molecule_name |               mechanism_of_action               | clinical_phase_label | gene_publication_count
-------------+---------------+-------------------------------------------------+----------------------+------------------------
 BRAF        | DABRAFENIB    | Serine/threonine-protein kinase B-raf inhibitor | Approved             |                  71598
 BRAF        | ENCORAFENIB   | Serine/threonine-protein kinase B-raf inhibitor | Approved             |                  71598
 BRAF        | VEMURAFENIB   | Serine/threonine-protein kinase B-raf inhibitor | Approved             |                  71598
```

### Clinical Interpretation

**BRAF V600E Mutation in Colorectal Cancer:**
- Occurs in ~10% of metastatic CRC
- Poor prognosis: median OS 10-12 months with chemotherapy alone
- Associated with right-sided tumors, MSS phenotype, older age
- Single-agent BRAF inhibitors ineffective due to feedback MAPK activation

**FDA-Approved BRAF-Targeted Combination Therapy:**

**1. Encorafenib + Cetuximab +/- Binimetinib (FDA-Approved 2020)**
- **BEACON CRC Trial Results:**
  - **Triplet therapy (encorafenib + cetuximab + binimetinib):**
    - ORR: 26% vs 2% (control)
    - Median OS: 9.3 months vs 5.9 months (HR 0.60)
    - Disease control rate: 61% vs 20%
  - **Doublet therapy (encorafenib + cetuximab):**
    - ORR: 20%
    - Median OS: 9.3 months (non-inferior to triplet)
    - Better tolerability than triplet
- **Dosing:**
  - Encorafenib: 300 mg PO daily (continuous)
  - Cetuximab: Loading 400 mg/m2, then 250 mg/m2 IV weekly
  - Binimetinib (optional): 45 mg PO twice daily
- **Side Effects:**
  - BRAF inhibitor: Arthralgia, fatigue, nausea
  - MEK inhibitor: Diarrhea, rash, vision changes, left ventricular dysfunction
  - EGFR inhibitor: Acneiform rash, hypomagnesemia
- **Clinical Use:** Standard second-line or later therapy for BRAF V600E CRC

**2. Dabrafenib + Trametinib (Off-Label for CRC, FDA-Approved for Other Cancers)**
- **Mechanism:** BRAF + MEK inhibitor combination
- **FDA Status:** Approved for BRAF V600E melanoma, NSCLC, not specifically for CRC
- **Limited efficacy in CRC:** ORR ~10% (monotherapy or doublet without EGFR inhibitor)
- **Clinical Use:** Not recommended for CRC (inferior to encorafenib + cetuximab)

**3. Vemurafenib (Not Recommended for CRC)**
- **Mechanism:** BRAF V600E inhibitor
- **FDA Status:** Approved for BRAF V600E melanoma
- **CRC Data:** Monotherapy ineffective, combination with cetuximab inferior to encorafenib
- **Clinical Use:** Not used in CRC

**Why Combination Therapy is Required in CRC:**
- Single-agent BRAF inhibitors cause paradoxical EGFR-mediated MAPK reactivation in RAS-WT cells
- EGFR inhibitor (cetuximab) prevents feedback activation
- MEK inhibitor (binimetinib) provides additional downstream blockade (optional)
- Triplet therapy blocks pathway at three levels: BRAF, MEK, EGFR

**First-Line Considerations for BRAF V600E CRC:**
- **Standard first-line:** FOLFOXIRI + bevacizumab (if fit for triplet chemotherapy)
  - More intensive chemotherapy for aggressive biology
  - Better outcomes than doublet chemotherapy
- **Alternative:** FOLFOX/FOLFIRI + bevacizumab (if not fit for triplet)
- **Second-line:** Encorafenib + cetuximab (after progression)

**Prognostic Impact and Outcomes:**
- **Historical OS with chemotherapy alone:** 10-12 months
- **With FOLFOXIRI + bevacizumab:** 15-18 months
- **With encorafenib + cetuximab:** 9-10 months (second-line+)
- **Still poorer prognosis than RAS WT or RAS mutant CRC**

**Key References:**
- BEACON CRC trial: PMID 31566309
- TRIBE trial (FOLFOXIRI BRAF V600E subgroup): PMID 25185994

---

## Query 6: Checkpoint Inhibitors for MSI-H Colorectal Cancer

### Clinical Question
What immune checkpoint inhibitors are FDA-approved for MSI-H/dMMR colorectal cancer?

### SQL Query

```sql
-- Query 6: Checkpoint Inhibitors for MSI-H CRC
SELECT
    g.gene_symbol,
    otd.molecule_name,
    otd.mechanism_of_action,
    otd.clinical_phase_label,
    COALESCE(COUNT(DISTINCT pub.pmid), 0) as gene_publication_count
FROM genes g
JOIN opentargets_known_drugs otd ON g.gene_id = otd.target_gene_id
LEFT JOIN gene_publications pub ON g.gene_id = pub.gene_id
WHERE g.gene_symbol IN ('PDCD1', 'CD274')
    AND otd.is_approved = true
    AND otd.molecule_name IN ('PEMBROLIZUMAB', 'NIVOLUMAB', 'DOSTARLIMAB', 'ATEZOLIZUMAB')
GROUP BY g.gene_symbol, otd.molecule_name, otd.mechanism_of_action, otd.clinical_phase_label
ORDER BY g.gene_symbol, otd.molecule_name;
```

### Expected Results

```
 gene_symbol | molecule_name |            mechanism_of_action             | clinical_phase_label | gene_publication_count
-------------+---------------+--------------------------------------------+----------------------+------------------------
 CD274       | ATEZOLIZUMAB  | Programmed cell death 1 ligand 1 inhibitor | Approved             |                  93434
 PDCD1       | DOSTARLIMAB   | Programmed cell death protein 1 antagonist | Approved             |                  62263
 PDCD1       | NIVOLUMAB     | Programmed cell death protein 1 inhibitor  | Approved             |                  62263
 PDCD1       | PEMBROLIZUMAB | Programmed cell death protein 1 inhibitor  | Approved             |                  62263
```

### Clinical Interpretation

**FDA-Approved Checkpoint Inhibitors for MSI-H/dMMR CRC:**

**1. Pembrolizumab (Keytruda) - First-Line FDA Approval**
- **FDA Indication:** First-line unresectable/metastatic MSI-H or dMMR CRC (June 2020)
- **KEYNOTE-177 Trial (First-Line):**
  - Pembrolizumab vs. chemotherapy (FOLFOX/FOLFIRI +/- bevacizumab/cetuximab)
  - PFS: 16.5 vs 8.2 months (HR 0.60, p=0.0002)
  - ORR: 43.8% vs 33.1%
  - 24-month OS: 72.4% vs 65.6%
  - Superior toxicity profile (fewer grade 3-5 adverse events)
  - Duration of response: 83% ongoing at 24 months
- **Dosing:** 200 mg IV every 3 weeks or 400 mg IV every 6 weeks
- **Clinical Use:** **Preferred first-line therapy for MSI-H/dMMR metastatic CRC**
- **Key Reference:** PMID 32846927

**2. Nivolumab +/- Ipilimumab (Opdivo +/- Yervoy) - FDA-Approved**
- **CheckMate 142 Trial:**
  - **Nivolumab monotherapy:**
    - ORR: 31%, DCR: 69%
    - 12-month PFS: 50%, 12-month OS: 73%
  - **Nivolumab + Ipilimumab combination:**
    - ORR: 55%, DCR: 80%
    - 12-month PFS: 71%, 12-month OS: 85%
    - Superior to monotherapy
- **Dosing:**
  - **Monotherapy:** Nivolumab 240 mg IV every 2 weeks or 480 mg every 4 weeks
  - **Combination:** Nivolumab 3 mg/kg + ipilimumab 1 mg/kg IV every 3 weeks × 4 doses, then nivolumab 240 mg every 2 weeks
- **Side Effects:** Higher immune-related adverse events with combination (diarrhea, hepatitis, colitis, endocrinopathies)
- **Clinical Use:** Alternative first-line or later-line therapy, combination preferred over monotherapy
- **Key Reference:** PMID 29355075

**3. Dostarlimab (Jemperli) - FDA-Approved (Tissue-Agnostic)**
- **GARNET Trial:**
  - ORR: 41.6% in MSI-H/dMMR CRC (n=77)
  - 6-month DCR: 57.1%
  - Median DOR: Not reached (83% ongoing at 6 months)
- **FDA Indication:** MSI-H/dMMR solid tumors (after prior treatment)
- **Dosing:** 500 mg IV every 3 weeks × 4 doses, then 1000 mg every 6 weeks
- **Clinical Use:** Alternative checkpoint inhibitor option for MSI-H CRC
- **Key Reference:** PMID 34157926

**4. Atezolizumab (Tecentriq) - Limited CRC Data**
- **Mechanism:** Anti-PD-L1 antibody
- **FDA Status:** Approved for PD-L1+ NSCLC, urothelial carcinoma (not specifically CRC)
- **CRC Data:** Limited efficacy data, not standard of care for CRC
- **Clinical Use:** Not routinely used for CRC

**MSI-H vs MSS Response to Checkpoint Inhibitors:**
- **MSI-H/dMMR CRC:** ORR 40-55%, durable responses (often >2 years)
- **MSS CRC:** ORR <5%, checkpoint inhibitors NOT effective

**Why MSI-H Tumors Respond to Immunotherapy:**
1. High tumor mutational burden (TMB >20 mutations/Mb)
2. Abundant neoantigens from frameshift mutations
3. Strong immune infiltration (CD8+ T cells)
4. PD-1/PD-L1 upregulation
5. Defective DNA mismatch repair system

**Treatment Selection for MSI-H CRC:**
- **First-line metastatic:** Pembrolizumab monotherapy (preferred based on KEYNOTE-177)
- **Alternative first-line:** Nivolumab + ipilimumab
- **Later-line (after chemotherapy):** Any checkpoint inhibitor option

**Toxicity Management:**
- Immune-related adverse events (irAEs): Colitis, hepatitis, pneumonitis, endocrinopathies
- Grade 2+ irAEs: Hold checkpoint inhibitor, initiate corticosteroids
- Grade 4 irAEs: Permanently discontinue, high-dose corticosteroids
- Monitor TSH, ALT/AST, creatinine, glucose before each cycle

**Key References:**
- KEYNOTE-177 (pembrolizumab first-line): PMID 32846927
- CheckMate 142 (nivolumab +/- ipilimumab): PMID 29355075
- GARNET trial (dostarlimab): PMID 34157926

---

## Query 7: WNT Pathway Alterations (Universal in CRC)

### Clinical Question
What is the mutational landscape of the WNT signaling pathway? APC mutations occur in ~80% of CRC cases and are foundational to tumorigenesis.

### SQL Query

```sql
-- Query 7: WNT Pathway Genes (Universal in CRC)
SELECT
    g.gene_symbol,
    g.gene_name,
    COALESCE(array_length(gp_agg.pathways, 1), 0) as pathway_count,
    COALESCE(COUNT(DISTINCT pub.pmid), 0) as publication_count,
    COALESCE(COUNT(DISTINCT gp_wnt.pathway_id), 0) as wnt_pathway_count
FROM genes g
LEFT JOIN (
    SELECT gene_id, array_agg(DISTINCT pathway_id) as pathways
    FROM gene_pathways
    GROUP BY gene_id
) gp_agg ON g.gene_id = gp_agg.gene_id
LEFT JOIN gene_publications pub ON g.gene_id = pub.gene_id
LEFT JOIN gene_pathways gp_wnt ON g.gene_id = gp_wnt.gene_id
    AND gp_wnt.pathway_name ILIKE '%wnt%'
WHERE g.gene_symbol IN ('APC', 'CTNNB1', 'AXIN2', 'TCF7L2', 'TP53')
GROUP BY g.gene_symbol, g.gene_name, gp_agg.pathways
ORDER BY publication_count DESC;
```

### Expected Results

```
 gene_symbol | gene_name | pathway_count | publication_count | wnt_pathway_count
-------------+-----------+---------------+-------------------+-------------------
 TP53        | TP53      |             0 |            284428 |                 0
 CTNNB1      | CTNNB1    |            92 |            136445 |                 5
 APC         | APC       |             0 |             36577 |                 0
 TCF7L2      | TCF7L2    |             0 |              7662 |                 0
 AXIN2       | AXIN2     |            10 |              6075 |                 2
```

### Patient-Specific Query

For patient-specific databases with expression data:

```sql
-- Patient Database Query: WNT Pathway Expression
SELECT
    ctb.gene_symbol,
    ROUND(ctb.expression_fold_change::numeric, 3) as fold_change,
    COALESCE(array_length(ctb.pathways, 1), 0) as pathway_count,
    COALESCE(COUNT(DISTINCT gp.pmid), 0) as publication_count,
    CASE
        WHEN ctb.gene_symbol = 'APC' AND ctb.expression_fold_change < 0.5 THEN 'Tumor suppressor loss - WNT active'
        WHEN ctb.gene_symbol = 'CTNNB1' AND ctb.expression_fold_change > 2.0 THEN 'Beta-catenin activated - WNT active'
        WHEN ctb.gene_symbol = 'AXIN2' AND ctb.expression_fold_change > 2.0 THEN 'WNT pathway target activated'
        WHEN ctb.gene_symbol = 'TP53' AND ctb.expression_fold_change < 0.5 THEN 'P53 loss - late event in CRC'
        ELSE 'Normal WNT pathway component'
    END as wnt_interpretation
FROM cancer_transcript_base ctb
LEFT JOIN public.genes g ON ctb.gene_symbol = g.gene_symbol
LEFT JOIN public.gene_publications gp ON g.gene_id = gp.gene_id
WHERE ctb.gene_symbol IN ('APC', 'CTNNB1', 'AXIN2', 'TCF7L2', 'TP53')
GROUP BY ctb.gene_symbol, ctb.expression_fold_change, ctb.pathways
ORDER BY ctb.expression_fold_change DESC;
```

### Clinical Interpretation

**WNT Pathway in Colorectal Carcinogenesis:**

**1. APC (Adenomatous Polyposis Coli) - Gatekeeper Tumor Suppressor**
- **Mutation Frequency:** ~80% of sporadic CRC
- **Function:** Negative regulator of WNT pathway, β-catenin destruction complex component
- **Clinical Significance:**
  - Loss of APC → constitutive β-catenin/TCF signaling
  - Early event in adenoma-carcinoma sequence
  - Germline APC mutations: Familial adenomatous polyposis (FAP)
  - No direct targeted therapy currently available
- **Patient Testing:** Consider germline testing if early-onset CRC (<50 years) or family history

**2. CTNNB1 (Beta-Catenin) - Oncogenic Driver**
- **Mutation Frequency:** ~5% of CRC (mutually exclusive with APC loss)
- **Function:** Transcriptional coactivator, WNT effector
- **Clinical Significance:**
  - Stabilizing mutations in β-catenin N-terminus
  - Constitutive WNT pathway activation
  - Alternative mechanism to APC loss
  - Extensive pathway involvement (92 pathways)
- **Therapeutic Targeting:** WNT inhibitors under investigation (CBP/β-catenin antagonists)

**3. TP53 - Late Event in CRC Progression**
- **Mutation Frequency:** ~60% of CRC
- **Function:** Guardian of the genome, cell cycle checkpoint
- **Clinical Significance:**
  - Late event in adenoma-to-carcinoma progression
  - Loss of TP53 → genomic instability, apoptosis resistance
  - Poor prognostic marker
  - Associated with more aggressive disease
- **Therapeutic Considerations:** No direct TP53-targeted therapy (tumor suppressor)

**4. AXIN2 - WNT Pathway Negative Regulator**
- **Mutation Frequency:** Rare in CRC
- **Function:** Scaffold protein in β-catenin destruction complex
- **Clinical Significance:** WNT pathway target gene (transcriptional readout of pathway activity)

**5. TCF7L2 - WNT Transcriptional Effector**
- **Function:** T-cell factor, β-catenin transcriptional partner
- **Clinical Significance:** Mediates oncogenic transcription downstream of WNT activation

**Adenoma-Carcinoma Sequence:**
1. **APC loss** → Early adenoma formation (WNT activation)
2. **KRAS activation** → Advanced adenoma
3. **TP53 loss** → Carcinoma formation
4. **PIK3CA, SMAD4, other alterations** → Metastatic progression

**WNT Pathway Therapeutic Targeting (Investigational):**
- **Porcupine inhibitors** (e.g., WNT974, LGK974): Block WNT ligand secretion
- **CBP/β-catenin antagonists** (e.g., PRI-724): Disrupt β-catenin transcription
- **Tankyrase inhibitors**: Stabilize AXIN2, promote β-catenin degradation
- **Status:** All in clinical trials, none FDA-approved for CRC yet

**Why WNT Inhibitors Are Challenging:**
- WNT pathway is essential for normal stem cell homeostasis (intestinal crypts, bone, hair)
- Therapeutic window narrow (on-target toxicity to normal tissues)
- Redundancy in WNT signaling pathway
- Biomarker-driven patient selection needed

**Key References:**
- APC mutations in CRC: PMID 8162572
- WNT pathway in CRC: PMID 23719381
- WNT inhibitors clinical trials: PMID 30181419

---

## Query 8: PI3K/AKT/MTOR Pathway and Resistance Mechanisms

### Clinical Question
Is the PI3K/AKT/MTOR pathway activated? This pathway is a major resistance mechanism to anti-EGFR therapy and occurs in ~20% of CRC via PIK3CA mutations.

### SQL Query

```sql
-- Query 8: PI3K/AKT Resistance Pathway (Simplified - Avoid Subqueries)
SELECT
    g.gene_symbol,
    g.gene_name,
    COUNT(DISTINCT gp.pathway_id) as pathway_count,
    COUNT(DISTINCT pub.pmid) as publication_count,
    COUNT(DISTINCT CASE WHEN otd.is_approved = true THEN otd.molecule_name END) as approved_drugs
FROM genes g
LEFT JOIN gene_pathways gp ON g.gene_id = gp.gene_id
LEFT JOIN gene_publications pub ON g.gene_id = pub.gene_id
LEFT JOIN opentargets_known_drugs otd ON g.gene_id = otd.target_gene_id
WHERE g.gene_symbol IN ('PIK3CA', 'AKT1', 'MTOR', 'PTEN')
GROUP BY g.gene_symbol, g.gene_name
ORDER BY publication_count DESC;
```

### Expected Results

```
 gene_symbol | gene_name | pathway_count | publication_count | approved_drugs
-------------+-----------+---------------+-------------------+----------------
 PIK3CA      | PIK3CA    |           137 |            128974 |              3
 PTEN        | PTEN      |            88 |             95896 |              0
 AKT1        | AKT1      |           112 |             80394 |              0
 MTOR        | MTOR      |            47 |             64429 |              0
```

### Patient-Specific Query

For patient-specific databases with expression data:

```sql
-- Patient Database Query: PI3K Pathway Activation
SELECT
    ctb.gene_symbol,
    ROUND(ctb.expression_fold_change::numeric, 3) as fold_change,
    COALESCE(array_length(ctb.pathways, 1), 0) as pathway_count,
    COALESCE(COUNT(DISTINCT gp.pmid), 0) as publication_count,
    CASE
        WHEN ctb.gene_symbol = 'PIK3CA' AND ctb.expression_fold_change > 2.5 THEN 'PI3K activated - Anti-EGFR resistance likely'
        WHEN ctb.gene_symbol IN ('AKT1', 'AKT2', 'AKT3') AND ctb.expression_fold_change > 2.5 THEN 'AKT activated - Consider PI3K inhibitor'
        WHEN ctb.gene_symbol = 'MTOR' AND ctb.expression_fold_change > 2.0 THEN 'MTOR activated - mTOR inhibitor candidate'
        WHEN ctb.gene_symbol = 'PTEN' AND ctb.expression_fold_change < 0.5 THEN 'PTEN loss - PI3K pathway activated'
        ELSE 'Normal PI3K pathway'
    END as pi3k_interpretation
FROM cancer_transcript_base ctb
LEFT JOIN public.genes g ON ctb.gene_symbol = g.gene_symbol
LEFT JOIN public.gene_publications gp ON g.gene_id = gp.gene_id
WHERE ctb.gene_symbol IN ('PIK3CA', 'AKT1', 'AKT2', 'AKT3', 'MTOR', 'PTEN')
GROUP BY ctb.gene_symbol, ctb.expression_fold_change, ctb.pathways
ORDER BY ctb.expression_fold_change DESC;
```

### Clinical Interpretation

**PI3K/AKT/MTOR Pathway in Colorectal Cancer:**

**1. PIK3CA Mutations - 20% of CRC**
- **Hotspot Mutations:** E542K, E545K (exon 9), H1047R (exon 20)
- **Mechanism:** Constitutive PI3K-alpha catalytic subunit activation → AKT/MTOR signaling
- **Clinical Significance:**
  - Associated with resistance to anti-EGFR therapy (cetuximab, panitumumab)
  - May predict worse outcomes with anti-EGFR monotherapy
  - Co-occurrence with RAS mutations: Additive negative effect
- **FDA-Approved PI3K Inhibitors:**
  - **Alpelisib (Piqray):** Approved for PIK3CA-mutant breast cancer (with fulvestrant)
  - **Copanlisib:** Approved for relapsed follicular lymphoma
  - **CRC Status:** Investigational (clinical trials ongoing)
- **Treatment Strategy:**
  - PIK3CA mutation + RAS WT: Consider anti-VEGF therapy instead of anti-EGFR
  - PIK3CA mutation + RAS mutant: Standard anti-VEGF therapy
  - Clinical trials: Anti-EGFR + PI3K inhibitor combinations

**2. PTEN Loss - 10-15% of CRC**
- **Mechanism:** Loss of phosphatase that antagonizes PI3K → constitutive AKT activation
- **Clinical Significance:**
  - Associated with resistance to anti-EGFR therapy
  - Enriched in RAS WT tumors with poor anti-EGFR response
- **Testing:** IHC for PTEN protein loss or NGS for PTEN mutations/deletions

**3. AKT Activation**
- **Function:** Central signaling node downstream of PI3K, upstream of MTOR
- **Clinical Significance:** AKT overexpression/hyperactivation drives survival and proliferation
- **Therapeutic Targeting:** No FDA-approved AKT inhibitors for CRC (investigational)

**4. MTOR Pathway**
- **Function:** Master regulator of cell growth, metabolism, autophagy
- **Drugs:** Everolimus, temsirolimus (FDA-approved for renal cell carcinoma, not CRC)
- **CRC Trials:** Limited efficacy as monotherapy, combinations under investigation

**PI3K Pathway as Resistance Mechanism to Anti-EGFR Therapy:**

**Primary Resistance:**
- PIK3CA mutations: Present at baseline, predict poor response
- PTEN loss: Present at baseline, associated with primary resistance
- Frequency: ~30% of RAS WT CRC have PI3K pathway activation

**Acquired Resistance:**
- PIK3CA mutations can emerge during anti-EGFR therapy
- Bypass signaling maintains AKT/MTOR activity despite EGFR blockade

**Strategies to Overcome PI3K-Mediated Resistance:**
1. **Dual EGFR + PI3K inhibition:** Clinical trials (cetuximab + alpelisib)
2. **Triple blockade:** EGFR + PI3K + MEK inhibitors
3. **Alternative pathway targeting:** Switch to anti-VEGF therapy

**Clinical Trials of Interest:**
- Cetuximab + alpelisib (PI3K inhibitor) for PIK3CA-mutant RAS WT CRC
- Panitumumab + everolimus (mTOR inhibitor)
- Status: Phase II trials, not yet standard of care

**Biomarker Testing Recommendations:**
- **PIK3CA mutation testing:** Consider in RAS WT CRC before anti-EGFR therapy
- **PTEN IHC:** Optional, may predict anti-EGFR resistance
- **NGS panel:** Comprehensive genomic profiling captures PIK3CA, PTEN, AKT alterations

**Key References:**
- PIK3CA mutations and anti-EGFR resistance: PMID 22156372
- PTEN loss and cetuximab resistance: PMID 20619739
- Alpelisib in PIK3CA-mutant cancers: PMID 31091374

---

## Query 9: HER2 Amplification in RAS Wild-Type CRC (2-5%)

### Clinical Question
Is HER2 amplification present? This is an emerging biomarker in 2-5% of RAS wild-type CRC, now targetable with FDA-approved HER2-directed therapy.

### SQL Query

```sql
-- Query 9: HER2 (ERBB2) and MET Bypass Resistance
SELECT
    g.gene_symbol,
    g.gene_name,
    COUNT(DISTINCT gp.pathway_id) as pathway_count,
    COUNT(DISTINCT pub.pmid) as publication_count,
    COUNT(DISTINCT CASE WHEN otd.is_approved = true THEN otd.molecule_name END) as approved_drugs
FROM genes g
LEFT JOIN gene_pathways gp ON g.gene_id = gp.gene_id
LEFT JOIN gene_publications pub ON g.gene_id = pub.gene_id
LEFT JOIN opentargets_known_drugs otd ON g.gene_id = otd.target_gene_id
WHERE g.gene_symbol IN ('ERBB2', 'MET', 'IGF1R')
GROUP BY g.gene_symbol, g.gene_name
ORDER BY publication_count DESC;
```

### Expected Results

```
 gene_symbol | gene_name | pathway_count | publication_count | approved_drugs
-------------+-----------+---------------+-------------------+----------------
 ERBB2       | ERBB2     |            58 |            135276 |             17
 MET         | MET       |            44 |             50823 |              8
 IGF1R       | IGF1R     |            35 |             28104 |              1
```

### Patient-Specific Query

For patient-specific databases with expression data:

```sql
-- Patient Database Query: HER2/MET Bypass Signaling
SELECT
    ctb.gene_symbol,
    ROUND(ctb.expression_fold_change::numeric, 3) as fold_change,
    COALESCE(array_length(ctb.pathways, 1), 0) as pathway_count,
    COALESCE(COUNT(DISTINCT gp.pmid), 0) as publication_count,
    CASE
        WHEN ctb.gene_symbol = 'ERBB2' AND ctb.expression_fold_change > 4.0 THEN 'HER2+ candidate - Test IHC/FISH'
        WHEN ctb.gene_symbol = 'MET' AND ctb.expression_fold_change > 3.0 THEN 'MET amplification possible - Consider MET inhibitor'
        WHEN ctb.gene_symbol = 'IGF1R' AND ctb.expression_fold_change > 2.5 THEN 'IGF1R overexpression - Bypass pathway active'
        ELSE 'Normal receptor tyrosine kinase expression'
    END as bypass_interpretation
FROM cancer_transcript_base ctb
LEFT JOIN public.genes g ON ctb.gene_symbol = g.gene_symbol
LEFT JOIN public.gene_publications gp ON g.gene_id = gp.gene_id
WHERE ctb.gene_symbol IN ('ERBB2', 'MET', 'IGF1R', 'EGFR')
GROUP BY ctb.gene_symbol, ctb.expression_fold_change, ctb.pathways
ORDER BY ctb.expression_fold_change DESC;
```

### Clinical Interpretation

**HER2 Amplification in Colorectal Cancer:**

**1. HER2-Positive CRC (ERBB2 Amplification)**
- **Frequency:** 2-5% of metastatic CRC (enriched in RAS WT tumors)
- **Mechanism:** Alternative receptor tyrosine kinase activation bypassing EGFR blockade
- **Clinical Significance:**
  - Associated with resistance to anti-EGFR therapy even if RAS WT
  - More common in right-sided tumors
  - Poor prognosis without HER2-targeted therapy
- **Testing Criteria:**
  - RAS WT CRC with progression on anti-EGFR therapy
  - IHC 3+ or IHC 2+/FISH+ (using breast cancer HER2 scoring criteria)

**FDA-Approved HER2-Targeted Therapy for CRC (2023):**

**Trastuzumab + Pertuzumab (MOUNTAINEER Trial)**
- **Regimen:** Trastuzumab (loading 8 mg/kg, then 6 mg/kg IV every 3 weeks) + pertuzumab (loading 840 mg, then 420 mg IV every 3 weeks)
- **Efficacy:**
  - ORR: 30% (in HER2+ RAS WT refractory CRC)
  - Disease control rate: 70%
  - Median PFS: 5.7 months
- **FDA Status:** Approved June 2023 for HER2+ metastatic CRC
- **Patient Selection:** IHC 3+ or IHC 2+/FISH+ (HER2 amplification)

**Trastuzumab + Lapatinib**
- **MyPathway Trial:** ORR 32% in HER2+ CRC
- **Alternative dual HER2 blockade strategy**

**Trastuzumab Deruxtecan (Fam-Trastuzumab Deruxtecan-nxki)**
- **DESTINY-CRC01 Trial:**
  - ORR: 45.3% in HER2 IHC 3+ CRC
  - Median PFS: 6.9 months
- **Antibody-drug conjugate (ADC) delivering topoisomerase I inhibitor**
- **Investigational in CRC, FDA-approved for HER2+ breast/gastric cancer**

**Tucatinib + Trastuzumab**
- **MOUNTAINEER Trial:**
  - Tucatinib (oral HER2 tyrosine kinase inhibitor) + trastuzumab
  - ORR: 38%
- **Alternative HER2-targeted strategy**

**2. MET Amplification - Resistance Mechanism**
- **Frequency:** 1-5% of CRC, enriched after anti-EGFR therapy
- **Mechanism:** Bypass EGFR/VEGF inhibition via alternative RTK signaling
- **Clinical Significance:** Acquired resistance to anti-EGFR therapy
- **FDA-Approved MET Inhibitors (for MET exon 14 skipping in NSCLC):**
  - Crizotinib, capmatinib, tepotinib
  - CRC trials: Ongoing investigation
  - Not standard of care for CRC currently

**3. IGF1R Overexpression - Compensatory Signaling**
- **Mechanism:** Maintains PI3K/AKT pathway during EGFR blockade
- **Clinical Significance:** Potential resistance mechanism
- **Drugs:** No FDA-approved IGF1R inhibitors for CRC

**HER2 Testing Recommendations for CRC:**
- **When to test:**
  - RAS WT metastatic CRC
  - Progression on anti-EGFR therapy (cetuximab/panitumumab)
  - Consider upfront testing in RAS WT CRC
- **Testing method:**
  - IHC (HER2 protein expression)
  - FISH (HER2 gene amplification)
  - NGS panel (ERBB2 amplification, copy number)
- **Positive criteria:** IHC 3+ or IHC 2+/FISH+ (HER2:CEP17 ratio ≥2.0)

**Treatment Algorithm for HER2+ CRC:**
1. **Confirm HER2 positivity:** IHC/FISH testing
2. **First-line:** Standard chemotherapy (FOLFOX/FOLFIRI +/- bevacizumab)
3. **Second-line+:** Trastuzumab + pertuzumab (FDA-approved)
4. **Alternative:** Trastuzumab deruxtecan (investigational), tucatinib + trastuzumab

**Key References:**
- MOUNTAINEER trial (trastuzumab + pertuzumab): PMID 35038720
- MyPathway trial (trastuzumab + lapatinib): PMID 31980579
- DESTINY-CRC01 trial (trastuzumab deruxtecan): PMID 34115980
- HER2 amplification in CRC: PMID 30181419

---

## Query 10: Comprehensive CRC Drug Landscape Across All Targets

### Clinical Question
What is the complete therapeutic landscape for key colorectal cancer molecular targets?

### SQL Query

```sql
-- Query 10: Comprehensive CRC Drug Landscape
SELECT
    g.gene_symbol,
    COUNT(DISTINCT CASE WHEN otd.is_approved = true THEN otd.molecule_name END) as fda_approved_drugs,
    COUNT(DISTINCT pub.pmid) as publication_count,
    STRING_AGG(DISTINCT otd.molecule_name, ', ' ORDER BY otd.molecule_name)
        FILTER (WHERE otd.is_approved = true
               AND otd.molecule_name IN ('CETUXIMAB', 'PANITUMUMAB', 'BEVACIZUMAB',
                                        'RAMUCIRUMAB', 'ENCORAFENIB', 'PEMBROLIZUMAB',
                                        'NIVOLUMAB', 'FRUQUINTINIB', 'REGORAFENIB'))
        as key_crc_drugs
FROM genes g
LEFT JOIN opentargets_known_drugs otd ON g.gene_id = otd.target_gene_id
LEFT JOIN gene_publications pub ON g.gene_id = pub.gene_id
WHERE g.gene_symbol IN ('EGFR', 'VEGFA', 'KDR', 'BRAF', 'KRAS', 'PDCD1', 'ERBB2')
GROUP BY g.gene_symbol
ORDER BY fda_approved_drugs DESC, publication_count DESC;
```

### Expected Results

```
 gene_symbol | fda_approved_drugs | publication_count |        key_crc_drugs
-------------+--------------------+-------------------+------------------------------
 EGFR        |                 25 |            219621 | CETUXIMAB, PANITUMUMAB
 KDR         |                 21 |            106847 | FRUQUINTINIB, RAMUCIRUMAB, REGORAFENIB
 ERBB2       |                 17 |            135276 |
 BRAF        |                  7 |             71598 | ENCORAFENIB, REGORAFENIB
 PDCD1       |                  4 |             62263 | NIVOLUMAB, PEMBROLIZUMAB
 KRAS        |                  2 |             97567 |
 VEGFA       |                  2 |             72634 | BEVACIZUMAB
```

### Clinical Interpretation

**Tier 1: FDA-Approved Standard of Care for CRC**

1. **EGFR Inhibitors (RAS WT only):**
   - Cetuximab, panitumumab
   - First-line or later-line therapy
   - Left-sided tumors preferred

2. **VEGF/VEGFR Inhibitors (Any RAS status):**
   - Bevacizumab (first-line, VEGFA inhibitor)
   - Ramucirumab (second-line, VEGFR2 inhibitor)
   - Aflibercept (second-line, VEGF-trap)
   - Regorafenib (third-line+, multi-kinase inhibitor)
   - Fruquintinib (third-line+, selective VEGFR inhibitor)

3. **BRAF Inhibitors (BRAF V600E only):**
   - Encorafenib + cetuximab +/- binimetinib
   - Second-line or later therapy

4. **Checkpoint Inhibitors (MSI-H/dMMR only):**
   - Pembrolizumab (first-line preferred)
   - Nivolumab +/- ipilimumab (first-line or later)
   - Dostarlimab (later-line)

5. **HER2-Targeted Therapy (HER2+ only):**
   - Trastuzumab + pertuzumab (2-5% of RAS WT CRC)
   - FDA-approved 2023

**Tier 2: Investigational/Clinical Trials**

1. **KRAS G12C Inhibitors:**
   - Sotorasib (AMG 510) - FDA-approved for NSCLC
   - Adagrasib (MRTX849)
   - CRC trials ongoing (3-4% of CRC)

2. **PI3K Inhibitors:**
   - Alpelisib (for PIK3CA mutant CRC)
   - Clinical trials: Combination with anti-EGFR

3. **MET Inhibitors:**
   - Crizotinib, capmatinib, tepotinib
   - For MET-amplified CRC (rare)

**Tier 3: No Direct Targeting (Tumor Suppressors)**

1. **APC, TP53:** No targetable therapies (tumor suppressors)
2. **PTEN:** Loss of function (cannot target directly)

**Treatment Decision Algorithm Summary:**

**Step 1: Determine MSI Status**
- **MSI-H/dMMR (15%):** → Pembrolizumab or nivolumab (first-line)
- **MSS (85%):** → Proceed to Step 2

**Step 2: RAS/BRAF Mutation Analysis**
- **RAS WT (40-50%):** → Left-sided: Anti-EGFR + chemotherapy; Right-sided: Anti-VEGF + chemotherapy
- **RAS Mutant (40-50%):** → Anti-VEGF + chemotherapy
- **BRAF V600E (10%):** → FOLFOXIRI + bevacizumab (first-line), encorafenib + cetuximab (second-line+)

**Step 3: Extended Molecular Testing (for resistant disease)**
- **HER2 amplification:** → Trastuzumab + pertuzumab
- **KRAS G12C:** → Clinical trial (sotorasib, adagrasib)
- **PIK3CA mutation:** → Consider PI3K inhibitor trial
- **MET amplification:** → Consider MET inhibitor trial

**Expected Survival Outcomes with Sequential Therapy:**
- MSI-H + checkpoint inhibitors: Median OS >5 years (many patients)
- RAS WT left-sided + anti-EGFR: Median OS 28-32 months
- RAS WT right-sided + anti-VEGF: Median OS 24-28 months
- RAS mutant + anti-VEGF: Median OS 24-30 months
- BRAF V600E + triplet therapy: Median OS 15-18 months (improving)

**Key References:**
- NCCN Guidelines for Colon Cancer (2024-2025)
- ESMO Clinical Practice Guidelines for CRC
- ASCO Guidelines for Molecular Biomarkers in CRC

---

## Treatment Decision Algorithm

### First-Line Therapy Selection

**Step 1: MSI Status Determination**
- **MSI-H/dMMR (15% of CRC):**
  - First-line: Pembrolizumab monotherapy (KEYNOTE-177)
  - Alternative: Nivolumab + ipilimumab
  - Expected outcomes: ORR 40-55%, median PFS 16.5 months
  - Duration of response: Often durable (>2 years)

- **MSS (85% of CRC):**
  - Proceed to RAS/BRAF testing for targeted therapy selection

**Step 2: RAS/BRAF Mutation Analysis (for MSS tumors)**

**RAS Wild-Type (40-50% of MSS CRC):**
- **Tumor Sidedness Assessment:**
  - **Left-sided (splenic flexure to rectum):**
    - FOLFOX + cetuximab (CRYSTAL trial)
    - FOLFOX + panitumumab (PRIME trial)
    - FOLFIRI + cetuximab
    - FOLFIRI + panitumumab
    - Expected outcomes: ORR 60-70%, median OS 28-32 months

  - **Right-sided (cecum to mid-transverse colon):**
    - FOLFOX + bevacizumab (preferred)
    - FOLFIRI + bevacizumab
    - Note: Anti-EGFR therapy less effective in right-sided tumors
    - Expected outcomes: ORR 40-50%, median OS 24-28 months

**RAS Mutant (40-50% of MSS CRC):**
- **Anti-EGFR therapy CONTRAINDICATED** (no benefit, potential harm)
- First-line options:
  - FOLFOX + bevacizumab
  - FOLFIRI + bevacizumab
  - CAPOX + bevacizumab
- Expected outcomes: ORR 40-50%, median OS 24-30 months

**BRAF V600E Mutant (10% of MSS CRC):**
- **Poor prognosis subgroup** (aggressive biology)
- First-line options (if fit):
  - FOLFOXIRI + bevacizumab (triplet chemotherapy)
  - FOLFOX/FOLFIRI + bevacizumab (if not fit for triplet)
- Second-line: Encorafenib + cetuximab +/- binimetinib
- Expected outcomes: Median OS 15-18 months with optimal therapy

### Second-Line Therapy

**After FOLFOX-Based First-Line:**
- FOLFIRI + ramucirumab (RAISE trial)
- FOLFIRI + aflibercept (VELOUR trial)
- FOLFIRI + bevacizumab (if not used first-line)
- FOLFIRI + cetuximab or panitumumab (if RAS WT and not used first-line)

**After FOLFIRI-Based First-Line:**
- FOLFOX + bevacizumab (if not used first-line)
- FOLFOX + cetuximab or panitumumab (if RAS WT and not used first-line)

**Special Considerations:**
- HER2+ (2-5% of RAS WT): Trastuzumab + pertuzumab
- MET amplification: Consider clinical trials
- PIK3CA mutation: Consider PI3K inhibitor trials

### Third-Line and Refractory Disease

**FDA-Approved Options:**
1. **Fruquintinib:** Selective VEGFR inhibitor (preferred, better tolerated)
   - Median OS: 9.3 vs 6.6 months (placebo)
2. **Regorafenib:** Multi-kinase inhibitor
   - Median OS: 6.4 vs 5.0 months (placebo)
3. **TAS-102 (trifluridine/tipiracil):** Nucleoside analog
   - Median OS: 7.1 vs 5.3 months (placebo)
4. **KRAS G12C inhibitors** (if KRAS G12C mutation):
   - Sotorasib, adagrasib (clinical trials)
5. **Encorafenib + cetuximab** (if BRAF V600E):
   - After progression on chemotherapy

**Emerging Therapies (Clinical Trials):**
- NTRK fusion inhibitors (larotrectinib, entrectinib) for NTRK+ tumors (<1%)
- WNT pathway inhibitors (porcupine inhibitors, CBP/β-catenin antagonists)
- Claudin 18.2 antibodies (zolbetuximab)
- Bispecific antibodies (EGFR/MET)

### Treatment Sequencing Strategy

**Optimal Sequence for MSS RAS WT Left-Sided CRC:**
1. First-line: FOLFOX + cetuximab → ~12 months
2. Second-line: FOLFIRI + ramucirumab → ~8 months
3. Third-line: Fruquintinib or regorafenib or TAS-102 → ~6-9 months
4. Clinical trials or best supportive care
- **Total median OS: 30-36 months**

**Optimal Sequence for MSS RAS Mutant CRC:**
1. First-line: FOLFOX + bevacizumab → ~10 months
2. Second-line: FOLFIRI + ramucirumab → ~8 months
3. Third-line: Fruquintinib or regorafenib or TAS-102 → ~6-9 months
4. Clinical trials or best supportive care
- **Total median OS: 24-30 months**

**Optimal Sequence for MSS BRAF V600E CRC:**
1. First-line: FOLFOXIRI + bevacizumab → ~10 months (if fit)
2. Second-line: Encorafenib + cetuximab → ~6 months
3. Third-line: Fruquintinib or regorafenib → ~6 months
4. Clinical trials or best supportive care
- **Total median OS: 15-18 months (improving with new therapies)**

---

## Key Clinical Caveats

### Mandatory Biomarker Testing

**All Metastatic CRC Patients Require:**
1. **MSI status** (IHC for MMR proteins or PCR-based MSI testing)
2. **RAS mutation status** (KRAS/NRAS exons 2, 3, 4)
3. **BRAF V600E mutation**
4. **Tumor sidedness** (anatomic location: left vs. right)

**Recommended Extended Testing:**
5. **HER2 amplification** (IHC/FISH) - especially for RAS WT after anti-EGFR failure
6. **DPYD genotyping** (for 5-FU toxicity risk assessment)
7. **UGT1A1*28** (for irinotecan dose adjustment)

**Emerging Biomarkers:**
8. **PIK3CA mutations** (predictive for anti-EGFR resistance)
9. **MET amplification** (resistance mechanism)
10. **NTRK fusions** (<1%, but highly actionable with larotrectinib/entrectinib)

### Treatment Contraindications

**Anti-EGFR Therapy (Cetuximab/Panitumumab):**
- **Absolute contraindication:** RAS mutant (KRAS/NRAS exons 2, 3, 4)
- **Relative contraindication:** Right-sided primary tumor (limited benefit)
- **Consider avoiding:** BRAF V600E (better with triplet BRAF + EGFR + MEK therapy)
- **HER2 amplification:** Negative predictor (consider HER2-targeted therapy instead)

**Bevacizumab:**
- Recent surgery (<4 weeks), anticipated surgery (<6 weeks)
- Uncontrolled hypertension (>150/100 mmHg)
- Recent arterial thromboembolic event (<6 months)
- Active bleeding or high risk of GI perforation
- Significant proteinuria (>2g/24h)

**Checkpoint Inhibitors:**
- **Ineffective in MSS CRC** (response rate <5%)
- Reserve for MSI-H/dMMR tumors only
- Monitor for immune-related adverse events (colitis, hepatitis, pneumonitis)

### Resistance Mechanisms

**Primary Resistance to Anti-EGFR Therapy:**
1. RAS mutations (KRAS, NRAS) - 40-50%
2. BRAF V600E mutation - 10%
3. PIK3CA mutations - 20%
4. HER2 amplification - 2-5%
5. MET amplification - 1-5%
6. PTEN loss - 10-15%
7. Right-sided tumor location

**Acquired Resistance to Anti-EGFR Therapy:**
1. Emergent RAS mutations (50-60% of acquired resistance)
2. HER2/MET/EGFR amplification
3. Downstream pathway activation (PIK3CA, MAPK)
4. **Strategy:** Liquid biopsy ctDNA monitoring, rechallenge after treatment holiday

### Special Populations

**Elderly/Frail Patients:**
- Consider de-intensified regimens: FOLFOX → CAPOX, FOLFIRI → reduced dose
- Bevacizumab generally well-tolerated
- Anti-EGFR therapy: Rash management critical (can affect quality of life)
- Balance efficacy with toxicity and quality of life goals

**UGT1A1*28 Homozygous (*28/*28):**
- 10% of population (7 TA repeats in promoter region)
- Reduce irinotecan starting dose by 20-30% (to 120-135 mg/m2)
- Monitor closely for neutropenia and severe diarrhea
- Higher risk of febrile neutropenia and hospitalization

**DPYD Deficiency:**
- 2-8% of population have DPYD variants (most common: *2A, D949V)
- **Heterozygous:** Reduce 5-FU/capecitabine dose by 50%
- **Homozygous:** Avoid fluoropyrimidines entirely (use alternative regimens)
- Severe toxicity risk: Grade 4 neutropenia, mucositis, diarrhea (potentially fatal)
- CPIC guidelines recommend pre-treatment DPYD genotyping

---

## Summary and Key Takeaways

### Molecular Profiling Requirements

**Essential Biomarkers:**
1. **MSI status** → Determines checkpoint inhibitor eligibility
2. **RAS mutation status** → Determines anti-EGFR eligibility
3. **BRAF V600E** → Poor prognosis marker, targetable with encorafenib + cetuximab
4. **Tumor sidedness** → Predicts anti-EGFR response (left > right)

**Extended Testing (Recommended):**
5. **HER2 amplification** → Emerging targetable alteration (2-5% of RAS WT CRC)
6. **PIK3CA mutation** → Predictive for anti-EGFR resistance
7. **DPYD/UGT1A1 genotyping** → Chemotherapy toxicity risk assessment

### Standard of Care First-Line Regimens

**MSI-H/dMMR (15% of CRC):**
- Pembrolizumab monotherapy (KEYNOTE-177) - preferred
- Nivolumab +/- ipilimumab - alternative
- Expected outcomes: ORR 40-55%, median PFS 16.5 months, durable responses

**MSS RAS WT Left-Sided (20-25% of CRC):**
- FOLFOX or FOLFIRI + cetuximab or panitumumab
- Expected outcomes: ORR 60-70%, median OS 28-32 months

**MSS RAS WT Right-Sided (15-20% of CRC):**
- FOLFOX or FOLFIRI + bevacizumab (preferred over anti-EGFR)
- Expected outcomes: ORR 40-50%, median OS 24-28 months

**MSS RAS Mutant (40-50% of CRC):**
- FOLFOX or FOLFIRI + bevacizumab
- Anti-EGFR therapy CONTRAINDICATED
- Expected outcomes: ORR 40-50%, median OS 24-30 months

**MSS BRAF V600E (8-10% of CRC):**
- FOLFOXIRI + bevacizumab (if fit for triplet chemotherapy)
- FOLFOX/FOLFIRI + bevacizumab (if not fit)
- Expected outcomes: Median OS 15-18 months (improving)

### Druggable Targets Summary

| Gene/Target | Prevalence | FDA-Approved CRC Drugs | Clinical Phase |
|-------------|-----------|------------------------|----------------|
| **EGFR** | 60-80% expression | Cetuximab, panitumumab | Standard of care (RAS WT only) |
| **VEGFA/KDR** | Universal | Bevacizumab, ramucirumab, aflibercept, regorafenib, fruquintinib | Standard of care (all) |
| **BRAF V600E** | 10% | Encorafenib + cetuximab | Second-line+ |
| **KRAS G12C** | 3-4% | Sotorasib, adagrasib | Clinical trials (FDA-approved for NSCLC) |
| **HER2 amp** | 2-5% | Trastuzumab + pertuzumab | FDA-approved 2023 |
| **MET amp** | 1-5% | None (clinical trials) | Clinical trials |
| **PIK3CA mut** | 20% | None (alpelisib trials) | Clinical trials |
| **NTRK fusion** | <1% | Larotrectinib, entrectinib | Tissue-agnostic FDA approval |
| **MSI-H/dMMR** | 15% | Pembrolizumab, nivolumab, dostarlimab | First-line standard |

### Expected Outcomes with Sequential Therapy

**Median Overall Survival:**
- MSI-H + checkpoint inhibitors: >5 years (many patients with durable responses)
- RAS WT left-sided + sequential therapy: 30-36 months
- RAS WT right-sided + sequential therapy: 24-28 months
- RAS mutant + sequential therapy: 24-30 months
- BRAF V600E + optimal therapy: 15-18 months (improving with new regimens)

**Response Rates (First-Line):**
- MSI-H + pembrolizumab: 40-45%
- RAS WT left-sided + anti-EGFR: 60-70%
- RAS mutant + bevacizumab: 40-50%
- BRAF V600E + triplet chemotherapy: 30-40%

### Future Directions and Emerging Therapies

**Investigational Therapies:**
1. KRAS G12C inhibitors (sotorasib, adagrasib) - ongoing CRC trials
2. KRAS G12D inhibitors (MRTX1133) - preclinical
3. SHP2 inhibitors (upstream of RAS)
4. WNT pathway inhibitors (porcupine inhibitors, CBP/β-catenin antagonists)
5. Claudin 18.2 antibodies (zolbetuximab)
6. Bispecific antibodies (EGFR/MET, EGFR/LGR5)

**Precision Medicine Approaches:**
1. Liquid biopsy ctDNA monitoring for resistance mutations
2. Rechallenge strategies after therapy holidays
3. Adaptive treatment based on molecular evolution
4. Combination targeted therapies (EGFR + PI3K, BRAF + MEK + EGFR)

---

## Key References and Guidelines

### Landmark Clinical Trials

**Anti-EGFR Therapy:**
- CRYSTAL trial (cetuximab + FOLFIRI RAS WT): PMID 19949011
- PRIME trial (panitumumab + FOLFOX RAS WT): PMID 24024839
- Extended RAS analysis: PMID 23630200

**Anti-VEGF Therapy:**
- Bevacizumab first-line: PMID 15383407
- RAISE trial (ramucirumab + FOLFIRI): PMID 25823737
- VELOUR trial (aflibercept + FOLFIRI): PMID 23177514
- CORRECT trial (regorafenib): PMID 23177514
- FRESCO trial (fruquintinib): PMID 30207593

**BRAF V600E:**
- BEACON CRC trial (encorafenib + cetuximab): PMID 31566309
- TRIBE trial (FOLFOXIRI + bevacizumab): PMID 25185994

**MSI-H Checkpoint Inhibitors:**
- KEYNOTE-177 (pembrolizumab first-line MSI-H): PMID 32846927
- CheckMate 142 (nivolumab +/- ipilimumab MSI-H): PMID 29355075
- GARNET trial (dostarlimab MSI-H): PMID 34157926

**HER2-Targeted Therapy:**
- MOUNTAINEER trial (trastuzumab + pertuzumab HER2+): PMID 35038720
- DESTINY-CRC01 (trastuzumab deruxtecan HER2+): PMID 34115980

### Clinical Practice Guidelines

**NCCN Guidelines:**
- NCCN Clinical Practice Guidelines in Oncology: Colon Cancer (Version 1.2025)
- NCCN Guidelines: Rectal Cancer (Version 1.2025)

**ESMO Guidelines:**
- ESMO Clinical Practice Guidelines: Colorectal Cancer (2023 update)

**ASCO Guidelines:**
- ASCO Guidelines: Molecular Biomarkers for Colorectal Cancer
- ASCO Guidelines: Treatment of Metastatic Colorectal Cancer

### Database Sources

**MEDIABASE Integration:**
- Gene annotations: GENCODE v46
- Gene-disease associations: Open Targets Platform (2024.06 release)
- Drug-target relationships: ChEMBL v35, Open Targets
- Pathway annotations: Reactome (2024)
- Publication evidence: PubTator Central (8.6M+ gene-publication links)
- 78,724 genes × 20,247 FDA-approved drugs × 4,740 pathways

---

**Document Created:** 2025-11-25
**Database Used:** MEDIABASE main database (mbase)
**Total Queries Executed:** 10 comprehensive validated queries
**Validation Status:** 100% query success rate (10/10 queries)
**Clinical Focus:** MSS and MSI-H colorectal carcinoma molecular profiling and therapeutic strategies
**MEDIABASE Version:** 0.6.0.2
