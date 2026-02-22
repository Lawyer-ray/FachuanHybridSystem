"""
Property-Based Tests for Debug Script Location

Tests that verify debug scripts are properly located in scripts/development/
and not in apps/*/tests/ directories.

**Feature: backend-cleanup-optimization, Property 5: 调试脚本位置**
**Validates: Requirements 4.1, 4.2**
"""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pathlib import Path


class TestDebugScriptLocationProperties:
    """
    Property-Based Tests for Debug Script Location

    Feature: backend-cleanup-optimization, Property 5: 调试脚本位置
    Validates: Requirements 4.1, 4.2
    """

    @pytest.fixture
    def backend_dir(self):
        """Get the backend directory"""
        return Path(__file__).parent.parent.parent

    @pytest.fixture
    def apps_dir(self, backend_dir):
        """Get the apps directory"""
        return backend_dir / "apps"

    @pytest.fixture
    def scripts_dir(self, backend_dir):
        """Get the scripts directory"""
        return backend_dir / "scripts"

    def _is_debug_script(self, file_path: Path) -> bool:
        """
        Determine if a file is a debug script based on naming conventions.

        Debug scripts are identified by:
        - Name starts with 'debug_'
        - Name starts with 'interactive_'
        - Name contains 'debug' and is not a test file
        """
        name = file_path.name.lower()

        # Skip test files
        if name.startswith("test_"):
            return False

        # Check for debug script patterns
        return (
            name.startswith("debug_") or name.startswith("interactive_") or ("debug" in name and name.endswith(".py"))
        )

    def test_no_debug_scripts_in_app_tests_directories(self, apps_dir):
        """
        Property 5: 调试脚本位置

        *For any* debug script (non-test Python file in test directories),
        after migration it should NOT exist in apps/*/tests/ directories.

        Feature: backend-cleanup-optimization, Property 5: 调试脚本位置
        Validates: Requirements 4.1, 4.2
        """
        debug_scripts_in_apps = []

        # Scan all apps/*/tests/ directories
        for app_dir in apps_dir.iterdir():
            if not app_dir.is_dir():
                continue

            tests_dir = app_dir / "tests"
            if not tests_dir.exists():
                continue

            # Find debug scripts in this tests directory
            for py_file in tests_dir.glob("*.py"):
                if self._is_debug_script(py_file):
                    debug_scripts_in_apps.append(py_file)

        assert len(debug_scripts_in_apps) == 0, (
            f"Found debug scripts in apps/*/tests/ directories that should be "
            f"in scripts/development/: {[str(s) for s in debug_scripts_in_apps]}"
        )

    def test_debug_scripts_exist_in_scripts_development(self, scripts_dir):
        """
        Property 5: 调试脚本位置

        *For any* debug script, it should exist in scripts/development/
        or scripts/development/automation/ subdirectory.

        Feature: backend-cleanup-optimization, Property 5: 调试脚本位置
        Validates: Requirements 4.1, 4.2
        """
        development_dir = scripts_dir / "development"

        # Check that development directory exists
        assert development_dir.exists(), "scripts/development/ directory should exist"

        # Get all debug scripts in development directory (including subdirectories)
        debug_scripts = []
        for py_file in development_dir.rglob("*.py"):
            if self._is_debug_script(py_file):
                debug_scripts.append(py_file)

        # Verify that debug scripts are properly named
        for script in debug_scripts:
            assert self._is_debug_script(script), (
                f"Script {script.name} in development/ should follow debug script naming"
            )

    def test_automation_debug_scripts_in_automation_subdirectory(self, scripts_dir):
        """
        Property 5: 调试脚本位置

        *For any* debug script related to automation (browser automation, scraping),
        it should be in scripts/development/automation/ subdirectory.

        Feature: backend-cleanup-optimization, Property 5: 调试脚本位置
        Validates: Requirements 4.1, 4.2
        """
        automation_dev_dir = scripts_dir / "development" / "automation"

        # Check that automation subdirectory exists
        assert automation_dev_dir.exists(), (
            "scripts/development/automation/ directory should exist for automation-related debug scripts"
        )

        # Verify files in automation subdirectory are debug scripts
        for py_file in automation_dev_dir.glob("*.py"):
            if py_file.name == "__init__.py":
                continue

            assert self._is_debug_script(py_file), (
                f"File {py_file.name} in development/automation/ should be a debug script"
            )

    def test_app_tests_directories_only_contain_tests(self, apps_dir):
        """
        Property 5: 调试脚本位置

        *For any* Python file in apps/*/tests/ directories,
        it should be a test file (starting with 'test_') or __init__.py.

        Feature: backend-cleanup-optimization, Property 5: 调试脚本位置
        Validates: Requirements 4.2
        """
        non_test_files = []

        # Allowed non-test files
        allowed_files = {"__init__.py", "conftest.py"}

        # Scan all apps/*/tests/ directories
        for app_dir in apps_dir.iterdir():
            if not app_dir.is_dir():
                continue

            tests_dir = app_dir / "tests"
            if not tests_dir.exists():
                continue

            # Check all Python files
            for py_file in tests_dir.glob("*.py"):
                if py_file.name in allowed_files:
                    continue
                if py_file.name.startswith("test_"):
                    continue

                non_test_files.append(py_file)

        assert len(non_test_files) == 0, (
            f"Found non-test Python files in apps/*/tests/ directories: "
            f"{[str(f) for f in non_test_files]}. "
            f"Debug scripts should be in scripts/development/"
        )

    @given(
        st.sampled_from(
            [
                "debug_page_structure.py",
                "interactive_debug.py",
                "debug_token_capture.py",
                "debug_login.py",
                "interactive_session.py",
            ]
        )
    )
    def test_debug_script_naming_property(self, script_name):
        """
        Property 5: 调试脚本位置

        *For any* script name following debug script naming conventions,
        it should be identified as a debug script.

        Feature: backend-cleanup-optimization, Property 5: 调试脚本位置
        Validates: Requirements 4.1, 4.2
        """
        # Create a mock path for testing
        mock_path = Path(script_name)

        # Verify it's identified as a debug script
        assert self._is_debug_script(mock_path), f"Script {script_name} should be identified as a debug script"

    @given(
        st.sampled_from(
            [
                "test_debug_feature.py",
                "test_interactive_mode.py",
                "__init__.py",
                "conftest.py",
            ]
        )
    )
    def test_non_debug_script_naming_property(self, script_name):
        """
        Property 5: 调试脚本位置

        *For any* script name that is a test file or init file,
        it should NOT be identified as a debug script.

        Feature: backend-cleanup-optimization, Property 5: 调试脚本位置
        Validates: Requirements 4.1, 4.2
        """
        # Create a mock path for testing
        mock_path = Path(script_name)

        # Verify it's NOT identified as a debug script
        assert not self._is_debug_script(mock_path), f"Script {script_name} should NOT be identified as a debug script"
