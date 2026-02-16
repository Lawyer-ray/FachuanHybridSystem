import ast
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).parent.parent.parent


def _contains_objects_write_call(func: ast.FunctionDef) -> bool:
    write_names = {"create", "update", "delete"}

    for node in ast.walk(func):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in write_names:
            continue

        cursor = node.func.value
        while cursor is not None:
            if isinstance(cursor, ast.Attribute) and cursor.attr == "objects":
                return True
            if isinstance(cursor, ast.Call) and isinstance(cursor.func, ast.Attribute):
                cursor = cursor.func.value
                continue
            if isinstance(cursor, ast.Attribute):
                cursor = cursor.value
                continue
            break

    return False


def test_case_service_adapter_has_no_direct_orm_writes() -> None:
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
    for item in adapter.body:
        if isinstance(item, ast.FunctionDef):
            if _contains_objects_write_call(item):
                offenders.append(item.name)

    assert not offenders, f"CaseServiceAdapter contains direct ORM writes in methods: {sorted(offenders)}"
