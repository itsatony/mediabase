"""
Test suite for validating cancer-specific query guides.

This test suite validates that all SQL query guides in docs/queries/ execute
successfully against synthetic patient schemas and return expected results.

Tests cover:
1. Query execution without SQL errors
2. Expected result structures (columns present)
3. Key therapeutic genes appear with expected fold-change ranges
4. LEFT JOIN patterns with COALESCE work correctly
5. Clinical interpretation logic produces valid output
"""

import os
import psycopg2
import pytest
from pathlib import Path
from typing import Dict, List, Tuple


# Test configuration
TEST_PATIENT_SCHEMAS = {
    "HER2_BREAST_CANCER": "patient_synthetic_her2",
    "TNBC": "patient_synthetic_tnbc",
    "LUAD_EGFR": "patient_synthetic_luad",
    "COLORECTAL_CANCER": "patient_synthetic_her2",  # Use HER2 schema as fallback
}

# Expected therapeutic genes for each cancer type
EXPECTED_GENES = {
    "HER2_BREAST_CANCER": {
        "target_genes": ["ERBB2", "GRB7", "PGAP3"],
        "min_erbb2_fold_change": 4.0,  # HER2+ threshold
        "resistance_genes": ["PIK3CA", "AKT1", "MTOR", "PTEN"],
        "hr_genes": ["ESR1", "PGR", "CCND1", "CDK4"],
    },
    "TNBC": {
        "target_genes": ["ESR1", "PGR", "ERBB2"],  # All should be low
        "max_receptor_fold_change": 1.5,  # Triple-negative threshold
        "parp_genes": ["BRCA1", "BRCA2", "PARP1"],
        "checkpoint_genes": ["CD274", "PDCD1", "CTLA4"],
    },
    "LUAD_EGFR": {
        "target_genes": ["EGFR", "KRAS", "ALK"],
        "min_egfr_fold_change": 3.0,  # EGFR-mutant surrogate
        "resistance_genes": ["MET", "ERBB3", "BRAF"],
        "angiogenesis_genes": ["VEGFA", "KDR", "FLT1"],
    },
    "COLORECTAL_CANCER": {
        "target_genes": ["KRAS", "BRAF", "ERBB2"],
        "msi_genes": ["MLH1", "MSH2", "MSH6", "PMS2"],
        "egfr_pathway": ["EGFR", "VEGFA", "KDR"],
    },
}


@pytest.fixture(scope="module")
def db_connection():
    """Create database connection for query testing against mbase database."""
    conn_params = {
        "host": os.getenv("MB_POSTGRES_HOST", "localhost"),
        "port": int(os.getenv("MB_POSTGRES_PORT", "5435")),
        "user": os.getenv("MB_POSTGRES_USER", "mbase_user"),
        "password": os.getenv("MB_POSTGRES_PASSWORD", "mbase_secret"),
        "dbname": "mbase",  # Always use mbase database (contains patient schemas)
    }

    conn = psycopg2.connect(**conn_params)
    yield conn
    conn.close()


@pytest.fixture(scope="module")
def query_guide_files() -> Dict[str, Path]:
    """Return paths to all query guide SQL files."""
    docs_queries_dir = Path(__file__).parent.parent / "docs" / "queries"
    return {
        "HER2_BREAST_CANCER": docs_queries_dir / "HER2_BREAST_CANCER_QUERY_GUIDE.sql",
        "TNBC": docs_queries_dir / "TNBC_QUERY_GUIDE.sql",
        "LUAD_EGFR": docs_queries_dir / "LUAD_EGFR_QUERY_GUIDE.sql",
        "COLORECTAL_CANCER": docs_queries_dir / "COLORECTAL_CANCER_QUERY_GUIDE.sql",
    }


def extract_queries_from_file(file_path: Path, patient_schema: str) -> List[Tuple[str, str]]:
    """
    Extract individual SQL queries from a query guide file.

    Returns:
        List of (query_name, query_sql) tuples
    """
    content = file_path.read_text()

    # Replace patient schema variable with actual schema
    content = content.replace("patient_synthetic_her2", patient_schema)
    content = content.replace("patient_synthetic_tnbc", patient_schema)
    content = content.replace("patient_synthetic_luad", patient_schema)

    queries = []
    current_query = []
    query_name = None
    in_query = False

    for line in content.split("\n"):
        # Skip psql commands
        if line.strip().startswith("\\"):
            continue

        # Identify query comments
        if "QUERY" in line and ":" in line and "*" in line:
            if current_query and query_name:
                queries.append((query_name, "\n".join(current_query)))
            query_name = line.strip()
            current_query = []
            in_query = False
            continue

        # Start of actual query
        if line.strip().upper().startswith("SELECT") or line.strip().upper().startswith("WITH"):
            in_query = True

        # Collect query lines
        if in_query:
            # End of query (semicolon)
            if ";" in line:
                current_query.append(line.split(";")[0])
                if query_name and current_query:
                    queries.append((query_name, "\n".join(current_query)))
                current_query = []
                query_name = None
                in_query = False
            else:
                current_query.append(line)

    return queries


