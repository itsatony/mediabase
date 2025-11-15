#!/usr/bin/env python3
"""MEDIABASE FastAPI Server.

Provides RESTful API endpoints for querying cancer transcriptome data
with comprehensive drug interactions, pathway annotations, and publication references.
"""

import logging
import os
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional, Union

import uvicorn
from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# Add project root to Python path
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(project_root))

from src.db.database import get_db_manager, DatabaseManager
from src.utils.logging import setup_logging


# Configure logging
logger = setup_logging(
    module_name=__name__,
    log_file="api_server.log"
)

# API Models
class TranscriptQuery(BaseModel):
    """Query parameters for transcript search."""
    gene_symbols: Optional[List[str]] = Field(None, description="List of gene symbols to search")
    transcript_ids: Optional[List[str]] = Field(None, description="List of transcript IDs to search")
    fold_change_min: Optional[float] = Field(None, ge=0, description="Minimum fold change threshold")
    fold_change_max: Optional[float] = Field(None, ge=0, description="Maximum fold change threshold")
    has_drugs: Optional[bool] = Field(None, description="Filter by drug interaction presence")
    has_pathways: Optional[bool] = Field(None, description="Filter by pathway annotation presence")
    limit: int = Field(100, ge=1, le=10000, description="Maximum number of results")
    offset: int = Field(0, ge=0, description="Offset for pagination")

class TranscriptResponse(BaseModel):
    """Response model for transcript data."""
    transcript_id: str
    gene_symbol: Optional[str]
    gene_id: Optional[str]
    gene_type: Optional[str]
    chromosome: Optional[str]
    expression_fold_change: Optional[float]
    product_type: Optional[str]
    go_terms: Optional[List[str]]
    pathways: Optional[List[str]]
    drugs: Optional[Dict[str, Any]]
    molecular_functions: Optional[List[str]]
    cellular_location: Optional[List[str]]
    source_references: Optional[Dict[str, Any]]

class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    version: str
    database_connected: bool

# FastAPI App Configuration
app = FastAPI(
    title="MEDIABASE API",
    description="Cancer Transcriptome Database API with drug interactions and pathway annotations",
    version="0.2.1",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware
allowed_origins = os.getenv('MB_ALLOWED_ORIGINS', 'http://localhost:3000').split(',')
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

# Database dependency
def get_database() -> DatabaseManager:
    """Get database connection dependency."""
    db_config = {
        'host': os.getenv('MB_POSTGRES_HOST', 'localhost'),
        'port': int(os.getenv('MB_POSTGRES_PORT', '5432')),
        'dbname': os.getenv('MB_POSTGRES_NAME', 'mediabase'),
        'user': os.getenv('MB_POSTGRES_USER', 'postgres'),
        'password': os.getenv('MB_POSTGRES_PASSWORD', 'postgres')
    }
    
    db_manager = get_db_manager(db_config)
    if not db_manager.ensure_connection():
        raise HTTPException(status_code=503, detail="Database connection failed")
    
    try:
        yield db_manager
    finally:
        db_manager.close()

# API Endpoints
@app.get("/health", response_model=HealthResponse)
async def health_check(db: DatabaseManager = Depends(get_database)):
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        version="0.2.1",
        database_connected=True
    )

