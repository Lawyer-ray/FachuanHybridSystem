from pathlib import Path


def test_interfaces_does_not_define_legacy_or_event_bus_inline():
    """
    测试 interfaces 包的结构：ServiceLocator 和 EventBus 应该在 service_locator.py 中定义
    """
    root = Path(__file__).resolve().parents[2]
    interfaces_dir = root / "apps" / "core" / "interfaces"

    # 确认 interfaces 是一个包（目录）
    assert interfaces_dir.is_dir(), "interfaces 应该是一个包（目录）"

    # 确认 service_locator.py 存在
    service_locator_py = interfaces_dir / "service_locator.py"
    assert service_locator_py.exists(), "service_locator.py 应该存在"

    # 确认 __init__.py 不包含这些类的定义（只应该 re-export）
    init_py = interfaces_dir / "__init__.py"
    assert init_py.exists()
    init_content = init_py.read_text(encoding="utf-8")

    # __init__.py 应该只包含 import 和 __all__，不应该定义这些类
    assert "class LegacyServiceLocator" not in init_content, "__init__.py 不应该定义 LegacyServiceLocator"
    assert "class EventBus:" not in init_content, "__init__.py 不应该定义 EventBus"
    assert "class Events:" not in init_content, "__init__.py 不应该定义 Events"
    assert "class ServiceLocator:" not in init_content, "__init__.py 不应该定义 ServiceLocator"


def test_legacy_service_locator_not_used_outside_allowlist():
    root = Path(__file__).resolve().parents[2]
    allow = {
        root / "apps" / "core" / "interfaces" / "__init__.py",
        root / "apps" / "core" / "interfaces" / "service_locator.py",
        root / "apps" / "core" / "legacy_service_locator.py",
    }

    offenders: list[Path] = []
    for py in (root / "apps").rglob("*.py"):
        if py in allow:
            continue
        if "LegacyServiceLocator" in py.read_text(encoding="utf-8"):
            offenders.append(py)

    assert offenders == []
