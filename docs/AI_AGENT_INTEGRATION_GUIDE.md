# AI Agent Integration Guide for MEDIABASE

Practical guide for integrating LLM-based AI agents with MEDIABASE cancer transcriptomics database for automated clinical decision support.

## Overview

MEDIABASE provides structured cancer transcriptomics data optimized for AI agent consumption. This guide shows how to translate natural language questions into SQL queries and interpret results clinically.

## Database Connection

```python
import psycopg2

conn = psycopg2.connect(
    host="localhost",
    port=5435,
    database="mbase",  # Or patient-specific: mediabase_patient_PATIENT_ID
    user="mbase_user",
    password="mbase_secret"
)
```

## Natural Language → SQL Translation Patterns

### Pattern 1: Drug Recommendations

**Natural Language:** "Which FDA-approved drugs target overexpressed genes in this patient?"

**SQL Template:**
```sql
SELECT
    g.gene_symbol,
    ctb.expression_fold_change,
    otd.drug_name,
    otd.mechanism_of_action,
    otd.phase
FROM cancer_transcript_base ctb
JOIN genes g ON ctb.gene_id = g.gene_id
JOIN opentargets_known_drugs otd ON g.gene_id = otd.gene_id
WHERE ctb.expression_fold_change > {threshold}
  AND otd.phase = 'Phase IV'
ORDER BY ctb.expression_fold_change DESC;
```

**Parameters:**
- `{threshold}`: Typically 2.0 for overexpression, 0.5 for underexpression

### Pattern 2: Pathway Enrichment

**Natural Language:** "Which biological pathways are dysregulated?"

**SQL Template:**
```sql
SELECT
    gp.pathway_name,
    COUNT(*) as gene_count,
    AVG(ctb.expression_fold_change) as avg_fold_change
FROM gene_pathways gp
JOIN cancer_transcript_base ctb ON gp.gene_id = ctb.gene_id
WHERE ctb.expression_fold_change != 1.0
GROUP BY gp.pathway_name
HAVING COUNT(*) >= 3
ORDER BY gene_count DESC, avg_fold_change DESC;
```

### Pattern 3: Disease Association

**Natural Language:** "What cancer types are associated with these genes?"

**SQL Template:**
```sql
SELECT
    od.disease_name,
    COUNT(DISTINCT ogda.gene_id) as associated_genes,
    AVG(ogda.overall_score) as avg_association_score
FROM opentargets_gene_disease_associations ogda
JOIN opentargets_diseases od ON ogda.disease_id = od.disease_id
JOIN cancer_transcript_base ctb ON ogda.gene_id = ctb.gene_id
WHERE ctb.expression_fold_change > 2.0
GROUP BY od.disease_name
ORDER BY associated_genes DESC, avg_association_score DESC;
```

### Pattern 4: Literature Support

**Natural Language:** "Which genes have strong literature support?"

**SQL Template:**
```sql
SELECT
    g.gene_symbol,
    COUNT(gp.pmid) as publication_count,
    SUM(gp.mention_count) as total_mentions
FROM genes g
JOIN gene_publications gp ON g.gene_id = gp.gene_id
JOIN cancer_transcript_base ctb ON g.gene_id = ctb.gene_id
WHERE ctb.expression_fold_change > {threshold}
GROUP BY g.gene_symbol
HAVING COUNT(gp.pmid) > 100
ORDER BY publication_count DESC;
```

### Pattern 5: Multi-Omics Integration

**Natural Language:** "Give me a comprehensive profile of actionable genes"

**SQL Template:**
```sql
SELECT
    g.gene_symbol,
    g.gene_name,
    ctb.expression_fold_change,
    COUNT(DISTINCT otd.drug_name) as drug_count,
    COUNT(DISTINCT gp.pathway_name) as pathway_count,
    COUNT(DISTINCT gpub.pmid) as publication_count,
    MAX(ogda.overall_score) as max_disease_score
FROM cancer_transcript_base ctb
JOIN genes g ON ctb.gene_id = g.gene_id
LEFT JOIN opentargets_known_drugs otd ON g.gene_id = otd.gene_id AND otd.phase IN ('Phase IV', 'Phase III')
LEFT JOIN gene_pathways gp ON g.gene_id = gp.gene_id
LEFT JOIN gene_publications gpub ON g.gene_id = gpub.gene_id
LEFT JOIN opentargets_gene_disease_associations ogda ON g.gene_id = ogda.gene_id
WHERE ctb.expression_fold_change > 2.0
GROUP BY g.gene_symbol, g.gene_name, ctb.expression_fold_change
HAVING COUNT(DISTINCT otd.drug_name) > 0
ORDER BY drug_count DESC, ctb.expression_fold_change DESC;
```

