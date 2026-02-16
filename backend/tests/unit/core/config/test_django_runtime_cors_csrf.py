import pytest


def test_resolve_cors_and_csrf_debug_uses_safe_origins():
    from apps.core.config.django_runtime import resolve_cors_and_csrf

    cfg = resolve_cors_and_csrf(debug=True, allow_lan=False, safe_cors_origins=["http://localhost:8000"])
    assert cfg["CORS_ALLOWED_ORIGINS"] == ["http://localhost:8000"]
    assert cfg["CSRF_TRUSTED_ORIGINS"] == ["http://localhost:8000"]


def test_resolve_cors_and_csrf_allow_lan_requires_explicit_env(monkeypatch):
    from apps.core.config.django_runtime import resolve_cors_and_csrf

    monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)
    monkeypatch.delenv("CSRF_TRUSTED_ORIGINS", raising=False)

    with pytest.raises(RuntimeError, match="DJANGO_ALLOW_LAN"):
        resolve_cors_and_csrf(debug=False, allow_lan=True, safe_cors_origins=["http://localhost:8000"])


def test_resolve_cors_and_csrf_production_requires_explicit_env(monkeypatch):
    from apps.core.config.django_runtime import resolve_cors_and_csrf

    monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)
    monkeypatch.delenv("CSRF_TRUSTED_ORIGINS", raising=False)

    with pytest.raises(RuntimeError, match="CORS_ALLOWED_ORIGINS"):
        resolve_cors_and_csrf(debug=False, allow_lan=False, safe_cors_origins=["http://localhost:8000"])


def test_resolve_cors_and_csrf_production_uses_env_values(monkeypatch):
    from apps.core.config.django_runtime import resolve_cors_and_csrf

    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://a.example.com, https://b.example.com")
    monkeypatch.setenv("CSRF_TRUSTED_ORIGINS", "https://a.example.com, https://b.example.com")

    cfg = resolve_cors_and_csrf(debug=False, allow_lan=False, safe_cors_origins=["http://localhost:8000"])
    assert cfg["CORS_ALLOWED_ORIGINS"] == ["https://a.example.com", "https://b.example.com"]
    assert cfg["CSRF_TRUSTED_ORIGINS"] == ["https://a.example.com", "https://b.example.com"]