@app.get("/api/v1/transcripts", response_model=List[TranscriptResponse])
async def search_transcripts(
    query: TranscriptQuery = Depends(),
    db: DatabaseManager = Depends(get_database)
):
    """Search transcripts with filtering and pagination."""
    try:
        # Build SQL query dynamically
        where_conditions = []
        params = []
        
        if query.gene_symbols:
            placeholders = ','.join(['%s'] * len(query.gene_symbols))
            where_conditions.append(f"gene_symbol IN ({placeholders})")
            params.extend(query.gene_symbols)
        
        if query.transcript_ids:
            placeholders = ','.join(['%s'] * len(query.transcript_ids))
            where_conditions.append(f"transcript_id IN ({placeholders})")
            params.extend(query.transcript_ids)
        
        if query.fold_change_min is not None:
            where_conditions.append("expression_fold_change >= %s")
            params.append(query.fold_change_min)
        
        if query.fold_change_max is not None:
            where_conditions.append("expression_fold_change <= %s")
            params.append(query.fold_change_max)
        
        if query.has_drugs is not None:
            if query.has_drugs:
                where_conditions.append("drugs IS NOT NULL AND jsonb_typeof(drugs) = 'object' AND drugs != '{}'::jsonb")
            else:
                where_conditions.append("(drugs IS NULL OR drugs = '{}'::jsonb)")
        
        if query.has_pathways is not None:
            if query.has_pathways:
                where_conditions.append("(pathways IS NOT NULL AND array_length(pathways, 1) > 0)")
            else:
                where_conditions.append("(pathways IS NULL OR array_length(pathways, 1) = 0)")
        
        # Construct final query using materialized views for better performance
        where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"

        # Use transcript_enrichment_view for optimized queries
        sql_query = f"""
            SELECT
                te.transcript_id,
                te.gene_symbol,
                te.gene_id,
                te.gene_type,
                te.chromosome,
                te.expression_fold_change,
                COALESCE(ga_product.product_types, ARRAY[]::text[]) as product_type,
                COALESCE(tgt.go_terms, '{{}}'::jsonb) as go_terms,
                COALESCE(gp.pathways, ARRAY[]::text[]) as pathways,
                COALESCE(gdi.drugs, '{{}}'::jsonb) as drugs,
                ARRAY[]::text[] as molecular_functions,
                ARRAY[]::text[] as cellular_location,
                '{{}}'::jsonb as source_references
            FROM transcript_enrichment_view te
            LEFT JOIN (
                SELECT gene_id, array_agg(annotation_value) as product_types
                FROM gene_annotations
                WHERE annotation_type = 'product_type'
                GROUP BY gene_id
            ) ga_product ON ga_product.gene_id = te.gene_id
            LEFT JOIN (
                SELECT transcript_id, jsonb_agg(jsonb_build_object(
                    'go_id', go_id, 'name', go_term, 'category', go_category
                )) as go_terms
                FROM transcript_go_terms
                GROUP BY transcript_id
            ) tgt ON tgt.transcript_id = te.transcript_id
            LEFT JOIN (
                SELECT gene_id, array_agg(pathway_name) as pathways
                FROM gene_pathways
                GROUP BY gene_id
            ) gp ON gp.gene_id = te.gene_id
            LEFT JOIN (
                SELECT gene_id, jsonb_object_agg(drug_name, jsonb_build_object(
                    'drug_id', drug_id, 'interaction_type', interaction_type, 'source', source
                )) as drugs
                FROM gene_drug_interactions
                GROUP BY gene_id
            ) gdi ON gdi.gene_id = te.gene_id
            WHERE {where_clause}
            ORDER BY te.expression_fold_change DESC NULLS LAST
            LIMIT %s OFFSET %s
        """
        
        params.extend([query.limit, query.offset])
        
        # Execute query
        cursor = db.cursor
        cursor.execute(sql_query, params)
        
        results = []
        columns = [desc[0] for desc in cursor.description]
        
        for row in cursor.fetchall():
            row_dict = dict(zip(columns, row))
            results.append(TranscriptResponse(**row_dict))
        
        logger.info(f"Retrieved {len(results)} transcripts")
        return results
        
    except Exception as e:
        logger.error(f"Error searching transcripts: {e}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")

