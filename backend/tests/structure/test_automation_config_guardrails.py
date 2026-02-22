import ast
from pathlib import Path


def test_automation_config_endpoint_is_admin_guarded(): # noqa: C901
    backend_root = Path(__file__).parent.parent.parent
    api_py = backend_root / "apps" / "automation" / "api" / "main_api.py"
    tree = ast.parse(api_py.read_text(encoding="utf-8"))

    get_config = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "get_config":
            get_config = node
            break

    assert get_config is not None

    has_admin_rate_limit = False
    for deco in get_config.decorator_list:
        if not isinstance(deco, ast.Call):
            continue
        if not isinstance(deco.func, ast.Name):
            continue
        if deco.func.id != "rate_limit_from_settings":
            continue
        if not deco.args:
            continue
        if isinstance(deco.args[0], ast.Constant) and deco.args[0].value == "ADMIN":
            has_admin_rate_limit = True

    assert has_admin_rate_limit

    has_admin_guard = False
    for call in ast.walk(get_config):
        if not isinstance(call, ast.Call):
            continue
        if isinstance(call.func, ast.Name) and call.func.id == "ensure_admin_request":
            has_admin_guard = True
            break

    assert has_admin_guard