## Query Optimization Tips

### 1. Use Indexes Efficiently
- Always filter on indexed columns: `gene_id`, `gene_symbol`, `pmid`
- Use `expression_fold_change` filters early in WHERE clause

### 2. Limit Result Sets
```sql
LIMIT 20  -- Top 20 results typically sufficient for clinical review
```

### 3. Avoid SELECT *
```sql
-- Bad: SELECT * FROM genes
-- Good: SELECT gene_symbol, gene_name FROM genes
```

## Result Interpretation Framework

### Fold-Change Thresholds
- **>5.0:** Strong overexpression (high priority target)
- **2.0-5.0:** Moderate overexpression (actionable target)
- **0.5-2.0:** Baseline expression (monitor)
- **<0.5:** Underexpression (potential tumor suppressor loss)

### Drug Phase Classification
- **Phase IV:** FDA-approved (prescribe immediately)
- **Phase III:** Late-stage trials (clinical trial enrollment)
- **Phase II:** Mid-stage trials (experimental options)
- **Phase I:** Early trials (salvage therapy only)

### Disease Score Interpretation (OpenTargets)
- **>0.8:** Very strong association (definitive therapeutic target)
- **0.5-0.8:** Strong association (prioritize for treatment)
- **0.2-0.5:** Moderate association (consider as secondary target)
- **<0.2:** Weak association (deprioritize)

### Literature Count Guidelines
- **>1000 publications:** Well-studied gene (reliable target)
- **100-1000:** Moderate evidence (validate with other sources)
- **10-100:** Limited evidence (requires careful evaluation)
- **<10:** Poorly characterized (high-risk target)

## Error Handling

### Common Query Errors

**1. No Results Found**
```python
if not results:
    return "No actionable targets found at expression threshold {threshold}. Consider lowering threshold or expanding search criteria."
```

**2. Database Connection Lost**
```python
try:
    cursor.execute(query)
except psycopg2.OperationalError:
    reconnect()
    cursor.execute(query)
```

**3. Invalid Gene Symbol**
```python
# Validate gene symbol exists
check_query = "SELECT COUNT(*) FROM genes WHERE gene_symbol = %s"
if count == 0:
    return f"Gene symbol {gene_symbol} not found in database. Check spelling or use Ensembl ID."
```

## Example AI Agent Workflow

```python
def generate_treatment_report(patient_id: str) -> dict:
    """Generate comprehensive treatment report for patient."""

    # 1. Connect to patient database
    conn = connect_patient_db(patient_id)

    # 2. Find overexpressed drug targets
    targets = query_drug_targets(conn, fold_threshold=2.0)

    # 3. Identify dysregulated pathways
    pathways = query_pathway_enrichment(conn, min_genes=3)

    # 4. Check disease associations
    diseases = query_disease_associations(conn)

    # 5. Assess literature support
    literature = query_publication_support(conn, targets)

    # 6. Rank by actionability
    ranked_targets = rank_by_actionability(
        targets, pathways, diseases, literature
    )

    # 7. Generate clinical recommendations
    recommendations = generate_recommendations(ranked_targets)

    return {
        "patient_id": patient_id,
        "top_targets": ranked_targets[:10],
        "pathways": pathways[:5],
        "recommendations": recommendations,
        "evidence_summary": literature
    }
```

## Actionability Scoring Algorithm

```python
def calculate_actionability_score(gene_data: dict) -> float:
    """Calculate 0-100 actionability score for gene target."""

    score = 0.0

    # Expression level (0-30 points)
    fold_change = gene_data['expression_fold_change']
    if fold_change > 5.0:
        score += 30
    elif fold_change > 2.0:
        score += 20
    elif fold_change > 1.5:
        score += 10

    # Drug availability (0-25 points)
    if gene_data['fda_approved_drugs'] > 0:
        score += 25
    elif gene_data['phase3_drugs'] > 0:
        score += 15
    elif gene_data['phase2_drugs'] > 0:
        score += 5

    # Disease association (0-20 points)
    disease_score = gene_data.get('disease_score', 0)
    score += disease_score * 20

    # Literature support (0-15 points)
    pub_count = gene_data.get('publication_count', 0)
    if pub_count > 1000:
        score += 15
    elif pub_count > 100:
        score += 10
    elif pub_count > 10:
        score += 5

    # Pathway membership (0-10 points)
    pathway_count = gene_data.get('pathway_count', 0)
    score += min(pathway_count, 10)

    return min(score, 100.0)
```

