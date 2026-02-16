import ast
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).parent.parent.parent


def test_case_service_adapter_does_not_use_model_objects() -> None:
    root = _project_root()
    file_path = root / "apps" / "cases" / "services" / "case" / "case_service_adapter.py"
    tree = ast.parse(file_path.read_text(encoding="utf-8"))

    adapter = None
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "CaseServiceAdapter":
            adapter = node
            break
    assert adapter is not None, "CaseServiceAdapter class not found"

    offenders = []
    for node in ast.walk(adapter):
        if isinstance(node, ast.Attribute) and node.attr == "objects":
            offenders.append((node.lineno, node.col_offset))

    assert not offenders, f"CaseServiceAdapter should not reference Model.objects, found at: {offenders}"
