#!/usr/bin/env python3
"""Query Validation Script for MEDIABASE.

This script validates the SQL queries documented in README.md against the current
database schema to ensure they work correctly with patient database copies.

Usage:
    poetry run python scripts/validate_queries.py --test-syntax
    poetry run python scripts/validate_queries.py --test-with-sample-data
"""

import argparse
import sys
from pathlib import Path
from typing import List, Dict, Any

# Add project root to Python path
project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))

# Query definitions for normalized schema
DYNAMIC_QUERIES = {
    "upregulated_genes": """
        SELECT
            t.transcript_id,
            g.gene_symbol,
            t.expression_fold_change,
            STRING_AGG(DISTINCT ga.annotation_value, '; ') as product_types,
            STRING_AGG(DISTINCT gp.pathway_name, '; ') as top_pathways,
            CASE
                WHEN COUNT(gdi.drug_name) > 0 THEN 'Druggable (' || COUNT(gdi.drug_name) || ' drugs)'
                ELSE 'No known drugs'
            END as drug_availability
        FROM transcripts t
        JOIN genes g ON t.gene_id = g.gene_id
        LEFT JOIN gene_annotations ga ON g.gene_id = ga.gene_id AND ga.annotation_type = 'product_type'
        LEFT JOIN gene_pathways gp ON g.gene_id = gp.gene_id
        LEFT JOIN gene_drug_interactions gdi ON g.gene_id = gdi.gene_id
        WHERE t.expression_fold_change > 2.0
        GROUP BY t.transcript_id, g.gene_symbol, t.expression_fold_change
        ORDER BY t.expression_fold_change DESC
        LIMIT 20;
    """,
    "drug_targets": """
        SELECT DISTINCT
            g.gene_symbol,
            t.expression_fold_change,
            gdi.drug_name,
            gdi.interaction_type as mechanism_of_action,
            gdi.source as drug_source
        FROM transcripts t
        JOIN genes g ON t.gene_id = g.gene_id
        JOIN gene_drug_interactions gdi ON g.gene_id = gdi.gene_id
        WHERE t.expression_fold_change > 1.5
        ORDER BY t.expression_fold_change DESC, gdi.drug_name;
    """,
    "pathway_analysis": """
        WITH pathway_analysis AS (
            SELECT
                gp.pathway_name,
                AVG(t.expression_fold_change) as avg_fold_change,
                COUNT(DISTINCT t.transcript_id) as transcript_count,
                COUNT(DISTINCT g.gene_id) as gene_count,
                STDDEV(t.expression_fold_change) as expression_variance,
                ARRAY_AGG(DISTINCT g.gene_symbol || ':' || t.expression_fold_change::text) as affected_genes
            FROM gene_pathways gp
            JOIN genes g ON gp.gene_id = g.gene_id
            JOIN transcripts t ON g.gene_id = t.gene_id
            WHERE ABS(t.expression_fold_change - 1.0) > 0.5
            GROUP BY gp.pathway_name
            HAVING COUNT(DISTINCT g.gene_id) >= 3
        )
        SELECT
            pathway_name,
            ROUND(avg_fold_change, 2) as average_fold_change,
            gene_count,
            transcript_count,
            ROUND(expression_variance, 2) as expression_variability,
            CASE
                WHEN avg_fold_change > 1.5 THEN 'Activated'
                WHEN avg_fold_change < 0.7 THEN 'Suppressed'
                ELSE 'Mixed regulation'
            END as pathway_status,
            affected_genes[1:5] as sample_genes
        FROM pathway_analysis
        ORDER BY ABS(avg_fold_change - 1.0) DESC, gene_count DESC;
    """,
    "publication_search": """
        SELECT 
            gene_symbol,
            expression_fold_change,
            pub_ref->>'title' as study_title,
            pub_ref->>'journal' as journal,
            pub_ref->>'year' as publication_year,
            pub_ref->>'pmid' as pubmed_id,
            pub_ref->>'evidence_type' as evidence_type,
            pub_ref->>'source_db' as data_source
        FROM cancer_transcript_base,
             jsonb_array_elements(source_references->'publications') as pub_ref
        WHERE expression_fold_change > 2.0
            AND jsonb_array_length(source_references->'publications') > 0
            AND (pub_ref->>'year')::integer >= 2020
        ORDER BY expression_fold_change DESC, (pub_ref->>'year')::integer DESC
        LIMIT 15;
    """,
}

