import re
from pathlib import Path

from .test_cross_module_import_properties import get_backend_path

GETATTR_SERVICE_PATTERN = re.compile(r"getattr\([^\n]*,\s*['\"]service['\"]")


def _iter_service_files(backend_path: Path) -> list[Path]:
    services_dirs = [p for p in (backend_path / "apps").glob("*/services") if p.is_dir()]
    files: list[Path] = []
    for services_dir in services_dirs:
        for py_file in services_dir.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue
            files.append(py_file)
    return files


def test_services_layer_does_not_use_getattr_service_hack():
    backend_path = get_backend_path()
    violations: list[tuple[str, int, str]] = []

    for file_path in _iter_service_files(backend_path):
        rel = file_path.relative_to(backend_path).as_posix()
        content = file_path.read_text(encoding="utf-8")
        for idx, line in enumerate(content.splitlines(), start=1):
            if GETATTR_SERVICE_PATTERN.search(line):
                violations.append((rel, idx, line.strip()))

    assert len(violations) == 0, (
        "services 层禁止通过 getattr(..., 'service') 访问 Adapter 内部字段，请改为 wiring 显式注入:\n"
        + "\n".join(f"  {path}:{line} - {stmt}" for path, line, stmt in violations)
    )
