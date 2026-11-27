"""openai_compatible backend 补充覆盖测试。"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from apps.core.llm.backends.base import BackendConfig, LLMResponse, LLMStreamChunk, LLMUsage
from apps.core.llm.exceptions import LLMAPIError, LLMAuthenticationError, LLMNetworkError, LLMTimeoutError
from apps.core.llm.gateway_profile import GATEWAY_EFFORTS


def _cfg(**kwargs: Any) -> BackendConfig:
    defaults = {"name": "oai", "enabled": True, "priority": 1, "default_model": "gpt-4o"}
    defaults.update(kwargs)
    return BackendConfig(**defaults)


# ── _build_extra_body ─────────────────────────────────────────────


# 开启思考时两个字段都必须下发：``thinking`` 管「要不要想」，``reasoning_effort``
# 管「想多深」。断言**逐个写在用例里**而不是收进一个 helper——
# ``tests/ci/structure/test_test_quality_ratchet.py`` 是按函数体扫 ``assert`` 的，
# 把断言藏进 helper 会让这些用例被判成「零断言」，而那正是该棘轮要防的形状。


class TestBuildExtraBody:
    def test_kimi_model_disables_thinking(self):
        """平台没开思考时推理模型仍要显式下发 false（省略开关实测无效，模型依旧思考）。"""
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        backend = OpenAICompatibleBackend()
        result = backend._build_extra_body("kimi26-chat")
        assert result == {"chat_template_kwargs": {"thinking": False}}

    def test_provider_enable_thinking_sends_true(self):
        """平台开启思考模式后显式下发 thinking=true（省略开关实测无效）。"""
        from apps.core.llm.backends.base import OpenAIProviderConfig
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        backend = OpenAICompatibleBackend()
        provider = OpenAIProviderConfig(name="p", default_model="kimi26", enable_thinking=True)
        fields = backend._build_extra_body("kimi26", provider)
        assert fields is not None
        assert fields["chat_template_kwargs"] == {"thinking": True}
        assert fields["reasoning_effort"] in GATEWAY_EFFORTS

    def test_kimi_k2_uses_gateway_capability_table(self):
        """``kimi-k2`` 是旧窄表（``{"kimi26", ...}``）漏掉的模型名。

        以前服务通道对它一个字段都不发、Agent 通道却判为可思考——同一模型两个入口
        思考与否相反且没有任何报错（P0）。现在两侧共用 gateway_profile 的能力表。
        """
        from apps.core.llm.backends.base import OpenAIProviderConfig
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        backend = OpenAICompatibleBackend()
        provider = OpenAIProviderConfig(name="p", default_model="kimi-k2", enable_thinking=True)
        fields = backend._build_extra_body("kimi-k2", provider)
        assert fields is not None
        assert fields["chat_template_kwargs"] == {"thinking": True}
        assert fields["reasoning_effort"] in GATEWAY_EFFORTS

    def test_enable_thinking_false_sends_only_thinking_false(self):
        """关闭思考时只发 false，**不带** reasoning_effort。"""
        from apps.core.llm.backends.base import OpenAIProviderConfig
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        backend = OpenAICompatibleBackend()
        provider = OpenAIProviderConfig(name="p", default_model="kimi-k2", enable_thinking=False)
        assert backend._build_extra_body("kimi-k2", provider) == {"chat_template_kwargs": {"thinking": False}}

    def test_call_level_override_can_turn_thinking_off(self):
        """单次调用可以**只关不开**。

        真机事故：`kimi-2.6` 平台开着思考去审一份泰国合同，3 分钟全花在输出
        「We need answer JSON only…」这类过程文字上，JSON 一个字符都没写出来，
        整轮审查零结论。结构化抽取类调用必须能在**这一次**关掉思考。
        """
        from apps.core.llm.backends.base import OpenAIProviderConfig
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        backend = OpenAICompatibleBackend()
        provider = OpenAIProviderConfig(name="p", default_model="kimi-k2", enable_thinking=True)
        fields = backend._build_extra_body("kimi-k2", provider, enable_thinking=False)
        assert fields == {"chat_template_kwargs": {"thinking": False}}

    def test_call_level_override_cannot_turn_thinking_on(self):
        """平台关着的时候，单次调用**不许**打开思考（等于绕过平台总开关）。"""
        from apps.core.llm.backends.base import OpenAIProviderConfig
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        backend = OpenAICompatibleBackend()
        provider = OpenAIProviderConfig(name="p", default_model="kimi-k2", enable_thinking=False)
        fields = backend._build_extra_body("kimi-k2", provider, enable_thinking=True)
        assert fields == {"chat_template_kwargs": {"thinking": False}}

    def test_payload_carries_call_level_thinking_override(self):
        """`enable_thinking` 必须真的进请求体——只看 `_build_extra_body` 会漏掉接线。"""
        from apps.core.llm.backends.base import OpenAIProviderConfig
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        backend = OpenAICompatibleBackend()
        provider = OpenAIProviderConfig(name="p", default_model="kimi-k2", enable_thinking=True)
        payload = backend._build_payload(
            "kimi-k2", [{"role": "user", "content": "hi"}], 0.2, 100, provider=provider, enable_thinking=False
        )
        assert payload["extra_body"] == {"chat_template_kwargs": {"thinking": False}}

    def test_non_reasoning_model_returns_none(self):
        """非推理模型（qwen3）不下发任何开关，即使平台开关是打开的。"""
        from apps.core.llm.backends.base import OpenAIProviderConfig
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        backend = OpenAICompatibleBackend()
        provider = OpenAIProviderConfig(name="p", default_model="qwen3", enable_thinking=True)
        assert backend._build_extra_body("qwen3", provider) is None

    def test_hyphenated_kimi_name_matches(self):
        """真实配置是 ``kimi-2.6``（带连字符），必须与 ``kimi26`` 同样命中。"""
        from apps.core.llm.backends.base import OpenAIProviderConfig
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        backend = OpenAICompatibleBackend()
        off = OpenAIProviderConfig(name="p", default_model="kimi-2.6", enable_thinking=False)
        on = OpenAIProviderConfig(name="p", default_model="kimi-2.6", enable_thinking=True)
        assert backend._build_extra_body("kimi-2.6", off) == {"chat_template_kwargs": {"thinking": False}}
        fields = backend._build_extra_body("kimi-2.6", on)
        assert fields is not None
        assert fields["chat_template_kwargs"] == {"thinking": True}
        assert fields["reasoning_effort"] in GATEWAY_EFFORTS
        # 网关里的 Anthropic 别名同样要命中
        alias_fields = backend._build_extra_body("kimi-2.6(Anthropic)", on)
        assert alias_fields is not None
        assert alias_fields["chat_template_kwargs"] == {"thinking": True}
        assert alias_fields["reasoning_effort"] in GATEWAY_EFFORTS

    def test_payload_carries_thinking_switch(self):
        """_build_payload 必须把开关放进 extra_body（而非顶级字段）。"""
        from apps.core.llm.backends.base import OpenAIProviderConfig
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        backend = OpenAICompatibleBackend()
        on = OpenAIProviderConfig(name="p", default_model="kimi-2.6", enable_thinking=True)
        payload = backend._build_payload("kimi-2.6", [{"role": "user", "content": "hi"}], 0.7, 10, provider=on)
        extra_body = payload["extra_body"]
        assert extra_body is not None
        assert extra_body["chat_template_kwargs"] == {"thinking": True}
        assert extra_body["reasoning_effort"] in GATEWAY_EFFORTS
        # 开关必须落在 extra_body 里，不能漏到顶级字段（SDK 不认顶级 chat_template_kwargs）
        assert "chat_template_kwargs" not in payload

    def test_provider_enable_thinking_ignored_for_plain_model(self):
        """开启思考不影响非推理模型：非推理模型不下发任何开关。"""
        from apps.core.llm.backends.base import OpenAIProviderConfig
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        backend = OpenAICompatibleBackend()
        provider = OpenAIProviderConfig(name="p", default_model="kimi26", enable_thinking=True)
        assert backend._build_extra_body("gpt-4o", provider) is None

    def test_mimo_model_disables_thinking(self):
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        backend = OpenAICompatibleBackend()
        result = backend._build_extra_body("mimo-v1")
        assert result == {"chat_template_kwargs": {"thinking": False}}

    def test_normal_model_no_extra(self):
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        backend = OpenAICompatibleBackend()
        result = backend._build_extra_body("gpt-4o")
        assert result is None

    def test_none_model_uses_default(self):
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        config = _cfg(default_model="normal-model")
        backend = OpenAICompatibleBackend(config=config)
        result = backend._build_extra_body(None)
        assert result is None


# ── 降级 ─────────────────────────────────────────────────


class TestModelFallbackChain:
    def _backend(self, fallback_models: list[str]) -> Any:
        """把平台配置塞进 ``_config.providers``（``_providers_from_config`` 的口径）。"""
        from apps.core.llm.backends.base import OpenAIProviderConfig
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        provider = OpenAIProviderConfig(
            name="p",
            base_url="http://test",
            api_keys=["k"],  # pragma: allowlist secret
            default_model="kimi-2.6",
            fallback_models=fallback_models,
        )
        return OpenAICompatibleBackend(config=_cfg(providers=[provider]))

    def _calls_until_error(self, backend: Any, error: Exception) -> list[str]:
        calls: list[str] = []

        def _primary(messages: Any, model: str | None = None, *a: Any, **kw: Any) -> Any:
            calls.append(model or "")
            raise error

        with patch.object(backend, "_chat_primary", side_effect=_primary):
            with pytest.raises(type(error)):
                backend.chat([{"role": "user", "content": "hi"}], model="kimi-2.6")
        return calls

    def test_parameter_error_400_does_not_fall_back(self):
        """400 参数错换模型必然同一个错：旧实现会把整条链每个模型各打一遍。"""
        backend = self._backend(["glm53", "kimi-2.6(Anthropic)"])
        calls = self._calls_until_error(backend, LLMAPIError(message="bad request", status_code=400))
        assert calls == ["kimi-2.6"]

    def test_server_error_500_falls_back(self):
        backend = self._backend(["glm53", "kimi-2.6(Anthropic)"])
        calls = self._calls_until_error(backend, LLMAPIError(message="upstream boom", status_code=500))
        assert calls == ["kimi-2.6", "glm53", "kimi-2.6(Anthropic)"]

    def test_timeout_falls_back(self):
        backend = self._backend(["glm53"])
        calls = self._calls_until_error(backend, LLMTimeoutError(message="timed out", timeout_seconds=30))
        assert calls == ["kimi-2.6", "glm53"]

    def test_backend_unavailable_does_not_fall_back(self):
        """所有后端都不可用时再降级等于把整链再打一遍。"""
        from apps.core.llm.exceptions import LLMBackendUnavailableError

        backend = self._backend(["glm53"])
        calls = self._calls_until_error(backend, LLMBackendUnavailableError())
        assert calls == ["kimi-2.6"]

    def test_fallback_models_is_list_of_str(self):
        """``OpenAIProviderConfig.fallback_models`` 是 ``list[str]``：逐项去重、排除主模型。"""
        backend = self._backend(["glm53", "kimi-2.6", "glm53", " kimi-2.6(Anthropic) "])
        assert backend._fallback_models_for("kimi-2.6") == ["glm53", "kimi-2.6(Anthropic)"]


# ── Properties ────────────────────────────────────────────


class TestProperties:
    @patch("apps.core.llm.backends.openai_compatible.LLMConfig")
    def test_api_key_from_config(self, mock_cfg):
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        config = _cfg(api_key="sk-test-key")  # pragma: allowlist secret
        backend = OpenAICompatibleBackend(config=config)
        assert backend.api_key == "sk-test-key"  # pragma: allowlist secret

    @patch("apps.core.llm.backends.openai_compatible.LLMConfig")
    def test_api_key_from_settings(self, mock_cfg):
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        mock_cfg.get_openai_compatible_api_key.return_value = "sk-from-settings"  # pragma: allowlist secret
        backend = OpenAICompatibleBackend()
        assert backend.api_key == "sk-from-settings"  # pragma: allowlist secret

    def test_base_url_from_config(self):
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        config = _cfg(base_url="http://custom")
        backend = OpenAICompatibleBackend(config=config)
        assert backend.base_url == "http://custom"

    @patch("apps.core.llm.backends.openai_compatible.LLMConfig")
    def test_base_url_from_settings(self, mock_cfg):
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        mock_cfg.get_openai_compatible_base_url.return_value = "http://default"
        backend = OpenAICompatibleBackend()
        assert backend.base_url == "http://default"

    def test_default_model_from_config(self):
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        config = _cfg(default_model="deepseek-chat")
        backend = OpenAICompatibleBackend(config=config)
        assert backend.default_model == "deepseek-chat"

    @patch("apps.core.llm.backends.openai_compatible.LLMConfig")
    def test_default_model_from_settings(self, mock_cfg):
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        mock_cfg.get_openai_compatible_model.return_value = "gpt-3.5"
        backend = OpenAICompatibleBackend()
        assert backend.default_model == "gpt-3.5"

    def test_timeout_from_config(self):
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        config = _cfg(timeout=60)
        backend = OpenAICompatibleBackend(config=config)
        assert backend.timeout == 60

    @patch("apps.core.llm.backends.openai_compatible.LLMConfig")
    def test_timeout_from_settings(self, mock_cfg):
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        mock_cfg.get_openai_compatible_timeout.return_value = 120
        backend = OpenAICompatibleBackend()
        assert backend.timeout == 120


# ── _resolve_embedding_model ──────────────────────────────────────


class TestResolveEmbeddingModel:
    def test_explicit_model(self):
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        config = _cfg(default_model="gpt-4o")
        backend = OpenAICompatibleBackend(config=config)
        assert backend._resolve_embedding_model("text-embedding-3-small") == "text-embedding-3-small"

    def test_config_embedding_model(self):
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        config = _cfg(default_model="gpt-4o", embedding_model="embed-v2")
        backend = OpenAICompatibleBackend(config=config)
        assert backend._resolve_embedding_model() == "embed-v2"

    @patch("apps.core.llm.backends.openai_compatible.LLMConfig")
    def test_settings_embedding_model(self, mock_cfg):
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        mock_cfg.get_openai_compatible_api_key.return_value = "k"
        mock_cfg.get_openai_compatible_base_url.return_value = "http://test"
        mock_cfg.get_openai_compatible_model.return_value = "default-model"
        mock_cfg.get_openai_compatible_embedding_model.return_value = "embed-from-settings"
        mock_cfg.get_openai_compatible_timeout.return_value = 30
        backend = OpenAICompatibleBackend()
        assert backend._resolve_embedding_model() == "embed-from-settings"

    @patch("apps.core.llm.backends.openai_compatible.LLMConfig")
    def test_unconfigured_returns_empty(self, mock_cfg):
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        mock_cfg.get_openai_compatible_api_key.return_value = "k"
        mock_cfg.get_openai_compatible_base_url.return_value = "http://test"
        mock_cfg.get_openai_compatible_model.return_value = "gpt-4o"
        mock_cfg.get_openai_compatible_embedding_model.return_value = ""
        mock_cfg.get_openai_compatible_timeout.return_value = 30
        backend = OpenAICompatibleBackend()
        # 未配置向量模型：返回空字符串（不启用向量能力），不再回退默认模型
        assert backend._resolve_embedding_model() == ""


# ── _raise_mapped_error ───────────────────────────────────────────


class TestRaiseMappedError:
    def test_authentication_error(self):
        import openai

        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        backend = OpenAICompatibleBackend()
        err = openai.AuthenticationError(
            message="Invalid API key",
            response=MagicMock(status_code=401, headers={}),
            body=None,
        )
        with pytest.raises(LLMAuthenticationError):
            backend._raise_mapped_error(err, 30.0, "http://test")

    def test_timeout_error(self):
        import openai

        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        backend = OpenAICompatibleBackend()
        err = openai.APITimeoutError(request=MagicMock())
        with pytest.raises(LLMTimeoutError):
            backend._raise_mapped_error(err, 30.0, "http://test")

    def test_connection_error(self):
        import openai

        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        backend = OpenAICompatibleBackend()
        err = openai.APIConnectionError(request=MagicMock())
        with pytest.raises(LLMNetworkError):
            backend._raise_mapped_error(err, 30.0, "http://test")

    def test_api_error(self):
        import openai

        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        backend = OpenAICompatibleBackend()
        err = openai.APIError(
            message="Server error",
            request=MagicMock(),
            body={"error": "internal"},
        )
        with pytest.raises(LLMAPIError):
            backend._raise_mapped_error(err, 30.0, "http://test")

    def test_generic_error(self):
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        backend = OpenAICompatibleBackend()
        with pytest.raises(LLMAPIError):
            backend._raise_mapped_error(RuntimeError("unexpected"), 30.0, "http://test")


# ── chat (sync) ───────────────────────────────────────────────────


class TestChat:
    def test_chat_success(self):
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        config = _cfg(api_key="sk-test", base_url="http://test", default_model="gpt-4o")
        backend = OpenAICompatibleBackend(config=config)

        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Hello!"))]
        mock_response.usage = MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)

        with patch.object(backend, "_build_sync_client") as mock_build:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_build.return_value = mock_client

            result = backend.chat([{"role": "user", "content": "Hi"}])
            assert result.content == "Hello!"
            assert result.model == "gpt-4o"
            assert result.prompt_tokens == 10
            assert result.completion_tokens == 5

    def test_chat_with_kimi_model_injects_extra_body(self):
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        config = _cfg(api_key="sk-test", base_url="http://test", default_model="kimi26-chat")
        backend = OpenAICompatibleBackend(config=config)

        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="OK"))]
        mock_response.usage = MagicMock(prompt_tokens=5, completion_tokens=3, total_tokens=8)

        with patch.object(backend, "_build_sync_client") as mock_build:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_build.return_value = mock_client

            result = backend.chat([{"role": "user", "content": "test"}])
            call_kwargs = mock_client.chat.completions.create.call_args[1]
            assert "extra_body" in call_kwargs
            assert call_kwargs["extra_body"]["chat_template_kwargs"]["thinking"] is False

    def test_chat_with_max_tokens(self):
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        config = _cfg(api_key="sk-test", base_url="http://test", default_model="gpt-4o")
        backend = OpenAICompatibleBackend(config=config)

        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="OK"))]
        mock_response.usage = MagicMock(prompt_tokens=5, completion_tokens=3, total_tokens=8)

        with patch.object(backend, "_build_sync_client") as mock_build:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_build.return_value = mock_client

            result = backend.chat([{"role": "user", "content": "test"}], max_tokens=100)
            call_kwargs = mock_client.chat.completions.create.call_args[1]
            assert call_kwargs["max_tokens"] == 100

    def test_chat_error_raises(self):
        import openai

        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        config = _cfg(api_key="sk-test", base_url="http://test", default_model="gpt-4o")
        backend = OpenAICompatibleBackend(config=config)

        with patch.object(backend, "_build_sync_client") as mock_build:
            mock_client = MagicMock()
            mock_client.chat.completions.create.side_effect = openai.APITimeoutError(request=MagicMock())
            mock_build.return_value = mock_client

            with pytest.raises(LLMTimeoutError):
                backend.chat([{"role": "user", "content": "test"}])


# ── stream ────────────────────────────────────────────────────────


class TestStream:
    def test_stream_yields_chunks(self):
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        config = _cfg(api_key="sk-test", base_url="http://test", default_model="gpt-4o")
        backend = OpenAICompatibleBackend(config=config)

        chunk1 = MagicMock()
        chunk1.choices = [MagicMock(delta=MagicMock(content="Hello"))]
        chunk1.usage = None

        chunk2 = MagicMock()
        chunk2.choices = [MagicMock(delta=MagicMock(content=" world"))]
        chunk2.usage = None

        final_chunk = MagicMock()
        final_chunk.choices = []
        final_chunk.usage = MagicMock(prompt_tokens=5, completion_tokens=3, total_tokens=8)

        with patch.object(backend, "_build_sync_client") as mock_build:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = iter([chunk1, chunk2, final_chunk])
            mock_build.return_value = mock_client

            chunks = list(backend.stream([{"role": "user", "content": "test"}]))
            content_chunks = [c for c in chunks if c.content]
            assert len(content_chunks) == 2
            assert content_chunks[0].content == "Hello"
            assert content_chunks[1].content == " world"

    def test_stream_with_max_tokens(self):
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        config = _cfg(api_key="sk-test", base_url="http://test", default_model="gpt-4o")
        backend = OpenAICompatibleBackend(config=config)

        chunk = MagicMock()
        chunk.choices = [MagicMock(delta=MagicMock(content="OK"))]
        chunk.usage = MagicMock(prompt_tokens=5, completion_tokens=3, total_tokens=8)

        with patch.object(backend, "_build_sync_client") as mock_build:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = iter([chunk])
            mock_build.return_value = mock_client

            chunks = list(backend.stream([{"role": "user", "content": "test"}], max_tokens=50))
            call_kwargs = mock_client.chat.completions.create.call_args[1]
            assert call_kwargs["max_tokens"] == 50

    def test_stream_with_kimi_model(self):
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        config = _cfg(api_key="sk-test", base_url="http://test", default_model="kimi26-chat")
        backend = OpenAICompatibleBackend(config=config)

        chunk = MagicMock()
        chunk.choices = [MagicMock(delta=MagicMock(content="OK"))]
        chunk.usage = MagicMock(prompt_tokens=5, completion_tokens=3, total_tokens=8)

        with patch.object(backend, "_build_sync_client") as mock_build:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = iter([chunk])
            mock_build.return_value = mock_client

            list(backend.stream([{"role": "user", "content": "test"}]))
            call_kwargs = mock_client.chat.completions.create.call_args[1]
            assert "extra_body" in call_kwargs

    def test_stream_error_raises(self):
        import openai

        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        config = _cfg(api_key="sk-test", base_url="http://test", default_model="gpt-4o")
        backend = OpenAICompatibleBackend(config=config)

        with patch.object(backend, "_build_sync_client") as mock_build:
            mock_client = MagicMock()
            mock_client.chat.completions.create.side_effect = openai.APIConnectionError(request=MagicMock())
            mock_build.return_value = mock_client

            with pytest.raises(LLMNetworkError):
                list(backend.stream([{"role": "user", "content": "test"}]))

    def test_stream_empty_choices(self):
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        config = _cfg(api_key="sk-test", base_url="http://test", default_model="gpt-4o")
        backend = OpenAICompatibleBackend(config=config)

        chunk = MagicMock()
        chunk.choices = []
        chunk.usage = MagicMock(prompt_tokens=5, completion_tokens=3, total_tokens=8)

        with patch.object(backend, "_build_sync_client") as mock_build:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = iter([chunk])
            mock_build.return_value = mock_client

            chunks = list(backend.stream([{"role": "user", "content": "test"}]))
            # Should still yield the usage chunk
            assert any(c.usage is not None for c in chunks)

    def test_stream_no_content_no_usage(self):
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        config = _cfg(api_key="sk-test", base_url="http://test", default_model="gpt-4o")
        backend = OpenAICompatibleBackend(config=config)

        chunk = MagicMock()
        chunk.choices = [MagicMock(delta=MagicMock(content=None))]
        chunk.usage = None

        with patch.object(backend, "_build_sync_client") as mock_build:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = iter([chunk])
            mock_build.return_value = mock_client

            chunks = list(backend.stream([{"role": "user", "content": "test"}]))
            # No content and no usage => no chunks yielded
            assert len(chunks) == 0


# ── _build_sync_client ────────────────────────────────────────────


class TestBuildSyncClient:
    @patch.dict("os.environ", {"LLM_SSL_VERIFY": "false"})
    def test_ssl_verify_disabled(self):
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        config = _cfg(api_key="sk-test", base_url="http://test")
        backend = OpenAICompatibleBackend(config=config)
        client = backend._build_sync_client(api_key="sk-test", base_url="http://test", timeout_seconds=30)
        assert client is not None

    @patch.dict("os.environ", {"LLM_SSL_VERIFY": "true"})
    def test_ssl_verify_enabled(self):
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        config = _cfg(api_key="sk-test", base_url="http://test")
        backend = OpenAICompatibleBackend(config=config)
        client = backend._build_sync_client(api_key="sk-test", base_url="http://test", timeout_seconds=30)
        assert client is not None
