"""Tests for apps/automation/services/config_service.py — AutomationConfigService."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from types import SimpleNamespace


class TestAutomationConfigService:
    """AutomationConfigService 单元测试。"""

    def _make_service(self):
        from apps.automation.services.config_service import AutomationConfigService

        return AutomationConfigService()

    def test_get_automation_config_returns_dict(self) -> None:
        """get_automation_config 返回包含三个后端配置的字典。"""
        mock_llm_cfg = MagicMock()
        mock_llm_cfg.get_default_backend.return_value = "openai_compatible"
        mock_llm_cfg.get_default_model.return_value = "gpt-4"
        mock_llm_cfg.get_embedding_model.return_value = "emb-1"
        mock_llm_cfg.get_openai_compatible_base_url.return_value = "http://116.196.92.175:8001/v1"
        mock_llm_cfg.get_ollama_model.return_value = "qwen2"
        mock_llm_cfg.get_ollama_embedding_model.return_value = "nomic-embed"
        mock_llm_cfg.get_ollama_base_url.return_value = "http://localhost:11434"
        mock_llm_cfg.get_openai_compatible_model.return_value = "gpt-4o"
        mock_llm_cfg.get_openai_compatible_embedding_model.return_value = "text-embed"
        mock_llm_cfg.get_openai_compatible_base_url.return_value = "https://api.openai.com"

        with patch("apps.core.llm.config.LLMConfig", mock_llm_cfg):
            svc = self._make_service()
            result = svc.get_automation_config()

        assert "default_backend" in result
        assert "openai_compatible" in result
        assert "ollama" in result
        assert result["default_backend"] == "openai_compatible"

    def test_openai_compatible_section(self) -> None:
        """openai_compatible 部分包含 model/embedding_model/base_url。"""
        mock_llm_cfg = MagicMock()
        mock_llm_cfg.get_default_backend.return_value = "openai_compatible"
        mock_llm_cfg.get_openai_compatible_model.return_value = "m1"
        mock_llm_cfg.get_openai_compatible_embedding_model.return_value = "e1"
        mock_llm_cfg.get_openai_compatible_base_url.return_value = "http://116.196.92.175:8001/v1"
        mock_llm_cfg.get_ollama_model.return_value = ""
        mock_llm_cfg.get_ollama_embedding_model.return_value = ""
        mock_llm_cfg.get_ollama_base_url.return_value = ""

        with patch("apps.core.llm.config.LLMConfig", mock_llm_cfg):
            svc = self._make_service()
            result = svc.get_automation_config()
        assert result["openai_compatible"]["model"] == "m1"
        assert result["openai_compatible"]["embedding_model"] == "e1"
        assert result["openai_compatible"]["base_url"] == "http://116.196.92.175:8001/v1"

    def test_ollama_section(self) -> None:
        """ollama 部分包含正确的配置。"""
        mock_llm_cfg = MagicMock()
        mock_llm_cfg.get_default_backend.return_value = "ollama"
        mock_llm_cfg.get_default_model.return_value = ""
        mock_llm_cfg.get_embedding_model.return_value = ""
        mock_llm_cfg.get_base_url.return_value = ""
        mock_llm_cfg.get_ollama_model.return_value = "qwen2:7b"
        mock_llm_cfg.get_ollama_embedding_model.return_value = "nomic-embed-text"
        mock_llm_cfg.get_ollama_base_url.return_value = "http://localhost:11434"
        mock_llm_cfg.get_openai_compatible_model.return_value = ""
        mock_llm_cfg.get_openai_compatible_embedding_model.return_value = ""
        mock_llm_cfg.get_openai_compatible_base_url.return_value = ""

        with patch("apps.core.llm.config.LLMConfig", mock_llm_cfg):
            svc = self._make_service()
            result = svc.get_automation_config()
        assert result["ollama"]["model"] == "qwen2:7b"
        assert result["ollama"]["embedding_model"] == "nomic-embed-text"
        assert result["ollama"]["base_url"] == "http://localhost:11434"

    def test_get_system_status_debug_true(self) -> None:
        """DEBUG_MODE='true' 时 debug 返回 True。"""
        mock_sys_svc = MagicMock()
        mock_sys_svc.get_value.return_value = "true"

        with patch(
            "apps.core.services.system_config_service.SystemConfigService",
            return_value=mock_sys_svc,
        ):
            svc = self._make_service()
            result = svc.get_system_status()
            assert result["debug"] is True

    def test_get_system_status_debug_false(self) -> None:
        """DEBUG_MODE='false' 时 debug 返回 False。"""
        mock_sys_svc = MagicMock()
        mock_sys_svc.get_value.return_value = "false"

        with patch(
            "apps.core.services.system_config_service.SystemConfigService",
            return_value=mock_sys_svc,
        ):
            svc = self._make_service()
            result = svc.get_system_status()
            assert result["debug"] is False

    def test_get_system_status_debug_1(self) -> None:
        """DEBUG_MODE='1' 时 debug 返回 True。"""
        mock_sys_svc = MagicMock()
        mock_sys_svc.get_value.return_value = "1"

        with patch(
            "apps.core.services.system_config_service.SystemConfigService",
            return_value=mock_sys_svc,
        ):
            svc = self._make_service()
            result = svc.get_system_status()
            assert result["debug"] is True

    def test_get_system_status_debug_yes(self) -> None:
        """DEBUG_MODE='yes' 时 debug 返回 True。"""
        mock_sys_svc = MagicMock()
        mock_sys_svc.get_value.return_value = "yes"

        with patch(
            "apps.core.services.system_config_service.SystemConfigService",
            return_value=mock_sys_svc,
        ):
            svc = self._make_service()
            result = svc.get_system_status()
            assert result["debug"] is True
