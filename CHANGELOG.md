# Changelog

All notable changes to MEDIABASE will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2025-01-20

### 🎉 Major Features - Complete SOTA Query System

#### Working SOTA Queries with Patient Databases
- **BREAKTHROUGH**: All 4 SOTA queries now work correctly with realistic expression data
- **Patient Database System**: Creates patient-specific databases with comprehensive biomedical annotation
- **Clinical Significance**: Emoji-coded priority indicators (🔴🟡⚪) for oncologists
- **Therapeutic Targeting**: Integration of drug availability with expression dysregulation

#### Comprehensive Demo Patient Databases
- **6 Cancer Type Datasets** with biomedically realistic expression patterns:
  - **Breast HER2+** (500 genes): ERBB2 ↑12.6x, EGFR ↑6.4x, PTEN ↓0.17x
  - **Breast Triple-Negative** (400 genes): BRCA pathway defects, immune targets
  - **Lung EGFR-Mutant** (300 genes): EGFR activation, resistance pathways
  - **Colorectal MSI-High** (400 genes): MMR deficiency, immune activation
  - **Pancreatic PDAC** (350 genes): KRAS activation, stromal interaction
  - **Comprehensive Pan-Cancer** (1000 genes): Cross-cancer biomarkers

#### Enhanced SOTA Query Library
1. **Oncogene/Tumor Suppressor Analysis**: Clinical significance with cellular location
2. **Therapeutic Target Prioritization**: Drug availability assessment and targeting priority
3. **Pathway-Based Analysis**: Hyperactivated pathway identification (86+ genes in Signal Transduction)
4. **Pharmacogenomic Variant Analysis**: Personalized medicine with PGx variants

#### Cancer-Specific Query System
- **Specialized Queries** for each cancer type with clinical recommendations:
  - **HER2+ Breast**: Trastuzumab/Pertuzumab targeting, resistance pathway analysis
  - **TNBC Breast**: PARP inhibitor candidates, immunotherapy targeting
  - **EGFR Lung**: TKI targeting strategies, resistance bypass mechanisms
  - **MSI Colorectal**: Immunotherapy prediction, mismatch repair analysis
  - **PDAC Pancreatic**: KRAS targeting, challenging tumor microenvironment
  - **Pan-Cancer**: Universal biomarkers across cancer types

### 🔧 Technical Enhancements

#### Automated Dataset Generation
- **Expert Cancer Knowledge**: Realistic fold-change patterns based on literature
- **Biomedical Accuracy**: Oncogene activation (2-12x), tumor suppressor loss (0.1-0.5x)
- **Cancer-Specific Signatures**: Tailored expression patterns for each cancer type
- **Comprehensive Statistics**: Detailed generation reports with validation metrics

#### Production-Ready Automation
- **Automated Patient Database Creation**: `create_all_demo_patients.py` script
- **Batch Processing**: Create all 6 databases in ~5 minutes
- **Validation Framework**: Built-in testing and verification commands
- **Clinical Workflow Integration**: Step-by-step usage documentation

### 📚 Documentation Overhaul

#### Enhanced README
- **Complete SOTA Query Documentation** with working examples
- **Step-by-Step Clinical Workflows** from data upload to therapeutic planning
- **Expected Results Examples** showing actual query output
- **Validation Commands** to verify correct system operation
- **Cancer-Specific Usage** guidance for different tumor types

#### Clinical Integration
- **Patient Data Upload Process** with CSV format specification
- **Query Execution Workflows** for comprehensive clinical assessment
- **Therapeutic Planning Integration** with treatment selection guidance
- **Validation Results** confirming expression data ranges (0.12x - 12.6x)

### 🐛 Bug Fixes

#### SOTA Query System
- **Fixed Expression Data Issue**: Main database queries now work with patient databases containing actual fold-change data
- **Database Connection**: Proper environment variable handling for port 5435
- **Query Syntax**: Updated all queries to use correct column names (gene_symbol vs symbol)
- **Data Validation**: Comprehensive testing against demo databases

### 🗑️ Removed

#### Cleanup and Organization
- **Large Database Dumps**: Removed 31MB+ dump files not suitable for version control
- **Legacy Test Files**: Cleaned up 8+ root-level test files superseded by proper test structure
- **Obsolete Notebooks**: Removed outdated Jupyter notebooks replaced by working query system
- **Superseded Files**: Removed intermediate working files replaced by final versions

### 🔄 Changed

#### Core System Updates
- **Database Schema**: Enhanced support for patient-specific expression data
- **ETL Pipeline**: Improved drug, pathway, and publication processing
- **Query Architecture**: Restructured for patient database compatibility
- **File Organization**: Better separation of demo data, scripts, and queries

## [0.2.1] - Previous Version
- DESeq2 support and RESTful API server
- Flexible transcript ID matching
- Enhanced patient copy examples

## [0.2.0] - Previous Version
- Initial DESeq2 functionality
- API server implementation
- Patient workflow integration

---

### Migration Guide

**From v0.2.x to v0.3.0:**

1. **Create Demo Databases**: Run `poetry run python scripts/create_all_demo_patients.py`
2. **Update Query Usage**: Use patient databases instead of main database for SOTA queries
3. **New Command Structure**: Follow updated README for proper database connection
4. **Validation**: Use provided test commands to verify system operation

### Breaking Changes

- **SOTA Queries**: Now require patient databases with expression data (not backward compatible with main database)
- **Database Connection**: Patient databases use different naming convention (mediabase_patient_*)
- **File Structure**: New organization of demo data and query files

### Notes

This major release (0.3.0) represents the culmination of the SOTA query system development, providing a complete, working platform for cancer transcriptomics analysis with clinical decision support capabilities.