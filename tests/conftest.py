"""Test configuration and shared fixtures."""

import os
import pytest
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from dotenv import load_dotenv
from pathlib import Path

# Load test environment variables from .env.test
env_test_path = Path(__file__).parent.parent / '.env.test'
if env_test_path.exists():
    load_dotenv(env_test_path, override=True)
    print(f"✓ Loaded test configuration from {env_test_path}")
else:
    print(f"⚠ Warning: .env.test not found at {env_test_path}, using default values")

@pytest.fixture(scope="session")
def test_db():
    """Create and manage test database."""
    # Connection parameters from environment variables
    params = {
        'host': os.getenv('MB_POSTGRES_HOST', 'localhost'),
        'port': int(os.getenv('MB_POSTGRES_PORT', '5435')),
        'user': os.getenv('MB_POSTGRES_USER', 'mbase_user'),
        'password': os.getenv('MB_POSTGRES_PASSWORD', 'mbase_secret'),
        'dbname': 'postgres'  # Connect to postgres to create test database
    }

    test_db_name = os.getenv('MB_POSTGRES_NAME', 'mediabase_test')
    
    # Create test database
    conn = psycopg2.connect(**params)
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()
    
    # Drop test database if it exists
    cur.execute(f"DROP DATABASE IF EXISTS {test_db_name}")
    cur.execute(f"CREATE DATABASE {test_db_name}")
    
    cur.close()
    conn.close()
    
    # Create schema in test database
    test_params = params.copy()
    test_params['dbname'] = test_db_name
    conn = psycopg2.connect(**test_params)
    
    with conn.cursor() as cur:
        # Create normalized schema tables for API testing
        cur.execute("""
            -- Genes table
            CREATE TABLE genes (
                gene_id TEXT PRIMARY KEY,
                gene_symbol TEXT NOT NULL,
                gene_name TEXT,
                gene_type TEXT,
                chromosome TEXT,
                start_position BIGINT,
                end_position BIGINT,
                strand SMALLINT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- Transcripts table
            CREATE TABLE transcripts (
                transcript_id TEXT PRIMARY KEY,
                gene_id TEXT REFERENCES genes(gene_id),
                transcript_name TEXT,
                transcript_type TEXT,
                transcript_support_level INTEGER,
                expression_fold_change FLOAT DEFAULT 1.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- Gene annotations table (for product types, etc.)
            CREATE TABLE gene_annotations (
                id SERIAL PRIMARY KEY,
                gene_id TEXT REFERENCES genes(gene_id),
                annotation_type TEXT NOT NULL,
                annotation_value TEXT NOT NULL,
                confidence_score FLOAT,
                source TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- Transcript GO terms table
            CREATE TABLE transcript_go_terms (
                id SERIAL PRIMARY KEY,
                transcript_id TEXT REFERENCES transcripts(transcript_id),
                go_id TEXT NOT NULL,
                go_term TEXT NOT NULL,
                go_category TEXT,
                evidence_code TEXT,
                source TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- Gene pathways table
            CREATE TABLE gene_pathways (
                id SERIAL PRIMARY KEY,
                gene_id TEXT REFERENCES genes(gene_id),
                pathway_id TEXT,
                pathway_name TEXT NOT NULL,
                pathway_source TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- Gene drug interactions table
            CREATE TABLE gene_drug_interactions (
                id SERIAL PRIMARY KEY,
                gene_id TEXT REFERENCES genes(gene_id),
                drug_id TEXT,
                drug_name TEXT NOT NULL,
                interaction_type TEXT,
                source TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- Create indexes for performance
            CREATE INDEX idx_transcripts_gene_id ON transcripts(gene_id);
            CREATE INDEX idx_gene_annotations_gene_id ON gene_annotations(gene_id);
            CREATE INDEX idx_gene_annotations_type ON gene_annotations(annotation_type);
            CREATE INDEX idx_transcript_go_terms_transcript_id ON transcript_go_terms(transcript_id);
            CREATE INDEX idx_gene_pathways_gene_id ON gene_pathways(gene_id);
            CREATE INDEX idx_gene_drug_interactions_gene_id ON gene_drug_interactions(gene_id);

            -- Create materialized views
            CREATE MATERIALIZED VIEW gene_summary_view AS
            SELECT
                g.gene_id,
                g.gene_symbol,
                g.gene_name,
                g.gene_type,
                g.chromosome,
                g.start_position,
                g.end_position,
                g.strand,
                COUNT(t.transcript_id) as transcript_count,
                AVG(t.expression_fold_change) as avg_expression_fold_change,
                MAX(t.expression_fold_change) as max_expression_fold_change,
                MIN(t.expression_fold_change) as min_expression_fold_change
            FROM genes g
            LEFT JOIN transcripts t ON g.gene_id = t.gene_id
            GROUP BY g.gene_id, g.gene_symbol, g.gene_name, g.gene_type,
                     g.chromosome, g.start_position, g.end_position, g.strand;

            CREATE MATERIALIZED VIEW transcript_enrichment_view AS
            SELECT
                t.transcript_id,
                t.gene_id,
                g.gene_symbol,
                g.gene_name,
                g.gene_type,
                g.chromosome,
                t.transcript_name,
                t.transcript_type,
                t.transcript_support_level,
                t.expression_fold_change,
                CASE
                    WHEN t.expression_fold_change > 2.0 THEN 'upregulated'
                    WHEN t.expression_fold_change < 0.5 THEN 'downregulated'
                    ELSE 'normal'
                END as expression_status
            FROM transcripts t
            INNER JOIN genes g ON t.gene_id = g.gene_id;

            -- Create indexes on materialized views
            CREATE UNIQUE INDEX idx_gene_summary_gene_id ON gene_summary_view (gene_id);
            CREATE INDEX idx_gene_summary_symbol ON gene_summary_view (gene_symbol);
            CREATE UNIQUE INDEX idx_transcript_enrichment_id ON transcript_enrichment_view (transcript_id);
            CREATE INDEX idx_transcript_enrichment_gene_id ON transcript_enrichment_view (gene_id);
            CREATE INDEX idx_transcript_enrichment_symbol ON transcript_enrichment_view (gene_symbol);

            -- Seed test data for API tests
            INSERT INTO genes (gene_id, gene_symbol, gene_name, gene_type, chromosome, start_position, end_position, strand)
            VALUES
                ('ENSG00000012048', 'BRCA1', 'BRCA1 DNA repair associated', 'protein_coding', '17', 43044295, 43170245, 1),
                ('ENSG00000141510', 'TP53', 'tumor protein p53', 'protein_coding', '17', 7661779, 7687550, -1);

            INSERT INTO transcripts (transcript_id, gene_id, transcript_name, transcript_type, transcript_support_level, expression_fold_change)
            VALUES
                ('ENST00000357654', 'ENSG00000012048', 'BRCA1-201', 'protein_coding', 1, 2.5),
                ('ENST00000269305', 'ENSG00000141510', 'TP53-201', 'protein_coding', 1, 0.3);

            INSERT INTO gene_annotations (gene_id, annotation_type, annotation_value, source)
            VALUES
                ('ENSG00000012048', 'product_type', 'enzyme', 'UniProt'),
                ('ENSG00000141510', 'product_type', 'transcription_factor', 'UniProt');

            INSERT INTO transcript_go_terms (transcript_id, go_id, go_term, go_category, source)
            VALUES
                ('ENST00000357654', 'GO:0003677', 'DNA binding', 'molecular_function', 'GOA'),
                ('ENST00000269305', 'GO:0003700', 'DNA-binding transcription factor activity', 'molecular_function', 'GOA');

            INSERT INTO gene_pathways (gene_id, pathway_id, pathway_name, pathway_source)
            VALUES
                ('ENSG00000012048', 'R-HSA-5693532', 'DNA Double-Strand Break Repair', 'Reactome'),
                ('ENSG00000141510', 'R-HSA-69620', 'Cell Cycle Checkpoints', 'Reactome');

            INSERT INTO gene_drug_interactions (gene_id, drug_id, drug_name, interaction_type, source)
            VALUES
                ('ENSG00000012048', 'DB09074', 'Olaparib', 'inhibitor', 'DrugBank'),
                ('ENSG00000141510', 'DB11642', 'Nutlin-3', 'activator', 'DrugBank');

            -- Refresh materialized views with seed data
            REFRESH MATERIALIZED VIEW gene_summary_view;
            REFRESH MATERIALIZED VIEW transcript_enrichment_view;

            -- Create legacy cancer_transcript_base table for backwards compatibility
            -- (Used by create_patient_copy.py for gene symbol mappings)
            CREATE TABLE cancer_transcript_base (
                transcript_id TEXT PRIMARY KEY,
                gene_symbol TEXT,
                gene_id TEXT,
                gene_type TEXT,
                chromosome TEXT,
                coordinates JSONB,
                product_type TEXT[],
                cellular_location TEXT[],
                go_terms JSONB,
                pathways TEXT[],
                drugs JSONB,
                drug_scores JSONB,
                publications JSONB,
                expression_fold_change FLOAT DEFAULT 1.0,
                expression_freq JSONB DEFAULT '{"high": [], "low": []}',
                cancer_types TEXT[] DEFAULT '{}'
            );

            -- Populate with data from normalized schema
            INSERT INTO cancer_transcript_base (transcript_id, gene_symbol, gene_id, gene_type, chromosome, expression_fold_change)
            SELECT t.transcript_id, g.gene_symbol, g.gene_id, g.gene_type, g.chromosome, t.expression_fold_change
            FROM transcripts t
            INNER JOIN genes g ON t.gene_id = g.gene_id;
        """)

    conn.commit()
    conn.close()
    
    yield test_db_name
    
    # Cleanup
    conn = psycopg2.connect(**params)
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()
    cur.execute(f"DROP DATABASE IF EXISTS {test_db_name}")
    cur.close()
    conn.close()
