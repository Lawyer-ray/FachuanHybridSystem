import ast
from pathlib import Path


def get_backend_path() -> Path:
    return Path(__file__).parent.parent.parent


def load_baseline(backend_path: Path) -> set[str]:
    baseline_path = backend_path / "tests" / "structure" / "baselines" / "services_django_settings_imports.txt"
    if not baseline_path.exists():
        return set()
    lines = [line.strip() for line in baseline_path.read_text(encoding="utf-8").splitlines()]
    return {line for line in lines if line and not line.startswith("#")}


ALLOWED_SERVICE_FILES = {
    "apps/automation/services/scraper/core/browser_service.py",
}


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


def imports_django_settings(file_path: Path) -> bool:
    try:
        content = file_path.read_text(encoding="utf-8")
        tree = ast.parse(content)
    except Exception:
        return False

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "django.conf":
            for alias in node.names:
                if alias.name == "settings":
                    return True
    return False


def test_services_should_not_import_django_settings_by_default():
    backend_path = get_backend_path()
    baseline = load_baseline(backend_path)
    offenders: list[str] = []
    for file_path in find_service_files():
        rel = file_path.relative_to(backend_path).as_posix()
        if not imports_django_settings(file_path):
            continue
        if rel in ALLOWED_SERVICE_FILES:
            continue
        offenders.append(rel)

    extra = sorted(set(offenders) - baseline)
    assert extra == [], "发现新增 services 层 settings 导入，请改为注入/组合根解析或显式更新 baseline：\n" + "\n".join(
        extra
    )
