"""ollama.py 单元测试。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


class TestOllamaBackendBuildOptions:

    def _make_backend(self):
        from apps.core.llm.backends.ollama import OllamaBackend
        config = SimpleNamespace(
            base_url="http://localhost:11434",
            default_model="qwen3:0.6b",
            timeout=120.0,
            embedding_model=None,
            enabled=True,
        )
        return OllamaBackend(config=config)

    def test_default_temperature_omitted(self):
        backend = self._make_backend()
        result = backend._build_options(temperature=0.7)
        assert result is None  # 默认温度不设置

    def test_custom_temperature(self):
        backend = self._make_backend()
        result = backend._build_options(temperature=0.3)
        assert result is not None
        assert result["temperature"] == 0.3

    def test_num_predict_priority_over_max_tokens(self):
        backend = self._make_backend()
        result = backend._build_options(temperature=0.5, max_tokens=100, num_predict=200)
        assert result["num_predict"] == 200

    def test_max_tokens_maps_to_num_predict(self):
        backend = self._make_backend()
        result = backend._build_options(temperature=0.5, max_tokens=100)
        assert result["num_predict"] == 100

    def test_ollama_specific_params(self):
        backend = self._make_backend()
        result = backend._build_options(temperature=0.5, top_k=40, top_p=0.9, seed=42)
        assert result["top_k"] == 40
        assert result["top_p"] == 0.9
        assert result["seed"] == 42


class TestOllamaBackendBuildApiUrl:

    def test_strips_trailing_slash(self):
        from apps.core.llm.backends.ollama import OllamaBackend
        config = SimpleNamespace(
            base_url="http://localhost:11434/",
            default_model="qwen3:0.6b",
            timeout=120.0,
            embedding_model=None,
            enabled=True,
        )
        backend = OllamaBackend(config=config)
        assert backend._build_api_url() == "http://localhost:11434/api/chat"

    def test_no_trailing_slash(self):
        from apps.core.llm.backends.ollama import OllamaBackend
        config = SimpleNamespace(
            base_url="http://localhost:11434",
            default_model="qwen3:0.6b",
            timeout=120.0,
            embedding_model=None,
            enabled=True,
        )
        backend = OllamaBackend(config=config)
        assert backend._build_api_url() == "http://localhost:11434/api/chat"


class TestOllamaBackendBuildLlmResponse:

    def test_basic_response(self):
        from apps.core.llm.backends.ollama import OllamaBackend
        config = SimpleNamespace(
            base_url="http://localhost:11434",
            default_model="qwen3:0.6b",
            timeout=120.0,
            embedding_model=None,
            enabled=True,
        )
        backend = OllamaBackend(config=config)
        data = {
            "message": {"content": "你好", "thinking": ""},
            "prompt_eval_count": 10,
            "eval_count": 20,
        }
        result = backend._build_llm_response(data, "qwen3:0.6b", 100.0)
        assert result.content == "你好"
        assert result.prompt_tokens == 10
        assert result.completion_tokens == 20
        assert result.total_tokens == 30

    def test_thinking_fallback(self):
        from apps.core.llm.backends.ollama import OllamaBackend
        config = SimpleNamespace(
            base_url="http://localhost:11434",
            default_model="qwen3:0.6b",
            timeout=120.0,
            embedding_model=None,
            enabled=True,
        )
        backend = OllamaBackend(config=config)
        data = {
            "message": {"content": "", "thinking": "深度思考结果"},
            "prompt_eval_count": 10,
            "eval_count": 20,
        }
        result = backend._build_llm_response(data, "model", 50.0)
        assert result.content == "深度思考结果"


class TestOllamaBackendProperties:

    def test_base_url_from_config(self):
        from apps.core.llm.backends.ollama import OllamaBackend
        config = SimpleNamespace(
            base_url="http://custom:9999",
            default_model="custom-model",
            timeout=60.0,
            embedding_model=None,
            enabled=True,
        )
        backend = OllamaBackend(config=config)
        assert backend.base_url == "http://custom:9999"
        assert backend.default_model == "custom-model"
        assert backend.timeout == 60.0

    def test_default_embedding_model_uses_default_model(self):
        from apps.core.llm.backends.ollama import OllamaBackend
        config = SimpleNamespace(
            base_url="http://localhost:11434",
            default_model="my-model",
            timeout=120.0,
            embedding_model=None,
            enabled=True,
        )
        backend = OllamaBackend(config=config)
        assert backend.default_embedding_model == "my-model"

    def test_custom_embedding_model(self):
        from apps.core.llm.backends.ollama import OllamaBackend
        config = SimpleNamespace(
            base_url="http://localhost:11434",
            default_model="chat-model",
            timeout=120.0,
            embedding_model="embed-model",
            enabled=True,
        )
        backend = OllamaBackend(config=config)
        assert backend.default_embedding_model == "embed-model"

    def test_get_default_model(self):
        from apps.core.llm.backends.ollama import OllamaBackend
        config = SimpleNamespace(
            base_url="http://localhost:11434",
            default_model="test-model",
            timeout=120.0,
            embedding_model=None,
            enabled=True,
        )
        backend = OllamaBackend(config=config)
        assert backend.get_default_model() == "test-model"


class TestOllamaBackendIsAvailable:

    def test_disabled_config(self):
        from apps.core.llm.backends.ollama import OllamaBackend
        config = SimpleNamespace(
            base_url="http://localhost:11434",
            default_model="model",
            timeout=120.0,
            embedding_model=None,
            enabled=False,
        )
        backend = OllamaBackend(config=config)
        assert backend.is_available() is False

    def test_empty_base_url_uses_config_value(self):
        from apps.core.llm.backends.ollama import OllamaBackend
        config = SimpleNamespace(
            base_url="",
            default_model="model",
            timeout=120.0,
            embedding_model=None,
            enabled=True,
        )
        backend = OllamaBackend(config=config)
        # base_url 为空字符串时，LLMConfig 可能提供默认值
        # 验证属性可访问且不抛异常
        url = backend.base_url
        assert isinstance(url, str)

    @patch("apps.core.llm.backends.ollama.get_sync_http_client")
    def test_available_when_probe_succeeds(self, mock_get_client):
        from apps.core.llm.backends.ollama import OllamaBackend
        config = SimpleNamespace(
            base_url="http://localhost:11434",
            default_model="model",
            timeout=120.0,
            embedding_model=None,
            enabled=True,
        )
        backend = OllamaBackend(config=config)
        backend._availability_checked = False  # reset
        resp = MagicMock()
        resp.status_code = 200
        mock_get_client.return_value.get.return_value = resp
        assert backend.is_available() is True

    @patch("apps.core.llm.backends.ollama.get_sync_http_client")
    def test_unavailable_when_probe_fails(self, mock_get_client):
        from apps.core.llm.backends.ollama import OllamaBackend
        config = SimpleNamespace(
            base_url="http://localhost:11434",
            default_model="model",
            timeout=120.0,
            embedding_model=None,
            enabled=True,
        )
        backend = OllamaBackend(config=config)
        backend._availability_checked = False  # reset
        mock_get_client.return_value.get.side_effect = ConnectionError("refused")
        assert backend.is_available() is False


class TestOllamaBackendEmbedTexts:

    def test_empty_texts(self):
        from apps.core.llm.backends.ollama import OllamaBackend
        config = SimpleNamespace(
            base_url="http://localhost:11434",
            default_model="model",
            timeout=120.0,
            embedding_model=None,
            enabled=True,
        )
        backend = OllamaBackend(config=config)
        assert backend.embed_texts([]) == []

    @patch("apps.core.llm.backends.ollama.get_sync_http_client")
    def test_embed_success(self, mock_get_client):
        from apps.core.llm.backends.ollama import OllamaBackend
        config = SimpleNamespace(
            base_url="http://localhost:11434",
            default_model="model",
            timeout=120.0,
            embedding_model=None,
            enabled=True,
        )
        backend = OllamaBackend(config=config)
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"embeddings": [[0.1, 0.2, 0.3]]}
        mock_get_client.return_value.post.return_value = resp
        result = backend.embed_texts(["hello"])
        assert len(result) == 1
        assert result[0] == [0.1, 0.2, 0.3]
