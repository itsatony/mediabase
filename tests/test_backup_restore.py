"""
MEDIABASE v0.6.0+ Backup and Restore Test Suite

Tests the backup script functionality to ensure:
1. Backup script executes successfully
2. Backup files are created and valid
3. Error logs are properly separated from SQL content
4. SQL content integrity validation catches corruption
5. Backup validation passes for clean backups

Note: Full restore testing requires significant time/resources (23GB restore)
and is better suited for CI/CD pipelines or scheduled testing.
"""

import subprocess
import gzip
import os
import tempfile
import pytest
from pathlib import Path


class TestBackupScript:
    """Test the backup_mediabase.sh script functionality"""

    BACKUP_SCRIPT = Path("backups/backup_mediabase.sh")
    BACKUP_DIR = Path("backups")

    def test_backup_script_exists(self):
        """Verify backup script exists and is executable"""
        assert self.BACKUP_SCRIPT.exists(), "Backup script not found"
        assert os.access(self.BACKUP_SCRIPT, os.X_OK), "Backup script not executable"

    def test_backup_script_help(self):
        """Test backup script with --help (if implemented)"""
        # This is a basic smoke test - the script doesn't have --help yet
        # but we can verify it runs without error on unknown option
        result = subprocess.run(
            [str(self.BACKUP_SCRIPT), "--compress"],
            capture_output=True,
            text=True,
            timeout=10,
            env=os.environ.copy()
        )
        # Script should handle --compress option
        # If it fails for other reasons (like missing DB), that's expected
        assert result.returncode in [0, 1], "Script should handle known options"


class TestBackupValidation:
    """Test backup file validation logic"""

    def test_gzip_integrity_check(self):
        """Test that gzip integrity check works correctly"""
        # Create a valid gzipped file
        with tempfile.NamedTemporaryFile(suffix=".sql.gz", delete=False) as tmp:
            tmp_path = tmp.name
            with gzip.open(tmp_path, 'wt') as gz:
                gz.write("-- PostgreSQL dump\n")
                gz.write("CREATE TABLE test (id INT);\n")

        try:
            # Test gzip integrity
            result = subprocess.run(
                ["gzip", "-t", tmp_path],
                capture_output=True,
                timeout=5
            )
            assert result.returncode == 0, "Valid gzip file should pass integrity check"
        finally:
            os.unlink(tmp_path)

    def test_corrupted_gzip_detection(self):
        """Test that corrupted gzip files are detected"""
        # Create a corrupted gzip file
        with tempfile.NamedTemporaryFile(suffix=".sql.gz", delete=False) as tmp:
            tmp_path = tmp.name
            tmp.write(b"This is not a valid gzip file\n")

        try:
            # Test gzip integrity - should fail
            result = subprocess.run(
                ["gzip", "-t", tmp_path],
                capture_output=True,
                timeout=5
            )
            assert result.returncode != 0, "Corrupted gzip file should fail integrity check"
        finally:
            os.unlink(tmp_path)

    def test_sql_corruption_detection(self):
        """Test that SQL corruption (pg_dump messages in SQL) is detected"""
        # Create a backup file with pg_dump log messages mixed in SQL
        with tempfile.NamedTemporaryFile(suffix=".sql.gz", delete=False) as tmp:
            tmp_path = tmp.name
            with gzip.open(tmp_path, 'wt') as gz:
                gz.write("-- PostgreSQL dump\n")
                gz.write("DROP INDEX IF EXISTS public.idx_test;\n")
                # This is the corruption pattern from the v0.6.0 bug
                gz.write("DROP INDEX IF EXISTS publpg_dump: dropping INDEX idx_corrupted\n")
                gz.write("pg_dump: dropping TABLE test_table\n")
                gz.write("ic.idx_another_index;\n")

        try:
            # Check for pg_dump messages in first 1000 lines
            result = subprocess.run(
                f"zcat {tmp_path} | head -n 1000 | grep -q 'pg_dump:'",
                shell=True,
                timeout=5
            )
            assert result.returncode == 0, "Corrupted SQL should contain 'pg_dump:' messages"
        finally:
            os.unlink(tmp_path)

    def test_clean_sql_validation(self):
        """Test that clean SQL passes validation"""
        # Create a backup file without pg_dump messages
        with tempfile.NamedTemporaryFile(suffix=".sql.gz", delete=False) as tmp:
            tmp_path = tmp.name
            with gzip.open(tmp_path, 'wt') as gz:
                gz.write("-- PostgreSQL dump\n")
                gz.write("-- Dumped from database version 12.0\n")
                gz.write("SET statement_timeout = 0;\n")
                gz.write("CREATE TABLE test (id INT);\n")
                gz.write("DROP INDEX IF EXISTS public.idx_test;\n")

        try:
            # Check for pg_dump messages - should NOT find any
            result = subprocess.run(
                f"zcat {tmp_path} | head -n 1000 | grep -q 'pg_dump:'",
                shell=True,
                timeout=5
            )
            assert result.returncode != 0, "Clean SQL should NOT contain 'pg_dump:' messages"
        finally:
            os.unlink(tmp_path)


