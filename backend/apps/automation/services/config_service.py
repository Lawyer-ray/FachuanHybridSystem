"""Business logic services."""

from __future__ import annotations

from typing import Any


class AutomationConfigService:
    def get_automation_config(self) -> dict[str, Any]:
        from apps.core.llm.config import LLMConfig

        return {
            "ollama": {
                "model": LLMConfig.get_ollama_model(),
                "base_url": LLMConfig.get_ollama_base_url(),
            },
            "moonshot": {
                "model": LLMConfig.get_moonshot_default_model(),
                "base_url": LLMConfig.get_moonshot_base_url(),
            },
        }

    def get_system_status(self) -> dict[str, Any]:
        from django.conf import settings

        return {
            "debug": bool(getattr(settings, "DEBUG", False)),
        }
