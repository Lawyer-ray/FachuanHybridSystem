import time
from unittest import TestCase

from apps.core.config.cache import ConfigCache
from apps.core.config.manager import ConfigManager


class TestConfigManagerCharacterization(TestCase):
    def test_config_cache_lru_eviction(self):
        cache = ConfigCache(max_size=1, ttl=3600.0)
        cache.set("a", 1)
        cache.set("b", 2)
        self.assertIsNone(cache.get("a"))
        self.assertEqual(cache.get("b"), 2)

    def test_config_cache_ttl_expiration(self):
        cache = ConfigCache(max_size=10, ttl=0.01)
        cache.set("a", 1)
        time.sleep(0.02)
        self.assertIsNone(cache.get("a"))

    def test_config_manager_set_and_get_roundtrip(self):
        manager = ConfigManager()
        manager.set("django.debug", True)
        self.assertEqual(manager.get("django.debug"), True)

