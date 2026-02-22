"""
检查点测试：确认 ServiceLocator, EventBus, Events 导入正常。
"""


def test_import_service_locator_from_interfaces():
    """确认 from apps.core.interfaces import ServiceLocator 正常工作。"""
    from apps.core.interfaces import ServiceLocator

    assert ServiceLocator is not None


def test_import_event_bus_from_interfaces():
    """确认 from apps.core.interfaces import EventBus 正常工作。"""
    from apps.core.interfaces import EventBus  # type: ignore[attr-defined]

    assert EventBus is not None


def test_import_events_from_interfaces():
    """确认 from apps.core.interfaces import Events 正常工作。"""
    from apps.core.interfaces import Events  # type: ignore[attr-defined]

    assert Events is not None


def test_service_locator_is_mixin_version():
    """确认 interfaces 导出的 ServiceLocator 是 mixin 版本（来自 apps.core.service_locator）。"""
    from apps.core.interfaces import ServiceLocator
    from apps.core.service_locator import ServiceLocator as MixinServiceLocator

    assert ServiceLocator is MixinServiceLocator, "interfaces 导出的 ServiceLocator 应该是 mixin 版本"


def test_event_bus_identity():
    """确认 interfaces 导出的 EventBus 与 event_bus 模块中的是同一个对象。"""
    from apps.core.event_bus import EventBus as DirectEventBus
    from apps.core.interfaces import EventBus  # type: ignore[attr-defined]

    assert EventBus is DirectEventBus, "interfaces 导出的 EventBus 应该与 event_bus 模块中的是同一个"
