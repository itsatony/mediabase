# Cancer-Specific Query Guides
**MEDIABASE v0.6.0** | Production-Ready SQL Query Library

This directory contains clinically-focused query guides for major cancer types. Each guide provides step-by-step SQL queries to assist oncologists in therapeutic decision-making based on patient transcriptome data.

---

## Available Query Guides

### 1. [HER2+ Breast Cancer Query Guide](HER2_BREAST_CANCER_QUERY_GUIDE.sql)
**Cancer Type:** HER2-Positive (ERBB2-Amplified) Breast Cancer

**Key Analyses:**
- HER2 amplification confirmation (ERBB2 >4.0x threshold)
- FDA-approved anti-HER2 therapies (Trastuzumab, Pertuzumab, T-DM1, T-DXd)
- PI3K/AKT pathway activation (resistance mechanism assessment)
- CDK4/6 inhibitor eligibility (HR+/HER2+ subtype)
- Comprehensive treatment recommendations (1st, 2nd, 3rd line)

**Patient Schema:** Use `patient_synthetic_her2` for testing

**Clinical Trials Referenced:**
- CLEOPATRA (Pertuzumab + Trastuzumab)
- FLAURA (Osimertinib first-line)
- MonarcHER (CDK4/6 + anti-HER2)

---

### 2. [Triple-Negative Breast Cancer (TNBC) Query Guide](TNBC_QUERY_GUIDE.sql)
**Cancer Type:** Triple-Negative Breast Cancer (ER-, PR-, HER2-)

**Key Analyses:**
- Triple-negative status confirmation (ESR1, PGR, ERBB2 all low)
- PARP inhibitor eligibility (BRCA1/2 deficiency markers)
- Immune checkpoint inhibitor eligibility (PD-L1/CD274 expression)
- Targetable genomic alterations (PI3K, AKT, AR for LAR subtype)
- Basal-like subtype markers (KRT5, KRT14, KRT17)

**Patient Schema:** Use `patient_synthetic_tnbc` for testing

**Clinical Trials Referenced:**
- KEYNOTE-355 (Pembrolizumab + chemotherapy)
- OlympiAD (Olaparib in BRCA-mutant)
- CAPItello-291 (Capivasertib AKT inhibitor)

**FDA-Approved Therapies:**
- Pembrolizumab (PD-L1+ first-line)
- Olaparib, Talazoparib (BRCA-mutant)
- Sacituzumab govitecan (Trodelvy, second-line)

---

### 3. [Lung Adenocarcinoma (EGFR-Mutant) Query Guide](LUAD_EGFR_QUERY_GUIDE.sql)
**Cancer Type:** EGFR-Mutant Lung Adenocarcinoma (LUAD)

**Key Analyses:**
- EGFR pathway activation assessment (EGFR, MAPK, PI3K/AKT)
- FDA-approved EGFR TKIs (1st, 2nd, 3rd generation)
- Resistance mechanisms (MET amplification, HER3 bypass, BRAF)
- Angiogenesis pathway (VEGF/VEGFR for ramucirumab)
- Immune checkpoint status (PD-L1 typically low in EGFR-mutant)

**Patient Schema:** Use `patient_synthetic_luad` for testing

**Clinical Trials Referenced:**
- FLAURA (Osimertinib first-line)
- ADAURA (Osimertinib adjuvant)
- RELAY (Ramucirumab + erlotinib)
- MARIPOSA (Amivantamab + lazertinib)

**FDA-Approved Therapies:**
- Osimertinib (3rd-gen, first-line standard)
- Erlotinib, Gefitinib (1st-gen)
- Afatinib, Dacomitinib (2nd-gen)
- Ramucirumab (anti-VEGFR2, combination)

---

### 4. [Colorectal Cancer (CRC) Query Guide](COLORECTAL_CANCER_QUERY_GUIDE.sql)
**Cancer Type:** Metastatic Colorectal Cancer (All Subtypes)

**Key Analyses:**
- KRAS/BRAF mutation status (anti-EGFR therapy eligibility)
- MSI-H/dMMR markers (immunotherapy eligibility)
- VEGF pathway activation (bevacizumab, ramucirumab)
- HER2 amplification assessment (~5% of CRC, emerging target)
- Comprehensive treatment algorithm (MSI-H, RAS WT, BRAF V600E)

**Patient Schema:** Template provided (modify with your CRC patient ID)

**Clinical Trials Referenced:**
- KEYNOTE-177 (Pembrolizumab MSI-H first-line)
- BEACON (Encorafenib + Cetuximab BRAF V600E)
- MOUNTAINEER (Tucatinib + Trastuzumab HER2+)
- RAISE (Ramucirumab + FOLFIRI)

**FDA-Approved Therapies:**
- Pembrolizumab, Nivolumab (MSI-H/dMMR)
- Cetuximab, Panitumumab (RAS/BRAF WT, anti-EGFR)
- Bevacizumab, Ramucirumab (anti-VEGF, all subtypes)
- Encorafenib + Cetuximab (BRAF V600E)
- Trastuzumab + Pertuzumab (HER2+ off-label/trials)

---

## How to Use These Guides

### Step 1: Connect to MEDIABASE Database
```bash
# Connect to the mbase database (contains public schema + all patient schemas)
PGPASSWORD=mbase_secret psql -h localhost -p 5435 -U mbase_user -d mbase
```

### Step 2: Identify Your Patient Schema
```sql
-- List all available patient schemas
SELECT schema_name
FROM information_schema.schemata
WHERE schema_name LIKE 'patient_%'
ORDER BY schema_name;
```

