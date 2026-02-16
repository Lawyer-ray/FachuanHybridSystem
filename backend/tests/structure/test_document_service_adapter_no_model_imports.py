import ast
from pathlib import Path


def _get_backend_root() -> Path:
    return Path(__file__).parent.parent.parent


def _has_models_import(file_path: Path) -> bool:
    content = file_path.read_text(encoding="utf-8")
    tree = ast.parse(content)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module and ".models" in node.module:
                return True
    return False


def test_document_service_adapter_should_not_import_models() -> None:
    root = _get_backend_root()
    adapter = root / "apps" / "documents" / "services" / "document_service_adapter.py"
    assert adapter.exists()
    assert not _has_models_import(adapter)