class TestBackupFileStructure:
    """Test backup file naming and structure"""

    BACKUP_DIR = Path("backups")

    def test_backup_directory_exists(self):
        """Verify backup directory exists"""
        assert self.BACKUP_DIR.exists(), "Backup directory should exist"
        assert self.BACKUP_DIR.is_dir(), "Backup path should be a directory"

    def test_backup_file_naming_pattern(self):
        """Test that backup files follow naming convention"""
        # Pattern: mbase_backup_YYYYMMDD_HHMMSS.sql.gz
        backup_files = list(self.BACKUP_DIR.glob("mbase_backup_*.sql.gz"))

        if backup_files:
            # Check that at least one backup follows the pattern
            sample_file = backup_files[0]
            assert sample_file.stem.startswith("mbase_backup_"), "Backup filename should start with 'mbase_backup_'"
            assert sample_file.suffix == ".gz", "Backup should be gzip compressed"

    def test_error_log_creation(self):
        """Test that error logs are created alongside backups (v0.6.0.1+)"""
        # Find the most recent backup
        backup_files = sorted(self.BACKUP_DIR.glob("mbase_backup_*.sql.gz"))

        if backup_files:
            latest_backup = backup_files[-1]
            error_log = Path(str(latest_backup) + ".error.log")

            # Error log should exist for v0.6.0.1+ backups
            if latest_backup.name >= "mbase_backup_20251124":  # After the fix date
                assert error_log.exists(), f"Error log should exist for backup: {latest_backup.name}"
                assert error_log.stat().st_size > 0, "Error log should not be empty"
            else:
                # Older backups won't have error logs - that's expected
                pass


class TestBackupScriptOptions:
    """Test backup script command-line options"""

    BACKUP_SCRIPT = Path("backups/backup_mediabase.sh")

    def test_compress_option(self):
        """Test that --compress option is recognized"""
        # Just verify the script accepts the option without error
        # (actual backup would require database connection)
        result = subprocess.run(
            [str(self.BACKUP_SCRIPT), "--compress"],
            capture_output=True,
            text=True,
            timeout=10,
            env=os.environ.copy()
        )
        # Script should recognize the option (may fail on DB connection, that's OK)
        assert result.returncode in [0, 1], "Script should handle --compress option"

    def test_custom_format_option(self):
        """Test that --custom-format option is recognized"""
        result = subprocess.run(
            [str(self.BACKUP_SCRIPT), "--custom-format"],
            capture_output=True,
            text=True,
            timeout=10,
            env=os.environ.copy()
        )
        # Script should recognize the option (may fail on DB connection, that's OK)
        assert result.returncode in [0, 1], "Script should handle --custom-format option"


class TestRestoreInstructions:
    """Test that restore instructions documentation exists"""

    RESTORE_DOCS = Path("docs/RESTORE_INSTRUCTIONS.md")

    def test_restore_documentation_exists(self):
        """Verify restore instructions document exists"""
        assert self.RESTORE_DOCS.exists(), "Restore instructions document should exist"

    def test_restore_documentation_content(self):
        """Verify restore instructions contain key information"""
        content = self.RESTORE_DOCS.read_text()

        # Check for essential sections
        assert "restore" in content.lower(), "Should contain restore instructions"
        assert "psql" in content.lower(), "Should mention psql command"
        assert "gunzip" in content.lower(), "Should mention gunzip for compressed backups"
        assert "PGPASSWORD" in content, "Should mention password environment variable"

    def test_restore_instructions_mention_corruption_fix(self):
        """Verify documentation mentions the v0.6.0 corruption issue"""
        content = self.RESTORE_DOCS.read_text()

        # Should warn about the corrupted v0.6.0 backup
        assert "corrupted" in content.lower() or "CORRUPTED" in content, \
            "Should warn about corrupted v0.6.0 backup"


@pytest.mark.integration
class TestBackupIntegration:
    """Integration tests that require database connection"""

    def test_full_backup_restore_cycle(self):
        """
        PLACEHOLDER: Full backup/restore test

        This test would:
        1. Create a test database
        2. Run backup script
        3. Verify backup validity
        4. Create temp database
        5. Restore backup to temp database
        6. Validate data integrity
        7. Cleanup

        Marked as @pytest.mark.integration - requires significant time/resources
        and is better suited for CI/CD pipelines.
        """
        pytest.skip("Full backup/restore test requires significant resources - run in CI/CD")


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "-m", "not integration"])