### Step 3: Run Cancer-Specific Query Guide
```bash
# Example: Run HER2+ breast cancer guide
PGPASSWORD=mbase_secret psql -h localhost -p 5435 -U mbase_user -d mbase \
  -f docs/queries/HER2_BREAST_CANCER_QUERY_GUIDE.sql
```

### Step 4: Modify Patient Schema Name
Each query guide includes a `\set PATIENT_SCHEMA` directive at the top. Modify this to match your actual patient schema:

```sql
-- Example from HER2_BREAST_CANCER_QUERY_GUIDE.sql
\set PATIENT_SCHEMA 'patient_synthetic_her2'

-- Change to your actual patient:
\set PATIENT_SCHEMA 'patient_YOUR_PATIENT_ID'
```

---

## Query Architecture (v0.6.0)

All queries follow the **v0.6.0 Shared Core Architecture:**

```sql
SELECT
    g.gene_symbol,
    COALESCE(pe.expression_fold_change, 1.0) as fold_change,
    -- Therapeutic interpretation logic
FROM public.genes g
LEFT JOIN patient_YOUR_PATIENT_ID.expression_data pe
    ON g.gene_id = pe.gene_id
WHERE g.gene_symbol IN ('ERBB2', 'PIK3CA', ...)
ORDER BY COALESCE(pe.expression_fold_change, 1.0) DESC;
```

**Key Pattern Elements:**
- `public.genes`: Shared core gene annotations
- `patient_<ID>.expression_data`: Patient-specific fold-change values
- `COALESCE(pe.expression_fold_change, 1.0)`: Baseline 1.0 for non-stored values
- **Sparse Storage**: Only stores fold_change != 1.0 (99.68% storage savings)

---

## Testing with Synthetic Patient Data

Three synthetic patient schemas are available for testing:

| Schema Name | Cancer Type | Key Signature Genes | Example ERBB2/EGFR Fold-Change |
|-------------|-------------|---------------------|-------------------------------|
| `patient_synthetic_her2` | HER2+ Breast Cancer | ERBB2 (5.51x), GRB7 (4.54x), PIK3CA (2.51x) | ERBB2 = 5.51x |
| `patient_synthetic_tnbc` | TNBC | ESR1 (0.15x), TP53 (0.26x), KRT5 (4.28x) | ERBB2 = 0.81x |
| `patient_synthetic_luad` | EGFR+ Lung Cancer | EGFR (4.20x), AKT1 (3.16x), VEGFA (3.28x) | EGFR = 4.20x |

---

## Clinical Decision Support Features

Each guide provides:

1. **Diagnostic Confirmation:** Verify molecular subtype (HER2+, TNBC, EGFR-mutant, etc.)
2. **FDA-Approved Therapies:** List approved drugs with mechanisms and indications
3. **Resistance Mechanisms:** Assess pathway activation predicting treatment failure
4. **Combination Opportunities:** Identify synergistic therapy combinations
5. **Publication Evidence:** PubMed links for supporting scientific literature
6. **Treatment Algorithm:** Prioritized 1st, 2nd, 3rd-line recommendations

---

## Important Clinical Notes

### RNA Expression vs. DNA Mutation Status

**CRITICAL REMINDER:**
- RNA expression (fold-change) is a **surrogate marker** for mutation status
- **ALWAYS confirm** with DNA sequencing:
  - KRAS/NRAS/BRAF mutations (CRC anti-EGFR eligibility)
  - EGFR mutations (Lung cancer TKI eligibility)
  - BRCA1/2 mutations (PARP inhibitor eligibility)
  - TP53, PIK3CA mutations

- RNA overexpression does **NOT** indicate mutation presence
- RNA underexpression suggests but does **NOT** confirm loss/mutation

### Testing Requirements Before Therapy

| Cancer Type | Required Confirmatory Tests |
|-------------|----------------------------|
| HER2+ Breast | IHC 3+ or FISH amplification (HER2:CEP17 ratio ≥2.0) |
| TNBC | IHC for ER/PR/HER2; Consider germline BRCA testing |
| EGFR+ Lung | DNA sequencing for EGFR mutations (Exon 19 del, L858R, T790M) |
| CRC | DNA sequencing for KRAS, NRAS, BRAF; MSI-H/dMMR testing (IHC or PCR) |

---

## Additional Resources

### General Query Libraries
- **[WORKING_QUERY_EXAMPLES.sql](../WORKING_QUERY_EXAMPLES.sql):** Comprehensive verified query library (20 queries, 100% success rate)
- **[SOTA_QUERIES_GUIDE.md](../SOTA_QUERIES_GUIDE.md):** State-of-the-art query methodologies

### Documentation
- **[MEDIABASE_QUERY_LIBRARY.md](../MEDIABASE_QUERY_LIBRARY.md):** Complete query reference
- **[MEDIABASE_SCHEMA_REFERENCE.md](../MEDIABASE_SCHEMA_REFERENCE.md):** Database schema documentation
- **[README.md](../../README.md):** Project overview and quickstart

### API Access
- **API Server:** `http://localhost:8000/api/v1/transcripts`
- **Interactive Docs:** `http://localhost:8000/docs`

---

## Support and Feedback

For questions, issues, or feature requests:
- **GitHub Issues:** https://github.com/your-repo/mediabase/issues
- **Documentation:** https://code.claude.com/docs/

**Version:** MEDIABASE v0.6.0
**Last Updated:** 2025-11-28
**Query Success Rate:** 100% (20/20 queries verified)
