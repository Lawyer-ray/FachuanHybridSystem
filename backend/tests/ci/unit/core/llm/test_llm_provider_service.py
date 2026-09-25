"""LLMProvider 模型解析与 LLMProviderService 缓存行为测试。"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from apps.core.llm.backends.base import OpenAIProviderConfig
from apps.core.models import LLMProvider
from apps.core.models.llm_provider import parse_key_entries
from apps.core.services import llm_provider_service as service_module
from apps.core.services.llm_provider_service import LLMProviderService


class TestParseKeyEntries:
    def test_legacy_lines_split_by_comma_and_semicolon(self) -> None:
        assert parse_key_entries("sk-1\nsk-2,sk-3; Bearer sk-4\n\n sk-1 ") == [
            ("sk-1", []),
            ("sk-2", []),
            ("sk-3", []),
            ("sk-4", []),
        ]

    def test_empty_input(self) -> None:
        assert parse_key_entries("") == []

    def test_key_with_model_scope(self) -> None:
        assert parse_key_entries("sk-a|kimi-2.6,glm53\nsk-b") == [
            ("sk-a", ["kimi-2.6", "glm53"]),
            ("sk-b", []),
        ]

    def test_pipe_line_does_not_split_key_on_comma(self) -> None:
        # 含 | 的行，逗号只用于分隔模型，不再拆 Key
        assert parse_key_entries("sk-a|m1,m2") == [("sk-a", ["m1", "m2"])]

    def test_scope_models_dedup_and_whitespace(self) -> None:
        assert parse_key_entries("sk-a| m1 , m2 ; m1 ") == [("sk-a", ["m1", "m2"])]

    def test_empty_scope_means_unrestricted(self) -> None:
        assert parse_key_entries("sk-a|") == [("sk-a", [])]

    def test_bearer_prefix_stripped_with_scope(self) -> None:
        assert parse_key_entries("Bearer sk-a|m1") == [("sk-a", ["m1"])]


class TestProviderKeyModelScopes:
    def test_models_for_key_defaults_to_empty(self) -> None:
        provider = OpenAIProviderConfig(name="law", api_keys=["k1"])
        assert provider.models_for_key("k1") == []
        assert provider.models_for_key("missing") == []

    def test_keys_for_model_filters_scoped_keys(self) -> None:
        provider = OpenAIProviderConfig(
            name="law",
            api_keys=["k1", "k2", "k3"],
            key_model_scopes={"k1": ["a"], "k3": ["b"]},
        )
        assert provider.keys_for_model("a") == ["k1", "k2"]
        assert provider.keys_for_model("b") == ["k2", "k3"]

    def test_keys_for_model_with_empty_model_returns_all(self) -> None:
        provider = OpenAIProviderConfig(
            name="law",
            api_keys=["k1", "k2"],
            key_model_scopes={"k1": ["a"]},
        )
        assert provider.keys_for_model("") == ["k1", "k2"]


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

    def test_parsed_key_model_scopes_skips_unrestricted_keys(self) -> None:
        provider = LLMProvider(
            name="law",
            base_url="http://law/v1",
            api_keys="sk-a|kimi-2.6,glm53\nsk-b",  # pragma: allowlist secret
            default_model="kimi-2.6",
        )
        assert provider.parsed_key_entries() == [("sk-a", ["kimi-2.6", "glm53"]), ("sk-b", [])]
        assert provider.parsed_key_model_scopes() == {"sk-a": ["kimi-2.6", "glm53"]}

    def test_parsed_models_dedup(self) -> None:
        provider = LLMProvider(
            name="xiaomi",
            base_url="http://xm/v1",
            default_model="mimo-v1",
            extra_models="mimo-v1\nmimo-v2,mimo-v1",
        )
        assert provider.parsed_models() == ["mimo-v1", "mimo-v2"]


class _FakeResponse:
    """httpx.Response 的最小替身。"""

    def __init__(self, payload: Any = None, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("GET", "http://gw/v1/models")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError("boom", request=request, response=response)

    def json(self) -> Any:
        return self._payload


class TestFetchRemoteModels:
    def test_aggregates_union_and_intersection_per_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        payloads = {
            "k1": {"data": [{"id": "m1"}, {"id": "m2"}]},
            "k2": {"data": [{"id": "m2"}, {"id": "m3"}]},
        }
        seen_headers: list[dict[str, str]] = []

        def fake_get(url: str, headers: dict[str, str] | None = None, timeout: float | None = None) -> _FakeResponse:
            seen_headers.append(headers or {})
            token = str((headers or {}).get("Authorization", "")).removeprefix("Bearer ")
            return _FakeResponse(payloads[token])

        monkeypatch.setattr(service_module.httpx, "get", fake_get)

        result = LLMProviderService.fetch_remote_models("http://gw/v1/", ["k1", "k2"], probe_chat=False)

        assert result.url == "http://gw/v1/models"
        assert result.ok is True
        assert [item.index for item in result.per_key] == [1, 2]
        assert result.models == ["m1", "m2", "m3"]
        assert result.common_models == ["m2"]
        assert seen_headers[0]["Authorization"] == "Bearer k1"

    def test_without_keys_requests_anonymously_once(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[dict[str, str]] = []

        def fake_get(url: str, headers: dict[str, str] | None = None, timeout: float | None = None) -> _FakeResponse:
            calls.append(headers or {})
            return _FakeResponse({"data": [{"id": "m1"}]})

        monkeypatch.setattr(service_module.httpx, "get", fake_get)

        result = LLMProviderService.fetch_remote_models("http://gw/v1", [], probe_chat=False)

        assert len(calls) == 1
        assert "Authorization" not in calls[0]
        assert result.models == ["m1"]
        assert result.common_models == ["m1"]

    def test_http_error_is_reported_per_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def fake_get(url: str, headers: dict[str, str] | None = None, timeout: float | None = None) -> _FakeResponse:
            return _FakeResponse(status_code=403)

        monkeypatch.setattr(service_module.httpx, "get", fake_get)

        result = LLMProviderService.fetch_remote_models("http://gw/v1", ["k1"], probe_chat=False)

        assert result.ok is False
        assert result.models == []
        assert result.common_models == []
        assert result.per_key[0].error == "HTTP 403"

    def test_accepts_plain_string_data(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(service_module.httpx, "get", lambda *a, **kw: _FakeResponse({"data": ["m1", "m1", "m2"]}))

        result = LLMProviderService.fetch_remote_models("http://gw/v1", ["k1"], probe_chat=False)

        assert result.models == ["m1", "m2"]

    def test_blank_base_url_skips_requests(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def boom(*args: Any, **kwargs: Any) -> Any:
            raise AssertionError("不应发起请求")

        monkeypatch.setattr(service_module.httpx, "get", boom)

        result = LLMProviderService.fetch_remote_models("  ", ["k1"])

        assert result.url == ""
        assert result.per_key == []
        assert result.ok is False

    def test_transport_error_is_reported_per_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def fake_get(url: str, headers: dict[str, str] | None = None, timeout: float | None = None) -> _FakeResponse:
            raise httpx.ConnectError("refused")

        monkeypatch.setattr(service_module.httpx, "get", fake_get)

        result = LLMProviderService.fetch_remote_models("http://gw/v1", ["k1"], probe_chat=False)

        assert result.ok is False
        assert result.per_key[0].error == "ConnectError"


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


class TestChatCapabilityProbe:
    """``/v1/models`` 会列出向量/重排/OCR 等非对话模型，需单独探测对话能力。"""

    @staticmethod
    def _patch_get(monkeypatch: pytest.MonkeyPatch, models_by_key: dict[str, list[str]]) -> None:
        def fake_get(url: str, headers: dict[str, str] | None = None, timeout: float | None = None) -> _FakeResponse:
            token = str((headers or {}).get("Authorization", "")).removeprefix("Bearer ")
            return _FakeResponse({"data": [{"id": m} for m in models_by_key[token]]})

        monkeypatch.setattr(service_module.httpx, "get", fake_get)

    def test_non_chat_model_is_excluded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._patch_get(monkeypatch, {"k1": ["chat-model", "embed-model"]})

        def fake_post(
            url: str,
            headers: dict[str, str] | None = None,
            json: dict[str, Any] | None = None,
            timeout: float | None = None,
        ) -> _FakeResponse:
            model = str((json or {}).get("model", ""))
            return _FakeResponse(status_code=200 if model == "chat-model" else 400)

        monkeypatch.setattr(service_module.httpx, "post", fake_post)

        result = LLMProviderService.fetch_remote_models("http://gw/v1", ["k1"])

        assert result.models == ["chat-model", "embed-model"]
        assert result.chat_models == ["chat-model"]

    def test_probe_disabled_skips_requests(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._patch_get(monkeypatch, {"k1": ["m1"]})

        def boom(*args: Any, **kwargs: Any) -> Any:
            raise AssertionError("probe_chat=False 时不应发起对话探测")

        monkeypatch.setattr(service_module.httpx, "post", boom)

        result = LLMProviderService.fetch_remote_models("http://gw/v1", ["k1"], probe_chat=False)

        assert result.chat_models == []
        assert result.models == ["m1"]

    def test_unknown_verdict_keeps_model(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """探测无法判定（网络异常）时按支持处理，避免漏掉可用模型。"""
        self._patch_get(monkeypatch, {"k1": ["m1"]})

        def boom(*args: Any, **kwargs: Any) -> Any:
            raise httpx.ConnectError("refused")

        monkeypatch.setattr(service_module.httpx, "post", boom)

        result = LLMProviderService.fetch_remote_models("http://gw/v1", ["k1"])

        assert result.chat_models == ["m1"]

    def test_server_error_verdict_keeps_model(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """5xx 属网关侧问题，不代表模型不支持对话。"""
        self._patch_get(monkeypatch, {"k1": ["m1"]})
        monkeypatch.setattr(service_module.httpx, "post", lambda *a, **kw: _FakeResponse(status_code=503))

        result = LLMProviderService.fetch_remote_models("http://gw/v1", ["k1"])

        assert result.chat_models == ["m1"]

    def test_probe_uses_a_key_authorized_for_that_model(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """探测 m2 必须用授权它的 k2，而不是列表里第一个 Key。"""
        self._patch_get(monkeypatch, {"k1": ["m1"], "k2": ["m1", "m2"]})
        seen: list[tuple[str, str]] = []

        def fake_post(
            url: str,
            headers: dict[str, str] | None = None,
            json: dict[str, Any] | None = None,
            timeout: float | None = None,
        ) -> _FakeResponse:
            token = str((headers or {}).get("Authorization", "")).removeprefix("Bearer ")
            seen.append((token, str((json or {}).get("model", ""))))
            return _FakeResponse(status_code=200)

        monkeypatch.setattr(service_module.httpx, "post", fake_post)

        LLMProviderService.fetch_remote_models("http://gw/v1", ["k1", "k2"])

        assert ("k1", "m1") in seen
        assert ("k2", "m2") in seen

    def test_failed_key_models_are_not_probed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """拉取失败的 Key 不参与探测。"""

        def fake_get(url: str, headers: dict[str, str] | None = None, timeout: float | None = None) -> _FakeResponse:
            return _FakeResponse({"data": [{"id": "m1"}]})

        monkeypatch.setattr(service_module.httpx, "get", fake_get)
        probed: list[str] = []

        def fake_post(
            url: str,
            headers: dict[str, str] | None = None,
            json: dict[str, Any] | None = None,
            timeout: float | None = None,
        ) -> _FakeResponse:
            probed.append(str((json or {}).get("model", "")))
            return _FakeResponse(status_code=200)

        monkeypatch.setattr(service_module.httpx, "post", fake_post)

        result = LLMProviderService.fetch_remote_models("http://gw/v1", ["k1"])

        assert result.chat_models == ["m1"]
        assert probed == ["m1"]
