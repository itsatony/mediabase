#!/usr/bin/env python3
"""
Generate Enhanced Demo Patient Datasets with Biomedically Realistic Expression Patterns

This script creates comprehensive patient datasets for major cancer types with
realistic fold-change patterns based on expert biomedical knowledge and literature.

Usage:
    poetry run python scripts/generate_demo_datasets.py --all
    poetry run python scripts/generate_demo_datasets.py --cancer-type breast_her2
"""

import argparse
import csv
import logging
import os
import random
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Set
import json
from datetime import datetime

import pandas as pd
import numpy as np
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, TaskID

# Add project root to Python path
project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))

from src.db.database import get_db_manager
from src.utils.logging import setup_logging

# Setup logging
logger = setup_logging(module_name=__name__)
console = Console()


class DemoDatasetGenerator:
    """Generate biomedically realistic demo datasets for cancer transcriptomics."""

    # Core cancer gene sets based on expert knowledge
    ONCOGENES = {
        "MYC": {
            "base_fold": 4.5,
            "range": (3.0, 8.0),
            "pathways": ["cell_cycle", "proliferation"],
        },
        "ERBB2": {
            "base_fold": 6.0,
            "range": (4.0, 12.0),
            "pathways": ["growth_signaling", "her2"],
        },
        "EGFR": {
            "base_fold": 5.5,
            "range": (3.5, 9.0),
            "pathways": ["growth_signaling", "egfr"],
        },
        "KRAS": {
            "base_fold": 3.8,
            "range": (2.5, 6.5),
            "pathways": ["ras_signaling", "proliferation"],
        },
        "PIK3CA": {
            "base_fold": 3.2,
            "range": (2.0, 5.5),
            "pathways": ["pi3k_akt", "growth"],
        },
        "AKT1": {
            "base_fold": 2.8,
            "range": (2.0, 4.5),
            "pathways": ["pi3k_akt", "survival"],
        },
        "CCND1": {
            "base_fold": 4.2,
            "range": (2.5, 7.0),
            "pathways": ["cell_cycle", "g1_s"],
        },
        "MDM2": {
            "base_fold": 3.5,
            "range": (2.0, 6.0),
            "pathways": ["p53_pathway", "apoptosis_inhibition"],
        },
        "BRAF": {
            "base_fold": 3.0,
            "range": (2.0, 5.0),
            "pathways": ["mapk", "proliferation"],
        },
        "NRAS": {
            "base_fold": 2.8,
            "range": (1.8, 4.5),
            "pathways": ["ras_signaling", "proliferation"],
        },
    }

    TUMOR_SUPPRESSORS = {
        "TP53": {
            "base_fold": 0.35,
            "range": (0.15, 0.65),
            "pathways": ["p53_pathway", "apoptosis", "dna_damage"],
        },
        "RB1": {
            "base_fold": 0.45,
            "range": (0.20, 0.70),
            "pathways": ["cell_cycle", "g1_s_checkpoint"],
        },
        "PTEN": {
            "base_fold": 0.40,
            "range": (0.15, 0.65),
            "pathways": ["pi3k_akt", "tumor_suppression"],
        },
        "BRCA1": {
            "base_fold": 0.30,
            "range": (0.10, 0.55),
            "pathways": ["dna_repair", "homologous_recombination"],
        },
        "BRCA2": {
            "base_fold": 0.32,
            "range": (0.12, 0.58),
            "pathways": ["dna_repair", "homologous_recombination"],
        },
        "CDKN2A": {
            "base_fold": 0.25,
            "range": (0.10, 0.50),
            "pathways": ["cell_cycle", "p16_pathway"],
        },
        "CDKN1A": {
            "base_fold": 0.55,
            "range": (0.30, 0.80),
            "pathways": ["cell_cycle", "p21_pathway"],
        },
        "CDKN1B": {
            "base_fold": 0.48,
            "range": (0.25, 0.75),
            "pathways": ["cell_cycle", "p27_pathway"],
        },
        "APC": {
            "base_fold": 0.38,
            "range": (0.15, 0.65),
            "pathways": ["wnt_signaling", "tumor_suppression"],
        },
        "VHL": {
            "base_fold": 0.42,
            "range": (0.20, 0.70),
            "pathways": ["hypoxia_response", "tumor_suppression"],
        },
    }

    DNA_REPAIR_GENES = {
        "ATM": {
            "base_fold": 0.45,
            "range": (0.25, 0.70),
            "pathways": ["dna_damage_response", "atm_checkpoint"],
        },
        "CHEK1": {
            "base_fold": 0.52,
            "range": (0.30, 0.75),
            "pathways": ["cell_cycle_checkpoint", "dna_repair"],
        },
        "CHEK2": {
            "base_fold": 0.48,
            "range": (0.28, 0.72),
            "pathways": ["cell_cycle_checkpoint", "dna_repair"],
        },
        "RAD51": {
            "base_fold": 0.55,
            "range": (0.35, 0.80),
            "pathways": ["homologous_recombination", "dna_repair"],
        },
        "PARP1": {
            "base_fold": 0.60,
            "range": (0.40, 0.85),
            "pathways": ["base_excision_repair", "parp_pathway"],
        },
        "MLH1": {
            "base_fold": 0.35,
            "range": (0.15, 0.60),
            "pathways": ["mismatch_repair", "msi"],
        },
        "MSH2": {
            "base_fold": 0.40,
            "range": (0.20, 0.65),
            "pathways": ["mismatch_repair", "msi"],
        },
        "XRCC1": {
            "base_fold": 0.58,
            "range": (0.35, 0.80),
            "pathways": ["base_excision_repair", "dna_repair"],
        },
    }

    HORMONE_RECEPTORS = {
        "ESR1": {
            "base_fold": 2.5,
            "range": (0.3, 6.0),
            "pathways": ["estrogen_signaling", "hormone_response"],
        },
        "PGR": {
            "base_fold": 2.2,
            "range": (0.2, 5.5),
            "pathways": ["progesterone_signaling", "hormone_response"],
        },
        "AR": {
            "base_fold": 1.8,
            "range": (0.3, 4.5),
            "pathways": ["androgen_signaling", "hormone_response"],
        },
    }

    # Cancer-specific patterns
    CANCER_SIGNATURES = {
        "breast_her2": {
            "dominant_pathways": ["her2", "growth_signaling", "pi3k_akt"],
            "oncogene_multipliers": {"ERBB2": 1.8, "PIK3CA": 1.4, "AKT1": 1.3},
            "suppressor_multipliers": {"PTEN": 0.7, "TP53": 0.8},
            "hormone_status": {"ESR1": 0.8, "PGR": 0.6},  # Often ER/PR negative
            "target_genes": 500,
        },
        "breast_tnbc": {
            "dominant_pathways": ["p53_pathway", "dna_repair", "cell_cycle"],
            "oncogene_multipliers": {"MYC": 1.5, "CCND1": 1.3},
            "suppressor_multipliers": {"TP53": 0.5, "BRCA1": 0.6, "BRCA2": 0.7},
            "hormone_status": {"ESR1": 0.2, "PGR": 0.2, "AR": 0.3},  # Triple negative
            "target_genes": 400,
        },
        "lung_egfr": {
            "dominant_pathways": ["egfr", "growth_signaling", "mapk"],
            "oncogene_multipliers": {
                "EGFR": 2.0,
                "KRAS": 0.8,
                "BRAF": 1.2,
            },  # EGFR high, KRAS often wild-type
            "suppressor_multipliers": {"TP53": 0.6, "RB1": 0.7},
            "target_genes": 300,
        },
        "colorectal_msi": {
            "dominant_pathways": [
                "mismatch_repair",
                "immune_response",
                "wnt_signaling",
            ],
            "oncogene_multipliers": {"KRAS": 1.4, "PIK3CA": 1.3},
            "suppressor_multipliers": {"MLH1": 0.4, "MSH2": 0.4, "APC": 0.5},
            "target_genes": 400,
        },
        "pancreatic_pdac": {
            "dominant_pathways": ["kras_signaling", "p53_pathway", "tgf_beta"],
            "oncogene_multipliers": {"KRAS": 2.2, "MYC": 1.6},  # Very high KRAS
            "suppressor_multipliers": {"TP53": 0.3, "CDKN2A": 0.2, "SMAD4": 0.4},
            "target_genes": 350,
        },
        "comprehensive": {
            "dominant_pathways": ["multiple"],
            "oncogene_multipliers": {},  # Use base values
            "suppressor_multipliers": {},  # Use base values
            "target_genes": 1000,
        },
    }

    def __init__(self, db_config: Dict):
        """Initialize the dataset generator.

        Args:
            db_config: Database configuration dictionary
        """
        self.db_config = db_config
        self.available_genes = {}  # gene_symbol -> [transcript_ids]
        self.gene_pathways = {}  # gene_symbol -> [pathways]
        self.gene_products = {}  # gene_symbol -> [product_types]
        self.gene_drugs = {}  # gene_symbol -> drug_info

        # Statistics
        self.stats = {
            "total_genes_in_db": 0,
            "available_cancer_genes": 0,
            "genes_with_pathways": 0,
            "genes_with_drugs": 0,
        }

    def load_database_gene_info(self):
        """Load gene information from database for realistic dataset generation."""
        console.print("[blue]Loading gene information from database...[/blue]")

        try:
            db_manager = get_db_manager(self.db_config)
            if not db_manager.ensure_connection():
                raise Exception("Failed to connect to database")

            cursor = db_manager.cursor

            # Load gene symbols with transcript IDs, pathways, products, and drugs from normalized schema
            cursor.execute(
                """
                SELECT DISTINCT
                    g.gene_symbol,
                    t.transcript_id,
                    COALESCE(gp_agg.pathways, ARRAY[]::text[]) as pathways,
                    COALESCE(ga_agg.product_types, ARRAY[]::text[]) as product_type,
                    ARRAY[]::text[] as molecular_functions,  -- Placeholder for now
                    COALESCE(gdi_agg.drugs, '{}'::jsonb) as drugs
                FROM genes g
                JOIN transcripts t ON g.gene_id = t.gene_id
                LEFT JOIN (
                    SELECT gene_id, array_agg(pathway_name) as pathways
                    FROM gene_pathways
                    GROUP BY gene_id
                ) gp_agg ON g.gene_id = gp_agg.gene_id
                LEFT JOIN (
                    SELECT gene_id, array_agg(annotation_value) as product_types
                    FROM gene_annotations
                    WHERE annotation_type = 'product_type'
                    GROUP BY gene_id
                ) ga_agg ON g.gene_id = ga_agg.gene_id
                LEFT JOIN (
                    SELECT gene_id, jsonb_object_agg(drug_name, jsonb_build_object(
                        'drug_id', drug_id, 'interaction_type', interaction_type, 'source', source
                    )) as drugs
                    FROM gene_drug_interactions
                    GROUP BY gene_id
                ) gdi_agg ON g.gene_id = gdi_agg.gene_id
                WHERE g.gene_symbol IS NOT NULL
                AND g.gene_symbol != ''
                ORDER BY g.gene_symbol
            """
            )

            for row in cursor.fetchall():
                (
                    gene_symbol,
                    transcript_id,
                    pathways,
                    product_type,
                    molecular_functions,
                    drugs,
                ) = row

                # Store transcript IDs
                if gene_symbol not in self.available_genes:
                    self.available_genes[gene_symbol] = []
                self.available_genes[gene_symbol].append(transcript_id)

                # Store pathways
                if pathways:
                    if gene_symbol not in self.gene_pathways:
                        self.gene_pathways[gene_symbol] = set()
                    self.gene_pathways[gene_symbol].update(pathways)

                # Store product types
                if product_type:
                    if gene_symbol not in self.gene_products:
                        self.gene_products[gene_symbol] = set()
                    self.gene_products[gene_symbol].update(product_type)

                # Store drug information
                if drugs and drugs != {}:
                    if gene_symbol not in self.gene_drugs:
                        self.gene_drugs[gene_symbol] = []
                    self.gene_drugs[gene_symbol] = dict(drugs)

            # Update statistics
            self.stats["total_genes_in_db"] = len(self.available_genes)

            # Count cancer-relevant genes
            all_cancer_genes = (
                set(self.ONCOGENES.keys())
                | set(self.TUMOR_SUPPRESSORS.keys())
                | set(self.DNA_REPAIR_GENES.keys())
                | set(self.HORMONE_RECEPTORS.keys())
            )
            self.stats["available_cancer_genes"] = len(
                all_cancer_genes & set(self.available_genes.keys())
            )
            self.stats["genes_with_pathways"] = len(self.gene_pathways)
            self.stats["genes_with_drugs"] = len(self.gene_drugs)

            console.print(
                f"[green]✓ Loaded information for {self.stats['total_genes_in_db']} genes[/green]"
            )
            console.print(
                f"  • Cancer genes available: {self.stats['available_cancer_genes']}"
            )
            console.print(
                f"  • Genes with pathways: {self.stats['genes_with_pathways']}"
            )
            console.print(f"  • Genes with drugs: {self.stats['genes_with_drugs']}")

        except Exception as e:
            logger.error(f"Failed to load gene information: {e}")
            raise
        finally:
            if "db_manager" in locals():
                db_manager.close()

    def generate_cancer_dataset(self, cancer_type: str, output_path: Path) -> Dict:
        """Generate a comprehensive cancer-specific dataset.

        Args:
            cancer_type: Type of cancer (e.g., 'breast_her2', 'lung_egfr')
            output_path: Path to save the generated CSV

        Returns:
            Dictionary with dataset statistics
        """
        if cancer_type not in self.CANCER_SIGNATURES:
            raise ValueError(
                f"Unknown cancer type: {cancer_type}. Available: {list(self.CANCER_SIGNATURES.keys())}"
            )

        signature = self.CANCER_SIGNATURES[cancer_type]
        console.print(
            f"[blue]Generating {cancer_type} dataset with {signature['target_genes']} genes...[/blue]"
        )

        dataset_rows = []
        gene_categories = {
            "oncogenes": 0,
            "tumor_suppressors": 0,
            "dna_repair": 0,
            "hormone_receptors": 0,
            "pathway_genes": 0,
            "drug_targets": 0,
        }

        # Process core cancer genes first
        processed_genes = set()

        # 1. Oncogenes
        for gene_symbol, gene_info in self.ONCOGENES.items():
            if gene_symbol in self.available_genes:
                fold_change = self._calculate_cancer_specific_fold_change(
                    gene_symbol, gene_info, signature, "oncogene"
                )
                transcript_id = random.choice(self.available_genes[gene_symbol])

                row = self._create_gene_row(
                    gene_symbol, transcript_id, fold_change, cancer_type, "oncogene"
                )
                dataset_rows.append(row)
                processed_genes.add(gene_symbol)
                gene_categories["oncogenes"] += 1

        # 2. Tumor Suppressors
        for gene_symbol, gene_info in self.TUMOR_SUPPRESSORS.items():
            if gene_symbol in self.available_genes:
                fold_change = self._calculate_cancer_specific_fold_change(
                    gene_symbol, gene_info, signature, "tumor_suppressor"
                )
                transcript_id = random.choice(self.available_genes[gene_symbol])

                row = self._create_gene_row(
                    gene_symbol,
                    transcript_id,
                    fold_change,
                    cancer_type,
                    "tumor_suppressor",
                )
                dataset_rows.append(row)
                processed_genes.add(gene_symbol)
                gene_categories["tumor_suppressors"] += 1

        # 3. DNA Repair Genes
        for gene_symbol, gene_info in self.DNA_REPAIR_GENES.items():
            if gene_symbol in self.available_genes:
                fold_change = self._calculate_cancer_specific_fold_change(
                    gene_symbol, gene_info, signature, "dna_repair"
                )
                transcript_id = random.choice(self.available_genes[gene_symbol])

                row = self._create_gene_row(
                    gene_symbol, transcript_id, fold_change, cancer_type, "dna_repair"
                )
                dataset_rows.append(row)
                processed_genes.add(gene_symbol)
                gene_categories["dna_repair"] += 1

        # 4. Hormone Receptors (cancer-specific patterns)
        for gene_symbol, gene_info in self.HORMONE_RECEPTORS.items():
            if gene_symbol in self.available_genes:
                # Apply cancer-specific hormone patterns
                if gene_symbol in signature.get("hormone_status", {}):
                    hormone_multiplier = signature["hormone_status"][gene_symbol]
                    if hormone_multiplier < 1.0:  # Suppressed
                        fold_change = np.random.uniform(0.1, hormone_multiplier)
                    else:  # Enhanced
                        fold_change = gene_info["base_fold"] * hormone_multiplier
                else:
                    fold_change = self._calculate_cancer_specific_fold_change(
                        gene_symbol, gene_info, signature, "hormone_receptor"
                    )

                transcript_id = random.choice(self.available_genes[gene_symbol])
                row = self._create_gene_row(
                    gene_symbol,
                    transcript_id,
                    fold_change,
                    cancer_type,
                    "hormone_receptor",
                )
                dataset_rows.append(row)
                processed_genes.add(gene_symbol)
                gene_categories["hormone_receptors"] += 1

        # 5. Add pathway-relevant genes and drug targets to reach target count
        remaining_needed = signature["target_genes"] - len(dataset_rows)
        if remaining_needed > 0:
            pathway_genes, drug_genes = self._select_additional_genes(
                signature, remaining_needed, processed_genes
            )

            for gene_symbol, transcript_id, fold_change, gene_type in (
                pathway_genes + drug_genes
            ):
                row = self._create_gene_row(
                    gene_symbol, transcript_id, fold_change, cancer_type, gene_type
                )
                dataset_rows.append(row)
                if gene_type == "pathway_gene":
                    gene_categories["pathway_genes"] += 1
                elif gene_type == "drug_target":
                    gene_categories["drug_targets"] += 1

        # Save dataset
        self._save_dataset(dataset_rows, output_path, cancer_type)

        # Generate statistics
        stats = {
            "cancer_type": cancer_type,
            "total_genes": len(dataset_rows),
            "gene_categories": gene_categories,
            "fold_change_range": {
                "min": min(row["cancer_fold"] for row in dataset_rows),
                "max": max(row["cancer_fold"] for row in dataset_rows),
                "mean": sum(row["cancer_fold"] for row in dataset_rows)
                / len(dataset_rows),
            },
            "upregulated_genes": len(
                [r for r in dataset_rows if r["cancer_fold"] > 1.5]
            ),
            "downregulated_genes": len(
                [r for r in dataset_rows if r["cancer_fold"] < 0.67]
            ),
            "output_path": str(output_path),
        }

        return stats

    def _calculate_cancer_specific_fold_change(
        self, gene_symbol: str, gene_info: Dict, signature: Dict, gene_type: str
    ) -> float:
        """Calculate cancer-specific fold change for a gene.

        Args:
            gene_symbol: Gene symbol
            gene_info: Base gene information
            signature: Cancer-specific signature
            gene_type: Type of gene (oncogene, tumor_suppressor, etc.)

        Returns:
            Calculated fold change value
        """
        base_fold = gene_info["base_fold"]
        base_range = gene_info["range"]

        # Apply cancer-specific multipliers
        if gene_type == "oncogene" and gene_symbol in signature.get(
            "oncogene_multipliers", {}
        ):
            multiplier = signature["oncogene_multipliers"][gene_symbol]
            base_fold *= multiplier
            base_range = (base_range[0] * multiplier, base_range[1] * multiplier)
        elif gene_type == "tumor_suppressor" and gene_symbol in signature.get(
            "suppressor_multipliers", {}
        ):
            multiplier = signature["suppressor_multipliers"][gene_symbol]
            base_fold *= multiplier
            base_range = (base_range[0] * multiplier, base_range[1] * multiplier)

        # Add biological noise
        fold_change = np.random.normal(base_fold, (base_range[1] - base_range[0]) / 6)
        fold_change = np.clip(fold_change, base_range[0], base_range[1])

        return round(fold_change, 3)

    def _select_additional_genes(
        self, signature: Dict, count_needed: int, processed_genes: Set[str]
    ) -> Tuple[List, List]:
        """Select additional pathway genes and drug targets.

        Args:
            signature: Cancer signature information
            count_needed: Number of additional genes needed
            processed_genes: Set of already processed genes

        Returns:
            Tuple of (pathway_genes, drug_genes) lists
        """
        pathway_genes = []
        drug_genes = []

        # Prioritize genes with pathways and drugs
        available_genes = set(self.available_genes.keys()) - processed_genes

        # Get genes with relevant pathways
        pathway_candidates = []
        for gene_symbol in available_genes:
            if gene_symbol in self.gene_pathways:
                # Prefer genes in cancer-relevant pathways
                gene_pathways = self.gene_pathways[gene_symbol]
                if any(
                    pathway in str(gene_pathways).lower()
                    for pathway in [
                        "cancer",
                        "tumor",
                        "cell_cycle",
                        "apoptosis",
                        "dna",
                        "repair",
                        "growth",
                        "proliferation",
                    ]
                ):
                    pathway_candidates.append(gene_symbol)

        # Get genes with drugs
        drug_candidates = [gene for gene in available_genes if gene in self.gene_drugs]

        # Mix pathway and drug genes
        pathway_count = min(count_needed // 2, len(pathway_candidates))
        drug_count = min(count_needed - pathway_count, len(drug_candidates))

        # Select pathway genes
        selected_pathway = (
            random.sample(pathway_candidates, pathway_count)
            if pathway_candidates
            else []
        )
        for gene_symbol in selected_pathway:
            transcript_id = random.choice(self.available_genes[gene_symbol])
            # Generate moderate expression changes for pathway genes
            fold_change = round(np.random.lognormal(0, 0.5), 3)  # Log-normal around 1.0
            fold_change = np.clip(fold_change, 0.3, 4.0)
            pathway_genes.append(
                (gene_symbol, transcript_id, fold_change, "pathway_gene")
            )

        # Select drug target genes
        selected_drugs = (
            random.sample(drug_candidates, drug_count) if drug_candidates else []
        )
        for gene_symbol in selected_drugs:
            transcript_id = random.choice(self.available_genes[gene_symbol])
            # Drug targets often show increased expression
            fold_change = round(np.random.uniform(1.2, 3.5), 3)
            drug_genes.append((gene_symbol, transcript_id, fold_change, "drug_target"))

        return pathway_genes, drug_genes

    def _create_gene_row(
        self,
        gene_symbol: str,
        transcript_id: str,
        fold_change: float,
        cancer_type: str,
        gene_category: str,
    ) -> Dict:
        """Create a row for the dataset.

        Args:
            gene_symbol: Gene symbol
            transcript_id: Transcript ID
            fold_change: Fold change value
            cancer_type: Cancer type
            gene_category: Category of gene

        Returns:
            Dictionary representing a dataset row
        """
        # Generate realistic p-values based on fold change
        if abs(np.log2(fold_change)) > 1.5:  # Strong changes
            p_value = np.random.uniform(0.000001, 0.001)
        elif abs(np.log2(fold_change)) > 1.0:  # Moderate changes
            p_value = np.random.uniform(0.001, 0.01)
        else:  # Weak changes
            p_value = np.random.uniform(0.01, 0.1)

        row = {
            "transcript_id": transcript_id,
            "cancer_fold": fold_change,
            "gene_symbol": gene_symbol,
            "p_value": round(p_value, 6),
            "tissue_type": "tumor",
            "gene_category": gene_category,
            "cancer_type": cancer_type,
        }

        # Add cancer-specific metadata
        if cancer_type == "breast_her2":
            row.update(
                {
                    "cancer_subtype": "HER2-positive",
                    "her2_status": "positive",
                    "ki67_status": "high",
                }
            )
        elif cancer_type == "breast_tnbc":
            row.update(
                {
                    "cancer_subtype": "triple-negative",
                    "er_status": "negative",
                    "pr_status": "negative",
                    "her2_status": "negative",
                }
            )
        elif cancer_type == "lung_egfr":
            row.update(
                {
                    "cancer_subtype": "adenocarcinoma",
                    "mutation_status": "EGFR_mutant",
                    "smoking_status": "never_smoker",
                }
            )
        elif cancer_type == "colorectal_msi":
            row.update(
                {
                    "cancer_subtype": "adenocarcinoma",
                    "msi_status": "MSI-high",
                    "tumor_location": "proximal_colon",
                }
            )
        elif cancer_type == "pancreatic_pdac":
            row.update(
                {
                    "cancer_subtype": "ductal_adenocarcinoma",
                    "kras_status": "G12D_mutant",
                    "ca19_9_level": "elevated",
                }
            )

        return row

    def _save_dataset(
        self, dataset_rows: List[Dict], output_path: Path, cancer_type: str
    ):
        """Save dataset to CSV file.

        Args:
            dataset_rows: List of dataset rows
            output_path: Output file path
            cancer_type: Cancer type for metadata
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Write CSV
        if dataset_rows:
            fieldnames = dataset_rows[0].keys()
            with open(output_path, "w", newline="") as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(dataset_rows)

        # Also create DESeq2 format version
        deseq2_path = output_path.parent / f"{output_path.stem}_deseq2.csv"
        deseq2_rows = []
        for row in dataset_rows:
            deseq2_row = {
                "symbol": row["gene_symbol"],
                "log2FoldChange": round(np.log2(row["cancer_fold"]), 3),
                "padj": row["p_value"],
                "baseMean": round(np.random.uniform(100, 5000), 2),
                "tissue_type": row["tissue_type"],
                "cancer_type": cancer_type,
            }
            deseq2_rows.append(deseq2_row)

        with open(deseq2_path, "w", newline="") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=deseq2_rows[0].keys())
            writer.writeheader()
            writer.writerows(deseq2_rows)

        console.print(f"[green]✓ Saved dataset: {output_path}[/green]")
        console.print(f"[green]✓ Saved DESeq2 format: {deseq2_path}[/green]")

    def generate_all_datasets(self, output_dir: Path) -> Dict:
        """Generate all cancer type datasets.

        Args:
            output_dir: Output directory for datasets

        Returns:
            Dictionary with all dataset statistics
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        all_stats = {}

        console.print("[bold blue]Generating all enhanced demo datasets...[/bold blue]")

        for cancer_type in self.CANCER_SIGNATURES.keys():
            filename = f"demo_{cancer_type}_enhanced.csv"
            output_path = output_dir / filename

            try:
                stats = self.generate_cancer_dataset(cancer_type, output_path)
                all_stats[cancer_type] = stats
                console.print(
                    f"[green]✓ Generated {cancer_type}: {stats['total_genes']} genes[/green]"
                )
            except Exception as e:
                logger.error(f"Failed to generate {cancer_type} dataset: {e}")
                console.print(f"[red]✗ Failed {cancer_type}: {e}[/red]")

        # Generate summary report
        self._generate_summary_report(all_stats, output_dir)

        return all_stats

    def _generate_summary_report(self, all_stats: Dict, output_dir: Path):
        """Generate a summary report of all datasets.

        Args:
            all_stats: Statistics for all datasets
            output_dir: Output directory
        """
        report_path = output_dir / "dataset_generation_report.json"

        report = {
            "generation_timestamp": datetime.now().isoformat(),
            "database_stats": self.stats,
            "dataset_stats": all_stats,
            "total_datasets": len(all_stats),
            "total_genes_generated": sum(
                stats["total_genes"] for stats in all_stats.values()
            ),
        }

        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)

        console.print(f"[blue]📊 Summary report saved: {report_path}[/blue]")

        # Display summary table
        table = Table(title="Generated Demo Datasets Summary")
        table.add_column("Cancer Type", style="cyan")
        table.add_column("Total Genes", style="green")
        table.add_column("Upregulated", style="red")
        table.add_column("Downregulated", style="blue")
        table.add_column("Fold Range", style="yellow")

        for cancer_type, stats in all_stats.items():
            fold_range = f"{stats['fold_change_range']['min']:.2f} - {stats['fold_change_range']['max']:.2f}"
            table.add_row(
                cancer_type.replace("_", " ").title(),
                str(stats["total_genes"]),
                str(stats["upregulated_genes"]),
                str(stats["downregulated_genes"]),
                fold_range,
            )

        console.print(table)


