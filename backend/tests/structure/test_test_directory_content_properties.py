"""
Property-Based Tests for Test Directory Content

Tests that verify the tests/admin/ directory primarily contains test code files
and not excessive report files.

**Feature: backend-cleanup-optimization, Property 6: 测试目录内容比例**
**Validates: Requirements 5.3**
"""

from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st


class TestTestDirectoryContentProperties:
    """
    Property-Based Tests for Test Directory Content

    Feature: backend-cleanup-optimization, Property 6: 测试目录内容比例
    Validates: Requirements 5.3
    """

    @pytest.fixture
    def backend_dir(self):
        """Get the backend directory"""
        return Path(__file__).parent.parent.parent

    @pytest.fixture
    def tests_admin_dir(self, backend_dir):
        """Get the tests/admin directory"""
        return backend_dir / "tests" / "admin"

    @pytest.fixture
    def archive_dir(self, backend_dir):
        """Get the docs/archive/admin-test-reports directory"""
        return backend_dir / "docs" / "archive" / "admin-test-reports"

    # Files that should be kept in tests/admin/
    ALLOWED_MD_FILES = {"README.md", "QUICK_START.md"}

    def _is_test_code_file(self, file_path: Path) -> bool:
        """Check if a file is a test code file (.py)"""
        return file_path.suffix == ".py"

    def _is_report_file(self, file_path: Path) -> bool:
        """
        Check if a file is a report file (.md) that should be archived.

        Report files are .md files that are NOT in the allowed list.
        """
        if file_path.suffix != ".md":
            return False
        return file_path.name not in self.ALLOWED_MD_FILES

    def test_test_directory_content_ratio(self, tests_admin_dir):
        """
        Property 6: 测试目录内容比例

        *For any* tests/admin/ directory, the ratio of test code files (.py)
        to report files (.md) should be greater than 1:1.

        Feature: backend-cleanup-optimization, Property 6: 测试目录内容比例
        Validates: Requirements 5.3
        """
        if not tests_admin_dir.exists():
            pytest.skip("tests/admin/ directory does not exist")

        # Count test code files
        test_code_files = [f for f in tests_admin_dir.glob("*.py") if self._is_test_code_file(f)]

        # Count report files (excluding allowed ones)
        report_files = [f for f in tests_admin_dir.glob("*.md") if self._is_report_file(f)]

        test_count = len(test_code_files)
        report_count = len(report_files)

        # The ratio of test files to report files should be > 1:1
        # This means test_count > report_count
        assert test_count > report_count, (
            f"Test directory content ratio violation: "
            f"Found {test_count} test code files and {report_count} report files. "
            f"The ratio should be greater than 1:1. "
            f"Report files that should be archived: {[f.name for f in report_files]}"
        )

    def test_only_allowed_md_files_in_tests_admin(self, tests_admin_dir):
        """
        Property 6: 测试目录内容比例

        *For any* .md file in tests/admin/, it should be in the allowed list
        (README.md, QUICK_START.md).

        Feature: backend-cleanup-optimization, Property 6: 测试目录内容比例
        Validates: Requirements 5.3
        """
        if not tests_admin_dir.exists():
            pytest.skip("tests/admin/ directory does not exist")

        # Find all .md files that are not in the allowed list
        disallowed_md_files = [f for f in tests_admin_dir.glob("*.md") if f.name not in self.ALLOWED_MD_FILES]

        assert len(disallowed_md_files) == 0, (
            f"Found .md files in tests/admin/ that should be archived: "
            f"{[f.name for f in disallowed_md_files]}. "
            f"Only {self.ALLOWED_MD_FILES} should remain in tests/admin/"
        )

    def test_archived_reports_exist_in_archive_directory(self, archive_dir):
        """
        Property 6: 测试目录内容比例

        *For any* archived report, it should exist in docs/archive/admin-test-reports/.

        Feature: backend-cleanup-optimization, Property 6: 测试目录内容比例
        Validates: Requirements 5.1, 5.2
        """
        if not archive_dir.exists():
            pytest.skip("docs/archive/admin-test-reports/ directory does not exist")

        # Check that archive directory contains .md files
        archived_files = list(archive_dir.glob("*.md"))

        # Archive directory should contain the moved report files
        assert len(archived_files) > 0, "docs/archive/admin-test-reports/ should contain archived report files"

    def test_tests_admin_primarily_contains_test_code(self, tests_admin_dir):
        """
        Property 6: 测试目录内容比例

        *For any* tests/admin/ directory, it should primarily contain test code files.

        Feature: backend-cleanup-optimization, Property 6: 测试目录内容比例
        Validates: Requirements 5.3
        """
        if not tests_admin_dir.exists():
            pytest.skip("tests/admin/ directory does not exist")

        # Count all files (excluding directories and __pycache__)
        all_files = [f for f in tests_admin_dir.iterdir() if f.is_file()]

        # Count test code files
        test_code_files = [f for f in all_files if f.suffix == ".py"]

        # Test code files should be the majority
        test_ratio = len(test_code_files) / len(all_files) if all_files else 0

        assert test_ratio >= 0.5, (
            f"Test directory should primarily contain test code files. "
            f"Found {len(test_code_files)} test files out of {len(all_files)} total files "
            f"(ratio: {test_ratio:.2%}). Expected at least 50%."
        )

    @given(
        st.sampled_from(
            [
                "STAGE3_SUMMARY.md",
                "FINAL_REPORT.md",
                "TASK2_CASE_STAGE_VALIDATION_COMPLETE.md",
                "TEST_REPORT_STAGE2.md",
                "SOLUTION_SUMMARY.md",
                "TEST_REPORT_SMOKE.md",
                "SUMMARY.md",
                "STAGE3_85_PERCENT_SUCCESS.md",
                "TESTING_PLAN.md",
                "STAGE3_FINAL_SUMMARY.md",
                "STAGE3_100_PERCENT_PLAN.md",
                "STAGE4_FRAMEWORK_IMPLEMENTATION.md",
                "STAGE3_COMPLETE.md",
                "EXECUTION_TASKS.md",
                "STAGE3_FINAL_REPORT.md",
            ]
        )
    )
    def test_report_file_identification_property(self, filename):
        """
        Property 6: 测试目录内容比例

        *For any* report file name from the known list,
        it should be identified as a report file that needs archiving.

        Feature: backend-cleanup-optimization, Property 6: 测试目录内容比例
        Validates: Requirements 5.1, 5.2
        """
        mock_path = Path(filename)

        assert self._is_report_file(mock_path), f"File {filename} should be identified as a report file to archive"

    @given(
        st.sampled_from(
            [
                "README.md",
                "QUICK_START.md",
            ]
        )
    )
    def test_allowed_md_file_identification_property(self, filename):
        """
        Property 6: 测试目录内容比例

        *For any* allowed .md file name,
        it should NOT be identified as a report file to archive.

        Feature: backend-cleanup-optimization, Property 6: 测试目录内容比例
        Validates: Requirements 5.2
        """
        mock_path = Path(filename)

        assert not self._is_report_file(
            mock_path
        ), f"File {filename} should NOT be identified as a report file to archive"
