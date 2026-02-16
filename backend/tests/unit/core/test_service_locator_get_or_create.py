from django.test import TestCase

from apps.core.service_locator_base import BaseServiceLocator


class _DummyLocator(BaseServiceLocator):
    _services = {}


class ServiceLocatorGetOrCreateTest(TestCase):
    def setUp(self):
        _DummyLocator.clear()

    def test_get_or_create_caches_singleton(self):
        calls = {"n": 0}

        def factory():
            calls["n"] += 1
            return object()

        a = _DummyLocator.get_or_create("x", factory)
        b = _DummyLocator.get_or_create("x", factory)
        self.assertIs(a, b)
        self.assertEqual(calls["n"], 1)

