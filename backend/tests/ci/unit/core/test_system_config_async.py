"""Tests for SystemConfigService.aget_value async method."""

from __future__ import annotations

import pytest

from apps.core.models.system_config import SystemConfig
from apps.core.services.system_config_service import SystemConfigService


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
class TestAGetValue:
    async def test_returns_value_for_existing_key(self):
        await SystemConfig.objects.acreate(
            key="ASYNC_TEST_KEY_001", value="async_value", is_active=True
        )
        result = await SystemConfigService.aget_value("ASYNC_TEST_KEY_001")
        assert result == "async_value"

    async def test_returns_default_for_missing_key(self):
        result = await SystemConfigService.aget_value("NONEXISTENT_KEY_XYZ", default="fallback")
        assert result == "fallback"

    async def test_ignores_inactive_configs(self):
        await SystemConfig.objects.acreate(
            key="INACTIVE_KEY_ASYNC", value="inactive_value", is_active=False
        )
        result = await SystemConfigService.aget_value("INACTIVE_KEY_ASYNC", default="none")
        assert result == "none"

    async def test_returns_none_when_no_default(self):
        result = await SystemConfigService.aget_value("TOTALLY_NONEXISTENT_KEY_123")
        assert result in (None, "")
