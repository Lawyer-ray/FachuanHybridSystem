"""
Property-Based Tests for Django App Structure

测试 Django app 结构的一致性
"""

import sys

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from apps.core.path import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from scripts.refactoring.structure_validator import ProjectStructureValidator


# 获取实际存在的 Django apps
def get_existing_apps():
    """获取实际存在的 Django apps"""
    apps_path = project_root / "apps"
    if not apps_path.exists():
        return []

    apps = []
    for item in apps_path.iterdir():
        if item.is_dir() and not item.name.startswith(".") and item.name != "__pycache__":
            apps.append(item.name)

    return apps


# 创建 app 名称策略
existing_apps = get_existing_apps()
if existing_apps:
    app_name_strategy = st.sampled_from(existing_apps)
else:
    # 如果没有 app，使用生成的名称（测试会跳过）
    app_name_strategy = st.text(
        min_size=1,
        max_size=50,
        alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd"), blacklist_characters="_"),
    )


@given(app_name_strategy)
@settings(max_examples=100, deadline=None)
def test_app_structure_consistency_property(app_name):
    """
    Property 1: Django App 结构一致性

    For any Django app in the apps/ directory, it should contain the standard
    directory structure (admin/, api/, services/, and migrations/)

    Feature: backend-structure-optimization, Property 1: Django App 结构一致性
    Validates: Requirements 1.3, 6.1
    """
    # 检查 app 是否存在
    app_path = project_root / "apps" / app_name
    assume(app_path.exists())

    # 创建验证器
    validator = ProjectStructureValidator(project_root)

    # 验证 app 结构
    errors = validator.validate_app_structure(app_name)

    # 断言：不应该有错误
    assert len(errors) == 0, f"App '{app_name}' structure validation failed:\n" + "\n".join(
        f"  - {error}" for error in errors
    )


@pytest.mark.parametrize("app_name", existing_apps)
def test_specific_app_structure(app_name):
    """
    测试特定 app 的结构

    这是一个补充测试，确保所有现有的 app 都符合标准结构
    """
    validator = ProjectStructureValidator(project_root)
    errors = validator.validate_app_structure(app_name)

    assert len(errors) == 0, f"App '{app_name}' structure validation failed:\n" + "\n".join(
        f"  - {error}" for error in errors
    )


def test_all_apps_have_required_directories():
    """
    测试所有 app 都有必需的目录

    验证每个 app 都包含 admin/, api/, services/ 目录
    """
    validator = ProjectStructureValidator(project_root)
    apps = validator.get_app_list()

    if not apps:
        pytest.skip("No apps found")

    failed_apps = {}
    for app_name in apps:
        errors = validator.validate_app_structure(app_name)
        if errors:
            failed_apps[app_name] = errors

    assert len(failed_apps) == 0, f"The following apps have structure issues:\n" + "\n".join(
        f"{app}:\n" + "\n".join(f"  - {error}" for error in errors) for app, errors in failed_apps.items()
    )


def test_all_apps_have_required_files():
    """
    测试所有 app 都有必需的文件

    验证每个 app 都包含 __init__.py, models.py, schemas.py
    """
    apps_path = project_root / "apps"
    if not apps_path.exists():
        pytest.skip("Apps directory does not exist")

    apps = get_existing_apps()
    if not apps:
        pytest.skip("No apps found")

    # Exclude special apps that don't need models.py and schemas.py
    special_apps = {"core", "tests"}

    missing_files = {}
    for app_name in apps:
        app_path = apps_path / app_name

        # core and tests are special apps that don't need models.py and schemas.py
        if app_name in special_apps:
            required_files = ["__init__.py"]
        else:
            required_files = ["__init__.py", "models.py", "schemas.py"]

        app_missing = []
        for file_name in required_files:
            if file_name == "models.py":
                if not (app_path / "models.py").exists() and not (app_path / "models" / "__init__.py").exists():
                    app_missing.append("models.py")
                continue
            if file_name == "schemas.py":
                if not (app_path / "schemas.py").exists() and not (app_path / "schemas" / "__init__.py").exists():
                    app_missing.append("schemas.py")
                continue

            file_path = app_path / file_name
            if not file_path.exists():
                app_missing.append(file_name)

        if app_missing:
            missing_files[app_name] = app_missing

    assert len(missing_files) == 0, f"The following apps are missing required files:\n" + "\n".join(
        f"{app}: {', '.join(files)}" for app, files in missing_files.items()
    )


def test_app_admin_directory_structure():
    """
    测试 app 的 admin 目录结构

    验证 admin 目录包含 __init__.py
    """
    apps_path = project_root / "apps"
    if not apps_path.exists():
        pytest.skip("Apps directory does not exist")

    apps = get_existing_apps()
    if not apps:
        pytest.skip("No apps found")

    issues = {}
    for app_name in apps:
        admin_path = apps_path / app_name / "admin"
        if admin_path.exists():
            init_file = admin_path / "__init__.py"
            if not init_file.exists():
                issues[app_name] = "Missing admin/__init__.py"

    assert len(issues) == 0, f"The following apps have admin directory issues:\n" + "\n".join(
        f"{app}: {issue}" for app, issue in issues.items()
    )


def test_app_api_directory_structure():
    """
    测试 app 的 api 目录结构

    验证 api 目录包含 __init__.py
    """
    apps_path = project_root / "apps"
    if not apps_path.exists():
        pytest.skip("Apps directory does not exist")

    apps = get_existing_apps()
    if not apps:
        pytest.skip("No apps found")

    issues = {}
    for app_name in apps:
        api_path = apps_path / app_name / "api"
        if api_path.exists():
            init_file = api_path / "__init__.py"
            if not init_file.exists():
                issues[app_name] = "Missing api/__init__.py"

    assert len(issues) == 0, f"The following apps have api directory issues:\n" + "\n".join(
        f"{app}: {issue}" for app, issue in issues.items()
    )


def test_app_services_directory_structure():
    """
    测试 app 的 services 目录结构

    验证 services 目录包含 __init__.py
    """
    apps_path = project_root / "apps"
    if not apps_path.exists():
        pytest.skip("Apps directory does not exist")

    apps = get_existing_apps()
    if not apps:
        pytest.skip("No apps found")

    issues = {}
    for app_name in apps:
        services_path = apps_path / app_name / "services"
        if services_path.exists():
            init_file = services_path / "__init__.py"
            if not init_file.exists():
                issues[app_name] = "Missing services/__init__.py"

    assert len(issues) == 0, f"The following apps have services directory issues:\n" + "\n".join(
        f"{app}: {issue}" for app, issue in issues.items()
    )
