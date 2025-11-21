"""Comprehensive Data Validation Framework for MEDIABASE Migration.

This module provides extensive validation for extracted and processed data,
ensuring data quality, consistency, and biomedical accuracy throughout
the migration process.
"""

import re
import json
import statistics
from typing import Dict, List, Optional, Any, Set, Tuple, Union
from collections import defaultdict, Counter
from datetime import datetime

import pandas as pd

from ..utils.logging import get_logger

logger = get_logger(__name__)


class ValidationError(Exception):
    """Custom exception for validation errors."""

    pass


class DataValidationFramework:
    """Comprehensive validation for extracted and processed data."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize validation framework.

        Args:
            config: Configuration dictionary with validation settings
        """
        self.config = config or {}
        self.validation_results = {}
        self.critical_errors = []
        self.warnings = []
        self.validation_timestamp = datetime.now()

        # Validation thresholds
        self.thresholds = {
            "max_duplicate_rate": self.config.get("max_duplicate_rate", 0.05),  # 5%
            "min_gene_symbol_length": self.config.get("min_gene_symbol_length", 1),
            "max_gene_symbol_length": self.config.get("max_gene_symbol_length", 50),
            "min_data_completeness": self.config.get(
                "min_data_completeness", 0.1
            ),  # 10%
            "max_error_rate": self.config.get("max_error_rate", 0.1),  # 10%
            "min_drug_name_length": self.config.get("min_drug_name_length", 2),
            "max_confidence_score": self.config.get("max_confidence_score", 1.0),
        }

        # Known valid patterns
        self.valid_patterns = {
            "ensembl_gene_id": re.compile(r"^ENSG\d{11}(\.\d+)?$"),
            "ensembl_transcript_id": re.compile(r"^ENST\d{11}(\.\d+)?$"),
            "chromosome": re.compile(
                r"^(chr)?(1|2|3|4|5|6|7|8|9|10|11|12|13|14|15|16|17|18|19|20|21|22|X|Y|MT?)$"
            ),
            "pmid": re.compile(r"^\d{7,8}$"),
            "uniprot_id": re.compile(r"^[A-Z][0-9][A-Z0-9]{3}[0-9]$|^[A-Z]{2,3}\d{5}$"),
        }

        # Biomedical knowledge for validation
        self.known_oncogenes = {
            "MYC",
            "EGFR",
            "ERBB2",
            "KRAS",
            "PIK3CA",
            "AKT1",
            "CCND1",
            "MDM2",
            "BCL2",
            "RAS",
            "ALK",
            "BRAF",
            "RET",
            "MET",
            "FGFR1",
            "FGFR2",
            "FGFR3",
        }

        self.known_tumor_suppressors = {
            "TP53",
            "RB1",
            "PTEN",
            "BRCA1",
            "BRCA2",
            "CDKN2A",
            "CDKN1A",
            "CDKN1B",
            "APC",
            "VHL",
            "NF1",
            "NF2",
            "PTCH1",
            "STK11",
            "ATM",
            "CHEK2",
        }

    def validate_genes(self, genes_data: List[Dict]) -> bool:
        """Validate extracted gene data comprehensively.

        Args:
            genes_data: List of gene dictionaries

        Returns:
            True if validation passes, False otherwise
        """
        logger.info(f"🔍 Validating {len(genes_data)} gene records...")

        validations = [
            ("unique_gene_ids", self._check_unique_gene_ids, True),
            ("unique_gene_symbols", self._check_unique_gene_symbols, True),
            ("valid_ensembl_ids", self._check_valid_ensembl_ids, False),
            ("gene_symbol_format", self._check_gene_symbol_format, False),
            ("chromosome_validity", self._check_chromosome_validity, False),
            ("coordinates_structure", self._check_coordinates_structure, False),
            ("biomedical_consistency", self._check_biomedical_consistency, False),
            ("data_completeness", self._check_gene_data_completeness, True),
            ("duplicate_detection", self._check_gene_duplicates, True),
        ]

        gene_validation_results = {}
        critical_failures = 0

        for validation_name, validation_func, is_critical in validations:
            try:
                logger.info(f"  Running {validation_name}...")
                result = validation_func(genes_data)
                gene_validation_results[validation_name] = result

                if not result.get("passed", False):
                    if is_critical:
                        self.critical_errors.append(
                            f"Gene validation CRITICAL: {validation_name}"
                        )
                        critical_failures += 1
                        logger.error(
                            f"❌ CRITICAL: {validation_name} - {result.get('message', 'Failed')}"
                        )
                    else:
                        self.warnings.append(
                            f"Gene validation warning: {validation_name}"
                        )
                        logger.warning(
                            f"⚠️ WARNING: {validation_name} - {result.get('message', 'Failed')}"
                        )
                else:
                    logger.info(f"✅ {validation_name} passed")

            except Exception as e:
                gene_validation_results[validation_name] = {
                    "passed": False,
                    "error": str(e),
                    "critical": is_critical,
                }

                if is_critical:
                    self.critical_errors.append(
                        f"Gene validation ERROR in {validation_name}: {e}"
                    )
                    critical_failures += 1
                    logger.error(f"❌ ERROR: {validation_name} - {e}")

        self.validation_results["genes"] = gene_validation_results

        success = critical_failures == 0
        logger.info(
            f"Gene validation {'✅ PASSED' if success else '❌ FAILED'} ({critical_failures} critical failures)"
        )

        return success

    def validate_drug_interactions(self, drug_data: List[Dict]) -> bool:
        """Validate extracted drug interaction data.

        Args:
            drug_data: List of drug interaction dictionaries

        Returns:
            True if validation passes, False otherwise
        """
        logger.info(f"🔍 Validating {len(drug_data)} drug interaction records...")

        validations = [
            ("drug_name_validity", self._check_drug_names, False),
            ("interaction_completeness", self._check_interaction_completeness, False),
            ("source_attribution", self._check_source_attribution, True),
            ("duplicate_detection", self._check_drug_duplicates, False),
            ("clinical_status_validity", self._check_clinical_status, False),
            ("confidence_scores", self._check_confidence_scores, False),
            ("gene_drug_consistency", self._check_gene_drug_consistency, True),
            (
                "biomedical_plausibility",
                self._check_drug_biomedical_plausibility,
                False,
            ),
        ]

        drug_validation_results = {}
        critical_failures = 0

        for validation_name, validation_func, is_critical in validations:
            try:
                logger.info(f"  Running {validation_name}...")
                result = validation_func(drug_data)
                drug_validation_results[validation_name] = result

                if not result.get("passed", False):
                    if is_critical:
                        self.critical_errors.append(
                            f"Drug validation CRITICAL: {validation_name}"
                        )
                        critical_failures += 1
                        logger.error(
                            f"❌ CRITICAL: {validation_name} - {result.get('message', 'Failed')}"
                        )
                    else:
                        self.warnings.append(
                            f"Drug validation warning: {validation_name}"
                        )
                        logger.warning(
                            f"⚠️ WARNING: {validation_name} - {result.get('message', 'Failed')}"
                        )
                else:
                    logger.info(f"✅ {validation_name} passed")

            except Exception as e:
                drug_validation_results[validation_name] = {
                    "passed": False,
                    "error": str(e),
                    "critical": is_critical,
                }

                if is_critical:
                    critical_failures += 1

        self.validation_results["drug_interactions"] = drug_validation_results

        success = critical_failures == 0
        logger.info(
            f"Drug validation {'✅ PASSED' if success else '❌ FAILED'} ({critical_failures} critical failures)"
        )

        return success

    def validate_annotations(self, annotations_data: List[Dict]) -> bool:
        """Validate gene annotation data.

        Args:
            annotations_data: List of annotation dictionaries

        Returns:
            True if validation passes, False otherwise
        """
        logger.info(f"🔍 Validating {len(annotations_data)} annotation records...")

        validations = [
            ("go_term_structure", self._check_go_term_structure, False),
            ("pathway_validity", self._check_pathway_validity, False),
            ("cross_reference_validity", self._check_cross_references, False),
            ("annotation_consistency", self._check_annotation_consistency, True),
            ("molecular_function_validity", self._check_molecular_functions, False),
        ]

        annotation_validation_results = {}
        critical_failures = 0

        for validation_name, validation_func, is_critical in validations:
            try:
                logger.info(f"  Running {validation_name}...")
                result = validation_func(annotations_data)
                annotation_validation_results[validation_name] = result

                if not result.get("passed", False):
                    if is_critical:
                        self.critical_errors.append(
                            f"Annotation validation CRITICAL: {validation_name}"
                        )
                        critical_failures += 1
                        logger.error(
                            f"❌ CRITICAL: {validation_name} - {result.get('message', 'Failed')}"
                        )
                    else:
                        self.warnings.append(
                            f"Annotation validation warning: {validation_name}"
                        )
                        logger.warning(
                            f"⚠️ WARNING: {validation_name} - {result.get('message', 'Failed')}"
                        )
                else:
                    logger.info(f"✅ {validation_name} passed")

            except Exception as e:
                annotation_validation_results[validation_name] = {
                    "passed": False,
                    "error": str(e),
                    "critical": is_critical,
                }

                if is_critical:
                    critical_failures += 1

        self.validation_results["annotations"] = annotation_validation_results

        success = critical_failures == 0
        logger.info(
            f"Annotation validation {'✅ PASSED' if success else '❌ FAILED'} ({critical_failures} critical failures)"
        )

        return success

    def cross_validate_data_consistency(
        self, genes: List[Dict], drugs: List[Dict], annotations: List[Dict]
    ) -> bool:
        """Cross-validate consistency across all data types.

        Args:
            genes: Gene data
            drugs: Drug interaction data
            annotations: Annotation data

        Returns:
            True if cross-validation passes
        """
        logger.info("🔍 Cross-validating data consistency...")

        cross_validations = [
            ("gene_id_consistency", self._check_gene_id_consistency),
            ("gene_symbol_consistency", self._check_gene_symbol_consistency),
            ("data_coverage_consistency", self._check_data_coverage_consistency),
            ("biomedical_coherence", self._check_biomedical_coherence),
        ]

        cross_validation_results = {}
        critical_failures = 0

        for validation_name, validation_func in cross_validations:
            try:
                logger.info(f"  Running {validation_name}...")
                result = validation_func(genes, drugs, annotations)
                cross_validation_results[validation_name] = result

                if not result.get("passed", False):
                    self.critical_errors.append(
                        f"Cross-validation CRITICAL: {validation_name}"
                    )
                    critical_failures += 1
                    logger.error(
                        f"❌ CRITICAL: {validation_name} - {result.get('message', 'Failed')}"
                    )
                else:
                    logger.info(f"✅ {validation_name} passed")

            except Exception as e:
                cross_validation_results[validation_name] = {
                    "passed": False,
                    "error": str(e),
                    "critical": True,
                }
                critical_failures += 1

        self.validation_results["cross_validation"] = cross_validation_results

        success = critical_failures == 0
        logger.info(
            f"Cross-validation {'✅ PASSED' if success else '❌ FAILED'} ({critical_failures} critical failures)"
        )

        return success

    def generate_validation_report(self) -> Dict[str, Any]:
        """Generate comprehensive validation report.

        Returns:
            Dictionary with detailed validation report
        """
        overall_status = "PASS" if len(self.critical_errors) == 0 else "FAIL"

        # Calculate summary statistics
        total_validations = 0
        passed_validations = 0

        for category, results in self.validation_results.items():
            if isinstance(results, dict):
                for validation_name, result in results.items():
                    total_validations += 1
                    if result.get("passed", False):
                        passed_validations += 1

        pass_rate = (passed_validations / max(total_validations, 1)) * 100

        report = {
            "validation_metadata": {
                "timestamp": self.validation_timestamp.isoformat(),
                "overall_status": overall_status,
                "pass_rate_percent": round(pass_rate, 1),
                "total_validations": total_validations,
                "passed_validations": passed_validations,
                "failed_validations": total_validations - passed_validations,
            },
            "error_summary": {
                "critical_errors": len(self.critical_errors),
                "warnings": len(self.warnings),
                "critical_error_details": self.critical_errors[:10],  # First 10
                "warning_details": self.warnings[:10],  # First 10
            },
            "validation_results": self.validation_results,
            "recommendations": self._generate_recommendations(),
        }

        return report

    def save_validation_report(self, output_path: str) -> None:
        """Save validation report to file.

        Args:
            output_path: Path to save the report
        """
        report = self.generate_validation_report()

        with open(output_path, "w") as f:
            json.dump(report, f, indent=2, default=str)

        logger.info(f"📄 Validation report saved to: {output_path}")

    # Gene validation methods

    def _check_unique_gene_ids(self, genes_data: List[Dict]) -> Dict[str, Any]:
        """Check for duplicate gene IDs."""
        gene_ids = [g.get("gene_id") for g in genes_data if g.get("gene_id")]
        unique_ids = set(gene_ids)

        duplicates = []
        for gene_id in unique_ids:
            count = gene_ids.count(gene_id)
            if count > 1:
                duplicates.append((gene_id, count))

        duplicate_rate = len(duplicates) / max(len(unique_ids), 1)

        return {
            "passed": duplicate_rate <= self.thresholds["max_duplicate_rate"],
            "duplicates_found": len(duplicates),
            "duplicate_rate": round(duplicate_rate, 3),
            "total_unique_ids": len(unique_ids),
            "sample_duplicates": duplicates[:5],
            "message": f"Found {len(duplicates)} duplicate gene IDs ({duplicate_rate:.1%} rate)",
        }

    def _check_unique_gene_symbols(self, genes_data: List[Dict]) -> Dict[str, Any]:
        """Check for duplicate gene symbols."""
        gene_symbols = [
            g.get("gene_symbol") for g in genes_data if g.get("gene_symbol")
        ]
        unique_symbols = set(gene_symbols)

        duplicates = []
        for symbol in unique_symbols:
            count = gene_symbols.count(symbol)
            if count > 1:
                duplicates.append((symbol, count))

        duplicate_rate = len(duplicates) / max(len(unique_symbols), 1)

        return {
            "passed": duplicate_rate <= self.thresholds["max_duplicate_rate"],
            "duplicates_found": len(duplicates),
            "duplicate_rate": round(duplicate_rate, 3),
            "total_unique_symbols": len(unique_symbols),
            "sample_duplicates": duplicates[:5],
            "message": f"Found {len(duplicates)} duplicate gene symbols ({duplicate_rate:.1%} rate)",
        }

    def _check_valid_ensembl_ids(self, genes_data: List[Dict]) -> Dict[str, Any]:
        """Check validity of Ensembl gene IDs."""
        valid_count = 0
        invalid_ids = []

        for gene in genes_data:
            gene_id = gene.get("gene_id", "")
            if gene_id:
                if self.valid_patterns["ensembl_gene_id"].match(gene_id):
                    valid_count += 1
                else:
                    invalid_ids.append(gene_id)

        total_with_ids = len([g for g in genes_data if g.get("gene_id")])
        validity_rate = valid_count / max(total_with_ids, 1)

        return {
            "passed": validity_rate >= 0.8,  # 80% should be valid Ensembl IDs
            "valid_count": valid_count,
            "invalid_count": len(invalid_ids),
            "validity_rate": round(validity_rate, 3),
            "sample_invalid_ids": invalid_ids[:10],
            "message": f"{validity_rate:.1%} of gene IDs are valid Ensembl format",
        }

    def _check_gene_symbol_format(self, genes_data: List[Dict]) -> Dict[str, Any]:
        """Check gene symbol format validity."""
        valid_count = 0
        invalid_symbols = []

        for gene in genes_data:
            symbol = gene.get("gene_symbol", "")
            if symbol:
                # Check length and character validity
                if self.thresholds["min_gene_symbol_length"] <= len(
                    symbol
                ) <= self.thresholds["max_gene_symbol_length"] and re.match(
                    r"^[A-Z0-9\-@\.\_]+$", symbol
                ):
                    valid_count += 1
                else:
                    invalid_symbols.append(symbol)

        total_with_symbols = len([g for g in genes_data if g.get("gene_symbol")])
        validity_rate = valid_count / max(total_with_symbols, 1)

        return {
            "passed": validity_rate >= 0.9,  # 90% should have valid symbols
            "valid_count": valid_count,
            "invalid_count": len(invalid_symbols),
            "validity_rate": round(validity_rate, 3),
            "sample_invalid_symbols": invalid_symbols[:10],
            "message": f"{validity_rate:.1%} of gene symbols have valid format",
        }

    def _check_chromosome_validity(self, genes_data: List[Dict]) -> Dict[str, Any]:
        """Check chromosome field validity."""
        valid_count = 0
        invalid_chromosomes = []

        for gene in genes_data:
            chromosome = gene.get("chromosome", "")
            if chromosome:
                if self.valid_patterns["chromosome"].match(str(chromosome)):
                    valid_count += 1
                else:
                    invalid_chromosomes.append(chromosome)

        total_with_chromosome = len([g for g in genes_data if g.get("chromosome")])
        validity_rate = (
            valid_count / max(total_with_chromosome, 1)
            if total_with_chromosome > 0
            else 1.0
        )

        return {
            "passed": validity_rate >= 0.8,
            "valid_count": valid_count,
            "invalid_count": len(invalid_chromosomes),
            "validity_rate": round(validity_rate, 3),
            "total_with_chromosome": total_with_chromosome,
            "sample_invalid_chromosomes": invalid_chromosomes[:10],
            "message": f"{validity_rate:.1%} of chromosomes have valid format",
        }

    def _check_coordinates_structure(self, genes_data: List[Dict]) -> Dict[str, Any]:
        """Check coordinates structure validity."""
        valid_count = 0
        invalid_coordinates = []

        for gene in genes_data:
            coordinates = gene.get("coordinates")
            if coordinates:
                if (
                    isinstance(coordinates, dict)
                    and "start" in coordinates
                    and "end" in coordinates
                ):
                    try:
                        start = int(coordinates["start"])
                        end = int(coordinates["end"])
                        if start > 0 and end > start:
                            valid_count += 1
                        else:
                            invalid_coordinates.append(coordinates)
                    except (ValueError, TypeError):
                        invalid_coordinates.append(coordinates)
                else:
                    invalid_coordinates.append(coordinates)

        total_with_coordinates = len([g for g in genes_data if g.get("coordinates")])
        validity_rate = (
            valid_count / max(total_with_coordinates, 1)
            if total_with_coordinates > 0
            else 1.0
        )

        return {
            "passed": validity_rate >= 0.7,
            "valid_count": valid_count,
            "invalid_count": len(invalid_coordinates),
            "validity_rate": round(validity_rate, 3),
            "total_with_coordinates": total_with_coordinates,
            "message": f"{validity_rate:.1%} of coordinates have valid structure",
        }

    def _check_biomedical_consistency(self, genes_data: List[Dict]) -> Dict[str, Any]:
        """Check biomedical consistency of gene data."""
        known_cancer_genes = self.known_oncogenes.union(self.known_tumor_suppressors)
        found_cancer_genes = set()

        for gene in genes_data:
            symbol = gene.get("gene_symbol", "")
            if symbol in known_cancer_genes:
                found_cancer_genes.add(symbol)

        coverage_rate = len(found_cancer_genes) / len(known_cancer_genes)

        return {
            "passed": coverage_rate
            >= 0.3,  # Should have at least 30% of known cancer genes
            "known_cancer_genes_found": len(found_cancer_genes),
            "total_known_cancer_genes": len(known_cancer_genes),
            "coverage_rate": round(coverage_rate, 3),
            "found_genes": sorted(list(found_cancer_genes)),
            "message": f"Found {len(found_cancer_genes)}/{len(known_cancer_genes)} known cancer genes",
        }

    def _check_gene_data_completeness(self, genes_data: List[Dict]) -> Dict[str, Any]:
        """Check data completeness for genes."""
        required_fields = ["gene_id", "gene_symbol"]
        optional_fields = ["gene_type", "chromosome", "coordinates"]

        completeness_stats = {}

        for field in required_fields + optional_fields:
            count_with_field = len([g for g in genes_data if g.get(field)])
            completeness_rate = count_with_field / len(genes_data)
            completeness_stats[field] = {
                "count": count_with_field,
                "rate": round(completeness_rate, 3),
            }

        # Check if all required fields have high completeness
        required_completeness = min(
            [completeness_stats[field]["rate"] for field in required_fields]
        )

        return {
            "passed": required_completeness
            >= 0.95,  # 95% completeness for required fields
            "required_completeness": required_completeness,
            "completeness_by_field": completeness_stats,
            "total_records": len(genes_data),
            "message": f"Required field completeness: {required_completeness:.1%}",
        }

    def _check_gene_duplicates(self, genes_data: List[Dict]) -> Dict[str, Any]:
        """Check for various types of gene duplicates."""
        # Check by gene_id
        gene_ids = [g.get("gene_id") for g in genes_data if g.get("gene_id")]
        gene_id_duplicates = len(gene_ids) - len(set(gene_ids))

        # Check by gene_symbol
        gene_symbols = [
            g.get("gene_symbol") for g in genes_data if g.get("gene_symbol")
        ]
        symbol_duplicates = len(gene_symbols) - len(set(gene_symbols))

        total_duplicates = gene_id_duplicates + symbol_duplicates
        duplicate_rate = total_duplicates / max(len(genes_data), 1)

        return {
            "passed": duplicate_rate <= self.thresholds["max_duplicate_rate"],
            "gene_id_duplicates": gene_id_duplicates,
            "symbol_duplicates": symbol_duplicates,
            "total_duplicates": total_duplicates,
            "duplicate_rate": round(duplicate_rate, 3),
            "message": f"Total duplicate rate: {duplicate_rate:.1%}",
        }

    # Drug validation methods

    def _check_drug_names(self, drug_data: List[Dict]) -> Dict[str, Any]:
        """Check drug name validity."""
        valid_count = 0
        invalid_drugs = []

        for drug in drug_data:
            drug_name = drug.get("drug_name", "").strip()
            if drug_name:
                if (
                    len(drug_name) >= self.thresholds["min_drug_name_length"]
                    and not re.match(r"^[0-9]+$", drug_name)
                    and not re.match(r"^[^a-zA-Z]*$", drug_name)  # Not just numbers
                ):  # Contains letters
                    valid_count += 1
                else:
                    invalid_drugs.append(drug_name)

        total_drugs = len([d for d in drug_data if d.get("drug_name")])
        validity_rate = valid_count / max(total_drugs, 1)

        return {
            "passed": validity_rate >= 0.8,
            "valid_count": valid_count,
            "invalid_count": len(invalid_drugs),
            "validity_rate": round(validity_rate, 3),
            "sample_invalid_drugs": invalid_drugs[:10],
            "message": f"{validity_rate:.1%} of drug names are valid",
        }

    def _check_interaction_completeness(self, drug_data: List[Dict]) -> Dict[str, Any]:
        """Check completeness of drug interaction data."""
        required_fields = ["gene_id", "drug_name", "source_database"]
        optional_fields = ["interaction_type", "mechanism_of_action", "clinical_phase"]

        completeness_stats = {}

        for field in required_fields + optional_fields:
            count_with_field = len([d for d in drug_data if d.get(field)])
            completeness_rate = count_with_field / max(len(drug_data), 1)
            completeness_stats[field] = {
                "count": count_with_field,
                "rate": round(completeness_rate, 3),
            }

        required_completeness = (
            min([completeness_stats[field]["rate"] for field in required_fields])
            if drug_data
            else 1.0
        )

        return {
            "passed": required_completeness >= 0.9,
            "required_completeness": required_completeness,
            "completeness_by_field": completeness_stats,
            "total_interactions": len(drug_data),
            "message": f"Required field completeness: {required_completeness:.1%}",
        }

    def _check_source_attribution(self, drug_data: List[Dict]) -> Dict[str, Any]:
        """Check source attribution for drug data."""
        sources = [
            d.get("source_database") for d in drug_data if d.get("source_database")
        ]
        source_counts = Counter(sources)

        valid_sources = {"drugcentral", "chembl", "pharmgkb"}
        invalid_sources = [s for s in source_counts.keys() if s not in valid_sources]

        attribution_rate = len(sources) / max(len(drug_data), 1)

        return {
            "passed": attribution_rate >= 0.95 and len(invalid_sources) == 0,
            "attribution_rate": round(attribution_rate, 3),
            "source_distribution": dict(source_counts),
            "invalid_sources": invalid_sources,
            "total_with_source": len(sources),
            "message": f"Source attribution rate: {attribution_rate:.1%}",
        }

    def _check_drug_duplicates(self, drug_data: List[Dict]) -> Dict[str, Any]:
        """Check for duplicate drug interactions."""
        interaction_keys = []

        for drug in drug_data:
            key = (
                drug.get("gene_id", ""),
                drug.get("drug_name", "").lower().strip(),
                drug.get("source_database", ""),
            )
            interaction_keys.append(key)

        unique_interactions = set(interaction_keys)
        duplicate_count = len(interaction_keys) - len(unique_interactions)
        duplicate_rate = duplicate_count / max(len(interaction_keys), 1)

        return {
            "passed": duplicate_rate <= self.thresholds["max_duplicate_rate"],
            "total_interactions": len(interaction_keys),
            "unique_interactions": len(unique_interactions),
            "duplicate_count": duplicate_count,
            "duplicate_rate": round(duplicate_rate, 3),
            "message": f"Duplicate interaction rate: {duplicate_rate:.1%}",
        }

    def _check_clinical_status(self, drug_data: List[Dict]) -> Dict[str, Any]:
        """Check validity of clinical status fields."""
        valid_phases = {
            "Phase 0",
            "Phase 1",
            "Phase 2",
            "Phase 3",
            "Phase 4",
            "Approved",
            "Withdrawn",
        }
        valid_statuses = {"Approved", "Investigational", "Experimental", "Withdrawn"}

        phase_validity = 0
        status_validity = 0
        total_with_phase = 0
        total_with_status = 0

        for drug in drug_data:
            clinical_phase = drug.get("clinical_phase", "")
            approval_status = drug.get("approval_status", "")

            if clinical_phase:
                total_with_phase += 1
                if clinical_phase in valid_phases:
                    phase_validity += 1

            if approval_status:
                total_with_status += 1
                if approval_status in valid_statuses:
                    status_validity += 1

        phase_validity_rate = (
            phase_validity / max(total_with_phase, 1) if total_with_phase > 0 else 1.0
        )
        status_validity_rate = (
            status_validity / max(total_with_status, 1)
            if total_with_status > 0
            else 1.0
        )

        overall_validity = (phase_validity_rate + status_validity_rate) / 2

        return {
            "passed": overall_validity >= 0.7,
            "phase_validity_rate": round(phase_validity_rate, 3),
            "status_validity_rate": round(status_validity_rate, 3),
            "overall_validity": round(overall_validity, 3),
            "total_with_phase": total_with_phase,
            "total_with_status": total_with_status,
            "message": f"Clinical status validity: {overall_validity:.1%}",
        }

    def _check_confidence_scores(self, drug_data: List[Dict]) -> Dict[str, Any]:
        """Check confidence scores if present."""
        scores = [
            d.get("confidence_score")
            for d in drug_data
            if d.get("confidence_score") is not None
        ]

        if not scores:
            return {"passed": True, "message": "No confidence scores to validate"}

        valid_scores = [
            s for s in scores if 0 <= s <= self.thresholds["max_confidence_score"]
        ]
        validity_rate = len(valid_scores) / len(scores)

        return {
            "passed": validity_rate >= 0.9,
            "total_scores": len(scores),
            "valid_scores": len(valid_scores),
            "validity_rate": round(validity_rate, 3),
            "score_range": [min(scores), max(scores)] if scores else [None, None],
            "message": f"Confidence score validity: {validity_rate:.1%}",
        }

    def _check_gene_drug_consistency(self, drug_data: List[Dict]) -> Dict[str, Any]:
        """Check consistency between genes and drug interactions."""
        gene_ids_in_drugs = set(d.get("gene_id") for d in drug_data if d.get("gene_id"))
        gene_symbols_in_drugs = set(
            d.get("gene_symbol") for d in drug_data if d.get("gene_symbol")
        )

        # Check for obvious inconsistencies
        inconsistencies = []

        # Group by gene_id and check symbol consistency
        gene_groups = defaultdict(set)
        for drug in drug_data:
            gene_id = drug.get("gene_id")
            gene_symbol = drug.get("gene_symbol")
            if gene_id and gene_symbol:
                gene_groups[gene_id].add(gene_symbol)

        # Find gene IDs with multiple symbols
        for gene_id, symbols in gene_groups.items():
            if len(symbols) > 1:
                inconsistencies.append(
                    {
                        "gene_id": gene_id,
                        "symbols": list(symbols),
                        "type": "multiple_symbols_for_gene_id",
                    }
                )

        consistency_rate = 1.0 - (len(inconsistencies) / max(len(gene_groups), 1))

        return {
            "passed": consistency_rate >= 0.95,
            "consistency_rate": round(consistency_rate, 3),
            "total_gene_drug_pairs": len(gene_groups),
            "inconsistencies": len(inconsistencies),
            "sample_inconsistencies": inconsistencies[:5],
            "message": f"Gene-drug consistency rate: {consistency_rate:.1%}",
        }

    def _check_drug_biomedical_plausibility(
        self, drug_data: List[Dict]
    ) -> Dict[str, Any]:
        """Check biomedical plausibility of drug-gene interactions."""
        # Check if known cancer genes have drug interactions
        cancer_gene_drug_count = 0
        total_cancer_genes = 0

        for drug in drug_data:
            gene_symbol = drug.get("gene_symbol", "")
            if (
                gene_symbol in self.known_oncogenes
                or gene_symbol in self.known_tumor_suppressors
            ):
                cancer_gene_drug_count += 1

        # Count unique cancer genes in drug data
        cancer_genes_with_drugs = set()
        for drug in drug_data:
            gene_symbol = drug.get("gene_symbol", "")
            if (
                gene_symbol in self.known_oncogenes
                or gene_symbol in self.known_tumor_suppressors
            ):
                cancer_genes_with_drugs.add(gene_symbol)

        total_known_cancer_genes = len(
            self.known_oncogenes.union(self.known_tumor_suppressors)
        )
        cancer_gene_coverage = len(cancer_genes_with_drugs) / total_known_cancer_genes

        return {
            "passed": cancer_gene_coverage
            >= 0.1,  # At least 10% of known cancer genes should have drugs
            "cancer_gene_interactions": cancer_gene_drug_count,
            "unique_cancer_genes_with_drugs": len(cancer_genes_with_drugs),
            "total_known_cancer_genes": total_known_cancer_genes,
            "coverage_rate": round(cancer_gene_coverage, 3),
            "cancer_genes_found": sorted(list(cancer_genes_with_drugs)),
            "message": f"Cancer gene drug coverage: {cancer_gene_coverage:.1%}",
        }

    # Annotation validation methods

    def _check_go_term_structure(self, annotations_data: List[Dict]) -> Dict[str, Any]:
        """Check GO term structure validity."""
        valid_structures = 0
        total_with_go = 0

        for annotation in annotations_data:
            go_terms = annotation.get("go_terms", {})
            if go_terms:
                total_with_go += 1
                if isinstance(go_terms, dict) and any(
                    key in go_terms
                    for key in [
                        "molecular_function",
                        "biological_process",
                        "cellular_component",
                    ]
                ):
                    valid_structures += 1

        structure_validity_rate = (
            valid_structures / max(total_with_go, 1) if total_with_go > 0 else 1.0
        )

        return {
            "passed": structure_validity_rate >= 0.8,
            "valid_structures": valid_structures,
            "total_with_go_terms": total_with_go,
            "structure_validity_rate": round(structure_validity_rate, 3),
            "message": f"GO term structure validity: {structure_validity_rate:.1%}",
        }

    def _check_pathway_validity(self, annotations_data: List[Dict]) -> Dict[str, Any]:
        """Check pathway validity."""
        total_pathways = 0
        reactome_pathways = 0

        for annotation in annotations_data:
            pathways = annotation.get("pathways", []) or annotation.get(
                "reactome_pathways", []
            )
            if pathways and isinstance(pathways, list):
                total_pathways += len(pathways)
                for pathway in pathways:
                    if isinstance(pathway, str) and "Reactome:R-HSA-" in pathway:
                        reactome_pathways += 1

        reactome_rate = (
            reactome_pathways / max(total_pathways, 1) if total_pathways > 0 else 0
        )

        return {
            "passed": reactome_rate >= 0.5
            or total_pathways == 0,  # 50% should be Reactome format
            "total_pathways": total_pathways,
            "reactome_pathways": reactome_pathways,
            "reactome_rate": round(reactome_rate, 3),
            "message": f"Reactome pathway rate: {reactome_rate:.1%}",
        }

    def _check_cross_references(self, annotations_data: List[Dict]) -> Dict[str, Any]:
        """Check cross-reference validity."""
        valid_uniprot = 0
        total_uniprot = 0

        for annotation in annotations_data:
            uniprot_ids = annotation.get("uniprot_ids", [])
            if uniprot_ids and isinstance(uniprot_ids, list):
                for uniprot_id in uniprot_ids:
                    total_uniprot += 1
                    if self.valid_patterns["uniprot_id"].match(uniprot_id):
                        valid_uniprot += 1

        uniprot_validity_rate = (
            valid_uniprot / max(total_uniprot, 1) if total_uniprot > 0 else 1.0
        )

        return {
            "passed": uniprot_validity_rate >= 0.8,
            "valid_uniprot_ids": valid_uniprot,
            "total_uniprot_ids": total_uniprot,
            "uniprot_validity_rate": round(uniprot_validity_rate, 3),
            "message": f"UniProt ID validity: {uniprot_validity_rate:.1%}",
        }

    def _check_annotation_consistency(
        self, annotations_data: List[Dict]
    ) -> Dict[str, Any]:
        """Check consistency of annotation data."""
        gene_id_consistency = {}
        inconsistencies = 0

        for annotation in annotations_data:
            gene_id = annotation.get("gene_id")
            gene_symbol = annotation.get("gene_symbol")

            if gene_id and gene_symbol:
                if gene_id not in gene_id_consistency:
                    gene_id_consistency[gene_id] = gene_symbol
                elif gene_id_consistency[gene_id] != gene_symbol:
                    inconsistencies += 1

        consistency_rate = 1.0 - (inconsistencies / max(len(gene_id_consistency), 1))

        return {
            "passed": consistency_rate >= 0.95,
            "total_annotations": len(annotations_data),
            "gene_id_symbol_pairs": len(gene_id_consistency),
            "inconsistencies": inconsistencies,
            "consistency_rate": round(consistency_rate, 3),
            "message": f"Annotation consistency rate: {consistency_rate:.1%}",
        }

    def _check_molecular_functions(
        self, annotations_data: List[Dict]
    ) -> Dict[str, Any]:
        """Check molecular function validity."""
        total_functions = 0
        go_formatted_functions = 0

        for annotation in annotations_data:
            functions = annotation.get("molecular_functions", []) or annotation.get(
                "go_molecular_functions", []
            )
            if functions and isinstance(functions, list):
                total_functions += len(functions)
                for func in functions:
                    if isinstance(func, str) and (
                        "GO:" in func
                        or "binding" in func.lower()
                        or "activity" in func.lower()
                    ):
                        go_formatted_functions += 1

        go_function_rate = (
            go_formatted_functions / max(total_functions, 1)
            if total_functions > 0
            else 0
        )

        return {
            "passed": go_function_rate >= 0.3
            or total_functions == 0,  # 30% should be GO-like
            "total_functions": total_functions,
            "go_formatted_functions": go_formatted_functions,
            "go_function_rate": round(go_function_rate, 3),
            "message": f"GO-formatted function rate: {go_function_rate:.1%}",
        }

    # Cross-validation methods

    def _check_gene_id_consistency(
        self, genes: List[Dict], drugs: List[Dict], annotations: List[Dict]
    ) -> Dict[str, Any]:
        """Check gene ID consistency across data types."""
        gene_ids_genes = set(g.get("gene_id") for g in genes if g.get("gene_id"))
        gene_ids_drugs = set(d.get("gene_id") for d in drugs if d.get("gene_id"))
        gene_ids_annotations = set(
            a.get("gene_id") for a in annotations if a.get("gene_id")
        )

        # Check coverage
        drugs_coverage = len(gene_ids_drugs.intersection(gene_ids_genes)) / max(
            len(gene_ids_drugs), 1
        )
        annotations_coverage = len(
            gene_ids_annotations.intersection(gene_ids_genes)
        ) / max(len(gene_ids_annotations), 1)

        overall_consistency = (drugs_coverage + annotations_coverage) / 2

        return {
            "passed": overall_consistency >= 0.9,
            "gene_ids_in_genes": len(gene_ids_genes),
            "gene_ids_in_drugs": len(gene_ids_drugs),
            "gene_ids_in_annotations": len(gene_ids_annotations),
            "drugs_coverage": round(drugs_coverage, 3),
            "annotations_coverage": round(annotations_coverage, 3),
            "overall_consistency": round(overall_consistency, 3),
            "message": f"Gene ID consistency: {overall_consistency:.1%}",
        }

    def _check_gene_symbol_consistency(
        self, genes: List[Dict], drugs: List[Dict], annotations: List[Dict]
    ) -> Dict[str, Any]:
        """Check gene symbol consistency across data types."""
        # Build gene_id -> gene_symbol mapping from genes
        gene_id_to_symbol = {
            g.get("gene_id"): g.get("gene_symbol")
            for g in genes
            if g.get("gene_id") and g.get("gene_symbol")
        }

        inconsistencies = 0
        total_checked = 0

        # Check drugs
        for drug in drugs:
            gene_id = drug.get("gene_id")
            gene_symbol = drug.get("gene_symbol")
            if gene_id and gene_symbol and gene_id in gene_id_to_symbol:
                total_checked += 1
                if gene_id_to_symbol[gene_id] != gene_symbol:
                    inconsistencies += 1

        # Check annotations
        for annotation in annotations:
            gene_id = annotation.get("gene_id")
            gene_symbol = annotation.get("gene_symbol")
            if gene_id and gene_symbol and gene_id in gene_id_to_symbol:
                total_checked += 1
                if gene_id_to_symbol[gene_id] != gene_symbol:
                    inconsistencies += 1

        consistency_rate = 1.0 - (inconsistencies / max(total_checked, 1))

        return {
            "passed": consistency_rate >= 0.95,
            "total_checked": total_checked,
            "inconsistencies": inconsistencies,
            "consistency_rate": round(consistency_rate, 3),
            "message": f"Gene symbol consistency: {consistency_rate:.1%}",
        }

    def _check_data_coverage_consistency(
        self, genes: List[Dict], drugs: List[Dict], annotations: List[Dict]
    ) -> Dict[str, Any]:
        """Check data coverage consistency."""
        total_genes = len(genes)
        genes_with_drugs = len(set(d.get("gene_id") for d in drugs if d.get("gene_id")))
        genes_with_annotations = len(
            set(a.get("gene_id") for a in annotations if a.get("gene_id"))
        )

        drug_coverage = genes_with_drugs / max(total_genes, 1)
        annotation_coverage = genes_with_annotations / max(total_genes, 1)

        return {
            "passed": drug_coverage >= 0.05
            and annotation_coverage >= 0.3,  # Minimum coverage expectations
            "total_genes": total_genes,
            "genes_with_drugs": genes_with_drugs,
            "genes_with_annotations": genes_with_annotations,
            "drug_coverage": round(drug_coverage, 3),
            "annotation_coverage": round(annotation_coverage, 3),
            "message": f"Coverage - Drugs: {drug_coverage:.1%}, Annotations: {annotation_coverage:.1%}",
        }

    def _check_biomedical_coherence(
        self, genes: List[Dict], drugs: List[Dict], annotations: List[Dict]
    ) -> Dict[str, Any]:
        """Check biomedical coherence across data types."""
        # Check that known cancer genes have appropriate annotations and drugs
        cancer_genes_in_data = set()
        cancer_genes_with_drugs = set()
        cancer_genes_with_annotations = set()

        all_known_cancer = self.known_oncogenes.union(self.known_tumor_suppressors)

        for gene in genes:
            symbol = gene.get("gene_symbol")
            gene_id = gene.get("gene_id")
            if symbol in all_known_cancer:
                cancer_genes_in_data.add(gene_id)

        for drug in drugs:
            gene_symbol = drug.get("gene_symbol")
            gene_id = drug.get("gene_id")
            if gene_symbol in all_known_cancer and gene_id in cancer_genes_in_data:
                cancer_genes_with_drugs.add(gene_id)

        for annotation in annotations:
            gene_symbol = annotation.get("gene_symbol")
            gene_id = annotation.get("gene_id")
            if gene_symbol in all_known_cancer and gene_id in cancer_genes_in_data:
                cancer_genes_with_annotations.add(gene_id)

        drug_coherence = len(cancer_genes_with_drugs) / max(
            len(cancer_genes_in_data), 1
        )
        annotation_coherence = len(cancer_genes_with_annotations) / max(
            len(cancer_genes_in_data), 1
        )
        overall_coherence = (drug_coherence + annotation_coherence) / 2

        return {
            "passed": overall_coherence
            >= 0.3,  # 30% of cancer genes should have drugs/annotations
            "cancer_genes_in_data": len(cancer_genes_in_data),
            "cancer_genes_with_drugs": len(cancer_genes_with_drugs),
            "cancer_genes_with_annotations": len(cancer_genes_with_annotations),
            "drug_coherence": round(drug_coherence, 3),
            "annotation_coherence": round(annotation_coherence, 3),
            "overall_coherence": round(overall_coherence, 3),
            "message": f"Biomedical coherence: {overall_coherence:.1%}",
        }

    def _generate_recommendations(self) -> List[str]:
        """Generate recommendations based on validation results."""
        recommendations = []

        if len(self.critical_errors) > 0:
            recommendations.append(
                "🚨 Address all critical errors before proceeding with migration"
            )

        if len(self.warnings) > 0:
            recommendations.append(
                "⚠️ Review and address validation warnings for improved data quality"
            )

        # Check specific validation results for targeted recommendations
        gene_results = self.validation_results.get("genes", {})
        drug_results = self.validation_results.get("drug_interactions", {})

        if gene_results.get("unique_gene_ids", {}).get("passed") is False:
            recommendations.append("🔄 Implement stronger gene ID deduplication logic")

        if drug_results.get("source_attribution", {}).get("passed") is False:
            recommendations.append(
                "📝 Improve source attribution for drug interaction data"
            )

        if gene_results.get("biomedical_consistency", {}).get("passed") is False:
            recommendations.append(
                "🧬 Review biomedical gene coverage - may be missing known cancer genes"
            )

        if not recommendations:
            recommendations.append(
                "✅ Validation passed - ready to proceed with migration"
            )

        return recommendations
