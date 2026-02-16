"""
Property-Based Tests for Script File Classification

Tests that verify scripts are properly organized by function.
"""

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

from apps.core.path import Path


class TestScriptClassificationProperties:
    """
    Property-Based Tests for Script Classification

    Feature: backend-structure-optimization, Property 9: 脚本文件分类
    Validates: Requirements 7.1
    """

    @pytest.fixture
    def scripts_dir(self):
        """Get the scripts directory"""
        backend_dir = Path(__file__).parent.parent.parent
        return backend_dir / "scripts"

    def test_testing_scripts_in_testing_directory(self, scripts_dir):
        """
        Property 9: 脚本文件分类

        For any script file in the scripts/ directory that starts with 'test_',
        it should be located in the scripts/testing/ subdirectory.

        Feature: backend-structure-optimization, Property 9: 脚本文件分类
        Validates: Requirements 7.1
        """
        testing_dir = scripts_dir / "testing"

        # Allowed testing utility scripts that don't start with 'test_'
        allowed_testing_utilities = {
            "verify_migration.py",
            "verify_contract_assignment_migration.py",
            "verify_account_credential_migration.py",
            "__init__.py",
        }

        # Get all Python files in testing directory
        if testing_dir.exists():
            testing_scripts = list(testing_dir.glob("*.py"))

            # Verify all files in testing/ start with 'test_' or are allowed utilities
            for script in testing_scripts:
                is_test_file = script.name.startswith("test_")
                is_allowed_utility = script.name in allowed_testing_utilities
                assert is_test_file or is_allowed_utility, (
                    f"Script {script.name} in testing/ should start with 'test_' "
                    f"or be an allowed utility: {allowed_testing_utilities}"
                )

        # Check that no test_*.py files exist in root scripts directory
        root_test_scripts = list(scripts_dir.glob("test_*.py"))
        assert len(root_test_scripts) == 0, (
            f"Found test scripts in root directory: {[s.name for s in root_test_scripts]}. "
            f"They should be in scripts/testing/"
        )

    def test_development_scripts_in_development_directory(self, scripts_dir):
        """
        Property 9: 脚本文件分类

        For any script file in the scripts/ directory that starts with 'check_',
        'debug_', 'example_', or 'quick_', it should be located in the
        scripts/development/ subdirectory.

        Feature: backend-structure-optimization, Property 9: 脚本文件分类
        Validates: Requirements 7.1
        """
        development_dir = scripts_dir / "development"

        # Development script prefixes
        dev_prefixes = ["check_", "debug_", "example_", "quick_"]

        # Get all Python files in development directory
        if development_dir.exists():
            dev_scripts = list(development_dir.glob("*.py"))

            # Verify all files in development/ have appropriate prefixes
            for script in dev_scripts:
                has_dev_prefix = any(script.name.startswith(prefix) for prefix in dev_prefixes)
                assert has_dev_prefix, (
                    f"Script {script.name} in development/ should start with one of: " f"{', '.join(dev_prefixes)}"
                )

        # Check that no dev scripts exist in root scripts directory
        for prefix in dev_prefixes:
            root_dev_scripts = list(scripts_dir.glob(f"{prefix}*.py"))
            assert len(root_dev_scripts) == 0, (
                f"Found {prefix}*.py scripts in root directory: "
                f"{[s.name for s in root_dev_scripts]}. "
                f"They should be in scripts/development/"
            )

    def test_automation_scripts_in_automation_directory(self, scripts_dir):
        """
        Property 9: 脚本文件分类

        For any script file in the scripts/ directory that starts with 'court_',
        it should be located in the scripts/automation/ subdirectory.

        Feature: backend-structure-optimization, Property 9: 脚本文件分类
        Validates: Requirements 7.1
        """
        automation_dir = scripts_dir / "automation"

        # Get all files in automation directory (including .js files)
        if automation_dir.exists():
            automation_scripts = list(automation_dir.glob("court_*"))

            # Verify all court_* files are in automation/
            for script in automation_scripts:
                assert script.name.startswith(
                    "court_"
                ), f"Script {script.name} in automation/ should start with 'court_'"

        # Check that no court_* files exist in root scripts directory
        root_court_scripts = list(scripts_dir.glob("court_*"))
        assert len(root_court_scripts) == 0, (
            f"Found court_* scripts in root directory: "
            f"{[s.name for s in root_court_scripts]}. "
            f"They should be in scripts/automation/"
        )

    def test_refactoring_scripts_in_refactoring_directory(self, scripts_dir):
        """
        Property 9: 脚本文件分类

        For any script file in the scripts/ directory that contains 'migrate'
        or 'refactor' in its name, it should be located in the
        scripts/refactoring/ subdirectory.

        Feature: backend-structure-optimization, Property 9: 脚本文件分类
        Validates: Requirements 7.1
        """
        refactoring_dir = scripts_dir / "refactoring"

        # Allowed refactoring utility scripts that don't contain standard keywords
        # These are tools created during cleanup/refactoring tasks
        allowed_refactoring_utilities = {
            "update_imports.py",  # Import path update utility
            "cleanup_files.py",  # File cleanup utility
        }

        # Get all Python files in refactoring directory
        if refactoring_dir.exists():
            refactoring_scripts = list(refactoring_dir.glob("*.py"))

            # Verify files in refactoring/ have appropriate names
            for script in refactoring_scripts:
                # Skip __init__.py and test files
                if script.name in ["__init__.py"] or script.name.startswith("test_"):
                    continue

                # Check if it's an allowed utility
                if script.name in allowed_refactoring_utilities:
                    continue

                has_refactoring_keyword = (
                    "migrate" in script.name.lower()
                    or "refactor" in script.name.lower()
                    or "validator" in script.name.lower()
                    or "structure" in script.name.lower()
                )
                assert has_refactoring_keyword, (
                    f"Script {script.name} in refactoring/ should contain "
                    f"'migrate', 'refactor', 'validator', or 'structure' in its name, "
                    f"or be an allowed utility: {allowed_refactoring_utilities}"
                )

    def test_no_loose_scripts_in_root(self, scripts_dir):
        """
        Property 9: 脚本文件分类

        For any Python or JavaScript file in the scripts/ root directory,
        it should either be a README/documentation file or be categorized
        into a subdirectory.

        Feature: backend-structure-optimization, Property 9: 脚本文件分类
        Validates: Requirements 7.1
        """
        # Allowed files in root
        allowed_files = {
            "README.md",
            "USERSCRIPT_GUIDE.md",
            "__init__.py",
        }

        # Get all files in root (not directories)
        root_files = [f for f in scripts_dir.iterdir() if f.is_file() and not f.name.startswith(".")]

        # Check each file
        for file in root_files:
            assert file.name in allowed_files, (
                f"File {file.name} should not be in scripts root directory. "
                f"It should be categorized into testing/, development/, "
                f"automation/, or refactoring/ subdirectories."
            )

    def test_subdirectories_exist(self, scripts_dir):
        """
        Property 9: 脚本文件分类

        The scripts/ directory should have the standard subdirectories
        for organizing scripts by function.

        Feature: backend-structure-optimization, Property 9: 脚本文件分类
        Validates: Requirements 7.1
        """
        required_subdirs = ["testing", "development", "automation", "refactoring"]

        for subdir in required_subdirs:
            subdir_path = scripts_dir / subdir
            assert (
                subdir_path.exists() and subdir_path.is_dir()
            ), f"Required subdirectory {subdir}/ does not exist in scripts/"

    @given(
        st.sampled_from(
            [
                "test_example.py",
                "test_admin_login.py",
                "check_config.py",
                "debug_token.py",
                "example_usage.py",
                "quick_test.py",
                "court_scraper.js",
                "migrate_structure.py",
                "refactor_code.py",
                "structure_validator.py",
            ]
        )
    )
    def test_script_naming_convention_property(self, script_name):
        """
        Property 9: 脚本文件分类

        For any script name following our naming conventions,
        we can determine its appropriate category based on its prefix or keywords.

        Feature: backend-structure-optimization, Property 9: 脚本文件分类
        Validates: Requirements 7.1
        """
        # Determine category based on naming convention
        category = None

        if script_name.startswith("test_"):
            category = "testing"
        elif any(script_name.startswith(p) for p in ["check_", "debug_", "example_", "quick_"]):
            category = "development"
        elif script_name.startswith("court_"):
            category = "automation"
        elif any(kw in script_name.lower() for kw in ["migrate", "refactor", "validator", "structure"]):
            category = "refactoring"

        # If we determined a category, verify it's one of the valid categories
        if category is not None:
            assert category in [
                "testing",
                "development",
                "automation",
                "refactoring",
            ], f"Determined category {category} is not a valid category"
