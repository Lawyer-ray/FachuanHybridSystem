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


def _pyproject_has(pyproject: Path, package: str) -> bool:
    """检查 pyproject.toml 中是否声明了指定依赖"""
    for raw_line in pyproject.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip().strip('"').strip("'").lower()
        if line.startswith(package.lower()):
            return True
    return False


def test_sentry_sdk_is_declared_when_settings_references_it():
    backend_root = _backend_root()
    settings_py = backend_root / "apiSystem" / "apiSystem" / "settings.py"
    content = settings_py.read_text(encoding="utf-8")
    if "import sentry_sdk" not in content:
        return

    # 2025-02: 项目使用 pyproject.toml 管理依赖，不再使用 requirements.txt
    requirements = backend_root / "requirements.txt"
    pyproject = backend_root / "pyproject.toml"

    if requirements.exists():
        assert _requirements_have(requirements, "sentry-sdk")
    else:
        assert pyproject.exists(), "既无 requirements.txt 也无 pyproject.toml"
        assert _pyproject_has(pyproject, "sentry-sdk"), "pyproject.toml 中未声明 sentry-sdk 依赖"