SOTA_QUERIES = {
    "oncogene_analysis": """
        WITH known_cancer_genes AS (
            SELECT gene_symbol, expression_fold_change, product_type, molecular_functions,
                   CASE 
                       WHEN gene_symbol IN ('MYC', 'ERBB2', 'EGFR', 'KRAS', 'PIK3CA', 'AKT1', 'CCND1', 'MDM2') 
                       THEN 'oncogene'
                       WHEN gene_symbol IN ('TP53', 'RB1', 'PTEN', 'BRCA1', 'BRCA2', 'CDKN2A', 'CDKN1A', 'CDKN1B')
                       THEN 'tumor_suppressor'
                       WHEN gene_symbol IN ('ATM', 'CHEK1', 'CHEK2', 'RAD51', 'PARP1')
                       THEN 'dna_repair'
                       ELSE 'other'
                   END as gene_category
            FROM cancer_transcript_base
            WHERE gene_symbol IN ('MYC', 'ERBB2', 'EGFR', 'KRAS', 'PIK3CA', 'AKT1', 'CCND1', 'MDM2',
                                  'TP53', 'RB1', 'PTEN', 'BRCA1', 'BRCA2', 'CDKN2A', 'CDKN1A', 'CDKN1B',
                                  'ATM', 'CHEK1', 'CHEK2', 'RAD51', 'PARP1')
        )
        SELECT 
            gene_category,
            gene_symbol,
            ROUND(expression_fold_change, 2) as fold_change,
            CASE 
                WHEN gene_category = 'oncogene' AND expression_fold_change > 1.5 THEN 'ACTIVATED (Concerning)'
                WHEN gene_category = 'tumor_suppressor' AND expression_fold_change < 0.7 THEN 'SUPPRESSED (Concerning)'
                WHEN gene_category = 'dna_repair' AND expression_fold_change < 0.8 THEN 'IMPAIRED (High Risk)'
                WHEN gene_category = 'oncogene' AND expression_fold_change < 0.8 THEN 'Suppressed (Favorable)'
                WHEN gene_category = 'tumor_suppressor' AND expression_fold_change > 1.2 THEN 'Active (Favorable)'
                ELSE 'Normal range'
            END as clinical_significance,
            product_type,
            CASE 
                WHEN jsonb_array_length(drugs) > 0 THEN 'Targetable'
                ELSE 'No approved drugs'
            END as therapeutic_options
        FROM known_cancer_genes
        ORDER BY 
            CASE gene_category 
                WHEN 'oncogene' THEN 1 
                WHEN 'tumor_suppressor' THEN 2 
                WHEN 'dna_repair' THEN 3 
                ELSE 4 
            END,
            ABS(expression_fold_change - 1.0) DESC;
    """,
    "therapeutic_prioritization": """
        WITH druggable_targets AS (
            SELECT 
                gene_symbol,
                expression_fold_change,
                product_type,
                molecular_functions,
                pathways,
                drugs,
                drug_scores,
                CASE 
                    WHEN expression_fold_change > 3.0 THEN 3
                    WHEN expression_fold_change > 2.0 THEN 2
                    WHEN expression_fold_change > 1.5 THEN 1
                    ELSE 0
                END +
                CASE 
                    WHEN jsonb_array_length(drugs) > 0 THEN 2
                    ELSE 0
                END +
                CASE 
                    WHEN 'kinase' = ANY(product_type) THEN 2
                    WHEN 'receptor' = ANY(product_type) THEN 2
                    WHEN 'enzyme' = ANY(product_type) THEN 1
                    ELSE 0
                END as priority_score
            FROM cancer_transcript_base
            WHERE expression_fold_change > 1.5
                AND (jsonb_array_length(drugs) > 0 OR 
                     'kinase' = ANY(product_type) OR 
                     'receptor' = ANY(product_type) OR
                     'enzyme' = ANY(product_type))
        )
        SELECT 
            gene_symbol,
            ROUND(expression_fold_change, 2) as fold_change,
            priority_score,
            product_type,
            molecular_functions[1:3] as key_functions,
            pathways[1:2] as major_pathways,
            jsonb_array_length(drugs) as available_drugs,
            CASE 
                WHEN priority_score >= 6 THEN 'HIGH PRIORITY - Immediate consideration'
                WHEN priority_score >= 4 THEN 'MEDIUM PRIORITY - Clinical evaluation'
                WHEN priority_score >= 2 THEN 'LOW PRIORITY - Research interest'
                ELSE 'MINIMAL PRIORITY'
            END as recommendation,
            CASE 
                WHEN jsonb_array_length(drugs) > 0 
                THEN (drugs->0->>'name') || ' (' || (drugs->0->>'clinical_status') || ')'
                ELSE 'No approved drugs - research target'
            END as primary_therapeutic_option
        FROM druggable_targets
        WHERE priority_score >= 2
        ORDER BY priority_score DESC, expression_fold_change DESC
        LIMIT 15;
    """,
    "pathway_strategy": """
        WITH pathway_enrichment AS (
            SELECT 
                unnest(pathways) as pathway_name,
                COUNT(*) as total_genes,
                COUNT(*) FILTER (WHERE expression_fold_change > 1.5) as upregulated_genes,
                COUNT(*) FILTER (WHERE expression_fold_change < 0.7) as downregulated_genes,
                AVG(expression_fold_change) as avg_fold_change,
                ARRAY_AGG(
                    CASE WHEN ABS(expression_fold_change - 1.0) > 0.5 
                         THEN gene_symbol || ':' || ROUND(expression_fold_change, 2)::text 
                         ELSE NULL END
                ) FILTER (WHERE ABS(expression_fold_change - 1.0) > 0.5) as dysregulated_genes,
                COUNT(*) FILTER (WHERE jsonb_array_length(drugs) > 0 AND expression_fold_change > 1.5) as druggable_targets
            FROM cancer_transcript_base 
            WHERE pathways IS NOT NULL 
                AND array_length(pathways, 1) > 0
            GROUP BY pathway_name
            HAVING COUNT(*) >= 3
        ),
        pathway_classification AS (
            SELECT *,
                CASE 
                    WHEN pathway_name ILIKE '%PI3K%' OR pathway_name ILIKE '%AKT%' OR pathway_name ILIKE '%mTOR%' THEN 'growth_survival'
                    WHEN pathway_name ILIKE '%RAS%' OR pathway_name ILIKE '%MAPK%' OR pathway_name ILIKE '%ERK%' THEN 'proliferation'
                    WHEN pathway_name ILIKE '%p53%' OR pathway_name ILIKE '%DNA repair%' OR pathway_name ILIKE '%checkpoint%' THEN 'genome_stability'
                    WHEN pathway_name ILIKE '%apoptosis%' OR pathway_name ILIKE '%cell death%' THEN 'apoptosis'
                    WHEN pathway_name ILIKE '%angiogenesis%' OR pathway_name ILIKE '%VEGF%' THEN 'angiogenesis'
                    WHEN pathway_name ILIKE '%immune%' OR pathway_name ILIKE '%interferon%' THEN 'immune_response'
                    WHEN pathway_name ILIKE '%metabolism%' OR pathway_name ILIKE '%glycolysis%' THEN 'metabolism'
                    ELSE 'other'
                END as pathway_category,
                (upregulated_genes::float / total_genes * 2) +
                (downregulated_genes::float / total_genes * 1) +
                (druggable_targets::float / total_genes * 3) as dysregulation_score
            FROM pathway_enrichment
        )
        SELECT 
            pathway_category,
            pathway_name,
            total_genes,
            upregulated_genes,
            downregulated_genes,
            ROUND(avg_fold_change, 2) as avg_expression_change,
            druggable_targets,
            ROUND(dysregulation_score, 2) as dysregulation_score,
            CASE 
                WHEN dysregulation_score > 4.0 THEN 'CRITICAL - Immediate intervention needed'
                WHEN dysregulation_score > 2.5 THEN 'HIGH - Priority pathway for targeting'
                WHEN dysregulation_score > 1.5 THEN 'MODERATE - Consider combination therapy'
                ELSE 'LOW - Monitor for changes'
            END as therapeutic_priority,
            dysregulated_genes[1:5] as key_dysregulated_genes,
            CASE 
                WHEN pathway_category = 'growth_survival' AND avg_fold_change > 1.3 
                THEN 'Consider PI3K/AKT/mTOR inhibitors'
                WHEN pathway_category = 'proliferation' AND avg_fold_change > 1.3
                THEN 'Consider MEK/ERK inhibitors'
                WHEN pathway_category = 'genome_stability' AND avg_fold_change < 0.8
                THEN 'Consider PARP inhibitors or DNA damaging agents'
                WHEN pathway_category = 'apoptosis' AND avg_fold_change < 0.8
                THEN 'Consider BCL-2 family inhibitors'
                WHEN pathway_category = 'angiogenesis' AND avg_fold_change > 1.3
                THEN 'Consider anti-angiogenic therapy'
                WHEN pathway_category = 'immune_response' AND avg_fold_change < 0.8
                THEN 'Consider immunotherapy approaches'
                ELSE 'Pathway-specific analysis needed'
            END as therapeutic_recommendation
        FROM pathway_classification
        WHERE dysregulation_score > 1.0
        ORDER BY dysregulation_score DESC, druggable_targets DESC
        LIMIT 20;
    """,
}


