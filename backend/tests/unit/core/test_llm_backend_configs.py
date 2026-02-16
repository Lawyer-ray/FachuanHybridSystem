import pytest
from django.conf import settings

from apps.core.llm.config import LLMConfig


@pytest.fixture(autouse=True)
def _disable_system_config_service(monkeypatch):
    monkeypatch.setattr(LLMConfig, "_get_config_service", classmethod(lambda cls: None))
    yield


def test_get_default_backend_falls_back_to_settings(monkeypatch):
    monkeypatch.setattr(settings, "LLM", {"DEFAULT_BACKEND": "ollama"}, raising=False)
    assert LLMConfig.get_default_backend() == "ollama"


def test_get_backend_configs_parses_enabled_and_priority(monkeypatch):
    def fake_get_system_config(cls, key: str, default: str = "") -> str:
        mapping = {
            "LLM_BACKEND_SILICONFLOW_ENABLED": "false",
            "LLM_BACKEND_OLLAMA_PRIORITY": "10",
            "LLM_BACKEND_MOONSHOT_ENABLED": "True",
            "LLM_BACKEND_MOONSHOT_PRIORITY": "2",
        }
        return mapping.get(key, default)

    monkeypatch.setattr(LLMConfig, "_get_system_config", classmethod(fake_get_system_config))

    configs = LLMConfig.get_backend_configs()
    assert configs["siliconflow"].enabled is False
    assert configs["ollama"].priority == 10
    assert configs["moonshot"].enabled is True
    assert configs["moonshot"].priority == 2
