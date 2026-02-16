from pathlib import Path


def test_proxy_and_forwarded_host_choices_are_explicit():
    backend_root = Path(__file__).parent.parent.parent
    settings_py = backend_root / "apiSystem" / "apiSystem" / "settings.py"
    text = settings_py.read_text(encoding="utf-8")

    assert "DJANGO_SECURE_PROXY_SSL_HEADER" in text
    assert "SECURE_PROXY_SSL_HEADER" in text
    assert "USE_X_FORWARDED_HOST" in text
