from pathlib import Path

import pytest

from .test_cross_module_import_properties import extract_service_locator_imports, get_backend_path


def load_baseline(backend_path: Path) -> set[str]:
    baseline_path = backend_path / "tests" / "structure" / "baselines" / "service_locator_imports_in_services.txt"
    if not baseline_path.exists():
        return set()
    lines = [line.strip() for line in baseline_path.read_text(encoding="utf-8").splitlines()]
    return {line for line in lines if line and not line.startswith("#")}


def find_service_files() -> list[Path]:
    backend_path = get_backend_path()
    services_dirs = [p for p in (backend_path / "apps").glob("*/services") if p.is_dir()]
    files: list[Path] = []
    for services_dir in services_dirs:
        for py_file in services_dir.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue
            files.append(py_file)
    return files


def is_allowed_service_file(rel_path: str) -> bool:
    if rel_path.startswith("apps/core/"):
        return True
    if rel_path.endswith("/wiring.py") or rel_path.endswith("_wiring.py"):
        return True
    if "/wiring/" in rel_path:
        return True
    return False


@pytest.mark.property_test
def test_services_layer_does_not_import_service_locator():
    backend_path = get_backend_path()
    baseline = load_baseline(backend_path)
    violations: list[tuple[str, int, str]] = []

    for file_path in find_service_files():
        rel = file_path.relative_to(backend_path).as_posix()
        if is_allowed_service_file(rel):
            continue
        for line, stmt in extract_service_locator_imports(file_path):
            violations.append((rel, line, stmt))

    current = {f"{path}:{line}:{stmt}" for path, line, stmt in violations}
    extra = sorted(current - baseline)
    assert (
        len(extra) == 0
    ), "发现新增 services 层 ServiceLocator 导入（请通过依赖注入/组合根装配，或显式更新 baseline）:\n" + "\n".join(
        extra
    )
