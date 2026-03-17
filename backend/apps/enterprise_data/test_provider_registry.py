from __future__ import annotations

import pytest

from apps.core.exceptions import ValidationException
from apps.enterprise_data.services.provider_registry import EnterpriseProviderRegistry


class _FakeConfigService:
    def __init__(self, values: dict[str, str]) -> None:
        self._values = values

    def get_value(self, key: str, default: str = "") -> str:
        return self._values.get(key, default)


def test_list_providers_contains_tianyancha_and_qichacha() -> None:
    registry = EnterpriseProviderRegistry(config_service=_FakeConfigService({}))
    providers = registry.list_providers()
    names = {item.name for item in providers}
    assert "tianyancha" in names
    assert "qichacha" in names


def test_get_provider_qichacha_disabled_by_default() -> None:
    registry = EnterpriseProviderRegistry(config_service=_FakeConfigService({}))
    with pytest.raises(ValidationException) as exc_info:
        registry.get_provider("qichacha")
    assert exc_info.value.code == "PROVIDER_DISABLED"


def test_get_provider_qichacha_enabled_without_key_raises() -> None:
    registry = EnterpriseProviderRegistry(
        config_service=_FakeConfigService(
            {
                "QICHACHA_MCP_ENABLED": "True",
            }
        )
    )
    with pytest.raises(ValidationException) as exc_info:
        registry.get_provider("qichacha")
    assert exc_info.value.code == "PROVIDER_API_KEY_MISSING"
