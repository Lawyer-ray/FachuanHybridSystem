import pytest


def _default_args():
    return {
        "dev_secret_key": "django-insecure-dev-only-do-not-use-in-production",
        "default_allowed_hosts_dev": ["localhost"],
        "default_allowed_hosts_prod": ["example.com"],
    }


@pytest.mark.parametrize(
    "env_secret_key",
    [
        "",
        "change-me-in-production",
        "django-insecure-123",
        "short",
        "x" * 49,
    ],
)
def test_resolve_security_config_production_requires_secure_secret_key(monkeypatch, env_secret_key):
    from cryptography.fernet import Fernet

    from apps.core.config.django_runtime import resolve_security_config

    monkeypatch.setenv("DJANGO_DEBUG", "0")
    monkeypatch.setenv("DJANGO_SECRET_KEY", env_secret_key)
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode())

    with pytest.raises(RuntimeError, match="DJANGO_SECRET_KEY"):
        resolve_security_config(**_default_args())


def test_resolve_security_config_production_accepts_long_secret_key(monkeypatch):
    from cryptography.fernet import Fernet

    from apps.core.config.django_runtime import resolve_security_config

    monkeypatch.setenv("DJANGO_DEBUG", "0")
    monkeypatch.setenv("DJANGO_SECRET_KEY", "x" * 64)
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode())

    cfg = resolve_security_config(**_default_args())
    assert cfg.is_production is True
    assert cfg.secret_key == "x" * 64
