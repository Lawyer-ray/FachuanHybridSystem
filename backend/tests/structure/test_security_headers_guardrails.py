import ast
from pathlib import Path


def _backend_root() -> Path:
    return Path(__file__).parent.parent.parent


def test_security_headers_middleware_is_enabled():
    settings_py = _backend_root() / "apiSystem" / "apiSystem" / "settings.py"
    tree = ast.parse(settings_py.read_text(encoding="utf-8"))

    middlewares = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "MIDDLEWARE" for t in node.targets):
            if isinstance(node.value, ast.List):
                items = []
                for elt in node.value.elts:
                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                        items.append(elt.value)
                middlewares = items
                break

    assert middlewares is not None
    assert "apps.core.middleware.SecurityHeadersMiddleware" in middlewares


def test_security_header_settings_exist():
    settings_py = _backend_root() / "apiSystem" / "apiSystem" / "settings.py"
    text = settings_py.read_text(encoding="utf-8")
    for name in (
        "CONTENT_SECURITY_POLICY_REPORT_ONLY",
        "CONTENT_SECURITY_POLICY",
        "CONTENT_SECURITY_POLICY_API_REPORT_ONLY",
        "CONTENT_SECURITY_POLICY_API",
        "CONTENT_SECURITY_POLICY_ADMIN_REPORT_ONLY",
        "CONTENT_SECURITY_POLICY_ADMIN",
        "CROSS_ORIGIN_OPENER_POLICY",
        "CROSS_ORIGIN_RESOURCE_POLICY",
        "CROSS_ORIGIN_EMBEDDER_POLICY",
    ):
        assert name in text
