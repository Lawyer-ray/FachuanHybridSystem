import ast
from pathlib import Path


def test_resource_metrics_endpoints_are_admin_only_and_rate_limited(): # noqa: C901
    backend_root = Path(__file__).parent.parent.parent
    api_py = backend_root / "apiSystem" / "apiSystem" / "api.py"
    tree = ast.parse(api_py.read_text(encoding="utf-8"))

    targets = {
        "resource_status",
        "resource_usage",
        "resource_recommendations",
        "resource_health",
        "resource_metrics",
        "resource_metrics_prometheus",
    }
    found: dict[str, ast.FunctionDef] = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in targets:
            found[node.name] = node

    assert targets.issubset(found.keys())

    for name, fn in found.items():
        if name in {"resource_metrics", "resource_metrics_prometheus"}:
            has_rate_limit = False
            for deco in fn.decorator_list:
                if not isinstance(deco, ast.Call):
                    continue
                if isinstance(deco.func, ast.Name) and deco.func.id == "rate_limit_from_settings":
                    if deco.args and isinstance(deco.args[0], ast.Constant) and deco.args[0].value == "EXPORT":
                        has_rate_limit = True
            assert has_rate_limit, f"{name} must be rate limited"

        has_admin_guard = False
        for stmt in fn.body:
            if not isinstance(stmt, ast.Expr):
                continue
            call = stmt.value
            if isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id == "_require_admin":
                has_admin_guard = True
        assert has_admin_guard, f"{name} must call _require_admin()"
