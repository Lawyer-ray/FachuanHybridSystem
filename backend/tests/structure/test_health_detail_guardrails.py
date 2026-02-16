import ast
from pathlib import Path


def test_health_detail_requires_auth():
    backend_root = Path(__file__).parent.parent.parent
    api_py = backend_root / "apiSystem" / "apiSystem" / "api.py"
    tree = ast.parse(api_py.read_text(encoding="utf-8"))

    fn = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "health_check_detail":
            fn = node
            break
    assert fn is not None

    found = False
    for deco in fn.decorator_list:
        if not isinstance(deco, ast.Call):
            continue
        if not isinstance(deco.func, ast.Attribute):
            continue
        if deco.func.attr != "get":
            continue
        for kw in deco.keywords or []:
            if kw.arg != "auth":
                continue
            if (
                isinstance(kw.value, ast.Call)
                and isinstance(kw.value.func, ast.Name)
                and kw.value.func.id == "JWTOrSessionAuth"
            ):
                found = True
    assert found


def test_health_detail_requires_admin():
    backend_root = Path(__file__).parent.parent.parent
    api_py = backend_root / "apiSystem" / "apiSystem" / "api.py"
    tree = ast.parse(api_py.read_text(encoding="utf-8"))

    fn = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "health_check_detail":
            fn = node
            break
    assert fn is not None

    found = False
    for stmt in fn.body:
        if not isinstance(stmt, ast.Expr):
            continue
        call = stmt.value
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id == "ensure_admin_request":
            found = True
    assert found, "health_check_detail 必须调用 ensure_admin_request()"
