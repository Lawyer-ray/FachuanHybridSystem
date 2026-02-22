import pytest

from .test_cross_module_import_properties import extract_service_locator_imports, get_backend_path


@pytest.mark.property_test
def test_api_layer_does_not_import_service_locator():
    backend_path = get_backend_path()
    apps_dir = backend_path / "apps"

    violations: list[tuple[str, int, str]] = []
    for file_path in apps_dir.rglob("api/**/*.py"):
        if file_path.name == "__init__.py":
            continue
        rel = file_path.relative_to(backend_path)
        if rel.parts[:3] == ("apps", "core", "api"):
            continue
        for line, stmt in extract_service_locator_imports(file_path):
            violations.append((str(rel), line, stmt))

    assert len(violations) == 0, (
        "API 层不应直接导入 ServiceLocator，请通过 composition/build_* 或 wiring 统一装配:\n"
        + "\n".join(f"  {path}:{line} - {stmt}" for path, line, stmt in violations)
    )
