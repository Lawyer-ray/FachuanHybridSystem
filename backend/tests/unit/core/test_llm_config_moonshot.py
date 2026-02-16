import pytest
from django.conf import settings

from apps.core.llm.config import LLMConfig


@pytest.fixture(autouse=True)
def _disable_system_config_service(monkeypatch):
    monkeypatch.setattr(LLMConfig, "_get_config_service", classmethod(lambda cls: None))
    yield


def test_moonshot_config_fallback_to_settings(monkeypatch):
    monkeypatch.setattr(
        settings,
        "MOONSHOT",
        {"API_KEY": "Bearer test_key", "BASE_URL": "https://api.moonshot.cn/v1/", "DEFAULT_MODEL": "  m1 ", "TIMEOUT": "120"},
        raising=False,
    )

    assert LLMConfig.get_moonshot_api_key() == "test_key"
    assert LLMConfig.get_moonshot_base_url() == "https://api.moonshot.cn/v1"
    assert LLMConfig.get_moonshot_default_model() == "m1"
    assert LLMConfig.get_moonshot_timeout() == 120


def test_moonshot_config_defaults_when_missing(monkeypatch):
    if hasattr(settings, "MOONSHOT"):
        monkeypatch.delattr(settings, "MOONSHOT", raising=False)

    assert LLMConfig.get_moonshot_api_key() == ""
    assert LLMConfig.get_moonshot_base_url() == LLMConfig.DEFAULT_MOONSHOT_BASE_URL.rstrip("/")
    assert LLMConfig.get_moonshot_default_model() == LLMConfig.DEFAULT_MOONSHOT_MODEL
    assert LLMConfig.get_moonshot_timeout() == LLMConfig.DEFAULT_MOONSHOT_TIMEOUT
