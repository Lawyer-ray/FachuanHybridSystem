"""LLMProvider 模型解析与 LLMProviderService 缓存行为测试。"""

from __future__ import annotations

import pytest

from apps.core.llm.backends.base import OpenAIProviderConfig
from apps.core.models import LLMProvider
from apps.core.services.llm_provider_service import LLMProviderService


class TestLLMProviderModelParsing:
    def test_parsed_api_keys_multiline_and_separators(self) -> None:
        provider = LLMProvider(
            name="law",
            base_url="http://law/v1",
            api_keys="sk-1\nsk-2,sk-3; Bearer sk-4\n\n sk-1 ",  # pragma: allowlist secret
            default_model="kimi26",
        )
        assert provider.parsed_api_keys() == ["sk-1", "sk-2", "sk-3", "sk-4"]

    def test_parsed_api_keys_empty(self) -> None:
        provider = LLMProvider(name="local", base_url="http://local/v1", api_keys="", default_model="m")
        assert provider.parsed_api_keys() == []

    def test_parsed_models_dedup(self) -> None:
        provider = LLMProvider(
            name="xiaomi",
            base_url="http://xm/v1",
            default_model="mimo-v1",
            extra_models="mimo-v1\nmimo-v2,mimo-v1",
        )
        assert provider.parsed_models() == ["mimo-v1", "mimo-v2"]


class TestLLMProviderService:
    def teardown_method(self) -> None:
        LLMProviderService.invalidate_cache()

    def test_cache_hit_and_invalidate(self, monkeypatch: pytest.MonkeyPatch) -> None:
        LLMProviderService.invalidate_cache()  # 清掉其他测试写入的缓存，避免污染
        calls = {"n": 0}

        def fake_load() -> list[OpenAIProviderConfig]:
            calls["n"] += 1
            return [OpenAIProviderConfig(name="law", base_url="http://law/v1", default_model="kimi26")]

        monkeypatch.setattr(LLMProviderService, "_load_from_db", staticmethod(fake_load))

        assert LLMProviderService.get_providers()[0].name == "law"
        assert LLMProviderService.get_providers()[0].name == "law"
        assert calls["n"] == 1  # 命中缓存，不重复读库

        LLMProviderService.invalidate_cache()
        LLMProviderService.get_providers()
        assert calls["n"] == 2

    @pytest.mark.asyncio
    async def test_aget_providers_shares_sync_cache(self, monkeypatch: pytest.MonkeyPatch) -> None:
        LLMProviderService.invalidate_cache()  # 清掉其他测试写入的缓存，避免污染
        calls = {"n": 0}

        def fake_load() -> list[OpenAIProviderConfig]:
            calls["n"] += 1
            return [OpenAIProviderConfig(name="law", base_url="http://law/v1", default_model="kimi26")]

        monkeypatch.setattr(LLMProviderService, "_load_from_db", staticmethod(fake_load))

        providers = await LLMProviderService.aget_providers()
        assert providers[0].name == "law"
        # async 写入的缓存，sync 读取直接命中
        assert LLMProviderService.get_providers()[0].name == "law"
        assert calls["n"] == 1

    def test_load_failure_returns_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def boom() -> list[OpenAIProviderConfig]:
            raise RuntimeError("db unavailable")

        monkeypatch.setattr(LLMProviderService, "_load_from_db", staticmethod(boom))
        assert LLMProviderService.get_providers() == []


class TestInitializeDefault:
    def teardown_method(self) -> None:
        LLMProviderService.invalidate_cache()

    @pytest.mark.django_db
    def test_initializes_default_when_empty(self) -> None:
        result = LLMProviderService.initialize_default()

        assert result == (1, 0)
        row = LLMProvider.objects.get()
        assert row.name == "律所 kimi"
        assert row.default_model == "kimi26"
        assert row.concurrency_per_key == 3
        assert row.enabled is True
        assert row.parsed_api_keys() == []

    @pytest.mark.django_db
    def test_skips_when_provider_exists(self) -> None:
        LLMProvider.objects.create(
            name="律所",
            base_url="http://law/v1",
            default_model="kimi-2.6",
            api_keys="sk-old",  # pragma: allowlist secret
            enabled=True,
        )

        result = LLMProviderService.initialize_default()

        assert result == (0, 1)
        assert LLMProvider.objects.count() == 1
        assert LLMProvider.objects.get().name == "律所"  # 不覆盖已有数据

    @pytest.mark.django_db
    def test_initialize_invalidates_cache(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = {"n": 0}

        def fake_load() -> list[OpenAIProviderConfig]:
            calls["n"] += 1
            return [OpenAIProviderConfig(name="律所 kimi", base_url="http://law/v1", default_model="kimi26")]

        monkeypatch.setattr(LLMProviderService, "_load_from_db", staticmethod(fake_load))
        LLMProviderService.initialize_default()
        LLMProviderService.get_providers()
        assert calls["n"] == 1
