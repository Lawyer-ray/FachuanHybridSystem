import ast
from pathlib import Path


def _backend_root() -> Path:
    return Path(__file__).parent.parent.parent


def test_security_middlewares_are_present_and_ordered():
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
    assert middlewares[0] == "corsheaders.middleware.CorsMiddleware"
    assert "django.middleware.security.SecurityMiddleware" in middlewares
    assert "django.middleware.csrf.CsrfViewMiddleware" in middlewares
    assert "django.middleware.clickjacking.XFrameOptionsMiddleware" in middlewares
    assert "apps.core.middleware_request_id.RequestIdMiddleware" in middlewares
    assert "apps.core.middleware.PermissionsPolicyMiddleware" in middlewares


def test_production_security_settings_are_explicit():
    settings_py = _backend_root() / "apiSystem" / "apiSystem" / "settings.py"
    text = settings_py.read_text(encoding="utf-8")

    assert "if not DEBUG:" in text
    assert "SECURE_HSTS_SECONDS" in text
    assert "SECURE_SSL_REDIRECT" in text
    assert "SESSION_COOKIE_SECURE" in text
    assert "CSRF_COOKIE_SECURE" in text
    assert "SESSION_COOKIE_HTTPONLY" in text
    assert "CSRF_COOKIE_HTTPONLY" in text


def test_production_csp_policy_is_configurable():
    settings_py = _backend_root() / "apiSystem" / "apiSystem" / "settings.py"
    text = settings_py.read_text(encoding="utf-8")
    assert "CONTENT_SECURITY_POLICY_REPORT_ONLY" in text
    assert "CONTENT_SECURITY_POLICY" in text
    assert "CONTENT_SECURITY_POLICY_ENFORCE" in text


def test_deployment_artifacts_explicitly_disable_debug():
    backend_root = _backend_root()
    dockerfile = backend_root / "deploy" / "docker" / "Dockerfile"
    compose = backend_root / "deploy" / "docker" / "docker-compose.yml"
    dockerfile_text = dockerfile.read_text(encoding="utf-8")
    compose_text = compose.read_text(encoding="utf-8")

    assert "DJANGO_DEBUG=0" in dockerfile_text
    assert "DJANGO_DEBUG" in compose_text and "\"0\"" in compose_text
