import ast
from pathlib import Path


def _backend_root() -> Path:
    return Path(__file__).parent.parent.parent


def _uses_csrf_exempt(decorator: ast.expr) -> bool:
    if isinstance(decorator, ast.Name) and decorator.id == "csrf_exempt":
        return True
    if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Name) and decorator.func.id == "method_decorator":
        for arg in decorator.args or []:
            if isinstance(arg, ast.Name) and arg.id == "csrf_exempt":
                return True
    return False


def test_csrf_exempt_is_only_used_in_allowlist():
    backend_root = _backend_root()
    apps_root = backend_root / "apps"

    allowlist = {(apps_root / "core" / "views" / "resource_views.py").resolve().as_posix()}
    violations: list[str] = []

    for py_file in apps_root.rglob("*.py"):
        if "migrations" in py_file.parts:
            continue
        if py_file.resolve().as_posix() in allowlist:
            continue
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
        except Exception:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            for deco in getattr(node, "decorator_list", []) or []:
                if _uses_csrf_exempt(deco):
                    violations.append(f"{py_file}:{getattr(node, 'name', '<unknown>')}")

    assert not violations, "Unexpected csrf_exempt usages:\n" + "\n".join(sorted(violations))


def test_csrf_exempt_view_is_not_wired_in_urls():
    backend_root = _backend_root()
    text = (backend_root / "apiSystem" / "apiSystem" / "urls.py").read_text(encoding="utf-8")
    assert "resource_views" not in text
    assert "ResourceControlView" not in text