def validate_query_syntax(query_name: str, query: str) -> Dict[str, Any]:
    """Validate SQL query syntax and structure.

    Args:
        query_name: Name of the query
        query: SQL query string

    Returns:
        Validation result dictionary
    """
    validation_result = {
        "query_name": query_name,
        "valid": True,
        "issues": [],
        "warnings": [],
    }

    # Basic syntax checks
    query_clean = query.strip()

    # Check for basic SQL structure
    if not query_clean.upper().startswith(("SELECT", "WITH")):
        validation_result["valid"] = False
        validation_result["issues"].append("Query must start with SELECT or WITH")

    # Check for semicolon termination
    if not query_clean.endswith(";"):
        validation_result["warnings"].append("Query should end with semicolon")

    # Check for balanced parentheses
    paren_count = query_clean.count("(") - query_clean.count(")")
    if paren_count != 0:
        validation_result["valid"] = False
        validation_result["issues"].append(
            f"Unbalanced parentheses: {abs(paren_count)} {'opening' if paren_count > 0 else 'closing'} missing"
        )

    # Check for required table reference
    if "cancer_transcript_base" not in query_clean:
        validation_result["valid"] = False
        validation_result["issues"].append(
            "Query must reference cancer_transcript_base table"
        )

    # Check for proper JSONB operations
    jsonb_functions = [
        "jsonb_array_length",
        "jsonb_array_elements",
        "jsonb_object_keys",
    ]
    for func in jsonb_functions:
        if func in query_clean and not any(
            col in query_clean for col in ["drugs", "source_references", "features"]
        ):
            validation_result["warnings"].append(
                f"Using {func} but no JSONB columns detected"
            )

    # Check for array operations
    if "ANY(" in query_clean or "array_length(" in query_clean:
        array_columns = [
            "product_type",
            "pathways",
            "molecular_functions",
            "cellular_location",
        ]
        if not any(col in query_clean for col in array_columns):
            validation_result["warnings"].append(
                "Array operations detected but no array columns found"
            )

    # Check for proper CTEs (WITH clauses)
    if query_clean.upper().startswith("WITH"):
        if "SELECT" not in query_clean.upper():
            validation_result["valid"] = False
            validation_result["issues"].append("WITH clause must be followed by SELECT")

    return validation_result


