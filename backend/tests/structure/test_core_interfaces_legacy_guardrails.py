from pathlib import Path


def test_interfaces_does_not_define_legacy_or_event_bus_inline():
    """
    测试 interfaces 包的结构：ServiceLocator 和 EventBus 应该在 service_locator.py 中定义，
    __init__.py 仅作为重导出层。
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
    assert "class EventBus:" not in init_content, "__init__.py 不应该定义 EventBus"
    assert "class Events:" not in init_content, "__init__.py 不应该定义 Events"
    assert "class ServiceLocator:" not in init_content, "__init__.py 不应该定义 ServiceLocator"


def test_legacy_service_locator_file_deleted():
    """
    确认 legacy_service_locator.py 已被删除，ServiceLocator 已统一为 mixin 版本。
    """
    root = Path(__file__).resolve().parents[2]
    legacy_file = root / "apps" / "core" / "legacy_service_locator.py"
    assert not legacy_file.exists(), (
        "legacy_service_locator.py 应该已被删除，ServiceLocator 已统一到 apps.core.service_locator"
    )


def test_service_locator_proxy_file_deleted():
    """
    确认 service_locator_proxy.py 已被删除。
    """
    root = Path(__file__).resolve().parents[2]
    proxy_file = root / "apps" / "core" / "service_locator_proxy.py"
    assert not proxy_file.exists(), "service_locator_proxy.py 应该已被删除"


def test_legacy_service_locator_not_referenced_in_codebase():
    """
    确认代码库中不再有任何对 LegacyServiceLocator 的引用。
    排除：文档文件、备份目录、spec 文件、本测试文件自身。
    """
    root = Path(__file__).resolve().parents[2]

    # 排除列表：文档、备份、spec、本测试文件
    exclude_dirs = {
        root / "docs",
        root.parent / ".kiro",
    }

    offenders: list[Path] = []
    for py in (root / "apps").rglob("*.py"):
        # 跳过排除目录
        if any(py.is_relative_to(d) for d in exclude_dirs):
            continue
        content = py.read_text(encoding="utf-8")
        if "LegacyServiceLocator" in content:
            offenders.append(py)

    assert offenders == [], f"以下文件仍引用 LegacyServiceLocator，应更新为 ServiceLocator: {offenders}"