def main():
    """Main entry point for dataset generation."""
    parser = argparse.ArgumentParser(
        description="Generate enhanced demo patient datasets with realistic expression patterns",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--all", action="store_true", help="Generate all cancer type datasets"
    )

    parser.add_argument(
        "--cancer-type",
        choices=[
            "breast_her2",
            "breast_tnbc",
            "lung_egfr",
            "colorectal_msi",
            "pancreatic_pdac",
            "comprehensive",
        ],
        help="Generate specific cancer type dataset",
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("examples/enhanced"),
        help="Output directory for generated datasets",
    )

    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level",
    )

    args = parser.parse_args()

    if not args.all and not args.cancer_type:
        parser.error("Must specify either --all or --cancer-type")

    # Setup logging
    setup_logging(log_level=args.log_level)

    try:
        # Database configuration
        db_config = {
            "host": os.getenv("MB_POSTGRES_HOST", "localhost"),
            "port": int(os.getenv("MB_POSTGRES_PORT", 5435)),
            "dbname": os.getenv("MB_POSTGRES_NAME", "mbase"),
            "user": os.getenv("MB_POSTGRES_USER", "mbase_user"),
            "password": os.getenv("MB_POSTGRES_PASSWORD", "mbase_secret"),
        }

        # Initialize generator
        generator = DemoDatasetGenerator(db_config)
        generator.load_database_gene_info()

        if args.all:
            all_stats = generator.generate_all_datasets(args.output_dir)
            console.print(
                f"\n[bold green]✓ Generated {len(all_stats)} datasets with {sum(s['total_genes'] for s in all_stats.values())} total genes![/bold green]"
            )
        else:
            output_path = args.output_dir / f"demo_{args.cancer_type}_enhanced.csv"
            stats = generator.generate_cancer_dataset(args.cancer_type, output_path)
            console.print(
                f"\n[bold green]✓ Generated {args.cancer_type} dataset with {stats['total_genes']} genes![/bold green]"
            )

    except Exception as e:
        logger.error(f"Dataset generation failed: {e}")
        console.print(f"[bold red]✗ Error: {e}[/bold red]")
        sys.exit(1)


if __name__ == "__main__":
    main()
