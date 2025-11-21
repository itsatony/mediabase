"""Performance benchmarks for v0.6.0 patient schema queries.

This script measures query performance for:
1. Single patient expression data access
2. Cross-patient query patterns
3. COALESCE baseline access patterns
4. Query optimization strategies

Usage:
    python scripts/benchmark_patient_queries.py
"""

import os
import sys
import time
import psycopg2
from typing import List, Dict, Tuple
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
import statistics

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

console = Console()


class PerformanceBenchmark:
    """Performance benchmark suite for patient schema queries."""

    def __init__(self):
        """Initialize database connection."""
        self.config = {
            "host": os.getenv("MB_POSTGRES_HOST", "localhost"),
            "port": int(os.getenv("MB_POSTGRES_PORT", "5435")),
            "dbname": "mbase",
            "user": os.getenv("MB_POSTGRES_USER", "mbase_user"),
            "password": os.getenv("MB_POSTGRES_PASSWORD", "mbase_secret"),
        }
        self.conn = psycopg2.connect(**self.config)
        self.results: List[Dict] = []

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()

    def get_patient_schemas(self) -> List[str]:
        """Get list of patient schemas in database.

        Returns:
            List of patient schema names
        """
        with self.conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT schema_name
                FROM information_schema.schemata
                WHERE schema_name LIKE 'patient_%'
                ORDER BY schema_name;
            """
            )
            return [row[0] for row in cursor.fetchall()]

    def execute_query_timed(
        self, query: str, params: tuple = None, runs: int = 5
    ) -> Tuple[float, float, int]:
        """Execute query multiple times and measure performance.

        Args:
            query: SQL query to execute
            params: Query parameters
            runs: Number of times to run query

        Returns:
            Tuple of (average_ms, median_ms, row_count)
        """
        timings = []
        row_count = 0

        for _ in range(runs):
            start = time.perf_counter()
            with self.conn.cursor() as cursor:
                if params:
                    cursor.execute(query, params)
                else:
                    cursor.execute(query)
                row_count = cursor.rowcount
            end = time.perf_counter()
            timings.append((end - start) * 1000)  # Convert to milliseconds

        avg_ms = statistics.mean(timings)
        median_ms = statistics.median(timings)

        return avg_ms, median_ms, row_count

    def benchmark_single_patient_baseline(self, schema_name: str):
        """Benchmark single patient baseline expression access.

        Tests: SELECT with COALESCE(expression_fold_change, 1.0)
        """
        console.print(
            f"\n[bold cyan]Benchmark 1:[/] Single Patient Baseline Expression ({schema_name})"
        )

        # Query: Get all overexpressed genes with COALESCE pattern
        query = f"""
            SELECT
                g.gene_symbol,
                g.gene_name,
                COALESCE(pe.expression_fold_change, 1.0) as fold_change
            FROM public.genes g
            INNER JOIN public.transcripts t ON g.gene_id = t.gene_id
            LEFT JOIN {schema_name}.expression_data pe ON t.transcript_id = pe.transcript_id
            WHERE COALESCE(pe.expression_fold_change, 1.0) > 2.0
            ORDER BY COALESCE(pe.expression_fold_change, 1.0) DESC
            LIMIT 100;
        """

        avg_ms, median_ms, row_count = self.execute_query_timed(query)

        self.results.append(
            {
                "benchmark": "Single Patient Baseline",
                "schema": schema_name,
                "query": "Overexpressed genes (>2.0x)",
                "avg_ms": avg_ms,
                "median_ms": median_ms,
                "rows": row_count,
            }
        )

        console.print(
            f"  Avg: {avg_ms:.2f}ms | Median: {median_ms:.2f}ms | Rows: {row_count}"
        )

    def benchmark_single_patient_sparse_storage(self, schema_name: str):
        """Benchmark single patient sparse storage access.

        Tests: Direct access to expression_data table (sparse storage)
        """
        console.print(
            f"\n[bold cyan]Benchmark 2:[/] Single Patient Sparse Storage ({schema_name})"
        )

        # Query: Get all patient-specific expression values (only non-baseline)
        query = f"""
            SELECT
                pe.transcript_id,
                pe.expression_fold_change
            FROM {schema_name}.expression_data pe
            WHERE pe.expression_fold_change != 1.0
            ORDER BY pe.expression_fold_change DESC
            LIMIT 1000;
        """

        avg_ms, median_ms, row_count = self.execute_query_timed(query)

        self.results.append(
            {
                "benchmark": "Sparse Storage Access",
                "schema": schema_name,
                "query": "All non-baseline values",
                "avg_ms": avg_ms,
                "median_ms": median_ms,
                "rows": row_count,
            }
        )

        console.print(
            f"  Avg: {avg_ms:.2f}ms | Median: {median_ms:.2f}ms | Rows: {row_count}"
        )

    def benchmark_cross_patient_comparison(self, schemas: List[str]):
        """Benchmark cross-patient comparison query.

        Tests: UNION query across multiple patient schemas
        """
        console.print(
            f"\n[bold cyan]Benchmark 3:[/] Cross-Patient Comparison (n={len(schemas)})"
        )

        if len(schemas) < 2:
            console.print("  [yellow]Skipped: Need at least 2 patient schemas[/]")
            return

        # Build UNION query for first 3 schemas
        union_queries = []
        for schema in schemas[:3]:
            union_queries.append(
                f"""
                SELECT
                    '{schema}' as patient_id,
                    g.gene_symbol,
                    COALESCE(pe.expression_fold_change, 1.0) as fold_change
                FROM public.genes g
                INNER JOIN public.transcripts t ON g.gene_id = t.gene_id
                LEFT JOIN {schema}.expression_data pe ON t.transcript_id = pe.transcript_id
                WHERE g.gene_symbol IN ('ERBB2', 'TP53', 'EGFR', 'BRCA1', 'PIK3CA')
            """
            )

        query = " UNION ALL ".join(union_queries) + " ORDER BY fold_change DESC;"

        avg_ms, median_ms, row_count = self.execute_query_timed(query, runs=3)

        self.results.append(
            {
                "benchmark": "Cross-Patient Comparison",
                "schema": f"{len(schemas[:3])} schemas",
                "query": "Compare 5 key genes",
                "avg_ms": avg_ms,
                "median_ms": median_ms,
                "rows": row_count,
            }
        )

        console.print(
            f"  Avg: {avg_ms:.2f}ms | Median: {median_ms:.2f}ms | Rows: {row_count}"
        )

    def benchmark_common_overexpression(self, schemas: List[str]):
        """Benchmark common overexpression analysis across patients.

        Tests: Complex query with multiple JOINs and aggregations
        """
        console.print(
            f"\n[bold cyan]Benchmark 4:[/] Common Overexpression Analysis (n={len(schemas)})"
        )

        if len(schemas) < 2:
            console.print("  [yellow]Skipped: Need at least 2 patient schemas[/]")
            return

        # Use first 3 schemas
        schemas_subset = schemas[:3]

        # Build query with CTEs for each patient
        cte_queries = []
        for i, schema in enumerate(schemas_subset):
            cte_queries.append(
                f"""
                p{i} AS (
                    SELECT
                        t.transcript_id,
                        COALESCE(pe.expression_fold_change, 1.0) as fold_change
                    FROM public.transcripts t
                    LEFT JOIN {schema}.expression_data pe ON t.transcript_id = pe.transcript_id
                    WHERE COALESCE(pe.expression_fold_change, 1.0) > 2.0
                )
            """
            )

        # Build intersection query
        join_conditions = []
        for i in range(1, len(schemas_subset)):
            join_conditions.append(
                f"INNER JOIN p{i} ON p0.transcript_id = p{i}.transcript_id"
            )

        query = f"""
            WITH {', '.join(cte_queries)}
            SELECT
                g.gene_symbol,
                g.gene_name,
                p0.fold_change as patient1_fc,
                p1.fold_change as patient2_fc
                {',' + 'p2.fold_change as patient3_fc' if len(schemas_subset) > 2 else ''}
            FROM p0
            {' '.join(join_conditions)}
            INNER JOIN public.transcripts t ON p0.transcript_id = t.transcript_id
            INNER JOIN public.genes g ON t.gene_id = g.gene_id
            ORDER BY p0.fold_change DESC
            LIMIT 50;
        """

        avg_ms, median_ms, row_count = self.execute_query_timed(query, runs=3)

        self.results.append(
            {
                "benchmark": "Common Overexpression",
                "schema": f"{len(schemas_subset)} schemas",
                "query": "Genes >2.0x in all patients",
                "avg_ms": avg_ms,
                "median_ms": median_ms,
                "rows": row_count,
            }
        )

        console.print(
            f"  Avg: {avg_ms:.2f}ms | Median: {median_ms:.2f}ms | Rows: {row_count}"
        )

    def benchmark_therapeutic_targeting(self, schema_name: str):
        """Benchmark therapeutic targeting query with multiple joins.

        Tests: Complex query joining expression data with drug information
        """
        console.print(
            f"\n[bold cyan]Benchmark 5:[/] Therapeutic Targeting Query ({schema_name})"
        )

        query = f"""
            SELECT
                g.gene_symbol,
                COALESCE(pe.expression_fold_change, 1.0) as fold_change,
                okd.molecule_name as drug_name,
                okd.mechanism_of_action,
                okd.clinical_phase_label
            FROM public.genes g
            INNER JOIN public.transcripts t ON g.gene_id = t.gene_id
            LEFT JOIN {schema_name}.expression_data pe ON t.transcript_id = pe.transcript_id
            LEFT JOIN public.opentargets_known_drugs okd ON g.gene_id = okd.target_gene_id
            WHERE COALESCE(pe.expression_fold_change, 1.0) > 2.0
              AND okd.is_approved = true
            ORDER BY COALESCE(pe.expression_fold_change, 1.0) DESC
            LIMIT 50;
        """

        avg_ms, median_ms, row_count = self.execute_query_timed(query, runs=3)

        self.results.append(
            {
                "benchmark": "Therapeutic Targeting",
                "schema": schema_name,
                "query": "Approved drugs for overexpressed genes",
                "avg_ms": avg_ms,
                "median_ms": median_ms,
                "rows": row_count,
            }
        )

        console.print(
            f"  Avg: {avg_ms:.2f}ms | Median: {median_ms:.2f}ms | Rows: {row_count}"
        )

    def benchmark_baseline_only_access(self):
        """Benchmark baseline expression access (public schema only).

        Tests: Query performance without patient-specific data
        """
        console.print(f"\n[bold cyan]Benchmark 6:[/] Baseline-Only Expression Access")

        query = """
            SELECT
                g.gene_symbol,
                g.gene_name,
                g.gene_type,
                COUNT(t.transcript_id) as transcript_count
            FROM public.genes g
            INNER JOIN public.transcripts t ON g.gene_id = t.gene_id
            WHERE g.gene_type = 'protein_coding'
            GROUP BY g.gene_id, g.gene_symbol, g.gene_name, g.gene_type
            ORDER BY transcript_count DESC
            LIMIT 100;
        """

        avg_ms, median_ms, row_count = self.execute_query_timed(query)

        self.results.append(
            {
                "benchmark": "Baseline-Only Access",
                "schema": "public",
                "query": "Protein-coding genes",
                "avg_ms": avg_ms,
                "median_ms": median_ms,
                "rows": row_count,
            }
        )

        console.print(
            f"  Avg: {avg_ms:.2f}ms | Median: {median_ms:.2f}ms | Rows: {row_count}"
        )

    def print_results_summary(self):
        """Print formatted results summary table."""
        console.print("\n")
        console.print(
            Panel.fit(
                "[bold]MEDIABASE v0.6.0 Performance Benchmark Results[/]",
                border_style="cyan",
            )
        )

        # Create results table
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Benchmark", style="cyan", width=25)
        table.add_column("Schema", style="yellow", width=20)
        table.add_column("Query", style="white", width=30)
        table.add_column("Avg (ms)", justify="right", style="green")
        table.add_column("Median (ms)", justify="right", style="blue")
        table.add_column("Rows", justify="right", style="white")

        for result in self.results:
            table.add_row(
                result["benchmark"],
                result["schema"],
                result["query"],
                f"{result['avg_ms']:.2f}",
                f"{result['median_ms']:.2f}",
                str(result["rows"]),
            )

        console.print(table)

        # Performance analysis
        console.print("\n[bold cyan]Performance Analysis:[/]")

        # Calculate statistics
        all_avg_times = [r["avg_ms"] for r in self.results]
        avg_query_time = statistics.mean(all_avg_times)
        fastest_query = min(self.results, key=lambda x: x["avg_ms"])
        slowest_query = max(self.results, key=lambda x: x["avg_ms"])

        console.print(f"  Average Query Time: {avg_query_time:.2f}ms")
        console.print(
            f"  Fastest: {fastest_query['benchmark']} ({fastest_query['avg_ms']:.2f}ms)"
        )
        console.print(
            f"  Slowest: {slowest_query['benchmark']} ({slowest_query['avg_ms']:.2f}ms)"
        )

        # Cross-patient query overhead
        single_patient_times = [
            r["avg_ms"] for r in self.results if "Single Patient" in r["benchmark"]
        ]
        cross_patient_times = [
            r["avg_ms"] for r in self.results if "Cross-Patient" in r["benchmark"]
        ]

        if single_patient_times and cross_patient_times:
            avg_single = statistics.mean(single_patient_times)
            avg_cross = statistics.mean(cross_patient_times)
            overhead_pct = ((avg_cross - avg_single) / avg_single) * 100
            console.print(
                f"\n  Cross-Patient Overhead: {overhead_pct:.1f}% slower than single patient"
            )

        # Storage efficiency metrics
        console.print("\n[bold cyan]Storage Efficiency:[/]")
        console.print("  Sparse storage: Only expression_fold_change != 1.0 stored")
        console.print(
            "  Baseline implicit: COALESCE(pe.expression_fold_change, 1.0) pattern"
        )
        console.print(
            "  Schema isolation: Each patient in separate schema within single DB"
        )

    def run_all_benchmarks(self):
        """Run all performance benchmarks."""
        console.print(
            "\n[bold]MEDIABASE v0.6.0 Patient Schema Performance Benchmarks[/]"
        )
        console.print("=" * 70)

        # Get available patient schemas
        schemas = self.get_patient_schemas()
        console.print(f"\nFound {len(schemas)} patient schemas: {', '.join(schemas)}")

        if not schemas:
            console.print("[red]Error: No patient schemas found in database[/]")
            return

        # Run benchmarks
        try:
            # Single patient benchmarks (first schema)
            self.benchmark_single_patient_baseline(schemas[0])
            self.benchmark_single_patient_sparse_storage(schemas[0])
            self.benchmark_therapeutic_targeting(schemas[0])

            # Baseline-only benchmark
            self.benchmark_baseline_only_access()

            # Cross-patient benchmarks (requires multiple schemas)
            if len(schemas) >= 2:
                self.benchmark_cross_patient_comparison(schemas)
                self.benchmark_common_overexpression(schemas)

            # Print summary
            self.print_results_summary()

        except Exception as e:
            console.print(f"\n[red]Error during benchmarking: {e}[/]")
            import traceback

            traceback.print_exc()


def main():
    """Main benchmark execution."""
    benchmark = PerformanceBenchmark()
    try:
        benchmark.run_all_benchmarks()
    finally:
        benchmark.close()


if __name__ == "__main__":
    main()
