import ast
from pathlib import Path


def _has_deletion_call(fn: ast.AST) -> bool:
    for node in ast.walk(fn):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in {"unlink", "remove_p"}:
                return True
            if isinstance(node.func.value, ast.Name) and node.func.value.id == "os" and node.func.attr == "remove":
                return True
    return False


def _has_media_root_boundary_check(fn: ast.AST) -> bool:
    for node in ast.walk(fn):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "relative_to":
            return True
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "to_media_abs":
            return True
    return False


def test_file_deletion_must_check_media_root_boundary():
    backend_root = Path(__file__).parent.parent.parent
    apps_root = backend_root / "apps"

    violations: list[str] = []

    for py_file in apps_root.rglob("*.py"):
        if "migrations" in py_file.parts:
            continue
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
        except Exception:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            arg_names = {a.arg for a in (node.args.args or [])}
            if "file_path" not in arg_names:
                continue
            if not _has_deletion_call(node):
                continue
            if _has_media_root_boundary_check(node):
                continue
            violations.append(f"{py_file}:{node.name}")

    assert not violations, "Missing MEDIA_ROOT boundary checks:\n" + "\n".join(sorted(violations))
