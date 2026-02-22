import django.core.cache

from apps.automation.services.document_delivery.document_delivery_schedule_service import (
    DocumentDeliveryScheduleService,
)


def test_document_delivery_schedule_execution_lock_key_is_stable():
    service = DocumentDeliveryScheduleService()
    assert service._get_execution_lock_key(schedule_id=123) == "automation:document_delivery_schedule:123:lock"


def test_document_delivery_schedule_acquire_release_lock_uses_cache(monkeypatch):
    calls: dict[str, list[object]] = {"add": [], "delete": []}

    class FakeCache:
        def add(self, key, value, timeout=None):
            calls["add"].append((key, value, timeout))
            return True

        def delete(self, key):
            calls["delete"].append(key)

    monkeypatch.setattr(django.core.cache, "cache", FakeCache())

    service = DocumentDeliveryScheduleService()
    assert service._acquire_execution_lock(schedule_id=7, ttl_seconds=12) is True
    service._release_execution_lock(schedule_id=7)

    assert calls["add"] == [("automation:document_delivery_schedule:7:lock", "1", 12)]
    assert calls["delete"] == ["automation:document_delivery_schedule:7:lock"]


def test_document_delivery_schedule_acquire_lock_returns_false_when_cache_add_fails(monkeypatch):
    class FakeCache:
        def add(self, key, value, timeout=None):
            return False

        def delete(self, key):
            raise AssertionError("should not delete in this test")

    monkeypatch.setattr(django.core.cache, "cache", FakeCache())

    service = DocumentDeliveryScheduleService()
    assert service._acquire_execution_lock(schedule_id=7, ttl_seconds=12) is False
