"""Migration Monitoring and Logging Dashboard for MEDIABASE.

This module provides real-time monitoring, progress tracking, and comprehensive
logging capabilities for the migration process with visual dashboards and
detailed analytics.
"""

import json
import time
import threading
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass, asdict
from collections import defaultdict, deque
import sqlite3

from ..utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class MigrationMetrics:
    """Migration performance and progress metrics."""

    stage_name: str
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_seconds: float = 0.0
    records_processed: int = 0
    records_failed: int = 0
    memory_usage_mb: float = 0.0
    cpu_usage_percent: float = 0.0
    status: str = "running"  # running, completed, failed
    error_count: int = 0
    warnings_count: int = 0


@dataclass
class SystemHealth:
    """System health metrics during migration."""

    timestamp: datetime
    memory_usage_mb: float
    memory_available_mb: float
    cpu_usage_percent: float
    disk_usage_percent: float
    database_connections: int
    active_queries: int
    query_response_time_ms: float


class MigrationMonitor:
    """Real-time monitoring system for migration progress and health."""

    def __init__(self, config: Dict[str, Any]):
        """Initialize migration monitor.

        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.monitoring_db_path = (
            Path(config.get("log_dir", "./migration_logs")) / "migration_monitor.db"
        )
        self.monitoring_db_path.parent.mkdir(parents=True, exist_ok=True)

        # Initialize monitoring database
        self._init_monitoring_db()

        # Monitoring state
        self.is_monitoring = False
        self.monitor_thread = None
        self.current_stage = None
        self.migration_start_time = None

        # Metrics storage
        self.stage_metrics: Dict[str, MigrationMetrics] = {}
        self.health_history: deque = deque(maxlen=1000)  # Last 1000 health checks
        self.event_log: deque = deque(maxlen=10000)  # Last 10000 events

        # Performance thresholds
        self.performance_thresholds = {
            "memory_warning_mb": config.get("memory_warning_mb", 1536),
            "memory_critical_mb": config.get("memory_critical_mb", 2048),
            "cpu_warning_percent": config.get("cpu_warning_percent", 80),
            "cpu_critical_percent": config.get("cpu_critical_percent", 95),
            "disk_warning_percent": config.get("disk_warning_percent", 85),
            "disk_critical_percent": config.get("disk_critical_percent", 95),
            "query_timeout_ms": config.get("query_timeout_ms", 5000),
        }

        # Callbacks for alerts
        self.alert_callbacks: List[Callable] = []

    def _init_monitoring_db(self) -> None:
        """Initialize SQLite database for monitoring data persistence."""
        try:
            with sqlite3.connect(str(self.monitoring_db_path)) as conn:
                cursor = conn.cursor()

                # Create tables for persistent monitoring data
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS migration_sessions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        migration_id TEXT UNIQUE,
                        start_time TIMESTAMP,
                        end_time TIMESTAMP,
                        total_duration_seconds REAL,
                        total_stages INTEGER,
                        completed_stages INTEGER,
                        failed_stages INTEGER,
                        status TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """
                )

                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS stage_metrics (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        migration_id TEXT,
                        stage_name TEXT,
                        start_time TIMESTAMP,
                        end_time TIMESTAMP,
                        duration_seconds REAL,
                        records_processed INTEGER,
                        records_failed INTEGER,
                        memory_usage_mb REAL,
                        cpu_usage_percent REAL,
                        status TEXT,
                        error_count INTEGER,
                        warnings_count INTEGER,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (migration_id) REFERENCES migration_sessions (migration_id)
                    )
                """
                )

                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS system_health (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        migration_id TEXT,
                        timestamp TIMESTAMP,
                        memory_usage_mb REAL,
                        memory_available_mb REAL,
                        cpu_usage_percent REAL,
                        disk_usage_percent REAL,
                        database_connections INTEGER,
                        active_queries INTEGER,
                        query_response_time_ms REAL,
                        FOREIGN KEY (migration_id) REFERENCES migration_sessions (migration_id)
                    )
                """
                )

                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS migration_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        migration_id TEXT,
                        timestamp TIMESTAMP,
                        event_type TEXT,
                        stage_name TEXT,
                        severity TEXT,
                        message TEXT,
                        details TEXT,
                        FOREIGN KEY (migration_id) REFERENCES migration_sessions (migration_id)
                    )
                """
                )

                # Create indexes for performance
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS idx_migration_id ON stage_metrics (migration_id)"
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS idx_health_timestamp ON system_health (timestamp)"
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS idx_events_timestamp ON migration_events (timestamp)"
                )

                conn.commit()
                logger.info("✅ Monitoring database initialized")

        except Exception as e:
            logger.error(f"Failed to initialize monitoring database: {e}")
            raise

    def start_migration_session(self, migration_id: str, total_stages: int) -> None:
        """Start monitoring a new migration session.

        Args:
            migration_id: Unique migration identifier
            total_stages: Total number of migration stages
        """
        try:
            self.migration_id = migration_id
            self.migration_start_time = datetime.now()
            self.is_monitoring = True

            # Record session start in database
            with sqlite3.connect(str(self.monitoring_db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO migration_sessions
                    (migration_id, start_time, total_stages, completed_stages, failed_stages, status)
                    VALUES (?, ?, ?, 0, 0, 'running')
                """,
                    (migration_id, self.migration_start_time, total_stages),
                )
                conn.commit()

            # Start monitoring thread
            self.monitor_thread = threading.Thread(
                target=self._monitoring_loop, daemon=True
            )
            self.monitor_thread.start()

            self._log_event(
                "session_start",
                None,
                "info",
                f"Started migration session: {migration_id}",
            )
            logger.info(f"📊 Started monitoring migration session: {migration_id}")

        except Exception as e:
            logger.error(f"Failed to start monitoring session: {e}")
            raise

    def start_stage(self, stage_name: str) -> None:
        """Start monitoring a migration stage.

        Args:
            stage_name: Name of the migration stage
        """
        try:
            self.current_stage = stage_name

            # Initialize stage metrics
            self.stage_metrics[stage_name] = MigrationMetrics(
                stage_name=stage_name, start_time=datetime.now(), status="running"
            )

            self._log_event(
                "stage_start", stage_name, "info", f"Started stage: {stage_name}"
            )
            logger.info(f"🔄 Started monitoring stage: {stage_name}")

        except Exception as e:
            logger.error(f"Failed to start stage monitoring: {e}")

    def complete_stage(
        self,
        stage_name: str,
        records_processed: int = 0,
        records_failed: int = 0,
        error_count: int = 0,
        warnings_count: int = 0,
    ) -> None:
        """Complete monitoring for a migration stage.

        Args:
            stage_name: Name of the migration stage
            records_processed: Number of records processed
            records_failed: Number of records that failed
            error_count: Number of errors encountered
            warnings_count: Number of warnings encountered
        """
        try:
            if stage_name in self.stage_metrics:
                metrics = self.stage_metrics[stage_name]
                metrics.end_time = datetime.now()
                metrics.duration_seconds = (
                    metrics.end_time - metrics.start_time
                ).total_seconds()
                metrics.records_processed = records_processed
                metrics.records_failed = records_failed
                metrics.error_count = error_count
                metrics.warnings_count = warnings_count
                metrics.status = "failed" if error_count > 0 else "completed"

                # Get current system metrics
                health = self._get_current_health()
                if health:
                    metrics.memory_usage_mb = health.memory_usage_mb
                    metrics.cpu_usage_percent = health.cpu_usage_percent

                # Save to database
                self._save_stage_metrics(metrics)

                self._log_event(
                    "stage_complete",
                    stage_name,
                    "info" if metrics.status == "completed" else "error",
                    f"Completed stage: {stage_name} ({metrics.duration_seconds:.1f}s)",
                )

                logger.info(
                    f"✅ Stage completed: {stage_name} ({metrics.duration_seconds:.1f}s)"
                )

                if self.current_stage == stage_name:
                    self.current_stage = None

        except Exception as e:
            logger.error(f"Failed to complete stage monitoring: {e}")

    def fail_stage(self, stage_name: str, error_message: str) -> None:
        """Mark a stage as failed.

        Args:
            stage_name: Name of the failed stage
            error_message: Error message
        """
        try:
            if stage_name in self.stage_metrics:
                metrics = self.stage_metrics[stage_name]
                metrics.end_time = datetime.now()
                metrics.duration_seconds = (
                    metrics.end_time - metrics.start_time
                ).total_seconds()
                metrics.status = "failed"
                metrics.error_count = metrics.error_count + 1

                # Save to database
                self._save_stage_metrics(metrics)

                self._log_event(
                    "stage_failed",
                    stage_name,
                    "error",
                    f"Stage failed: {stage_name} - {error_message}",
                )

                logger.error(f"❌ Stage failed: {stage_name} - {error_message}")

        except Exception as e:
            logger.error(f"Failed to mark stage as failed: {e}")

    def end_migration_session(self, status: str = "completed") -> Dict[str, Any]:
        """End the migration monitoring session.

        Args:
            status: Final migration status

        Returns:
            Migration summary dictionary
        """
        try:
            self.is_monitoring = False

            if self.monitor_thread and self.monitor_thread.is_alive():
                self.monitor_thread.join(timeout=5.0)

            migration_end_time = datetime.now()
            total_duration = (
                migration_end_time - self.migration_start_time
            ).total_seconds()

            # Count completed and failed stages
            completed_stages = sum(
                1 for m in self.stage_metrics.values() if m.status == "completed"
            )
            failed_stages = sum(
                1 for m in self.stage_metrics.values() if m.status == "failed"
            )

            # Update session in database
            with sqlite3.connect(str(self.monitoring_db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE migration_sessions
                    SET end_time = ?, total_duration_seconds = ?, completed_stages = ?,
                        failed_stages = ?, status = ?
                    WHERE migration_id = ?
                """,
                    (
                        migration_end_time,
                        total_duration,
                        completed_stages,
                        failed_stages,
                        status,
                        self.migration_id,
                    ),
                )
                conn.commit()

            # Generate summary
            summary = self._generate_migration_summary()

            self._log_event(
                "session_end",
                None,
                "info",
                f"Migration session ended: {status} ({total_duration:.1f}s)",
            )

            logger.info(
                f"📊 Migration monitoring ended: {status} ({total_duration:.1f}s)"
            )

            return summary

        except Exception as e:
            logger.error(f"Failed to end monitoring session: {e}")
            return {"error": str(e)}

    def _monitoring_loop(self) -> None:
        """Main monitoring loop running in background thread."""
        logger.info("🔍 Starting monitoring loop")

        while self.is_monitoring:
            try:
                # Collect system health metrics
                health = self._get_current_health()
                if health:
                    self.health_history.append(health)
                    self._save_health_metrics(health)
                    self._check_health_alerts(health)

                # Sleep for monitoring interval
                time.sleep(self.config.get("monitoring_interval_seconds", 30))

            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                time.sleep(5)  # Brief pause before retrying

        logger.info("🔍 Monitoring loop ended")

    def _get_current_health(self) -> Optional[SystemHealth]:
        """Get current system health metrics.

        Returns:
            SystemHealth object or None if collection fails
        """
        try:
            import psutil

            # Memory metrics
            memory = psutil.virtual_memory()
            memory_usage_mb = (memory.total - memory.available) / (1024 * 1024)
            memory_available_mb = memory.available / (1024 * 1024)

            # CPU metrics
            cpu_usage = psutil.cpu_percent(interval=1)

            # Disk metrics
            disk = psutil.disk_usage("/")
            disk_usage_percent = (disk.used / disk.total) * 100

            # Simplified database metrics (would need actual DB connection)
            database_connections = 1  # Placeholder
            active_queries = 0  # Placeholder
            query_response_time_ms = 10.0  # Placeholder

            return SystemHealth(
                timestamp=datetime.now(),
                memory_usage_mb=memory_usage_mb,
                memory_available_mb=memory_available_mb,
                cpu_usage_percent=cpu_usage,
                disk_usage_percent=disk_usage_percent,
                database_connections=database_connections,
                active_queries=active_queries,
                query_response_time_ms=query_response_time_ms,
            )

        except ImportError:
            logger.warning("psutil not available - using mock health metrics")
            return SystemHealth(
                timestamp=datetime.now(),
                memory_usage_mb=512.0,
                memory_available_mb=1536.0,
                cpu_usage_percent=25.0,
                disk_usage_percent=45.0,
                database_connections=1,
                active_queries=0,
                query_response_time_ms=15.0,
            )

        except Exception as e:
            logger.error(f"Failed to collect system health metrics: {e}")
            return None

    def _check_health_alerts(self, health: SystemHealth) -> None:
        """Check health metrics against thresholds and trigger alerts.

        Args:
            health: SystemHealth metrics
        """
        alerts = []

        # Memory alerts
        if health.memory_usage_mb >= self.performance_thresholds["memory_critical_mb"]:
            alerts.append(
                ("CRITICAL", f"Memory usage critical: {health.memory_usage_mb:.1f}MB")
            )
        elif health.memory_usage_mb >= self.performance_thresholds["memory_warning_mb"]:
            alerts.append(
                ("WARNING", f"Memory usage high: {health.memory_usage_mb:.1f}MB")
            )

        # CPU alerts
        if (
            health.cpu_usage_percent
            >= self.performance_thresholds["cpu_critical_percent"]
        ):
            alerts.append(
                ("CRITICAL", f"CPU usage critical: {health.cpu_usage_percent:.1f}%")
            )
        elif (
            health.cpu_usage_percent
            >= self.performance_thresholds["cpu_warning_percent"]
        ):
            alerts.append(
                ("WARNING", f"CPU usage high: {health.cpu_usage_percent:.1f}%")
            )

        # Disk alerts
        if (
            health.disk_usage_percent
            >= self.performance_thresholds["disk_critical_percent"]
        ):
            alerts.append(
                ("CRITICAL", f"Disk usage critical: {health.disk_usage_percent:.1f}%")
            )
        elif (
            health.disk_usage_percent
            >= self.performance_thresholds["disk_warning_percent"]
        ):
            alerts.append(
                ("WARNING", f"Disk usage high: {health.disk_usage_percent:.1f}%")
            )

        # Query performance alerts
        if (
            health.query_response_time_ms
            >= self.performance_thresholds["query_timeout_ms"]
        ):
            alerts.append(
                (
                    "WARNING",
                    f"Query response time high: {health.query_response_time_ms:.1f}ms",
                )
            )

        # Process alerts
        for severity, message in alerts:
            self._log_event(
                "health_alert", self.current_stage, severity.lower(), message
            )
            logger.warning(f"🚨 {severity}: {message}")

            # Call alert callbacks
            for callback in self.alert_callbacks:
                try:
                    callback(severity, message, health)
                except Exception as e:
                    logger.error(f"Alert callback failed: {e}")

    def _save_stage_metrics(self, metrics: MigrationMetrics) -> None:
        """Save stage metrics to database.

        Args:
            metrics: MigrationMetrics to save
        """
        try:
            with sqlite3.connect(str(self.monitoring_db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO stage_metrics
                    (migration_id, stage_name, start_time, end_time, duration_seconds,
                     records_processed, records_failed, memory_usage_mb, cpu_usage_percent,
                     status, error_count, warnings_count)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        self.migration_id,
                        metrics.stage_name,
                        metrics.start_time,
                        metrics.end_time,
                        metrics.duration_seconds,
                        metrics.records_processed,
                        metrics.records_failed,
                        metrics.memory_usage_mb,
                        metrics.cpu_usage_percent,
                        metrics.status,
                        metrics.error_count,
                        metrics.warnings_count,
                    ),
                )
                conn.commit()

        except Exception as e:
            logger.error(f"Failed to save stage metrics: {e}")

    def _save_health_metrics(self, health: SystemHealth) -> None:
        """Save health metrics to database.

        Args:
            health: SystemHealth metrics to save
        """
        try:
            with sqlite3.connect(str(self.monitoring_db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO system_health
                    (migration_id, timestamp, memory_usage_mb, memory_available_mb,
                     cpu_usage_percent, disk_usage_percent, database_connections,
                     active_queries, query_response_time_ms)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        self.migration_id,
                        health.timestamp,
                        health.memory_usage_mb,
                        health.memory_available_mb,
                        health.cpu_usage_percent,
                        health.disk_usage_percent,
                        health.database_connections,
                        health.active_queries,
                        health.query_response_time_ms,
                    ),
                )
                conn.commit()

        except Exception as e:
            logger.error(f"Failed to save health metrics: {e}")

    def _log_event(
        self,
        event_type: str,
        stage_name: Optional[str],
        severity: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log migration event.

        Args:
            event_type: Type of event
            stage_name: Associated stage name
            severity: Event severity (info, warning, error, critical)
            message: Event message
            details: Additional event details
        """
        try:
            timestamp = datetime.now()
            event = {
                "timestamp": timestamp,
                "event_type": event_type,
                "stage_name": stage_name,
                "severity": severity,
                "message": message,
                "details": details,
            }

            self.event_log.append(event)

            # Save to database
            with sqlite3.connect(str(self.monitoring_db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO migration_events
                    (migration_id, timestamp, event_type, stage_name, severity, message, details)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        self.migration_id,
                        timestamp,
                        event_type,
                        stage_name,
                        severity,
                        message,
                        json.dumps(details) if details else None,
                    ),
                )
                conn.commit()

        except Exception as e:
            logger.error(f"Failed to log event: {e}")

    def _generate_migration_summary(self) -> Dict[str, Any]:
        """Generate comprehensive migration summary.

        Returns:
            Migration summary dictionary
        """
        try:
            total_duration = (
                datetime.now() - self.migration_start_time
            ).total_seconds()

            # Calculate stage statistics
            completed_stages = [
                m for m in self.stage_metrics.values() if m.status == "completed"
            ]
            failed_stages = [
                m for m in self.stage_metrics.values() if m.status == "failed"
            ]

            total_records_processed = sum(m.records_processed for m in completed_stages)
            total_records_failed = sum(
                m.records_failed for m in self.stage_metrics.values()
            )
            total_errors = sum(m.error_count for m in self.stage_metrics.values())
            total_warnings = sum(m.warnings_count for m in self.stage_metrics.values())

            # Performance statistics
            avg_stage_duration = sum(
                m.duration_seconds for m in completed_stages
            ) / max(len(completed_stages), 1)
            longest_stage = (
                max(completed_stages, key=lambda m: m.duration_seconds)
                if completed_stages
                else None
            )

            # Health statistics
            if self.health_history:
                avg_memory = sum(h.memory_usage_mb for h in self.health_history) / len(
                    self.health_history
                )
                max_memory = max(h.memory_usage_mb for h in self.health_history)
                avg_cpu = sum(h.cpu_usage_percent for h in self.health_history) / len(
                    self.health_history
                )
                max_cpu = max(h.cpu_usage_percent for h in self.health_history)
            else:
                avg_memory = max_memory = avg_cpu = max_cpu = 0

            return {
                "migration_id": self.migration_id,
                "start_time": self.migration_start_time.isoformat(),
                "end_time": datetime.now().isoformat(),
                "total_duration_seconds": round(total_duration, 2),
                "total_duration_formatted": str(timedelta(seconds=int(total_duration))),
                "stage_summary": {
                    "total_stages": len(self.stage_metrics),
                    "completed_stages": len(completed_stages),
                    "failed_stages": len(failed_stages),
                    "success_rate_percent": round(
                        (len(completed_stages) / max(len(self.stage_metrics), 1)) * 100,
                        1,
                    ),
                },
                "data_summary": {
                    "total_records_processed": total_records_processed,
                    "total_records_failed": total_records_failed,
                    "success_rate_percent": round(
                        (
                            (total_records_processed - total_records_failed)
                            / max(total_records_processed, 1)
                        )
                        * 100,
                        1,
                    ),
                },
                "error_summary": {
                    "total_errors": total_errors,
                    "total_warnings": total_warnings,
                    "error_rate_per_stage": round(
                        total_errors / max(len(self.stage_metrics), 1), 2
                    ),
                },
                "performance_summary": {
                    "average_stage_duration_seconds": round(avg_stage_duration, 2),
                    "longest_stage": {
                        "name": longest_stage.stage_name if longest_stage else None,
                        "duration_seconds": round(longest_stage.duration_seconds, 2)
                        if longest_stage
                        else 0,
                    },
                    "records_per_second": round(
                        total_records_processed / max(total_duration, 1), 2
                    ),
                },
                "resource_usage": {
                    "average_memory_mb": round(avg_memory, 2),
                    "peak_memory_mb": round(max_memory, 2),
                    "average_cpu_percent": round(avg_cpu, 2),
                    "peak_cpu_percent": round(max_cpu, 2),
                },
                "detailed_stages": [
                    {
                        "name": m.stage_name,
                        "duration_seconds": round(m.duration_seconds, 2),
                        "records_processed": m.records_processed,
                        "records_failed": m.records_failed,
                        "status": m.status,
                        "error_count": m.error_count,
                        "warnings_count": m.warnings_count,
                    }
                    for m in self.stage_metrics.values()
                ],
            }

        except Exception as e:
            logger.error(f"Failed to generate migration summary: {e}")
            return {"error": str(e)}

    def get_current_status(self) -> Dict[str, Any]:
        """Get current migration status.

        Returns:
            Current status dictionary
        """
        if not self.is_monitoring:
            return {"status": "not_monitoring"}

        current_time = datetime.now()
        elapsed = (current_time - self.migration_start_time).total_seconds()

        completed_stages = sum(
            1 for m in self.stage_metrics.values() if m.status == "completed"
        )
        failed_stages = sum(
            1 for m in self.stage_metrics.values() if m.status == "failed"
        )

        # Get latest health metrics
        latest_health = self.health_history[-1] if self.health_history else None

        return {
            "status": "running",
            "migration_id": self.migration_id,
            "current_stage": self.current_stage,
            "elapsed_seconds": round(elapsed, 1),
            "completed_stages": completed_stages,
            "failed_stages": failed_stages,
            "total_stages": len(self.stage_metrics),
            "current_health": asdict(latest_health) if latest_health else None,
        }

    def add_alert_callback(self, callback: Callable) -> None:
        """Add callback for health alerts.

        Args:
            callback: Function to call when alert occurs
        """
        self.alert_callbacks.append(callback)

    def export_monitoring_data(self, output_file: str, format: str = "json") -> None:
        """Export monitoring data to file.

        Args:
            output_file: Output file path
            format: Export format (json, csv)
        """
        try:
            summary = self._generate_migration_summary()

            if format.lower() == "json":
                with open(output_file, "w") as f:
                    json.dump(summary, f, indent=2)

            elif format.lower() == "csv":
                import csv

                with open(output_file, "w", newline="") as f:
                    writer = csv.writer(f)

                    # Write stage details as CSV
                    writer.writerow(
                        [
                            "stage_name",
                            "duration_seconds",
                            "records_processed",
                            "records_failed",
                            "status",
                            "error_count",
                            "warnings_count",
                        ]
                    )

                    for stage in summary.get("detailed_stages", []):
                        writer.writerow(
                            [
                                stage["name"],
                                stage["duration_seconds"],
                                stage["records_processed"],
                                stage["records_failed"],
                                stage["status"],
                                stage["error_count"],
                                stage["warnings_count"],
                            ]
                        )

            logger.info(f"📄 Monitoring data exported to: {output_file}")

        except Exception as e:
            logger.error(f"Failed to export monitoring data: {e}")
            raise
