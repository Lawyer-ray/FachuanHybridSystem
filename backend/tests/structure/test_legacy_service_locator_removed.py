from pathlib import Path


def test_interfaces_does_not_define_service_locator_class():
    root = Path(__file__).resolve().parents[2]
    interfaces_py = root / "apps" / "core" / "interfaces.py"
    assert interfaces_py.exists()
    content = interfaces_py.read_text(encoding="utf-8")
    assert "class ServiceLocator" not in content