## Clinical Report Template

```markdown
# Molecular Treatment Report

**Patient ID:** {patient_id}
**Report Date:** {date}
**Cancer Type:** {cancer_type}

## Top Therapeutic Targets

### 1. {gene_symbol} ({expression_fold_change}x overexpressed)
- **FDA-Approved Drugs:** {drug_list}
- **Mechanism:** {mechanism_of_action}
- **Clinical Evidence:** {publication_count} publications, {disease_score} disease association
- **Recommendation:** {clinical_recommendation}

[Repeat for top 5-10 targets]

## Dysregulated Pathways
- {pathway_name} ({gene_count} genes affected)
- Treatment implications: {implications}

## Treatment Recommendations

### First-Line Therapy
{drug_combination_1}

### Second-Line Therapy (if progression)
{drug_combination_2}

### Clinical Trial Opportunities
{trial_recommendations}

## References
- NCCN Guidelines: {cancer_type}
- OpenTargets Disease Association: {disease_id}
- Key Publications: {top_pmids}
```

## Best Practices

1. **Always validate gene symbols** before querying
2. **Use parameterized queries** to prevent SQL injection
3. **Cache common queries** (e.g., drug lists, pathway mappings)
4. **Limit result sets** to clinically actionable targets (top 10-20)
5. **Provide confidence scores** with all recommendations
6. **Include literature citations** for all therapeutic suggestions
7. **Flag experimental therapies** clearly (Phase I/II trials)
8. **Consider drug-drug interactions** when suggesting combinations
9. **Account for tumor type** in treatment recommendations
10. **Always include human review requirement** in reports

## Integration with LLM Systems

### Prompt Engineering Tips

```python
system_prompt = """
You are a precision oncology AI assistant with access to MEDIABASE cancer transcriptomics database.

When answering treatment questions:
1. Query the database for relevant biomarkers
2. Prioritize FDA-approved drugs over experimental therapies
3. Consider literature support (>100 publications = well-validated)
4. Flag resistance mechanisms (compensatory pathway activation)
5. Always recommend human oncologist review

Available query patterns:
- drug_targets: Find druggable overexpressed genes
- pathway_enrichment: Identify dysregulated pathways
- disease_associations: Match molecular profile to disease subtypes
- literature_support: Assess evidence quality
- multi_omics: Comprehensive actionability profile
"""
```

### Function Calling Integration (OpenAI Format)

```python
functions = [
    {
        "name": "query_drug_targets",
        "description": "Find FDA-approved drugs targeting overexpressed genes",
        "parameters": {
            "type": "object",
            "properties": {
                "fold_threshold": {"type": "number", "default": 2.0},
                "drug_phase": {"type": "string", "enum": ["Phase IV", "Phase III"]},
                "cancer_type": {"type": "string"}
            },
            "required": ["cancer_type"]
        }
    },
    {
        "name": "query_pathway_enrichment",
        "description": "Identify dysregulated biological pathways",
        "parameters": {
            "type": "object",
            "properties": {
                "min_genes": {"type": "integer", "default": 3},
                "pathway_category": {"type": "string"}
            }
        }
    }
]
```

## Resources

- **MEDIABASE Schema Reference:** `MEDIABASE_SCHEMA_REFERENCE.md`
- **Query Library:** `MEDIABASE_QUERY_LIBRARY.md`
- **Breast Cancer Guide:** `BREAST_CANCER_HER2_GUIDE.md`
- **Colorectal Cancer Guide:** `COLORECTAL_CANCER_GUIDE.md`
- **OpenTargets Platform:** https://platform.opentargets.org/
- **NCCN Guidelines:** https://www.nccn.org/guidelines

## Support and Updates

For questions or contributions:
- GitHub Issues: [mediabase repository]
- Documentation: `/docs` directory
- Example queries: `MEDIABASE_QUERY_LIBRARY.md`

---

*This guide is for AI agent developers integrating with MEDIABASE. All clinical recommendations must be reviewed by qualified oncologists before patient care decisions.*
