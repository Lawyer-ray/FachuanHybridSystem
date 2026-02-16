import ast
from pathlib import Path


def _get_backend_root() -> Path:
    return Path(__file__).parent.parent.parent


def _has_contracts_services_import(file_path: Path) -> bool:
    content = file_path.read_text(encoding="utf-8")
    tree = ast.parse(content)

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module and node.module.startswith("apps.contracts.services"):
                return True
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("apps.contracts.services"):
                    return True
    return False


def test_documents_api_should_not_import_contracts_services() -> None:
    root = _get_backend_root()
    api_dir = root / "apps" / "documents" / "api"
    assert api_dir.exists()

    offenders = []
    for file_path in api_dir.glob("*.py"):
        if _has_contracts_services_import(file_path):
            offenders.append(file_path)

    assert offenders == []
