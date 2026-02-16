"""
Property-Based Tests for Module README Preservation

Tests that verify Django app module README.md files are preserved in place
after cleanup operations.

**Feature: backend-cleanup-optimization, Property 7: 模块 README 保留**
**Validates: Requirements 6.4**
"""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from apps.core.path import Path


class TestModuleReadmePreservationProperties:
    """
    Property-Based Tests for Module README Preservation

    Feature: backend-cleanup-optimization, Property 7: 模块 README 保留
    Validates: Requirements 6.4
    """

    @pytest.fixture
    def backend_dir(self):
        """Get the backend directory"""
        return Path(__file__).parent.parent.parent

    @pytest.fixture
    def apps_dir(self, backend_dir):
        """Get the apps directory"""
        return backend_dir / "apps"

    # List of Django app modules that should have README.md files
    DJANGO_APP_MODULES = [
        "automation",
        "cases",
        "client",
        "contracts",
        "core",
        "organization",
    ]

    def test_all_django_app_modules_have_readme(self, apps_dir):
        """
        Property 7: 模块 README 保留

        *For any* Django app module, its README.md file should exist.

        Feature: backend-cleanup-optimization, Property 7: 模块 README 保留
        Validates: Requirements 6.4
        """
        missing_readmes = []

        for module_name in self.DJANGO_APP_MODULES:
            module_dir = apps_dir / module_name
            readme_path = module_dir / "README.md"

            if not readme_path.exists():
                missing_readmes.append(module_name)

        assert len(missing_readmes) == 0, (
            f"The following Django app modules are missing README.md files: "
            f"{missing_readmes}. Module README files should be preserved in place."
        )

    def test_module_readme_not_empty(self, apps_dir):
        """
        Property 7: 模块 README 保留

        *For any* Django app module README.md, it should not be empty.

        Feature: backend-cleanup-optimization, Property 7: 模块 README 保留
        Validates: Requirements 6.4
        """
        empty_readmes = []

        for module_name in self.DJANGO_APP_MODULES:
            module_dir = apps_dir / module_name
            readme_path = module_dir / "README.md"

            if readme_path.exists():
                content = readme_path.read_text(encoding="utf-8")
                if len(content.strip()) == 0:
                    empty_readmes.append(module_name)

        assert len(empty_readmes) == 0, (
            f"The following Django app modules have empty README.md files: "
            f"{empty_readmes}. Module README files should contain documentation."
        )

    def test_module_readme_contains_module_name(self, apps_dir):
        """
        Property 7: 模块 README 保留

        *For any* Django app module README.md, it should reference the module name.

        Feature: backend-cleanup-optimization, Property 7: 模块 README 保留
        Validates: Requirements 6.4
        """
        invalid_readmes = []

        for module_name in self.DJANGO_APP_MODULES:
            module_dir = apps_dir / module_name
            readme_path = module_dir / "README.md"

            if readme_path.exists():
                content = readme_path.read_text(encoding="utf-8").lower()
                # Check if module name or related terms appear in README
                if module_name not in content:
                    invalid_readmes.append(module_name)

        assert len(invalid_readmes) == 0, (
            f"The following Django app module READMEs don't reference their module: "
            f"{invalid_readmes}. Module README should document the module."
        )

    @given(st.sampled_from(DJANGO_APP_MODULES))
    def test_module_readme_exists_property(self, module_name):
        """
        Property 7: 模块 README 保留

        *For any* Django app module name, the README.md should exist in that module.

        Feature: backend-cleanup-optimization, Property 7: 模块 README 保留
        Validates: Requirements 6.4
        """
        # Get apps_dir directly since we can't use fixtures with @given
        apps_dir = Path(__file__).parent.parent.parent / "apps"
        module_dir = apps_dir / module_name
        readme_path = module_dir / "README.md"

        assert readme_path.exists(), f"README.md should exist in apps/{module_name}/"

    def test_no_readme_moved_to_docs(self, backend_dir):
        """
        Property 7: 模块 README 保留

        *For any* Django app module, its README.md should NOT be moved to docs/.
        Module READMEs should stay in place.

        Feature: backend-cleanup-optimization, Property 7: 模块 README 保留
        Validates: Requirements 6.4
        """
        docs_dir = backend_dir / "docs"

        # Check that no module README was moved to docs
        for module_name in self.DJANGO_APP_MODULES:
            # Check various possible locations where README might be incorrectly moved
            incorrect_locations = [
                docs_dir / f"{module_name}_README.md",
                docs_dir / module_name / "README.md",
                docs_dir / "modules" / f"{module_name}.md",
            ]

            for incorrect_path in incorrect_locations:
                assert not incorrect_path.exists(), (
                    f"Module README for {module_name} should NOT be at {incorrect_path}. "
                    f"It should remain at apps/{module_name}/README.md"
                )

    def test_readme_is_markdown_format(self, apps_dir):
        """
        Property 7: 模块 README 保留

        *For any* Django app module README.md, it should be valid Markdown format.

        Feature: backend-cleanup-optimization, Property 7: 模块 README 保留
        Validates: Requirements 6.4
        """
        invalid_format = []

        for module_name in self.DJANGO_APP_MODULES:
            module_dir = apps_dir / module_name
            readme_path = module_dir / "README.md"

            if readme_path.exists():
                content = readme_path.read_text(encoding="utf-8")
                # Basic Markdown validation: should have at least one heading
                if not content.strip().startswith("#") and "# " not in content:
                    invalid_format.append(module_name)

        assert len(invalid_format) == 0, (
            f"The following module READMEs don't appear to be valid Markdown: "
            f"{invalid_format}. README files should start with a heading."
        )

    def test_services_readme_preserved(self, apps_dir):
        """
        Property 7: 模块 README 保留

        *For any* services subdirectory with a README.md, it should be preserved.

        Feature: backend-cleanup-optimization, Property 7: 模块 README 保留
        Validates: Requirements 6.4
        """
        # Check automation/services/insurance/README.md specifically
        insurance_readme = apps_dir / "automation" / "services" / "insurance" / "README.md"

        if insurance_readme.parent.exists():
            assert insurance_readme.exists(), "README.md in apps/automation/services/insurance/ should be preserved"
