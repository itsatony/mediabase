#!/usr/bin/env python3
"""
Download and process TCGA-BRCA patient data from UCSC Xena.

Creates MEDIABASE-compatible CSV files for 3 breast cancer subtypes:
- HER2+ (ERBB2 amplification)
- TNBC (Triple-Negative: ER-, PR-, HER2-)
- ER+ (Hormone receptor positive)

Data Source: UCSC Xena TCGA Breast Cancer (BRCA)
URL: https://xenabrowser.net/datapages/?cohort=TCGA%20Breast%20Cancer%20(BRCA)
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import requests
import pandas as pd
import numpy as np
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

console = Console()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class TCGABreastCancerDownloader:
    """Download and process TCGA-BRCA data from UCSC Xena."""

    # UCSC Xena API endpoints
    XENA_HUB = "https://tcga.xenahubs.net"

    # Expected gene signatures for validation
    EXPECTED_SIGNATURES = {
        'HER2+': {
            'ERBB2': (4.0, 10.0),   # 4-10x overexpression
            'GRB7': (3.0, 8.0),     # Co-amplified with ERBB2
            'PGAP3': (2.0, 6.0),    # Amplicon region
        },
        'TNBC': {
            'TP53': (0.0, 0.3),     # Tumor suppressor loss
            'KRT5': (5.0, 15.0),    # Basal marker
            'KRT14': (5.0, 15.0),   # Basal marker
            'EGFR': (2.0, 5.0),     # Common in TNBC
        },
        'ER+': {
            'ESR1': (8.0, 18.0),    # Estrogen receptor
            'PGR': (4.0, 12.0),     # Progesterone receptor
            'GATA3': (3.0, 9.0),    # Luminal marker
            'FOXA1': (3.0, 8.0),    # Luminal marker
        }
    }

    def __init__(self, cache_dir: Path, output_dir: Path):
        """Initialize downloader with cache and output directories."""
        self.cache_dir = cache_dir
        self.output_dir = output_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def download_xena_dataset(self, dataset: str, output_file: Path) -> Path:
        """
        Download dataset from UCSC Xena.

        Args:
            dataset: Dataset identifier (e.g., 'TCGA.BRCA.sampleMap/HiSeqV2')
            output_file: Path to save downloaded file

        Returns:
            Path to downloaded file
        """
        if output_file.exists():
            logger.info(f"Using cached file: {output_file}")
            return output_file

        url = f"{self.XENA_HUB}/download/{dataset}"
        logger.info(f"Downloading {dataset} from UCSC Xena...")

        try:
            response = requests.get(url, stream=True)
            response.raise_for_status()

            total_size = int(response.headers.get('content-length', 0))

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                console=console
            ) as progress:
                task = progress.add_task(f"Downloading {dataset}", total=total_size)

                with open(output_file, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                        progress.update(task, advance=len(chunk))

            logger.info(f"Downloaded to: {output_file}")
            return output_file

        except Exception as e:
            logger.error(f"Failed to download {dataset}: {e}")
            raise

    def load_gene_expression_data(self, expression_file: Path) -> pd.DataFrame:
        """
        Load gene expression data from downloaded file.

        Expected format: TSV with genes as rows, samples as columns
        First column: gene symbols

        Returns:
            DataFrame with gene symbols as index, samples as columns
        """
        logger.info(f"Loading expression data from {expression_file}")

        # TCGA Xena files are typically gzipped TSV
        if expression_file.suffix == '.gz':
            df = pd.read_csv(expression_file, sep='\t', index_col=0, compression='gzip')
        else:
            df = pd.read_csv(expression_file, sep='\t', index_col=0)

        logger.info(f"Loaded expression data: {df.shape[0]} genes, {df.shape[1]} samples")
        return df

    def load_clinical_data(self, clinical_file: Path) -> pd.DataFrame:
        """
        Load clinical annotations (subtype classifications).

        Returns:
            DataFrame with sample IDs as index, clinical annotations as columns
        """
        logger.info(f"Loading clinical data from {clinical_file}")

        if clinical_file.suffix == '.gz':
            df = pd.read_csv(clinical_file, sep='\t', compression='gzip')
        else:
            df = pd.read_csv(clinical_file, sep='\t')

        logger.info(f"Loaded clinical data: {df.shape[0]} samples")
        return df

    def select_representative_sample(
        self,
        expression_df: pd.DataFrame,
        sample_ids: List[str],
        subtype: str
    ) -> Tuple[str, pd.Series]:
        """
        Select most representative sample for given subtype.

        Criteria:
        - HER2+: Highest ERBB2 expression
        - TNBC: Lowest TP53, highest KRT5/14
        - ER+: Highest ESR1 expression

        Args:
            expression_df: Gene expression DataFrame
            sample_ids: List of candidate sample IDs
            subtype: Cancer subtype ('HER2+', 'TNBC', 'ER+')

        Returns:
            Tuple of (selected_sample_id, expression_series)
        """
        # Filter to available samples
        available_samples = [s for s in sample_ids if s in expression_df.columns]

        if not available_samples:
            raise ValueError(f"No samples available for subtype {subtype}")

        logger.info(f"Selecting representative {subtype} sample from {len(available_samples)} candidates")

        # Selection criteria by subtype
        if subtype == 'HER2+':
            # Select sample with highest ERBB2 expression
            if 'ERBB2' not in expression_df.index:
                raise ValueError("ERBB2 gene not found in expression data")
            erbb2_values = expression_df.loc['ERBB2', available_samples]
            selected_sample = erbb2_values.idxmax()

        elif subtype == 'TNBC':
            # Select sample with lowest TP53 and high basal markers
            scores = pd.Series(0.0, index=available_samples)

            if 'TP53' in expression_df.index:
                scores -= expression_df.loc['TP53', available_samples]  # Lower TP53 is better

            if 'KRT5' in expression_df.index:
                scores += expression_df.loc['KRT5', available_samples]

            if 'KRT14' in expression_df.index:
                scores += expression_df.loc['KRT14', available_samples]

            selected_sample = scores.idxmax()

        elif subtype == 'ER+':
            # Select sample with highest ESR1 expression
            if 'ESR1' not in expression_df.index:
                raise ValueError("ESR1 gene not found in expression data")
            esr1_values = expression_df.loc['ESR1', available_samples]
            selected_sample = esr1_values.idxmax()

        else:
            raise ValueError(f"Unknown subtype: {subtype}")

        logger.info(f"Selected sample: {selected_sample}")
        return selected_sample, expression_df[selected_sample]

    def convert_to_fold_change(
        self,
        expression_series: pd.Series,
        method: str = 'zscore_to_fold'
    ) -> pd.Series:
        """
        Convert expression values to fold-change format.

        TCGA Xena typically provides log2(FPKM+1) or z-scores.
        We need linear fold-change values for MEDIABASE.

        Args:
            expression_series: Gene expression values
            method: Conversion method ('zscore_to_fold', 'log2_to_fold')

        Returns:
            Series with fold-change values
        """
        logger.info(f"Converting expression values to fold-change using {method}")

        if method == 'zscore_to_fold':
            # Z-score to fold-change approximation
            # z-score = (x - mean) / std
            # Approximate: FC = 2^(z-score)
            fold_change = 2 ** expression_series

        elif method == 'log2_to_fold':
            # Direct log2 to linear conversion
            fold_change = 2 ** expression_series

        else:
            raise ValueError(f"Unknown conversion method: {method}")

        # Clip extreme values to reasonable range
        fold_change = fold_change.clip(lower=0.01, upper=100.0)

        logger.info(f"Fold-change range: {fold_change.min():.2f} - {fold_change.max():.2f}")
        return fold_change

    def validate_gene_signature(
        self,
        fold_change_df: pd.DataFrame,
        subtype: str
    ) -> Dict[str, bool]:
        """
        Validate that key genes match expected signature for subtype.

        Args:
            fold_change_df: DataFrame with gene_symbol and fold_change columns
            subtype: Cancer subtype to validate

        Returns:
            Dict mapping gene symbols to validation status
        """
        expected_genes = self.EXPECTED_SIGNATURES.get(subtype, {})
        validation_results = {}

        logger.info(f"Validating {subtype} gene signature...")

        for gene, (min_fc, max_fc) in expected_genes.items():
            gene_data = fold_change_df[fold_change_df['gene_symbol'] == gene]

            if gene_data.empty:
                logger.warning(f"  {gene}: NOT FOUND in expression data")
                validation_results[gene] = False
                continue

            fold_change = gene_data['fold_change'].iloc[0]

            if min_fc <= fold_change <= max_fc:
                logger.info(f"  {gene}: {fold_change:.2f}x ✓ (expected {min_fc}-{max_fc}x)")
                validation_results[gene] = True
            else:
                logger.warning(f"  {gene}: {fold_change:.2f}x ✗ (expected {min_fc}-{max_fc}x)")
                validation_results[gene] = False

        passed = sum(validation_results.values())
        total = len(validation_results)
        logger.info(f"Validation: {passed}/{total} key genes match expected signature")

        return validation_results

    def export_to_mediabase_csv(
        self,
        expression_series: pd.Series,
        gene_mapping: Dict[str, str],
        output_file: Path,
        subtype: str
    ) -> pd.DataFrame:
        """
        Export expression data to MEDIABASE CSV format.

        MEDIABASE CSV format:
        - gene_symbol: Official gene symbol (e.g., 'ERBB2')
        - fold_change: Linear fold-change value

        Args:
            expression_series: Gene expression values (gene symbols as index)
            gene_mapping: Mapping from gene symbols to Ensembl gene IDs (optional)
            output_file: Path to output CSV file
            subtype: Cancer subtype for validation

        Returns:
            DataFrame with exported data
        """
        logger.info(f"Exporting to MEDIABASE CSV format: {output_file}")

        # Convert to fold-change
        fold_change_series = self.convert_to_fold_change(expression_series)

        # Create DataFrame
        df = pd.DataFrame({
            'gene_symbol': fold_change_series.index,
            'fold_change': fold_change_series.values
        })

        # Filter to non-baseline values (sparse storage optimization)
        # Keep genes with fold-change != 1.0 (with tolerance)
        df = df[np.abs(df['fold_change'] - 1.0) > 0.05]

        logger.info(f"Sparse storage: {len(df)} genes with non-baseline expression (out of {len(expression_series)})")

        # Validate gene signature
        validation_results = self.validate_gene_signature(df, subtype)

        # Sort by fold-change (overexpressed first, then underexpressed)
        df = df.sort_values('fold_change', ascending=False)

        # Export to CSV
        df.to_csv(output_file, index=False)
        logger.info(f"Exported {len(df)} genes to {output_file}")

        # Print top overexpressed genes
        console.print(f"\n[bold]Top 10 Overexpressed Genes ({subtype}):[/bold]")
        for _, row in df.head(10).iterrows():
            console.print(f"  {row['gene_symbol']}: {row['fold_change']:.2f}x")

        return df


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Download and process TCGA-BRCA patient data from UCSC Xena",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Download all 3 subtypes
  python download_tcga_breast_cancer_data.py

  # Download specific subtype only
  python download_tcga_breast_cancer_data.py --subtypes HER2+

  # Use custom cache directory
  python download_tcga_breast_cancer_data.py --cache-dir /data/tcga_cache
"""
    )

    parser.add_argument(
        '--cache-dir',
        type=Path,
        default=Path('/tmp/mediabase/cache/tcga_brca'),
        help='Directory for caching downloaded files'
    )

    parser.add_argument(
        '--output-dir',
        type=Path,
        default=Path('examples/tcga_patients'),
        help='Directory for output CSV files'
    )

    parser.add_argument(
        '--subtypes',
        nargs='+',
        choices=['HER2+', 'TNBC', 'ER+'],
        default=['HER2+', 'TNBC', 'ER+'],
        help='Breast cancer subtypes to download'
    )

    parser.add_argument(
        '--skip-validation',
        action='store_true',
        help='Skip gene signature validation'
    )

    args = parser.parse_args()

    console.print("[bold green]TCGA-BRCA Patient Data Downloader[/bold green]")
    console.print(f"Cache: {args.cache_dir}")
    console.print(f"Output: {args.output_dir}")
    console.print(f"Subtypes: {', '.join(args.subtypes)}\n")

    downloader = TCGABreastCancerDownloader(args.cache_dir, args.output_dir)

    # NOTE: This is a template implementation.
    # The actual UCSC Xena datasets and API endpoints need to be verified.
    # For now, this will print instructions for manual download.

    console.print("[yellow]⚠️  IMPORTANT: Manual Download Required[/yellow]\n")
    console.print("UCSC Xena requires manual dataset selection via their web interface.")
    console.print("Please follow these steps:\n")

    console.print("[bold]1. Visit UCSC Xena Browser:[/bold]")
    console.print("   https://xenabrowser.net/datapages/?cohort=TCGA%20Breast%20Cancer%20(BRCA)\n")

    console.print("[bold]2. Download these datasets:[/bold]")
    console.print("   • Gene Expression: 'TCGA-BRCA.htseq_fpkm.tsv.gz'")
    console.print("   • Clinical Subtype: 'TCGA-BRCA.GDC_phenotype.tsv.gz'\n")

    console.print("[bold]3. Save files to cache directory:[/bold]")
    console.print(f"   {args.cache_dir}/\n")

    console.print("[bold]4. Re-run this script to process the data[/bold]\n")

    # Check if files already exist
    expression_file = args.cache_dir / 'TCGA-BRCA.htseq_fpkm.tsv.gz'
    clinical_file = args.cache_dir / 'TCGA-BRCA.GDC_phenotype.tsv.gz'

    if expression_file.exists() and clinical_file.exists():
        console.print("[green]✓ Found downloaded files, processing...[/green]\n")

        try:
            # Load data
            expression_df = downloader.load_gene_expression_data(expression_file)
            clinical_df = downloader.load_clinical_data(clinical_file)

            # Process each subtype
            for subtype in args.subtypes:
                console.print(f"\n[bold]Processing {subtype} subtype...[/bold]")

                # Define subtype filters (these column names need verification)
                subtype_filters = {
                    'HER2+': lambda df: df['paper_BRCA_Subtype_PAM50'] == 'Her2',
                    'TNBC': lambda df: df['paper_BRCA_Subtype_PAM50'] == 'Basal',
                    'ER+': lambda df: df['paper_BRCA_Subtype_PAM50'].isin(['LumA', 'LumB'])
                }

                # Filter samples by subtype
                subtype_filter = subtype_filters[subtype]
                subtype_samples = clinical_df[subtype_filter(clinical_df)]['sampleID'].tolist()

                if not subtype_samples:
                    logger.warning(f"No samples found for {subtype}, skipping...")
                    continue

                # Select representative sample
                sample_id, expression_series = downloader.select_representative_sample(
                    expression_df,
                    subtype_samples,
                    subtype
                )

                # Export to MEDIABASE CSV
                output_file = args.output_dir / f'tcga_patient_{subtype.lower().replace("+", "plus")}.csv'
                downloader.export_to_mediabase_csv(
                    expression_series,
                    {},  # No gene mapping needed (already gene symbols)
                    output_file,
                    subtype
                )

                console.print(f"[green]✓ Exported {subtype} patient data to {output_file}[/green]")

        except Exception as e:
            logger.error(f"Processing failed: {e}")
            console.print(f"[red]Error: {e}[/red]")
            return 1

    else:
        console.print("[yellow]Files not found. Please download manually as instructed above.[/yellow]")
        return 1

    console.print("\n[bold green]✓ TCGA-BRCA data processing complete![/bold green]")
    return 0


if __name__ == '__main__':
    sys.exit(main())
