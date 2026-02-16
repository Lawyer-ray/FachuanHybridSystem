from unittest import TestCase

from apps.core.config.manager import ConfigManager
from apps.core.config.providers.base import ConfigProvider


class _Provider(ConfigProvider):
    def __init__(self, priority: int, value: str):
        self._priority = priority
        self._value = value

    @property
    def priority(self) -> int:
        return self._priority

    def load(self):
        return {"key": self._value}

    def supports_reload(self) -> bool:
        return False


class TestConfigManagerProviderPriority(TestCase):
    def test_higher_priority_provider_wins(self):
        manager = ConfigManager()
        manager.add_provider(_Provider(priority=10, value="low"))
        manager.add_provider(_Provider(priority=100, value="high"))
        manager.load(force_reload=True)
        self.assertEqual(manager.get("key"), "high")

    def test_priority_sorting_independent_of_insertion_order(self):
        manager = ConfigManager()
        manager.add_provider(_Provider(priority=100, value="high"))
        manager.add_provider(_Provider(priority=10, value="low"))
        manager.load(force_reload=True)
        self.assertEqual(manager.get("key"), "high")
