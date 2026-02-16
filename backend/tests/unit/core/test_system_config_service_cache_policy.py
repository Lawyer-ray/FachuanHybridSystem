from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.core.services.system_config_service import SystemConfigService, _MISSING_SENTINEL


class _FakeModel:
    class DoesNotExist(Exception):
        pass

    def __init__(self):
        self.objects = MagicMock()


class SystemConfigServiceCachePolicyTest(SimpleTestCase):
    def test_missing_sentinel_returns_default(self):
        model = _FakeModel()
        service = SystemConfigService(model=model)

        with patch("apps.core.services.system_config_service.cache.get", return_value=_MISSING_SENTINEL):
            out = service.get_value("X", default="D")

        self.assertEqual(out, "D")
        model.objects.get.assert_not_called()

    def test_cache_negative_on_missing_row(self):
        model = _FakeModel()
        model.objects.get.side_effect = model.DoesNotExist()
        service = SystemConfigService(model=model)

        with patch("apps.core.services.system_config_service.cache.get", return_value=None), patch(
            "apps.core.services.system_config_service.cache.set"
        ) as set_mock:
            out = service.get_value("X", default="D")

        self.assertEqual(out, "D")
        set_mock.assert_called()
        args, kwargs = set_mock.call_args
        self.assertEqual(args[0], "system_config:X")
        self.assertEqual(args[1], _MISSING_SENTINEL)
        self.assertIn("timeout", kwargs)