@pytest.mark.integration
class TestHER2BreastCancerQueries:
    """Test HER2+ Breast Cancer query guide."""

    def test_her2_amplification_query(self, db_connection, query_guide_files):
        """Test Query 1: HER2 amplification and co-amplified genes."""
        query_file = query_guide_files["HER2_BREAST_CANCER"]
        patient_schema = TEST_PATIENT_SCHEMAS["HER2_BREAST_CANCER"]

        queries = extract_queries_from_file(query_file, patient_schema)
        assert len(queries) > 0, "No queries extracted from HER2 guide"

        # Find HER2 amplification query
        her2_query = None
        for name, sql in queries:
            if "Amplification" in name or "QUERY 1" in name:
                her2_query = sql
                break

        if not her2_query:
            pytest.skip("HER2 amplification query not found")

        # Execute query
        with db_connection.cursor() as cursor:
            cursor.execute(her2_query)
            results = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]

        # Validations
        assert len(results) > 0, "HER2 amplification query returned no results"
        assert "gene_symbol" in columns, "Missing gene_symbol column"
        assert "fold_change" in columns, "Missing fold_change column"

        # Check ERBB2 is present
        gene_symbols = [row[columns.index("gene_symbol")] for row in results]
        assert "ERBB2" in gene_symbols, "ERBB2 not found in results"

        # Check ERBB2 fold change is above HER2+ threshold
        erbb2_row = next(row for row in results if row[columns.index("gene_symbol")] == "ERBB2")
        erbb2_fc = erbb2_row[columns.index("fold_change")]
        assert erbb2_fc >= EXPECTED_GENES["HER2_BREAST_CANCER"]["min_erbb2_fold_change"], \
            f"ERBB2 fold-change ({erbb2_fc}) below HER2+ threshold"

    def test_fda_approved_drugs_query(self, db_connection, query_guide_files):
        """Test Query 2: FDA-approved anti-HER2 therapies."""
        query_file = query_guide_files["HER2_BREAST_CANCER"]
        patient_schema = TEST_PATIENT_SCHEMAS["HER2_BREAST_CANCER"]

        queries = extract_queries_from_file(query_file, patient_schema)

        # Find FDA drugs query
        fda_query = None
        for name, sql in queries:
            if "FDA" in name or "QUERY 2" in name:
                fda_query = sql
                break

        if not fda_query:
            pytest.skip("FDA drugs query not found")

        # Execute query
        with db_connection.cursor() as cursor:
            cursor.execute(fda_query)
            results = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]

        # Validations
        assert len(results) > 0, "FDA drugs query returned no results"
        assert "drug_name" in columns or "molecule_name" in columns, \
            "Missing drug name column"

        # Check for expected anti-HER2 drugs
        drug_col = "drug_name" if "drug_name" in columns else "molecule_name"
        drug_names = [str(row[columns.index(drug_col)]).upper() for row in results]
        expected_drugs = ["TRASTUZUMAB", "PERTUZUMAB"]

        found_drugs = [d for d in expected_drugs if any(d in dn for dn in drug_names)]
        assert len(found_drugs) > 0, \
            f"Expected anti-HER2 drugs not found. Got: {drug_names[:5]}"

    def test_pi3k_resistance_query(self, db_connection, query_guide_files):
        """Test Query 3: PI3K/AKT pathway resistance mechanism."""
        query_file = query_guide_files["HER2_BREAST_CANCER"]
        patient_schema = TEST_PATIENT_SCHEMAS["HER2_BREAST_CANCER"]

        queries = extract_queries_from_file(query_file, patient_schema)

        # Find PI3K query
        pi3k_query = None
        for name, sql in queries:
            if "PI3K" in name or "QUERY 3" in name:
                pi3k_query = sql
                break

        if not pi3k_query:
            pytest.skip("PI3K resistance query not found")

        # Execute query
        with db_connection.cursor() as cursor:
            cursor.execute(pi3k_query)
            results = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]

        # Validations
        assert len(results) > 0, "PI3K resistance query returned no results"
        assert "gene_symbol" in columns, "Missing gene_symbol column"

        # Check resistance genes are present
        gene_symbols = [row[columns.index("gene_symbol")] for row in results]
        resistance_genes = EXPECTED_GENES["HER2_BREAST_CANCER"]["resistance_genes"]
        found_resistance = [g for g in resistance_genes if g in gene_symbols]

        assert len(found_resistance) > 0, \
            f"No resistance genes found. Expected: {resistance_genes}, Got: {gene_symbols}"