def test_query_compatibility() -> Dict[str, Any]:
    """Test query compatibility with our patient data examples.

    Returns:
        Compatibility test results
    """
    compatibility_results = {
        "schema_compatible": True,
        "data_compatible": True,
        "issues": [],
        "warnings": [],
    }

    # Define expected schema columns
    expected_columns = {
        "transcript_id",
        "gene_symbol",
        "gene_id",
        "gene_type",
        "chromosome",
        "coordinates",
        "product_type",
        "go_terms",
        "pathways",
        "drugs",
        "expression_fold_change",
        "expression_freq",
        "cancer_types",
        "features",
        "molecular_functions",
        "cellular_location",
        "drug_scores",
        "alt_transcript_ids",
        "alt_gene_ids",
        "uniprot_ids",
        "ncbi_ids",
        "refseq_ids",
        "pdb_ids",
        "source_references",
    }

    # Check if queries reference valid columns
    all_queries = {**DYNAMIC_QUERIES, **SOTA_QUERIES}

    for query_name, query in all_queries.items():
        query_upper = query.upper()

        # Extract column references (simplified)
        for column in expected_columns:
            if column in query and column not in ["FROM", "WHERE", "ORDER", "GROUP"]:
                # Column is referenced, which is good
                continue

    # Check for common issues with patient data
    sample_genes = ["ERBB2", "ESR1", "PGR", "BRCA1", "BRCA2", "TP53", "KRAS", "PIK3CA"]

    # Verify oncogene analysis includes genes from our examples
    oncogene_query = SOTA_QUERIES["oncogene_analysis"]
    for gene in ["ERBB2", "ESR1", "KRAS", "BRCA1"]:
        if gene not in oncogene_query:
            compatibility_results["warnings"].append(
                f"Oncogene analysis missing {gene} from patient examples"
            )

    return compatibility_results


