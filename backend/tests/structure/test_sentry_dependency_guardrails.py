from pathlib import Path


def _backend_root() -> Path:
    return Path(__file__).parent.parent.parent


def _requirements_have(requirements: Path, package: str) -> bool:
    for raw_line in requirements.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith(package.lower()):
            return True
    return False


def test_sentry_sdk_is_declared_when_settings_references_it():
    backend_root = _backend_root()
    settings_py = backend_root / "apiSystem" / "apiSystem" / "settings.py"
    content = settings_py.read_text(encoding="utf-8")
    if "import sentry_sdk" not in content:
        return

    assert _requirements_have(backend_root / "requirements.txt", "sentry-sdk")