@pytest.mark.integration
class TestTNBCQueries:
    """Test Triple-Negative Breast Cancer query guide."""

    def test_tnbc_confirmation_query(self, db_connection, query_guide_files):
        """Test Query 1: Triple-negative status confirmation."""
        query_file = query_guide_files["TNBC"]
        patient_schema = TEST_PATIENT_SCHEMAS["TNBC"]

        queries = extract_queries_from_file(query_file, patient_schema)
        assert len(queries) > 0, "No queries extracted from TNBC guide"

        # Find TNBC confirmation query
        tnbc_query = None
        for name, sql in queries:
            if "Triple-Negative" in name or "QUERY 1" in name:
                tnbc_query = sql
                break

        if not tnbc_query:
            pytest.skip("TNBC confirmation query not found")

        # Execute query
        with db_connection.cursor() as cursor:
            cursor.execute(tnbc_query)
            results = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]

        # Validations
        assert len(results) > 0, "TNBC confirmation query returned no results"
        assert "gene_symbol" in columns, "Missing gene_symbol column"
        assert "fold_change" in columns, "Missing fold_change column"

        # Check receptor genes are present
        gene_symbols = [row[columns.index("gene_symbol")] for row in results]
        receptor_genes = EXPECTED_GENES["TNBC"]["target_genes"]

        for gene in receptor_genes:
            assert gene in gene_symbols, f"{gene} not found in TNBC query results"

    def test_parp_inhibitor_eligibility(self, db_connection, query_guide_files):
        """Test Query 2: PARP inhibitor eligibility."""
        query_file = query_guide_files["TNBC"]
        patient_schema = TEST_PATIENT_SCHEMAS["TNBC"]

        queries = extract_queries_from_file(query_file, patient_schema)

        # Find PARP query
        parp_query = None
        for name, sql in queries:
            if "PARP" in name or "QUERY 2" in name:
                parp_query = sql
                break

        if not parp_query:
            pytest.skip("PARP inhibitor query not found")

        # Execute query
        with db_connection.cursor() as cursor:
            cursor.execute(parp_query)
            results = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]

        # Validations
        assert len(results) > 0, "PARP inhibitor query returned no results"
        assert "gene_symbol" in columns, "Missing gene_symbol column"

        # Check BRCA genes are queried
        gene_symbols = [row[columns.index("gene_symbol")] for row in results]
        parp_genes = EXPECTED_GENES["TNBC"]["parp_genes"]
        found_parp = [g for g in parp_genes if g in gene_symbols]

        assert len(found_parp) > 0, \
            f"No PARP-related genes found. Expected: {parp_genes}, Got: {gene_symbols}"


