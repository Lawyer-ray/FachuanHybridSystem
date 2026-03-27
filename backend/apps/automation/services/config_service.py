"""Business logic services."""

from __future__ import annotations

from typing import Any


class AutomationConfigService:
    def get_automation_config(self) -> dict[str, Any]:
        from apps.core.llm.config import LLMConfig

        return {
            "default_backend": LLMConfig.get_default_backend(),
            "siliconflow": {
                "model": LLMConfig.get_default_model(),
                "embedding_model": LLMConfig.get_embedding_model(),
                "base_url": LLMConfig.get_base_url(),
            },
            "ollama": {
                "model": LLMConfig.get_ollama_model(),
                "embedding_model": LLMConfig.get_ollama_embedding_model(),
                "base_url": LLMConfig.get_ollama_base_url(),
            },
            "openai_compatible": {
                "model": LLMConfig.get_openai_compatible_model(),
                "embedding_model": LLMConfig.get_openai_compatible_embedding_model(),
                "base_url": LLMConfig.get_openai_compatible_base_url(),
            },
        }

    def get_system_status(self) -> dict[str, Any]:
        from apps.core.services.system_config_service import SystemConfigService

        svc = SystemConfigService()
        debug_val = svc.get_value("DEBUG_MODE", "false")
        return {
            "debug": debug_val.lower() in ("true", "1", "yes"),
        }