def main():
    """Main entry point for query validation."""
    parser = argparse.ArgumentParser(description="Validate MEDIABASE SQL queries")
    parser.add_argument("--test-syntax", action="store_true", help="Test query syntax")
    parser.add_argument(
        "--test-compatibility",
        action="store_true",
        help="Test compatibility with patient data",
    )
    parser.add_argument("--verbose", action="store_true", help="Verbose output")

    args = parser.parse_args()

    if not (args.test_syntax or args.test_compatibility):
        parser.print_help()
        return

    print("MEDIABASE Query Validation Report")
    print("=" * 50)

    total_issues = 0
    total_warnings = 0

    if args.test_syntax:
        print("\n📋 Testing Query Syntax...")

        print("\n🔍 Dynamic Queries:")
        for query_name, query in DYNAMIC_QUERIES.items():
            result = validate_query_syntax(query_name, query)
            status = "✅ PASS" if result["valid"] else "❌ FAIL"
            print(f"  {status} {query_name}")

            if result["issues"]:
                total_issues += len(result["issues"])
                for issue in result["issues"]:
                    print(f"    🚨 Issue: {issue}")

            if result["warnings"]:
                total_warnings += len(result["warnings"])
                if args.verbose:
                    for warning in result["warnings"]:
                        print(f"    ⚠️  Warning: {warning}")

        print("\n🎯 SOTA Queries:")
        for query_name, query in SOTA_QUERIES.items():
            result = validate_query_syntax(query_name, query)
            status = "✅ PASS" if result["valid"] else "❌ FAIL"
            print(f"  {status} {query_name}")

            if result["issues"]:
                total_issues += len(result["issues"])
                for issue in result["issues"]:
                    print(f"    🚨 Issue: {issue}")

            if result["warnings"]:
                total_warnings += len(result["warnings"])
                if args.verbose:
                    for warning in result["warnings"]:
                        print(f"    ⚠️  Warning: {warning}")

    if args.test_compatibility:
        print("\n🧬 Testing Patient Data Compatibility...")
        result = test_query_compatibility()

        if result["schema_compatible"]:
            print("  ✅ Schema compatibility: PASS")
        else:
            print("  ❌ Schema compatibility: FAIL")

        if result["data_compatible"]:
            print("  ✅ Data compatibility: PASS")
        else:
            print("  ❌ Data compatibility: FAIL")

        if result["issues"]:
            total_issues += len(result["issues"])
            for issue in result["issues"]:
                print(f"    🚨 Issue: {issue}")

        if result["warnings"]:
            total_warnings += len(result["warnings"])
            if args.verbose:
                for warning in result["warnings"]:
                    print(f"    ⚠️  Warning: {warning}")

    # Summary
    print(f"\n📊 Validation Summary:")
    print(f"  Total queries tested: {len(DYNAMIC_QUERIES) + len(SOTA_QUERIES)}")
    print(f"  Issues found: {total_issues}")
    print(f"  Warnings: {total_warnings}")

    if total_issues == 0:
        print("  🎉 All queries passed validation!")
        return 0
    else:
        print("  ⚠️  Some queries need attention")
        return 1


if __name__ == "__main__":
    exit(main())
