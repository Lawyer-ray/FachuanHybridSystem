import ast
from pathlib import Path

import pytest

from .test_cross_module_import_properties import get_backend_path

SERVICE_LOCATOR_MODULES = {
    "apps.core.interfaces",
    "apps.core.service_locator",
}


def load_baseline(backend_path: Path, baseline_filename: str) -> set[str]:
    baseline_path = backend_path / "tests" / "structure" / "baselines" / baseline_filename
    if not baseline_path.exists():
        return set()
    lines = [line.strip() for line in baseline_path.read_text(encoding="utf-8").splitlines()]
    return {line for line in lines if line and not line.startswith("#")}


def has_service_locator_import(file_path: Path) -> bool:
    try:
        content = file_path.read_text(encoding="utf-8")
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module in SERVICE_LOCATOR_MODULES:
                if any(alias.name == "ServiceLocator" for alias in node.names):
                    return True
    except (SyntaxError, UnicodeDecodeError):
        return False
    return False


def find_api_files(backend_path: Path) -> list[Path]:
    apps_dir = backend_path / "apps"
    files: list[Path] = []
    for api_dir in apps_dir.glob("*/api"):
        if not api_dir.is_dir():
            continue
        for py_file in api_dir.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue
            files.append(py_file)
    return files


def find_admin_files(backend_path: Path) -> list[Path]:
    apps_dir = backend_path / "apps"
    files: list[Path] = []
    for admin_dir in apps_dir.glob("*/admin"):
        if not admin_dir.is_dir():
            continue
        for py_file in admin_dir.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue
            files.append(py_file)
    return files


def find_task_files(backend_path: Path) -> list[Path]:
    apps_dir = backend_path / "apps"
    files: list[Path] = []
    patterns = [
        "*/tasks.py",
        "*/tasks_*.py",
        "*/tasks/**/*.py",
        "*/tasks_impl/**/*.py",
        "*/workers/**/*.py",
    ]
    for pattern in patterns:
        for py_file in apps_dir.glob(pattern):
            if py_file.is_file() and py_file.suffix == ".py" and "__pycache__" not in str(py_file):
                files.append(py_file)
    return files


@pytest.mark.property_test
def test_api_layer_no_new_service_locator_imports():
    backend_path = get_backend_path()
    baseline = load_baseline(backend_path, "service_locator_imports_in_api.txt")
    current = {
        file_path.relative_to(backend_path).as_posix()
        for file_path in find_api_files(backend_path)
        if has_service_locator_import(file_path)
    }
    extra = sorted(current - baseline)
    assert (
        len(extra) == 0
    ), "发现新增 API 层 ServiceLocator 导入（请将依赖下沉到 wiring/composition，或显式更新 baseline）:\n" + "\n".join(
        extra
    )


@pytest.mark.property_test
def test_admin_layer_no_new_service_locator_imports():
    backend_path = get_backend_path()
    baseline = load_baseline(backend_path, "service_locator_imports_in_admin.txt")
    current = {
        file_path.relative_to(backend_path).as_posix()
        for file_path in find_admin_files(backend_path)
        if has_service_locator_import(file_path)
    }
    extra = sorted(current - baseline)
    assert (
        len(extra) == 0
    ), (
        "发现新增 Admin 层 ServiceLocator 导入（请通过 wiring/composition 统一装配，或显式更新 baseline）:\n"
        + "\n".join(extra)
    )


@pytest.mark.property_test
def test_task_layer_no_new_service_locator_imports():
    backend_path = get_backend_path()
    baseline = load_baseline(backend_path, "service_locator_imports_in_tasks.txt")
    current = {
        file_path.relative_to(backend_path).as_posix()
        for file_path in find_task_files(backend_path)
        if has_service_locator_import(file_path)
    }
    extra = sorted(current - baseline)
    assert (
        len(extra) == 0
    ), "发现新增任务层 ServiceLocator 导入（请通过 wiring/composition 统一装配，或显式更新 baseline）:\n" + "\n".join(
        extra
    )