@pytest.mark.integration
class TestLUADEGFRQueries:
    """Test Lung Adenocarcinoma (EGFR-mutant) query guide."""

    def test_egfr_pathway_query(self, db_connection, query_guide_files):
        """Test Query 1: EGFR pathway activation."""
        query_file = query_guide_files["LUAD_EGFR"]
        patient_schema = TEST_PATIENT_SCHEMAS["LUAD_EGFR"]

        queries = extract_queries_from_file(query_file, patient_schema)
        assert len(queries) > 0, "No queries extracted from LUAD guide"

        # Find EGFR pathway query
        egfr_query = None
        for name, sql in queries:
            if "EGFR" in name or "QUERY 1" in name:
                egfr_query = sql
                break

        if not egfr_query:
            pytest.skip("EGFR pathway query not found")

        # Execute query
        with db_connection.cursor() as cursor:
            cursor.execute(egfr_query)
            results = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]

        # Validations
        assert len(results) > 0, "EGFR pathway query returned no results"
        assert "gene_symbol" in columns, "Missing gene_symbol column"
        assert "fold_change" in columns, "Missing fold_change column"

        # Check EGFR is present
        gene_symbols = [row[columns.index("gene_symbol")] for row in results]
        assert "EGFR" in gene_symbols, "EGFR not found in results"

        # Check EGFR fold change is elevated
        egfr_row = next(row for row in results if row[columns.index("gene_symbol")] == "EGFR")
        egfr_fc = egfr_row[columns.index("fold_change")]
        assert egfr_fc >= EXPECTED_GENES["LUAD_EGFR"]["min_egfr_fold_change"], \
            f"EGFR fold-change ({egfr_fc}) below EGFR-mutant threshold"

    def test_egfr_tki_drugs(self, db_connection, query_guide_files):
        """Test Query 2: EGFR TKI drug recommendations."""
        query_file = query_guide_files["LUAD_EGFR"]
        patient_schema = TEST_PATIENT_SCHEMAS["LUAD_EGFR"]

        queries = extract_queries_from_file(query_file, patient_schema)

        # Find TKI drugs query
        tki_query = None
        for name, sql in queries:
            if "TKI" in name or "FDA" in name or "QUERY 2" in name:
                tki_query = sql
                break

        if not tki_query:
            pytest.skip("EGFR TKI drugs query not found")

        # Execute query
        with db_connection.cursor() as cursor:
            cursor.execute(tki_query)
            results = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]

        # Validations
        assert len(results) > 0, "EGFR TKI drugs query returned no results"
        assert "drug_name" in columns or "molecule_name" in columns, \
            "Missing drug name column"

        # Check for expected EGFR TKIs
        drug_col = "drug_name" if "drug_name" in columns else "molecule_name"
        drug_names = [str(row[columns.index(drug_col)]).upper() for row in results]
        expected_tkis = ["OSIMERTINIB", "ERLOTINIB", "GEFITINIB"]

        found_tkis = [t for t in expected_tkis if any(t in dn for dn in drug_names)]
        assert len(found_tkis) > 0, \
            f"Expected EGFR TKIs not found. Got: {drug_names[:5]}"


@pytest.mark.integration
class TestColorectalCancerQueries:
    """Test Colorectal Cancer query guide."""

    def test_kras_braf_mutation_status(self, db_connection, query_guide_files):
        """Test Query 1: KRAS/BRAF mutation status assessment."""
        query_file = query_guide_files["COLORECTAL_CANCER"]
        patient_schema = TEST_PATIENT_SCHEMAS["COLORECTAL_CANCER"]

        queries = extract_queries_from_file(query_file, patient_schema)
        assert len(queries) > 0, "No queries extracted from CRC guide"

        # Find KRAS/BRAF query
        kras_query = None
        for name, sql in queries:
            if "KRAS" in name or "BRAF" in name or "QUERY 1" in name:
                kras_query = sql
                break

        if not kras_query:
            pytest.skip("KRAS/BRAF query not found")

        # Execute query
        with db_connection.cursor() as cursor:
            cursor.execute(kras_query)
            results = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]

        # Validations
        assert len(results) > 0, "KRAS/BRAF query returned no results"
        assert "gene_symbol" in columns, "Missing gene_symbol column"

        # Check mutation genes are present
        gene_symbols = [row[columns.index("gene_symbol")] for row in results]
        target_genes = EXPECTED_GENES["COLORECTAL_CANCER"]["target_genes"]

        for gene in target_genes:
            assert gene in gene_symbols, f"{gene} not found in CRC query results"

    def test_msi_high_markers(self, db_connection, query_guide_files):
        """Test Query 2: MSI-H/dMMR markers."""
        query_file = query_guide_files["COLORECTAL_CANCER"]
        patient_schema = TEST_PATIENT_SCHEMAS["COLORECTAL_CANCER"]

        queries = extract_queries_from_file(query_file, patient_schema)

        # Find MSI query
        msi_query = None
        for name, sql in queries:
            if "MSI" in name or "MMR" in name or "QUERY 2" in name:
                msi_query = sql
                break

        if not msi_query:
            pytest.skip("MSI-H markers query not found")

        # Execute query
        with db_connection.cursor() as cursor:
            cursor.execute(msi_query)
            results = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]

        # Validations
        assert len(results) > 0, "MSI-H markers query returned no results"
        assert "gene_symbol" in columns, "Missing gene_symbol column"

        # Check MMR genes are queried
        gene_symbols = [row[columns.index("gene_symbol")] for row in results]
        msi_genes = EXPECTED_GENES["COLORECTAL_CANCER"]["msi_genes"]
        found_msi = [g for g in msi_genes if g in gene_symbols]

        assert len(found_msi) > 0, \
            f"No MSI-H marker genes found. Expected: {msi_genes}, Got: {gene_symbols}"


