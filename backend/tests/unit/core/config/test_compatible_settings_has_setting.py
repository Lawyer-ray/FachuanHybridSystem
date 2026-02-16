from unittest import TestCase

from apps.core.config.compatibility import CompatibleSettings
from apps.core.config.manager import ConfigManager


class TestCompatibleSettingsHasSetting(TestCase):
    def test_has_setting_prefers_unified_config(self):
        manager = ConfigManager()
        manager.set("django.debug", True)
        settings = CompatibleSettings(manager)
        self.assertTrue(settings.has_setting("DEBUG"))

    def test_has_setting_unknown_returns_false(self):
        manager = ConfigManager()
        settings = CompatibleSettings(manager)
        self.assertFalse(settings.has_setting("SOME_UNKNOWN_SETTING_12345"))
