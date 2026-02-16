import ast
from pathlib import Path


def _backend_root() -> Path:
    return Path(__file__).parent.parent.parent


def _read_ast(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _find_function(tree: ast.Module, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def _has_rate_limit_decorator(fn: ast.FunctionDef | ast.AsyncFunctionDef, kind: str) -> bool:
    for deco in fn.decorator_list:
        if not isinstance(deco, ast.Call):
            continue
        if not isinstance(deco.func, ast.Name):
            continue
        if deco.func.id != "rate_limit_from_settings":
            continue
        if not deco.args:
            continue
        arg0 = deco.args[0]
        if isinstance(arg0, ast.Constant) and arg0.value == kind:
            return True
    return False


def _rate_limit_kinds(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    kinds: set[str] = set()
    for deco in fn.decorator_list:
        if not isinstance(deco, ast.Call):
            continue
        if not isinstance(deco.func, ast.Name):
            continue
        if deco.func.id != "rate_limit_from_settings":
            continue
        if not deco.args:
            continue
        arg0 = deco.args[0]
        if isinstance(arg0, ast.Constant) and isinstance(arg0.value, str):
            kinds.add(arg0.value)
    return kinds


def test_token_rate_limit_middleware_is_enabled():
    settings_py = _backend_root() / "apiSystem" / "apiSystem" / "settings.py"
    content = settings_py.read_text(encoding="utf-8")
    assert "apps.core.middleware.ApiRateLimitMiddleware" in content


def test_llm_endpoints_are_rate_limited():
    path = _backend_root() / "apps" / "core" / "api" / "ninja_llm_api.py"
    tree = _read_ast(path)
    fn = _find_function(tree, "chat_with_context")
    assert fn is not None
    assert _has_rate_limit_decorator(fn, "LLM")

    fn = _find_function(tree, "chat_with_context_stream")
    assert fn is not None
    assert _has_rate_limit_decorator(fn, "LLM")


def test_register_endpoint_is_rate_limited():
    path = _backend_root() / "apps" / "organization" / "api" / "auth_api.py"
    tree = _read_ast(path)
    fn = _find_function(tree, "login_view")
    assert fn is not None
    assert _has_rate_limit_decorator(fn, "AUTH")


def test_upload_and_export_endpoints_are_rate_limited():
    chat_api = _backend_root() / "apps" / "chat_records" / "api" / "chat_records_api.py"
    tree = _read_ast(chat_api)

    fn = _find_function(tree, "upload_recording")
    assert fn is not None
    assert _has_rate_limit_decorator(fn, "UPLOAD")

    fn = _find_function(tree, "download_export")
    assert fn is not None
    assert _has_rate_limit_decorator(fn, "EXPORT")


def test_high_risk_endpoints_are_rate_limited_systematically():
    backend_root = _backend_root()
    api_roots = [
        backend_root / "apps",
    ]
    http_methods = {"get", "post", "put", "patch", "delete"}
    export_keywords = ("export", "download")
    llm_keywords = ("llm", "chat", "suggest-rename")
    upload_keywords = ("upload", "import", "ocr", "extract", "process", "submit")

    missing: list[str] = []

    for root in api_roots:
        for path in root.rglob("api/**/*.py"):
            if path.name == "__init__.py":
                continue
            try:
                tree = _read_ast(path)
            except SyntaxError as e:
                raise AssertionError(f"无法解析 {path}: {e}") from e

            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue

                endpoints: list[tuple[str, str]] = []
                for deco in node.decorator_list:
                    if not isinstance(deco, ast.Call):
                        continue
                    if not isinstance(deco.func, ast.Attribute):
                        continue
                    if deco.func.attr not in http_methods:
                        continue
                    if not deco.args:
                        continue
                    arg0 = deco.args[0]
                    if not (isinstance(arg0, ast.Constant) and isinstance(arg0.value, str)):
                        continue
                    route_path = arg0.value
                    if not route_path.startswith("/"):
                        continue
                    endpoints.append((deco.func.attr, route_path))

                if not endpoints:
                    continue

                expected: set[str] = set()
                for method, route_path in endpoints:
                    p = route_path.lower()
                    if any(k in p for k in export_keywords):
                        expected.update({"EXPORT", "TASK"})
                    elif any(k in p for k in llm_keywords):
                        expected.update({"LLM", "LLM_HISTORY", "ADMIN"})
                    elif method.lower() in ("post", "put", "patch", "delete") and any(k in p for k in upload_keywords):
                        expected.update({"UPLOAD", "TASK"})

                if not expected:
                    continue

                actual = _rate_limit_kinds(node)
                if not (actual & expected):
                    missing.append(f"{path.relative_to(backend_root)}:{node.name} expected={sorted(expected)} actual={sorted(actual)}")

    assert not missing, "以下高风险端点缺少 rate_limit_from_settings：\n" + "\n".join(sorted(missing))


def test_trust_x_forwarded_for_requires_trusted_proxy_ips_in_production():
    settings_py = _backend_root() / "apiSystem" / "apiSystem" / "settings.py"
    content = settings_py.read_text(encoding="utf-8")
    assert "DJANGO_TRUST_X_FORWARDED_FOR" in content
    assert "DJANGO_TRUSTED_PROXY_IPS" in content
    assert "启用 DJANGO_TRUST_X_FORWARDED_FOR 必须配置 DJANGO_TRUSTED_PROXY_IPS" in content