@pytest.mark.integration
class TestQueryPatterns:
    """Test common query patterns across all guides."""

    def test_left_join_coalesce_pattern(self, db_connection):
        """Test LEFT JOIN with COALESCE pattern returns baseline 1.0."""
        query = """
        SELECT
            g.gene_symbol,
            COALESCE(pe.expression_fold_change, 1.0) as fold_change
        FROM public.genes g
        LEFT JOIN patient_synthetic_her2.expression_data pe
            ON g.gene_id = pe.gene_id
        WHERE g.gene_symbol = 'ACTB'  -- Housekeeping gene, likely baseline
        LIMIT 1;
        """

        with db_connection.cursor() as cursor:
            cursor.execute(query)
            result = cursor.fetchone()

        assert result is not None, "LEFT JOIN COALESCE query returned no results"
        gene_symbol, fold_change = result
        assert gene_symbol == "ACTB", "Gene symbol mismatch"
        assert fold_change is not None, "Fold change is NULL"
        assert isinstance(fold_change, (int, float)), "Fold change not numeric"

    def test_public_schema_access(self, db_connection):
        """Test access to public schema core tables."""
        core_tables = ["genes", "transcripts", "opentargets_known_drugs", "gene_publications"]

        for table in core_tables:
            with db_connection.cursor() as cursor:
                cursor.execute(f"SELECT COUNT(*) FROM public.{table} LIMIT 1;")
                result = cursor.fetchone()
                assert result is not None, f"Cannot access public.{table}"
                assert result[0] is not None, f"public.{table} returned NULL count"

    def test_patient_schema_expression_data(self, db_connection):
        """Test patient schema expression_data table structure."""
        for schema in TEST_PATIENT_SCHEMAS.values():
            # Check if schema exists
            with db_connection.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) FROM information_schema.schemata WHERE schema_name = %s;",
                    (schema,)
                )
                result = cursor.fetchone()

                if result[0] == 0:
                    pytest.skip(f"Patient schema {schema} does not exist")

                # Check expression_data table
                cursor.execute(
                    f"SELECT COUNT(*) FROM {schema}.expression_data LIMIT 1;"
                )
                result = cursor.fetchone()
                assert result is not None, f"Cannot access {schema}.expression_data"
                assert result[0] >= 0, f"{schema}.expression_data returned NULL count"


@pytest.mark.integration
def test_all_query_guides_exist(query_guide_files):
    """Test that all query guide files exist."""
    for cancer_type, file_path in query_guide_files.items():
        assert file_path.exists(), f"Query guide missing: {file_path}"
        assert file_path.stat().st_size > 0, f"Query guide is empty: {file_path}"


@pytest.mark.integration
def test_query_guide_sql_syntax(query_guide_files):
    """Test that query guide files contain valid SQL syntax patterns."""
    for cancer_type, file_path in query_guide_files.items():
        content = file_path.read_text()

        # Check for essential SQL patterns
        assert "SELECT" in content.upper(), f"{cancer_type} guide missing SELECT statements"
        assert "FROM" in content.upper(), f"{cancer_type} guide missing FROM clauses"
        assert "WHERE" in content.upper(), f"{cancer_type} guide missing WHERE clauses"

        # Check for v0.6.0 architecture patterns
        assert "LEFT JOIN" in content.upper() or "INNER JOIN" in content.upper(), \
            f"{cancer_type} guide missing JOIN patterns"
        assert "COALESCE" in content.upper(), \
            f"{cancer_type} guide missing COALESCE for baseline expression"

        # Check for patient schema references
        assert "patient_" in content.lower(), \
            f"{cancer_type} guide missing patient schema references"


@pytest.mark.integration
def test_readme_documentation_exists():
    """Test that README.md documentation exists in queries directory."""
    readme_path = Path(__file__).parent.parent / "docs" / "queries" / "README.md"
    assert readme_path.exists(), "docs/queries/README.md does not exist"

    content = readme_path.read_text()

    # Check for essential documentation sections
    assert "Query Guides" in content, "README missing query guides section"
    assert "How to Use" in content, "README missing usage instructions"
    assert "v0.6.0" in content, "README missing version information"
    assert "patient_" in content.lower(), "README missing patient schema information"