@app.get("/api/v1/transcripts/{transcript_id}", response_model=TranscriptResponse)
async def get_transcript(
    transcript_id: str,
    db: DatabaseManager = Depends(get_database)
):
    """Get detailed transcript information by ID."""
    try:
        cursor = db.cursor
        # Use the same optimized query structure as the search endpoint
        cursor.execute("""
            SELECT
                te.transcript_id,
                te.gene_symbol,
                te.gene_id,
                te.gene_type,
                te.chromosome,
                te.expression_fold_change,
                COALESCE(ga_product.product_types, ARRAY[]::text[]) as product_type,
                COALESCE(tgt.go_terms, '{}'::jsonb) as go_terms,
                COALESCE(gp.pathways, ARRAY[]::text[]) as pathways,
                COALESCE(gdi.drugs, '{}'::jsonb) as drugs,
                ARRAY[]::text[] as molecular_functions,
                ARRAY[]::text[] as cellular_location,
                '{}'::jsonb as source_references
            FROM transcript_enrichment_view te
            LEFT JOIN (
                SELECT gene_id, array_agg(annotation_value) as product_types
                FROM gene_annotations
                WHERE annotation_type = 'product_type'
                GROUP BY gene_id
            ) ga_product ON ga_product.gene_id = te.gene_id
            LEFT JOIN (
                SELECT transcript_id, jsonb_agg(jsonb_build_object(
                    'go_id', go_id, 'name', go_term, 'category', go_category
                )) as go_terms
                FROM transcript_go_terms
                GROUP BY transcript_id
            ) tgt ON tgt.transcript_id = te.transcript_id
            LEFT JOIN (
                SELECT gene_id, array_agg(pathway_name) as pathways
                FROM gene_pathways
                GROUP BY gene_id
            ) gp ON gp.gene_id = te.gene_id
            LEFT JOIN (
                SELECT gene_id, jsonb_object_agg(drug_name, jsonb_build_object(
                    'drug_id', drug_id, 'interaction_type', interaction_type, 'source', source
                )) as drugs
                FROM gene_drug_interactions
                GROUP BY gene_id
            ) gdi ON gdi.gene_id = te.gene_id
            WHERE te.transcript_id = %s
        """, (transcript_id,))
        
        result = cursor.fetchone()
        if not result:
            raise HTTPException(status_code=404, detail=f"Transcript {transcript_id} not found")
        
        columns = [desc[0] for desc in cursor.description]
        row_dict = dict(zip(columns, result))
        
        logger.info(f"Retrieved transcript: {transcript_id}")
        return TranscriptResponse(**row_dict)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving transcript {transcript_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Retrieval failed: {str(e)}")

@app.get("/api/v1/stats")
async def get_database_stats(db: DatabaseManager = Depends(get_database)):
    """Get database statistics from normalized schema."""
    try:
        cursor = db.cursor

        # Get basic counts from normalized schema
        cursor.execute("SELECT COUNT(*) FROM transcripts")
        total_transcripts = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM genes")
        unique_genes = cursor.fetchone()[0]

        # Get enrichment statistics
        cursor.execute("SELECT COUNT(DISTINCT gene_id) FROM gene_drug_interactions")
        genes_with_drugs = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(DISTINCT gene_id) FROM gene_pathways")
        genes_with_pathways = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(DISTINCT gene_id) FROM gene_annotations WHERE annotation_type = 'product_type'")
        genes_with_product_types = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(DISTINCT transcript_id) FROM transcript_go_terms")
        transcripts_with_go_terms = cursor.fetchone()[0]

        # Get materialized view statistics
        cursor.execute("SELECT COUNT(*) FROM gene_summary_view")
        materialized_view_genes = cursor.fetchone()[0]

        stats = {
            "total_transcripts": total_transcripts,
            "unique_genes": unique_genes,
            "genes_with_drugs": genes_with_drugs,
            "genes_with_pathways": genes_with_pathways,
            "genes_with_product_types": genes_with_product_types,
            "transcripts_with_go_terms": transcripts_with_go_terms,
            "materialized_view_genes": materialized_view_genes,
            "drug_coverage": (genes_with_drugs / unique_genes * 100) if unique_genes > 0 else 0,
            "pathway_coverage": (genes_with_pathways / unique_genes * 100) if unique_genes > 0 else 0,
            "product_type_coverage": (genes_with_product_types / unique_genes * 100) if unique_genes > 0 else 0,
            "go_term_coverage": (transcripts_with_go_terms / total_transcripts * 100) if total_transcripts > 0 else 0,
            "architecture": "normalized_schema_v1.0"
        }
        
        logger.info("Retrieved database statistics")
        return stats
        
    except Exception as e:
        logger.error(f"Error retrieving statistics: {e}")
        raise HTTPException(status_code=500, detail=f"Statistics retrieval failed: {str(e)}")

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler."""
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )

def main():
    """Run the API server."""
    host = os.getenv('MB_API_HOST', '0.0.0.0')
    port = int(os.getenv('MB_API_PORT', '8000'))
    debug = os.getenv('MB_API_DEBUG', 'false').lower() == 'true'
    
    logger.info(f"Starting MEDIABASE API server on {host}:{port}")
    
    uvicorn.run(
        "src.api.server:app",
        host=host,
        port=port,
        reload=debug,
        log_level="info" if not debug else "debug"
    )

if __name__ == "__main__":
    main()