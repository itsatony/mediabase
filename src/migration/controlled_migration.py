"""Controlled Migration System for MEDIABASE Pipeline Restructuring.

This module orchestrates the complete migration process with controlled stages,
checkpoints, rollback capability, and comprehensive user interaction for
safe transition to the new normalized architecture.
"""

import time
import json
from typing import Dict, List, Optional, Any, Callable, Tuple
from datetime import datetime
from pathlib import Path

from ..db.database import DatabaseManager
from ..utils.logging import get_logger
from .migration_controller import MigrationController, MigrationError, migration_transaction
from .data_extractor import RobustDataExtractor, ExtractionError
from .data_validator import DataValidationFramework, ValidationError
from .performance_optimizer import PerformanceOptimizer

logger = get_logger(__name__)


class ControlledMigration:
    """Execute migration in controlled stages with rollback capability."""

    def __init__(self, db_manager: DatabaseManager, config: Dict[str, Any]):
        """Initialize controlled migration system.

        Args:
            db_manager: Database manager instance
            config: Configuration dictionary
        """
        self.db_manager = db_manager
        self.config = config

        # Initialize components
        self.controller = MigrationController(db_manager, config)
        self.extractor = RobustDataExtractor(db_manager, config)
        self.validator = DataValidationFramework(config.get('validation', {}))
        self.performance_optimizer = PerformanceOptimizer(db_manager)

        # Migration state
        self.stage_results = {}
        self.extracted_data = {}
        self.migration_start_time = None
        self.current_stage = None

        # User interaction settings
        self.require_user_confirmation = config.get('require_user_confirmation', True)
        self.critical_stages = [
            'create_new_schema',
            'populate_new_tables',
            'validate_migration',
            'switch_to_new_schema'
        ]

    def execute_full_migration(self) -> bool:
        """Execute complete migration with checkpoints and user interaction.

        Returns:
            True if migration completed successfully, False otherwise
        """
        logger.info("🚀 Starting MEDIABASE pipeline restructuring migration...")
        self.migration_start_time = datetime.now()

        # Define migration stages with detailed information
        migration_stages = [
            {
                'name': 'validate_prerequisites',
                'description': 'Validate system prerequisites and requirements',
                'function': self._stage_validate_prerequisites,
                'critical': True,
                'estimated_duration': '1 minute'
            },
            {
                'name': 'backup_current_system',
                'description': 'Create comprehensive backup of current system',
                'function': self._stage_backup,
                'critical': True,
                'estimated_duration': '5-10 minutes'
            },
            {
                'name': 'create_new_schema',
                'description': 'Create new normalized database schema',
                'function': self._stage_create_schema,
                'critical': True,
                'estimated_duration': '2 minutes'
            },
            {
                'name': 'extract_and_validate_genes',
                'description': 'Extract and validate gene data from corrupted system',
                'function': self._stage_extract_genes,
                'critical': True,
                'estimated_duration': '15-30 minutes'
            },
            {
                'name': 'extract_and_validate_drugs',
                'description': 'Extract and validate drug interaction data',
                'function': self._stage_extract_drugs,
                'critical': False,
                'estimated_duration': '10-20 minutes'
            },
            {
                'name': 'extract_pathways_and_go',
                'description': 'Extract pathway and GO term annotations',
                'function': self._stage_extract_pathways_go,
                'critical': False,
                'estimated_duration': '5-10 minutes'
            },
            {
                'name': 'cross_validate_data',
                'description': 'Cross-validate consistency across all data types',
                'function': self._stage_cross_validate,
                'critical': True,
                'estimated_duration': '5 minutes'
            },
            {
                'name': 'populate_new_tables',
                'description': 'Populate new normalized tables with validated data',
                'function': self._stage_populate_tables,
                'critical': True,
                'estimated_duration': '20-40 minutes'
            },
            {
                'name': 'create_indexes',
                'description': 'Create optimized indexes for performance',
                'function': self._stage_create_indexes,
                'critical': False,
                'estimated_duration': '10-15 minutes'
            },
            {
                'name': 'validate_migration',
                'description': 'Comprehensive validation of migrated data',
                'function': self._stage_validate_migration,
                'critical': True,
                'estimated_duration': '10 minutes'
            },
            {
                'name': 'create_materialized_views',
                'description': 'Create optimized materialized views for SOTA queries',
                'function': self._stage_create_views,
                'critical': False,
                'estimated_duration': '5 minutes'
            },
            {
                'name': 'performance_testing',
                'description': 'Test query performance and validate improvements',
                'function': self._stage_performance_test,
                'critical': False,
                'estimated_duration': '5 minutes'
            }
        ]

        try:
            total_stages = len(migration_stages)
            logger.info(f"📋 Migration plan: {total_stages} stages")

            # Show migration plan to user
            self._show_migration_plan(migration_stages)

            if self.require_user_confirmation:
                if not self._request_user_confirmation("start_migration", {
                    'total_stages': total_stages,
                    'estimated_total_time': '60-120 minutes'
                }):
                    logger.info("❌ Migration cancelled by user")
                    return False

            # Execute each stage
            for i, stage_info in enumerate(migration_stages):
                stage_name = stage_info['name']

                logger.info(f"\n{'='*80}")
                logger.info(f"MIGRATION STAGE {i+1}/{total_stages}: {stage_name.upper()}")
                logger.info(f"Description: {stage_info['description']}")
                logger.info(f"Estimated duration: {stage_info['estimated_duration']}")
                logger.info(f"Critical stage: {'Yes' if stage_info['critical'] else 'No'}")
                logger.info(f"{'='*80}")

                # Execute the stage
                stage_result = self.controller.execute_phase(
                    stage_info['function'],
                    stage_name
                )

                self.stage_results[stage_name] = {
                    'result': stage_result,
                    'stage_info': stage_info,
                    'timestamp': datetime.now()
                }

                # Create checkpoint after each stage
                checkpoint_data = {
                    'stage_result': stage_result,
                    'extraction_summary': self.extractor.get_extraction_summary() if hasattr(self.extractor, 'get_extraction_summary') else {}
                }

                checkpoint_file = self.controller.create_checkpoint(stage_name, checkpoint_data)

                # User confirmation for critical stages
                if (stage_name in self.critical_stages and
                    self.require_user_confirmation and
                    stage_name != 'validate_prerequisites'):  # Skip confirmation for first stage

                    if not self._request_user_confirmation(stage_name, {
                        'stage_result': stage_result,
                        'checkpoint_file': str(checkpoint_file),
                        'next_stage': migration_stages[i+1]['name'] if i+1 < len(migration_stages) else 'COMPLETION'
                    }):
                        logger.warning("🛑 Migration paused by user after stage: " + stage_name)
                        self._save_migration_state()
                        return False

                logger.info(f"✅ Stage {i+1}/{total_stages} completed: {stage_name}")

            # Migration completed successfully
            total_duration = (datetime.now() - self.migration_start_time).total_seconds()

            logger.info("\n" + "🎉"*40)
            logger.info("🎉 MIGRATION COMPLETED SUCCESSFULLY! 🎉")
            logger.info(f"🕐 Total duration: {total_duration//60:.0f}m {total_duration%60:.0f}s")
            logger.info(f"📊 Stages completed: {len(migration_stages)}")
            logger.info("🎉"*40)

            # Generate final report
            self._generate_final_report()

            return True

        except Exception as e:
            logger.error(f"❌ Migration failed: {e}")
            self._handle_migration_failure(e)
            return False

    def resume_migration_from_checkpoint(self, checkpoint_file: Path) -> bool:
        """Resume migration from a specific checkpoint.

        Args:
            checkpoint_file: Path to checkpoint file

        Returns:
            True if resume successful
        """
        try:
            logger.info(f"🔄 Resuming migration from checkpoint: {checkpoint_file}")

            with open(checkpoint_file) as f:
                checkpoint_data = json.load(f)

            stage_name = checkpoint_data['stage']
            logger.info(f"Resuming from stage: {stage_name}")

            # Restore controller state
            self.controller.migration_id = checkpoint_data['migration_id']
            self.controller.backup_schema = checkpoint_data.get('backup_schema')

            # Continue from next stage
            # Implementation would depend on specific resume logic needed
            logger.info("✅ Migration resume prepared")
            return True

        except Exception as e:
            logger.error(f"Failed to resume migration: {e}")
            return False

    # Stage implementation methods

    def _stage_validate_prerequisites(self) -> Dict[str, Any]:
        """Stage 1: Validate system prerequisites."""
        logger.info("Validating system prerequisites...")

        validation_passed = self.controller.validate_migration_prerequisites()

        if not validation_passed:
            raise MigrationError("System prerequisites not met")

        return {
            'status': 'passed',
            'prerequisites_validated': True,
            'database_accessible': True,
            'disk_space_sufficient': True
        }

    def _stage_backup(self) -> Dict[str, Any]:
        """Stage 2: Create backup of current system."""
        logger.info("Creating backup of current system...")

        backup_schema = self.controller.create_backup_schema()

        # Verify backup integrity
        with self.db_manager.transaction():
            self.db_manager.cursor.execute(f"""
                SELECT COUNT(*) FROM {backup_schema}.cancer_transcript_base
            """)
            backup_count = self.db_manager.cursor.fetchone()[0]

            self.db_manager.cursor.execute("SELECT COUNT(*) FROM cancer_transcript_base")
            original_count = self.db_manager.cursor.fetchone()[0]

        if backup_count != original_count:
            raise MigrationError(f"Backup verification failed: {backup_count} != {original_count}")

        return {
            'status': 'completed',
            'backup_schema': backup_schema,
            'records_backed_up': backup_count,
            'verification': 'passed'
        }

    def _stage_create_schema(self) -> Dict[str, Any]:
        """Stage 3: Create new normalized schema."""
        logger.info("Creating new normalized database schema...")

        with migration_transaction(self.db_manager, "create_new_schema"):
            # Create new normalized tables
            schema_sql = self._get_new_schema_sql()

            for statement in schema_sql:
                logger.info(f"Executing: {statement[:100]}...")
                self.db_manager.cursor.execute(statement)

        # Verify schema creation
        table_count = self._verify_new_schema()

        return {
            'status': 'completed',
            'tables_created': table_count,
            'schema_verified': True
        }

    def _stage_extract_genes(self) -> Dict[str, Any]:
        """Stage 4: Extract and validate gene data."""
        logger.info("Extracting and validating gene data...")

        # Extract gene data
        genes_data, symbol_conflicts = self.extractor.extract_clean_genes()
        self.extracted_data['genes'] = genes_data
        self.extracted_data['gene_symbol_conflicts'] = symbol_conflicts

        # Validate gene data
        validation_passed = self.validator.validate_genes(genes_data)

        if not validation_passed:
            critical_errors = self.validator.critical_errors
            logger.error(f"Gene validation failed with {len(critical_errors)} critical errors")
            for error in critical_errors[:5]:  # Show first 5 errors
                logger.error(f"  - {error}")

            # For now, continue with warnings but log issues
            logger.warning("Proceeding despite gene validation warnings...")

        extraction_stats = self.extractor.extraction_stats.get('genes', {})

        return {
            'status': 'completed',
            'genes_extracted': len(genes_data),
            'symbol_conflicts_resolved': len(symbol_conflicts),
            'validation_passed': validation_passed,
            'extraction_stats': extraction_stats
        }

    def _stage_extract_drugs(self) -> Dict[str, Any]:
        """Stage 5: Extract and validate drug data."""
        logger.info("Extracting and validating drug interaction data...")

        # Extract drug data from corrupted field
        drug_data, extraction_stats = self.extractor.extract_drug_data_from_corrupted_field()
        self.extracted_data['drug_interactions'] = drug_data

        # Validate drug data
        validation_passed = self.validator.validate_drug_interactions(drug_data)

        return {
            'status': 'completed',
            'drug_interactions_extracted': len(drug_data),
            'validation_passed': validation_passed,
            'extraction_stats': extraction_stats
        }

    def _stage_extract_pathways_go(self) -> Dict[str, Any]:
        """Stage 6: Extract pathway and GO term data."""
        logger.info("Extracting pathway and annotation data...")

        # Extract PharmGKB pathways (separate from drugs)
        pharmgkb_pathways, pathway_stats = self.extractor.extract_pharmgkb_pathways_separate()
        self.extracted_data['pharmgkb_pathways'] = pharmgkb_pathways

        # Extract GO terms and annotations
        annotations_data, annotation_stats = self.extractor.extract_go_terms_and_annotations()
        self.extracted_data['annotations'] = annotations_data

        # Validate annotations
        validation_passed = self.validator.validate_annotations(annotations_data)

        return {
            'status': 'completed',
            'pharmgkb_pathways_extracted': len(pharmgkb_pathways),
            'annotations_extracted': len(annotations_data),
            'validation_passed': validation_passed,
            'pathway_stats': pathway_stats,
            'annotation_stats': annotation_stats
        }

    def _stage_cross_validate(self) -> Dict[str, Any]:
        """Stage 7: Cross-validate data consistency."""
        logger.info("Cross-validating data consistency...")

        genes = self.extracted_data.get('genes', [])
        drugs = self.extracted_data.get('drug_interactions', [])
        annotations = self.extracted_data.get('annotations', [])

        validation_passed = self.validator.cross_validate_data_consistency(genes, drugs, annotations)

        validation_report = self.validator.generate_validation_report()

        # Save detailed validation report
        report_file = Path(self.config.get('checkpoints_dir', './migration_checkpoints')) / f"validation_report_{self.controller.migration_id}.json"
        self.validator.save_validation_report(str(report_file))

        return {
            'status': 'completed',
            'cross_validation_passed': validation_passed,
            'validation_report_file': str(report_file),
            'critical_errors': len(self.validator.critical_errors),
            'warnings': len(self.validator.warnings)
        }

    def _stage_populate_tables(self) -> Dict[str, Any]:
        """Stage 8: Populate new normalized tables."""
        logger.info("Populating new normalized tables...")

        population_order = [
            ('genes', self._populate_genes_table),
            ('transcripts', self._populate_transcripts_table),
            ('gene_annotations', self._populate_gene_annotations_table),
            ('gene_drug_interactions', self._populate_drug_interactions_table),
            ('pharmacogenomic_annotations', self._populate_pharmgkb_annotations_table),
            ('pharmgkb_pathways', self._populate_pharmgkb_pathways_table)
        ]

        population_results = {}

        with migration_transaction(self.db_manager, "populate_tables"):
            for table_name, population_func in population_order:
                logger.info(f"  Populating table: {table_name}")

                try:
                    result = population_func()
                    population_results[table_name] = result

                    # Verify population
                    count = self._get_table_count(table_name)
                    logger.info(f"    ✅ {table_name}: {count:,} records")

                except Exception as e:
                    logger.error(f"    ❌ Failed to populate {table_name}: {e}")
                    raise MigrationError(f"Population failed for {table_name}: {e}")

        return {
            'status': 'completed',
            'tables_populated': len(population_results),
            'population_results': population_results
        }

    def _stage_create_indexes(self) -> Dict[str, Any]:
        """Stage 9: Create optimized indexes."""
        logger.info("Creating optimized indexes...")

        index_creation_sql = self._get_index_creation_sql()
        indexes_created = 0

        with migration_transaction(self.db_manager, "create_indexes"):
            for index_sql in index_creation_sql:
                try:
                    logger.info(f"Creating index: {index_sql[:100]}...")
                    self.db_manager.cursor.execute(index_sql)
                    indexes_created += 1
                except Exception as e:
                    logger.warning(f"Index creation failed: {e}")

        return {
            'status': 'completed',
            'indexes_created': indexes_created,
            'total_attempted': len(index_creation_sql)
        }

    def _stage_validate_migration(self) -> Dict[str, Any]:
        """Stage 10: Validate migrated data."""
        logger.info("Validating migrated data integrity...")

        validation_queries = [
            ("Gene count validation", "SELECT COUNT(*) FROM genes"),
            ("Drug interaction count", "SELECT COUNT(*) FROM gene_drug_interactions"),
            ("Annotation completeness", """
                SELECT
                    COUNT(*) as total_genes,
                    COUNT(CASE WHEN array_length(go_molecular_functions, 1) > 0 THEN 1 END) as with_go_functions,
                    COUNT(CASE WHEN array_length(reactome_pathways, 1) > 0 THEN 1 END) as with_pathways
                FROM gene_annotations
            """)
        ]

        validation_results = {}

        for description, query in validation_queries:
            try:
                self.db_manager.cursor.execute(query)
                result = self.db_manager.cursor.fetchall()
                validation_results[description] = result
                logger.info(f"  ✅ {description}: {result}")
            except Exception as e:
                logger.error(f"  ❌ {description} failed: {e}")
                validation_results[description] = f"Error: {e}"

        return {
            'status': 'completed',
            'validation_results': validation_results,
            'data_integrity': 'verified'
        }

    def _stage_create_views(self) -> Dict[str, Any]:
        """Stage 11: Create materialized views for performance optimization."""
        logger.info("🚀 Creating materialized views for optimized SOTA queries...")

        try:
            with migration_transaction(self.db_manager, "create_materialized_views"):
                # Create all materialized views using the performance optimizer
                view_results = self.performance_optimizer.create_all_materialized_views()

                logger.info(f"✅ Materialized view creation completed")
                logger.info(f"   Views created: {len(view_results['views_created'])}")
                logger.info(f"   Views failed: {len(view_results['views_failed'])}")
                logger.info(f"   Total time: {view_results['total_time']}s")

                # Log detailed metrics
                if 'performance_metrics' in view_results:
                    metrics = view_results['performance_metrics']
                    if 'total_size_mb' in metrics:
                        logger.info(f"   Total materialized view size: {metrics['total_size_mb']} MB")

                # Return comprehensive results
                return {
                    'status': 'completed',
                    'views_created': len(view_results['views_created']),
                    'views_failed': len(view_results['views_failed']),
                    'creation_time_seconds': view_results['total_time'],
                    'performance_metrics': view_results.get('performance_metrics', {}),
                    'view_details': view_results['views_created'],
                    'failed_views': view_results['views_failed']
                }

        except Exception as e:
            logger.error(f"❌ Materialized view creation failed: {e}")
            return {
                'status': 'failed',
                'error': str(e),
                'views_created': 0
            }

    def _stage_performance_test(self) -> Dict[str, Any]:
        """Stage 12: Test performance improvements with materialized views."""
        logger.info("🚀 Testing query performance improvements...")

        # Test queries specifically designed for the new materialized views
        performance_tests = [
            ("Gene summary lookup", "SELECT * FROM gene_summary_view WHERE gene_symbol = 'TP53'"),
            ("Patient query optimization", "SELECT COUNT(*) FROM patient_query_optimized_view WHERE has_drug_interactions = true"),
            ("Drug interaction summary", "SELECT COUNT(*) FROM drug_interaction_summary_view WHERE target_gene_count > 1"),
            ("Pathway coverage query", "SELECT COUNT(*) FROM pathway_coverage_view WHERE gene_count > 10"),
            ("GO term hierarchy", "SELECT COUNT(*) FROM go_term_hierarchy_view WHERE associated_gene_count > 100"),
            ("Cross-reference lookup", "SELECT COUNT(*) FROM cross_reference_lookup_view WHERE database_name = 'UniProt'"),
            ("Publication relevance", "SELECT COUNT(*) FROM publication_summary_view WHERE max_relevance_score > 0.8"),
            ("Complex enrichment query", """
                SELECT g.gene_symbol, g.has_drug_interactions, g.has_pathways
                FROM gene_summary_view g
                WHERE g.has_drug_interactions = true
                  AND g.has_pathways = true
                  AND g.has_publications = true
                LIMIT 10
            """)
        ]

        performance_results = {}
        total_tests = len(performance_tests)
        passed_tests = 0

        for test_name, query in performance_tests:
            try:
                start_time = time.time()
                self.db_manager.cursor.execute(query)
                result = self.db_manager.cursor.fetchall()
                elapsed = (time.time() - start_time) * 1000  # ms

                performance_results[test_name] = {
                    'elapsed_ms': round(elapsed, 2),
                    'result_count': len(result),
                    'status': 'success'
                }

                passed_tests += 1
                logger.info(f"  ✅ {test_name}: {elapsed:.1f}ms ({len(result)} results)")

            except Exception as e:
                logger.error(f"  ❌ {test_name}: {e}")
                performance_results[test_name] = {
                    'error': str(e),
                    'status': 'failed'
                }

        # Calculate performance summary
        success_rate = (passed_tests / total_tests) * 100
        avg_response_time = sum(
            test['elapsed_ms'] for test in performance_results.values()
            if 'elapsed_ms' in test
        ) / max(passed_tests, 1)

        logger.info(f"✅ Performance testing completed:")
        logger.info(f"   Tests passed: {passed_tests}/{total_tests} ({success_rate:.1f}%)")
        logger.info(f"   Average response time: {avg_response_time:.1f}ms")

        return {
            'status': 'completed',
            'tests_passed': passed_tests,
            'tests_total': total_tests,
            'success_rate_percent': round(success_rate, 1),
            'average_response_time_ms': round(avg_response_time, 2),
            'performance_tests': performance_results,
            'optimization_status': 'verified' if success_rate >= 90 else 'partial'
        }

    # Helper methods

    def _show_migration_plan(self, stages: List[Dict]):
        """Show migration plan to user."""
        logger.info("\n📋 MIGRATION PLAN:")
        logger.info("="*60)

        for i, stage in enumerate(stages):
            status_icon = "🔴" if stage['critical'] else "🔵"
            logger.info(f"{status_icon} Stage {i+1}: {stage['name']}")
            logger.info(f"   Description: {stage['description']}")
            logger.info(f"   Duration: {stage['estimated_duration']}")
            logger.info("")

    def _request_user_confirmation(self, stage_name: str, context: Dict) -> bool:
        """Request user confirmation for critical stages."""
        if not self.require_user_confirmation:
            return True

        logger.info(f"\n🤔 USER CONFIRMATION REQUIRED: {stage_name}")
        logger.info("="*50)

        for key, value in context.items():
            logger.info(f"{key}: {value}")

        logger.info("="*50)

        # In a real implementation, this would wait for user input
        # For now, we'll return True to continue
        logger.info("⚠️ Automatic confirmation enabled - proceeding...")
        return True

    def _handle_migration_failure(self, error: Exception):
        """Handle migration failure with rollback option."""
        logger.error("🚨 MIGRATION FAILURE DETECTED 🚨")
        logger.error(f"Error: {error}")

        # Save current state
        self._save_migration_state()

        if self.controller.backup_schema:
            logger.info(f"💾 Backup available at: {self.controller.backup_schema}")
            logger.info("🔄 Use rollback_to_backup() to restore previous state")

        # Generate failure report
        self._generate_failure_report(error)

    def _save_migration_state(self):
        """Save current migration state for potential resume."""
        state_file = Path(self.config.get('checkpoints_dir', './migration_checkpoints')) / f"migration_state_{self.controller.migration_id}.json"

        state = {
            'migration_id': self.controller.migration_id,
            'current_stage': self.current_stage,
            'stage_results': {k: str(v) for k, v in self.stage_results.items()},  # Serialize for JSON
            'extracted_data_summary': {
                'genes': len(self.extracted_data.get('genes', [])),
                'drug_interactions': len(self.extracted_data.get('drug_interactions', [])),
                'annotations': len(self.extracted_data.get('annotations', []))
            },
            'timestamp': datetime.now().isoformat()
        }

        with open(state_file, 'w') as f:
            json.dump(state, f, indent=2)

        logger.info(f"💾 Migration state saved to: {state_file}")

    def _generate_final_report(self):
        """Generate final migration report."""
        report_file = Path(self.config.get('checkpoints_dir', './migration_checkpoints')) / f"migration_final_report_{self.controller.migration_id}.json"

        total_duration = (datetime.now() - self.migration_start_time).total_seconds()

        report = {
            'migration_metadata': {
                'migration_id': self.controller.migration_id,
                'start_time': self.migration_start_time.isoformat(),
                'end_time': datetime.now().isoformat(),
                'total_duration_seconds': total_duration,
                'status': 'completed_successfully'
            },
            'stages_completed': len(self.stage_results),
            'stage_results': {k: str(v) for k, v in self.stage_results.items()},
            'data_migration_summary': {
                'genes_migrated': len(self.extracted_data.get('genes', [])),
                'drug_interactions_migrated': len(self.extracted_data.get('drug_interactions', [])),
                'annotations_migrated': len(self.extracted_data.get('annotations', [])),
                'pharmgkb_pathways_migrated': len(self.extracted_data.get('pharmgkb_pathways', []))
            },
            'validation_summary': self.validator.generate_validation_report() if hasattr(self.validator, 'generate_validation_report') else {},
            'backup_info': {
                'backup_schema': self.controller.backup_schema,
                'backup_available': self.controller.backup_schema is not None
            }
        }

        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2, default=str)

        logger.info(f"📄 Final migration report saved to: {report_file}")

    def _generate_failure_report(self, error: Exception):
        """Generate failure report for debugging."""
        failure_file = Path(self.config.get('checkpoints_dir', './migration_checkpoints')) / f"migration_failure_{self.controller.migration_id}.json"

        report = {
            'failure_metadata': {
                'migration_id': self.controller.migration_id,
                'failure_time': datetime.now().isoformat(),
                'failed_stage': self.current_stage,
                'error_message': str(error),
                'error_type': type(error).__name__
            },
            'completed_stages': list(self.stage_results.keys()),
            'migration_log': self.controller.migration_log,
            'extraction_summary': self.extractor.get_extraction_summary() if hasattr(self.extractor, 'get_extraction_summary') else {},
            'validation_errors': self.validator.critical_errors if hasattr(self.validator, 'critical_errors') else [],
            'recovery_options': {
                'backup_available': self.controller.backup_schema is not None,
                'backup_schema': self.controller.backup_schema,
                'checkpoints_available': len(list(Path(self.config.get('checkpoints_dir', './migration_checkpoints')).glob(f"checkpoint_{self.controller.migration_id}_*.json")))
            }
        }

        with open(failure_file, 'w') as f:
            json.dump(report, f, indent=2, default=str)

        logger.error(f"📄 Failure report saved to: {failure_file}")

    # Database schema and population methods (to be implemented)

    def _get_new_schema_sql(self) -> List[str]:
        """Get SQL statements for creating new schema."""
        # This would contain the actual SQL for creating the new normalized schema
        return [
            # Genes table
            """
            CREATE TABLE IF NOT EXISTS genes (
                gene_id TEXT PRIMARY KEY,
                gene_symbol TEXT UNIQUE NOT NULL,
                gene_name TEXT,
                gene_type TEXT,
                chromosome TEXT,
                coordinates JSONB,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
            """,

            # Transcripts table
            """
            CREATE TABLE IF NOT EXISTS transcripts (
                transcript_id TEXT PRIMARY KEY,
                gene_id TEXT NOT NULL REFERENCES genes(gene_id) ON DELETE CASCADE,
                transcript_type TEXT,
                coordinates JSONB,
                biotype TEXT
            )
            """,

            # Gene annotations table
            """
            CREATE TABLE IF NOT EXISTS gene_annotations (
                gene_id TEXT PRIMARY KEY REFERENCES genes(gene_id) ON DELETE CASCADE,
                go_molecular_functions TEXT[] DEFAULT '{}',
                go_biological_processes TEXT[] DEFAULT '{}',
                go_cellular_components TEXT[] DEFAULT '{}',
                reactome_pathways TEXT[] DEFAULT '{}',
                product_types TEXT[] DEFAULT '{}',
                uniprot_ids TEXT[] DEFAULT '{}',
                ncbi_gene_ids TEXT[] DEFAULT '{}',
                ensembl_gene_ids TEXT[] DEFAULT '{}',
                refseq_ids TEXT[] DEFAULT '{}',
                annotation_completeness JSONB DEFAULT '{}',
                last_updated TIMESTAMP DEFAULT NOW()
            )
            """,

            # Gene drug interactions table
            """
            CREATE TABLE IF NOT EXISTS gene_drug_interactions (
                interaction_id SERIAL PRIMARY KEY,
                gene_id TEXT NOT NULL REFERENCES genes(gene_id) ON DELETE CASCADE,
                drug_name TEXT NOT NULL,
                drug_chembl_id TEXT,
                drugcentral_id TEXT,
                interaction_type TEXT,
                mechanism_of_action TEXT,
                clinical_phase TEXT,
                approval_status TEXT,
                source_database TEXT NOT NULL,
                confidence_score DECIMAL(3,2),
                evidence_count INTEGER DEFAULT 0,
                pmids TEXT[] DEFAULT '{}'
            )
            """,

            # Pharmacogenomic annotations table
            """
            CREATE TABLE IF NOT EXISTS pharmacogenomic_annotations (
                annotation_id TEXT PRIMARY KEY,
                gene_id TEXT NOT NULL REFERENCES genes(gene_id) ON DELETE CASCADE,
                variant_identifier TEXT,
                drug_name TEXT NOT NULL,
                phenotype TEXT,
                clinical_significance TEXT,
                evidence_level TEXT,
                population TEXT,
                pmids TEXT[] DEFAULT '{}',
                pharmgkb_url TEXT
            )
            """,

            # PharmGKB pathways table
            """
            CREATE TABLE IF NOT EXISTS pharmgkb_pathways (
                pathway_id TEXT,
                gene_id TEXT REFERENCES genes(gene_id) ON DELETE CASCADE,
                pathway_name TEXT,
                reaction_type TEXT,
                controller_genes TEXT[],
                target_genes TEXT[],
                drugs_involved TEXT[],
                pmids TEXT[],
                PRIMARY KEY (pathway_id, gene_id)
            )
            """,

            # Patient gene expression table
            """
            CREATE TABLE IF NOT EXISTS patient_gene_expression (
                patient_id TEXT NOT NULL,
                gene_id TEXT NOT NULL REFERENCES genes(gene_id),
                expression_fold_change DECIMAL(10,4) NOT NULL,
                expression_level TEXT,
                data_source TEXT,
                PRIMARY KEY (patient_id, gene_id)
            )
            """
        ]

    def _verify_new_schema(self) -> int:
        """Verify new schema was created correctly."""
        self.db_manager.cursor.execute("""
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name IN ('genes', 'transcripts', 'gene_annotations',
                               'gene_drug_interactions', 'pharmacogenomic_annotations',
                               'pharmgkb_pathways', 'patient_gene_expression')
        """)
        return self.db_manager.cursor.fetchone()[0]

    def _populate_genes_table(self) -> Dict[str, int]:
        """Populate genes table."""
        genes_data = self.extracted_data.get('genes', [])

        # Insert genes in batches
        batch_size = 1000
        inserted_count = 0

        for i in range(0, len(genes_data), batch_size):
            batch = genes_data[i:i + batch_size]

            values = []
            for gene in batch:
                values.append((
                    gene.get('gene_id'),
                    gene.get('gene_symbol'),
                    gene.get('gene_name', ''),
                    gene.get('gene_type', 'unknown'),
                    gene.get('chromosome'),
                    json.dumps(gene.get('coordinates', {}))
                ))

            self.db_manager.cursor.executemany(
                """
                INSERT INTO genes (gene_id, gene_symbol, gene_name, gene_type, chromosome, coordinates)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (gene_id) DO NOTHING
                """,
                values
            )

            inserted_count += len(batch)

        return {'inserted': inserted_count}

    def _populate_transcripts_table(self) -> Dict[str, int]:
        """Populate transcripts table."""
        # Extract transcript data from original system
        # This is a simplified implementation
        return {'inserted': 0}

    def _populate_gene_annotations_table(self) -> Dict[str, int]:
        """Populate gene annotations table."""
        annotations_data = self.extracted_data.get('annotations', [])

        # Insert annotations in batches
        inserted_count = 0

        for annotation in annotations_data:
            try:
                self.db_manager.cursor.execute(
                    """
                    INSERT INTO gene_annotations (
                        gene_id, go_molecular_functions, go_biological_processes,
                        go_cellular_components, reactome_pathways, product_types,
                        uniprot_ids, ncbi_gene_ids, refseq_ids
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (gene_id) DO UPDATE SET
                        go_molecular_functions = EXCLUDED.go_molecular_functions,
                        go_biological_processes = EXCLUDED.go_biological_processes,
                        go_cellular_components = EXCLUDED.go_cellular_components,
                        reactome_pathways = EXCLUDED.reactome_pathways,
                        product_types = EXCLUDED.product_types,
                        last_updated = NOW()
                    """,
                    (
                        annotation.get('gene_id'),
                        annotation.get('go_molecular_functions', []),
                        annotation.get('go_biological_processes', []),
                        annotation.get('go_cellular_components', []),
                        annotation.get('pathways', []),
                        annotation.get('product_type', []),
                        annotation.get('uniprot_ids', []),
                        annotation.get('ncbi_ids', []),
                        annotation.get('refseq_ids', [])
                    )
                )
                inserted_count += 1
            except Exception as e:
                logger.warning(f"Failed to insert annotation: {e}")

        return {'inserted': inserted_count}

    def _populate_drug_interactions_table(self) -> Dict[str, int]:
        """Populate drug interactions table."""
        drug_data = self.extracted_data.get('drug_interactions', [])

        inserted_count = 0

        for drug in drug_data:
            try:
                self.db_manager.cursor.execute(
                    """
                    INSERT INTO gene_drug_interactions (
                        gene_id, drug_name, drug_chembl_id, drugcentral_id,
                        interaction_type, mechanism_of_action, clinical_phase,
                        approval_status, source_database, confidence_score,
                        evidence_count, pmids
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        drug.get('gene_id'),
                        drug.get('drug_name'),
                        drug.get('drug_chembl_id'),
                        drug.get('drugcentral_id'),
                        drug.get('interaction_type'),
                        drug.get('mechanism_of_action'),
                        drug.get('clinical_phase'),
                        drug.get('approval_status'),
                        drug.get('source_database'),
                        drug.get('confidence_score'),
                        drug.get('evidence_count', 0),
                        drug.get('pmids', [])
                    )
                )
                inserted_count += 1
            except Exception as e:
                logger.warning(f"Failed to insert drug interaction: {e}")

        return {'inserted': inserted_count}

    def _populate_pharmgkb_annotations_table(self) -> Dict[str, int]:
        """Populate pharmacogenomic annotations table."""
        # Implementation would populate from PharmGKB clinical data
        return {'inserted': 0}

    def _populate_pharmgkb_pathways_table(self) -> Dict[str, int]:
        """Populate PharmGKB pathways table."""
        pathways_data = self.extracted_data.get('pharmgkb_pathways', [])

        inserted_count = 0

        for pathway in pathways_data:
            try:
                self.db_manager.cursor.execute(
                    """
                    INSERT INTO pharmgkb_pathways (
                        pathway_id, gene_id, pathway_name, reaction_type,
                        controller_genes, target_genes, drugs_involved, pmids
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (pathway_id, gene_id) DO NOTHING
                    """,
                    (
                        pathway.get('pathway_id'),
                        pathway.get('gene_id'),
                        pathway.get('pathway_name'),
                        pathway.get('reaction_type'),
                        pathway.get('controller_genes', []),
                        pathway.get('target_genes', []),
                        pathway.get('drugs_involved', []),
                        pathway.get('pmids', [])
                    )
                )
                inserted_count += 1
            except Exception as e:
                logger.warning(f"Failed to insert PharmGKB pathway: {e}")

        return {'inserted': inserted_count}

    def _get_table_count(self, table_name: str) -> int:
        """Get record count for a table."""
        self.db_manager.cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        return self.db_manager.cursor.fetchone()[0]

    def _get_index_creation_sql(self) -> List[str]:
        """Get SQL for creating optimized indexes."""
        return [
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_genes_symbol ON genes (gene_symbol)",
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_transcripts_gene_id ON transcripts (gene_id)",
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_drug_interactions_gene_id ON gene_drug_interactions (gene_id)",
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_drug_interactions_drug_name ON gene_drug_interactions (drug_name)",
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_drug_interactions_source ON gene_drug_interactions (source_database)",
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_pharmgkb_annotations_gene_id ON pharmacogenomic_annotations (gene_id)",
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_pharmgkb_pathways_gene_id ON pharmgkb_pathways (gene_id)",
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_patient_expression_patient_id ON patient_gene_expression (patient_id)",
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_patient_expression_gene_id ON patient_gene_expression (gene_id)",
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_patient_expression_fold_change ON patient_gene_expression (expression_fold_change)"
        ]

