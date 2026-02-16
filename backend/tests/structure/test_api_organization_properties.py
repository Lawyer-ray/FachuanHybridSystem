"""
Property-Based Tests for API File Organization

Feature: backend-structure-optimization, Property 7: API 文件组织规范
Validates: Requirements 6.3
"""

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

from apps.core.path import Path

# 定义所有 Django app（排除 core 和 tests）
DJANGO_APPS = ["automation", "cases", "client", "contracts", "organization"]


@pytest.mark.property_test
def test_api_directory_exists():
    """
    Property 7: API 文件组织规范

    For any Django app with API endpoints, the api/ directory should exist
    and contain files named after the resources they handle

    Validates: Requirements 6.3
    """
    backend_path = Path(__file__).parent.parent.parent
    apps_path = backend_path / "apps"

    errors = []

    for app_name in DJANGO_APPS:
        app_path = apps_path / app_name

        # 检查 app 是否存在
        if not app_path.exists():
            errors.append(f"App {app_name} does not exist")
            continue

        # 检查 api/ 目录是否存在
        api_dir = app_path / "api"
        if not api_dir.exists():
            errors.append(f"App {app_name} missing api/ directory")
            continue

        # 检查 api/ 目录是否有 __init__.py
        api_init = api_dir / "__init__.py"
        if not api_init.exists():
            errors.append(f"App {app_name} api/ directory missing __init__.py")

        # 检查是否有 API 文件（至少一个 *_api.py）
        api_files = list(api_dir.glob("*_api.py"))
        if len(api_files) == 0:
            errors.append(f"App {app_name} api/ directory has no *_api.py files")

    assert len(errors) == 0, f"API organization validation failed:\n" + "\n".join(f"  - {e}" for e in errors)


@pytest.mark.property_test
def test_api_files_follow_naming_convention():
    """
    Property 7: API 文件命名规范

    For any API file in the api/ directory, it should follow the
    naming convention: [resource_name]_api.py

    Validates: Requirements 6.3
    """
    backend_path = Path(__file__).parent.parent.parent
    apps_path = backend_path / "apps"

    errors = []

    for app_name in DJANGO_APPS:
        app_path = apps_path / app_name
        api_dir = app_path / "api"

        if not api_dir.exists():
            continue

        # 检查所有 Python 文件
        for py_file in api_dir.glob("*.py"):
            if py_file.name == "__init__.py":
                continue

            # 检查文件名是否以 _api.py 结尾
            if not py_file.name.endswith("_api.py"):
                errors.append(
                    f"App {app_name}: API file {py_file.name} does not follow " f"naming convention (*_api.py)"
                )

    assert len(errors) == 0, f"API file naming validation failed:\n" + "\n".join(f"  - {e}" for e in errors)


@pytest.mark.property_test
def test_root_api_py_is_import_only():
    """
    Property 7: 根目录 api.py 只用于导入

    For any Django app, if it has a root api.py file, it should only
    contain imports from the api/ subdirectory

    Validates: Requirements 6.3
    """
    backend_path = Path(__file__).parent.parent.parent
    apps_path = backend_path / "apps"

    errors = []

    for app_name in DJANGO_APPS:
        app_path = apps_path / app_name
        root_api = app_path / "api.py"

        if not root_api.exists():
            continue

        # 读取文件内容
        content = root_api.read_text()

        # 检查是否包含 @router 装饰器（不应该有）
        if "@router." in content and "import" not in content.split("@router.")[0].split("\n")[-1]:
            errors.append(
                f"App {app_name}: root api.py contains @router decorator. " f"API routes should be in api/ subdirectory"
            )

        # 检查是否包含 Router() 实例化（不应该有，除非是导入）
        lines = content.split("\n")
        for i, line in enumerate(lines):
            if "Router(" in line and "=" in line:
                # 检查是否是导入语句
                if "from" not in line and "import" not in line:
                    # 检查前面几行是否有 import
                    is_import = False
                    for j in range(max(0, i - 3), i):
                        if "from" in lines[j] or "import" in lines[j]:
                            is_import = True
                            break

                    if not is_import:
                        errors.append(
                            f"App {app_name}: root api.py contains Router instantiation. "
                            f"Routers should be defined in api/ subdirectory"
                        )
                        break

    assert len(errors) == 0, f"Root api.py validation failed:\n" + "\n".join(f"  - {e}" for e in errors)


@pytest.mark.property_test
def test_api_files_contain_router():
    """
    Property 7: API 文件包含 Router

    For any API file in the api/ directory (except __init__.py),
    it should define a Router instance

    Validates: Requirements 6.3
    """
    backend_path = Path(__file__).parent.parent.parent
    apps_path = backend_path / "apps"

    errors = []

    for app_name in DJANGO_APPS:
        app_path = apps_path / app_name
        api_dir = app_path / "api"

        if not api_dir.exists():
            continue

        # 检查所有 *_api.py 文件
        for api_file in api_dir.glob("*_api.py"):
            content = api_file.read_text()

            # 检查是否定义了 router
            if "router = Router(" not in content and "router=Router(" not in content:
                errors.append(f"App {app_name}: API file {api_file.name} does not define a Router instance")

    assert len(errors) == 0, f"API Router validation failed:\n" + "\n".join(f"  - {e}" for e in errors)


@given(st.sampled_from(DJANGO_APPS))
@pytest.mark.property_test
def test_api_directory_structure_property(app_name):
    """
    Property 7: API 目录结构一致性

    For any Django app, the api/ directory should have a consistent structure:
    - api/__init__.py exists
    - api/*_api.py files exist
    - root api.py (if exists) only imports from api/

    Validates: Requirements 6.3
    """
    backend_path = Path(__file__).parent.parent.parent
    app_path = backend_path / "apps" / app_name

    # 假设 app 存在
    assume(app_path.exists())

    api_dir = app_path / "api"

    # 验证 api/ 目录存在
    assert api_dir.exists(), f"App {app_name} missing api/ directory"

    # 验证 api/__init__.py 存在
    api_init = api_dir / "__init__.py"
    assert api_init.exists(), f"App {app_name} api/ directory missing __init__.py"

    # 验证至少有一个 *_api.py 文件
    api_files = list(api_dir.glob("*_api.py"))
    assert len(api_files) > 0, f"App {app_name} api/ directory has no *_api.py files"
