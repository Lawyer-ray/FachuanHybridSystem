from pathlib import Path


def test_old_interfaces_monolith_file_deleted():
    """
    确认旧的 interfaces.py 单体文件已被删除，
    interfaces/ 包已完全替代其功能。
    """
    root = Path(__file__).resolve().parents[2]
    interfaces_py = root / "apps" / "core" / "interfaces.py"
    assert not interfaces_py.exists(), "旧的 interfaces.py 单体文件应该已被删除，interfaces/ 包已替代其功能"


def test_interfaces_package_does_not_define_service_locator_class():
    """
    确认 interfaces/ 包的 __init__.py 不直接定义 ServiceLocator 类，
    仅通过重导出提供。
    """
    root = Path(__file__).resolve().parents[2]
    interfaces_dir = root / "apps" / "core" / "interfaces"
    assert interfaces_dir.is_dir(), "interfaces 应该是一个包（目录）"

    init_py = interfaces_dir / "__init__.py"
    assert init_py.exists()
    content = init_py.read_text(encoding="utf-8")
    assert "class ServiceLocator" not in content, (
        "interfaces/__init__.py 不应该定义 ServiceLocator 类，应从 service_locator 模块重导出"
    )
