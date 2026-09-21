"""LLM / Provider 服务链路端到端测试（branch: refactor/core-cleanup）。

覆盖本分支 LLM 相关改动：
1. ``LLMProviderService`` 全链路（含 ``_load_from_db`` staticmethod → classmethod 回归）
2. ``ParseProviderService``（``_load_from_db`` staticmethod → classmethod 回归）
3. ``LLMService`` 集成链路（service → client → fallback_policy → backend，全程 mock backend）
4. ``ModelListService`` Ollama context_window 失败时记录 warning（原 ``except: pass``）
5. 已删除模块无残留（``llm.costs`` / ``infrastructure.event_bus`` / ``infrastructure.events``）
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
from contextlib import contextmanager
from typing import Any, Iterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from asgiref.sync import sync_to_async

from apps.core.llm.backends.base import LLMResponse
from apps.core.models import DocumentParseProvider, LLMProvider
from apps.core.services.document_parse_provider_service import ParseProviderService
from apps.core.services.llm_provider_service import LLMProviderService

# ── 常量 ──────────────────────────────────────────────────────────────────────

LOGGER_LLM_PROVIDER = "apps.core.services.llm_provider"
LOGGER_MODEL_LIST = "apps.core.llm.model_list_service"


def _make_response(content: str = "ok") -> LLMResponse:
    return LLMResponse(
        content=content,
        model="kimi26",
        prompt_tokens=1,
        completion_tokens=1,
        total_tokens=2,
        duration_ms=1.0,
        backend="openai_compatible",
    )


@contextmanager
def _patched_load(service_cls: Any, fake: Any) -> Iterator[None]:
    """临时替换 ``_load_from_db``（保持原实现可用），退出时可靠还原。"""
    real = service_cls.__dict__["_load_from_db"]
    try:
        service_cls._load_from_db = fake  # type: ignore[method-assign]
        yield
    finally:
        service_cls._load_from_db = real  # type: ignore[method-assign]


def _real_load(service_cls: Any) -> Any:
    """取出未绑定的真实 ``_load_from_db`` 实现（classmethod → 普通函数）。"""
    return service_cls.__dict__["_load_from_db"].__func__


def _counting_load(service_cls: Any, counter: dict[str, int]) -> Any:
    """包装真实实现，统计调用次数。"""
    real = _real_load(service_cls)

    def wrapper(cls: Any) -> list[Any]:
        counter["n"] += 1
        return real(cls)

    return classmethod(wrapper)


def _reset_provider_state() -> None:
    """清空平台表 + 清缓存（同步上下文；仅对 django_db 用例调用）。"""
    LLMProvider.objects.all().delete()
    DocumentParseProvider.objects.all().delete()
    LLMProviderService.invalidate_cache()
    ParseProviderService.invalidate_cache()


async def _areset_provider_state() -> None:
    """清空平台表 + 清缓存（异步上下文；用 async ORM，避免跨连接提交）。"""
    await LLMProvider.objects.all().adelete()
    await DocumentParseProvider.objects.all().adelete()
    LLMProviderService.invalidate_cache()
    ParseProviderService.invalidate_cache()


def _needs_db(request: pytest.FixtureRequest) -> bool:
    """判断当前用例是否声明了数据库访问（django_db marker / db / transactional_db）。"""
    if request.node.get_closest_marker("django_db"):
        return True
    return "db" in request.fixturenames or "transactional_db" in request.fixturenames


@pytest.fixture(autouse=True)
def _clean_provider_tables(request: pytest.FixtureRequest) -> Iterator[None]:
    """对声明 ``django_db`` 的用例，前后清空平台表 + 清缓存。

    异步用例（``transaction=True`` + 异步 ORM）的数据虽在事务内，但类级 TTL 缓存
    ``_cache`` 是进程级的，跨用例会串味，因此统一清理。非 DB 用例只清进程内缓存。
    """
    has_db = _needs_db(request)
    if has_db:
        _reset_provider_state()
    else:
        LLMProviderService.invalidate_cache()
        ParseProviderService.invalidate_cache()
    yield
    if has_db:
        _reset_provider_state()
    else:
        LLMProviderService.invalidate_cache()
        ParseProviderService.invalidate_cache()


# ── 场景 1：LLMProviderService 全链路 ─────────────────────────────────────────


class TestLLMProviderServiceE2E:
    """LLMProviderService 从 DB → 缓存 → OpenAIProviderConfig 的全链路。"""

    def teardown_method(self) -> None:
        LLMProviderService.invalidate_cache()

    @pytest.mark.django_db
    def test_get_providers_reads_db_and_sorts(self) -> None:
        LLMProviderService.invalidate_cache()
        LLMProvider.objects.create(
            name="platform-b",
            base_url="http://b/v1",
            api_keys="sk-b1\nsk-b2",  # pragma: allowlist secret
            default_model="m-b",
            extra_models="m-b2,m-b",
            embedding_model="e-b",
            timeout=30,
            concurrency_per_key=5,
            priority=20,
            enabled=True,
        )
        LLMProvider.objects.create(
            name="platform-a",
            base_url="  http://a/v1  ",
            api_keys="sk-a",  # pragma: allowlist secret
            default_model="m-a",
            priority=5,
            enabled=True,
        )
        # 禁用平台不应出现
        LLMProvider.objects.create(
            name="platform-off",
            base_url="http://off/v1",
            api_keys="sk-off",  # pragma: allowlist secret
            default_model="m-off",
            priority=1,
            enabled=False,
        )

        providers = LLMProviderService.get_providers()

        assert [p.name for p in providers] == ["platform-a", "platform-b"]
        a, b = providers
        # base_url 被 strip
        assert a.base_url == "http://a/v1"
        assert a.api_keys == ["sk-a"]
        assert a.default_model == "m-a"
        # 未填字段走 model 默认值
        assert a.embedding_model == ""
        assert a.timeout == 120
        assert a.concurrency_per_key == 3  # model default
        assert a.priority == 5
        assert a.enabled is True
        # 显式字段透传 + extra_models 解析去重
        assert b.api_keys == ["sk-b1", "sk-b2"]
        assert b.extra_models == ["m-b2", "m-b"]
        assert b.embedding_model == "e-b"
        assert b.timeout == 30
        assert b.concurrency_per_key == 5
        assert b.priority == 20

    @pytest.mark.django_db
    def test_zero_concurrency_when_none(self) -> None:
        """DB 中 concurrency_per_key 为 0 时透传 0（非 None 生效）。"""
        LLMProviderService.invalidate_cache()
        LLMProvider.objects.create(
            name="zero",
            base_url="http://z/v1",
            default_model="m",
            concurrency_per_key=0,
            enabled=True,
        )
        providers = LLMProviderService.get_providers()
        assert providers[0].concurrency_per_key == 0

    @pytest.mark.django_db
    def test_ttl_cache_hits_db_once(self) -> None:
        LLMProviderService.invalidate_cache()
        LLMProvider.objects.create(name="law", base_url="http://law/v1", default_model="kimi26", enabled=True)

        # 统计 _load_from_db 的真实调用次数（不 patch 实现，只包一层计数）
        calls = {"n": 0}
        with _patched_load(LLMProviderService, _counting_load(LLMProviderService, calls)):
            first = LLMProviderService.get_providers()
            second = LLMProviderService.get_providers()

        assert [p.name for p in first] == ["law"]
        assert [p.name for p in second] == ["law"]
        assert calls["n"] == 1, "TTL 缓存生效，第二次调用不应再查 DB"

    @pytest.mark.django_db
    def test_invalidate_cache_forces_db_reload(self) -> None:
        LLMProviderService.invalidate_cache()
        LLMProvider.objects.create(name="law", base_url="http://law/v1", default_model="kimi26", enabled=True)
        assert [p.name for p in LLMProviderService.get_providers()] == ["law"]

        LLMProvider.objects.create(name="xiaomi", base_url="http://xm/v1", default_model="mimo", enabled=True)
        LLMProviderService.invalidate_cache()

        names = [p.name for p in LLMProviderService.get_providers()]
        assert names == ["law", "xiaomi"]

    @pytest.mark.django_db
    def test_load_from_db_returns_empty_when_no_rows(self) -> None:
        LLMProviderService.invalidate_cache()
        assert LLMProviderService.get_providers() == []

    @pytest.mark.django_db
    def test_get_providers_swallows_db_error(self, caplog: pytest.LogCaptureFixture) -> None:
        """DB 读取抛异常时降级为空列表并记录 warning（不向上抛）。"""
        LLMProviderService.invalidate_cache()

        def boom(cls: Any) -> list[Any]:
            raise RuntimeError("db unavailable")

        with _patched_load(LLMProviderService, classmethod(boom)):
            with caplog.at_level(logging.WARNING, logger=LOGGER_LLM_PROVIDER):
                assert LLMProviderService.get_providers() == []

        assert any("读取平台配置失败" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    @pytest.mark.django_db(transaction=True)
    async def test_aget_providers_behaves_like_sync(self) -> None:
        await _areset_provider_state()
        await LLMProvider.objects.acreate(
            name="law", base_url="http://law/v1", default_model="kimi26", priority=10, enabled=True
        )
        await LLMProvider.objects.acreate(
            name="xiaomi", base_url="http://xm/v1", default_model="mimo", priority=5, enabled=True
        )

        providers = await LLMProviderService.aget_providers()

        assert [p.name for p in providers] == ["xiaomi", "law"]
        assert all(isinstance(p.name, str) for p in providers)

    @pytest.mark.asyncio
    @pytest.mark.django_db(transaction=True)
    async def test_aget_and_get_share_cache(self) -> None:
        """async 写入的缓存 sync 读取直接命中（缓存为 class 级共享）。"""
        await _areset_provider_state()
        await LLMProvider.objects.acreate(name="law", base_url="http://law/v1", default_model="kimi26", enabled=True)

        calls = {"n": 0}
        with _patched_load(LLMProviderService, _counting_load(LLMProviderService, calls)):
            await LLMProviderService.aget_providers()
            # sync 读取在 async 上下文中被 sync_to_async 包裹后命中同一缓存
            await sync_to_async(LLMProviderService.get_providers)()

        assert calls["n"] == 1

    @pytest.mark.asyncio
    @pytest.mark.django_db(transaction=True)
    async def test_aget_providers_db_error_returns_empty(self) -> None:
        LLMProviderService.invalidate_cache()

        def boom(cls: Any) -> list[Any]:
            raise RuntimeError("db down")

        with _patched_load(LLMProviderService, classmethod(boom)):
            assert await LLMProviderService.aget_providers() == []


class TestLoadFromDbClassmethodRegression:
    """重点：``_load_from_db`` 从 @staticmethod 改为 @classmethod 后的调用方式回归。"""

    @pytest.mark.django_db
    def test_load_from_db_is_classmethod(self) -> None:
        assert isinstance(LLMProviderService.__dict__["_load_from_db"], classmethod), "_load_from_db 应为 classmethod"

    @pytest.mark.django_db
    def test_direct_cls_call(self) -> None:
        """``cls._load_from_db()`` 形式调用正常。"""
        LLMProvider.objects.create(name="law", base_url="http://law/v1", default_model="kimi26", enabled=True)
        providers = LLMProviderService._load_from_db()
        assert [p.name for p in providers] == ["law"]

    @pytest.mark.asyncio
    @pytest.mark.django_db(transaction=True)
    async def test_sync_to_async_call(self) -> None:
        """``sync_to_async(cls._load_from_db)()`` 形式调用正常（aget_providers 内部用法）。"""
        await _areset_provider_state()
        await LLMProvider.objects.acreate(name="law", base_url="http://law/v1", default_model="kimi26", enabled=True)
        providers = await sync_to_async(LLMProviderService._load_from_db)()
        assert [p.name for p in providers] == ["law"]

    @pytest.mark.django_db
    def test_classmethod_receives_cls(self) -> None:
        """classmethod 首参为 cls，可在实现内访问类属性/类方法。"""
        captured: dict[str, Any] = {}
        real_load = LLMProviderService._load_from_db.__func__

        def fake(cls: type[Any]) -> list[Any]:
            captured["cls"] = cls
            assert cls is LLMProviderService
            # cls 上可访问类属性（验证 classmethod 语义未被破坏）
            assert cls._CACHE_TTL_SECONDS > 0
            return real_load(cls)

        with patch.object(LLMProviderService, "_load_from_db", classmethod(fake)):
            assert LLMProviderService._load_from_db() == []

        assert captured["cls"] is LLMProviderService


class TestInitializeDefaultE2E:
    """``initialize_default()`` 幂等性与默认平台内容。"""

    def teardown_method(self) -> None:
        LLMProviderService.invalidate_cache()

    @pytest.mark.django_db
    def test_creates_default_when_empty(self) -> None:
        assert LLMProviderService.initialize_default() == (1, 0)
        row = LLMProvider.objects.get()
        assert row.name == "律所 kimi"
        assert row.default_model == "kimi26"
        assert row.base_url
        assert row.api_keys == ""
        assert row.concurrency_per_key == 3
        assert row.priority == 10
        assert row.enabled is True

    @pytest.mark.django_db
    def test_idempotent_when_exists(self) -> None:
        LLMProviderService.initialize_default()
        assert LLMProviderService.initialize_default() == (0, 1)
        assert LLMProvider.objects.count() == 1

    @pytest.mark.django_db
    def test_skips_when_any_provider_exists(self) -> None:
        LLMProvider.objects.create(name="other", base_url="http://other/v1", default_model="m", enabled=True)
        assert LLMProviderService.initialize_default() == (0, 1)
        assert LLMProvider.objects.get().name == "other"

    @pytest.mark.django_db
    def test_initialize_default_then_get_providers(self) -> None:
        """初始化后清过缓存，get_providers 应读到新创建的默认平台。"""
        LLMProviderService.initialize_default()
        providers = LLMProviderService.get_providers()
        assert [p.name for p in providers] == ["律所 kimi"]
        assert providers[0].default_model == "kimi26"


# ── 场景 2：ParseProviderService ──────────────────────────────────────────────


class TestParseProviderServiceE2E:
    """文档解析平台服务链路（同样改了 staticmethod → classmethod）。"""

    def teardown_method(self) -> None:
        ParseProviderService.invalidate_cache()

    @pytest.mark.django_db
    def test_load_from_db_is_classmethod(self) -> None:
        assert isinstance(ParseProviderService.__dict__["_load_from_db"], classmethod), (
            "ParseProviderService._load_from_db 应为 classmethod"
        )

    @pytest.mark.django_db
    def test_direct_cls_call_and_sorting(self) -> None:
        DocumentParseProvider.objects.create(
            name="M1", provider_type="mineru", priority=10, enabled=True, credentials="k1\nk2"
        )
        DocumentParseProvider.objects.create(
            name="T1", provider_type="textin", priority=5, enabled=True, credentials="app|sec"
        )
        DocumentParseProvider.objects.create(
            name="M-off", provider_type="mineru", priority=1, enabled=False, credentials="k3"
        )

        rows = ParseProviderService._load_from_db()

        assert [r.name for r in rows] == ["T1", "M1"]
        assert all(r.enabled for r in rows)

    @pytest.mark.django_db
    def test_get_providers_cached_and_invalidated(self) -> None:
        DocumentParseProvider.objects.create(
            name="M1", provider_type="mineru", priority=10, enabled=True, credentials="k1"
        )
        calls = {"n": 0}
        with _patched_load(ParseProviderService, _counting_load(ParseProviderService, calls)):
            ParseProviderService.get_providers()
            ParseProviderService.get_providers()
            assert calls["n"] == 1
            ParseProviderService.invalidate_cache()
            ParseProviderService.get_providers()
            assert calls["n"] == 2

    @pytest.mark.django_db
    def test_get_provider_by_type(self) -> None:
        DocumentParseProvider.objects.create(
            name="M1", provider_type="mineru", priority=10, enabled=True, credentials="k1"
        )
        DocumentParseProvider.objects.create(
            name="M2", provider_type="mineru", priority=2, enabled=True, credentials="k2"
        )
        DocumentParseProvider.objects.create(
            name="T1", provider_type="textin", priority=5, enabled=True, credentials="app|sec"
        )

        assert ParseProviderService.get_provider("mineru").name == "M2"
        assert ParseProviderService.get_provider("textin").name == "T1"
        assert ParseProviderService.get_provider("local") is None

    @pytest.mark.django_db
    def test_get_providers_swallows_db_error(self) -> None:
        ParseProviderService.invalidate_cache()

        def boom(cls: Any) -> list[Any]:
            raise RuntimeError("db unavailable")

        with _patched_load(ParseProviderService, classmethod(boom)):
            assert ParseProviderService.get_providers() == []

    @pytest.mark.asyncio
    @pytest.mark.django_db(transaction=True)
    async def test_sync_to_async_call(self) -> None:
        """classmethod 可通过 sync_to_async 调用（与 aget 模式一致）。"""
        await _areset_provider_state()
        await DocumentParseProvider.objects.acreate(
            name="M1", provider_type="mineru", priority=10, enabled=True, credentials="k1"
        )
        rows = await sync_to_async(ParseProviderService._load_from_db)()
        assert [r.name for r in rows] == ["M1"]


# ── 场景 3：LLMService 集成（mock backend） ───────────────────────────────────


class TestLLMServiceIntegration:
    """service → client → fallback_policy → backend 链路（mock backend，不打真实 Ollama）。"""

    def _build_service(self, backend_configs: dict[str, Any]) -> Any:
        from apps.core.llm.service import LLMService

        return LLMService(backend_configs=backend_configs, default_backend="openai_compatible")

    @staticmethod
    def _mock_config() -> MagicMock:
        cfg = MagicMock()
        cfg.name = "openai_compatible"
        cfg.enabled = True
        cfg.priority = 1
        cfg.default_model = "kimi26"
        cfg.base_url = "http://mock/v1"
        cfg.api_key = "sk-mock"  # pragma: allowlist secret
        cfg.timeout = 30
        cfg.providers = []
        cfg.extra_options = {}
        return cfg

    def test_service_locator_get_llm_service(self) -> None:
        """ServiceLocator.get_llm_service() 能取到 LLMService 实例。"""
        from apps.core.interfaces import ServiceLocator
        from apps.core.llm.service import LLMService
        from apps.core.protocols import ILLMService

        with (
            patch("apps.core.llm.config.LLMConfig.get_backend_configs", return_value={}),
            patch("apps.core.llm.config.LLMConfig.get_default_backend", return_value="openai_compatible"),
        ):
            with ServiceLocator.scope():
                service = ServiceLocator.get_llm_service()
                assert isinstance(service, LLMService)
                # ILLMService 是 Protocol（未 @runtime_checkable，不能 isinstance），
                # 改为结构校验：LLMService 暴露协议要求的核心方法
                for method in ("chat", "achat", "complete", "stream", "astream", "embed_texts"):
                    assert callable(getattr(service, method)), method
                # 同一 scope 内缓存（同实例）
                assert ServiceLocator.get_llm_service() is service

    def test_chat_through_full_chain(self) -> None:
        """chat() 完整链路：service → client → fallback_policy → backend.chat。"""
        from apps.core.llm.backends.base import BackendConfig

        backend_configs: dict[str, BackendConfig] = {
            "openai_compatible": BackendConfig(
                name="openai_compatible",
                enabled=True,
                priority=1,
                default_model="kimi26",
                base_url="http://mock/v1",
                api_key="sk-mock",  # pragma: allowlist secret
                timeout=30,
            )
        }
        service = self._build_service(backend_configs)

        mock_backend = MagicMock()
        mock_backend.chat.return_value = _make_response("hello-from-backend")
        mock_backend.is_available.return_value = True

        with (
            patch.object(
                service._router, "get_backends_by_priority", return_value=[("openai_compatible", mock_backend)]
            ),
            patch.object(service._router, "get_backend", return_value=mock_backend),
        ):
            response = service.chat(
                messages=[{"role": "user", "content": "hi"}],
                model="kimi26",
                temperature=0.3,
                caller="test",
            )

        assert response.content == "hello-from-backend"
        assert response.backend == "openai_compatible"
        # 校验参数一路透传到 backend
        kwargs = mock_backend.chat.call_args[1]
        assert kwargs["messages"] == [{"role": "user", "content": "hi"}]
        assert kwargs["model"] == "kimi26"
        assert kwargs["temperature"] == 0.3

    def test_complete_through_full_chain(self) -> None:
        """complete() 把 prompt/system_prompt 转成 messages 后走同一链路。"""
        from apps.core.llm.backends.base import BackendConfig

        backend_configs: dict[str, BackendConfig] = {
            "openai_compatible": BackendConfig(
                name="openai_compatible",
                enabled=True,
                priority=1,
                default_model="kimi26",
                base_url="http://mock/v1",
                api_key="sk-mock",  # pragma: allowlist secret
            )
        }
        service = self._build_service(backend_configs)

        mock_backend = MagicMock()
        mock_backend.chat.return_value = _make_response("done")
        mock_backend.is_available.return_value = True

        with (
            patch.object(
                service._router, "get_backends_by_priority", return_value=[("openai_compatible", mock_backend)]
            ),
            patch.object(service._router, "get_backend", return_value=mock_backend),
        ):
            response = service.complete(
                prompt="hello",
                system_prompt="be brief",
                model="kimi26",
                caller="test",
            )

        assert response.content == "done"
        kwargs = mock_backend.chat.call_args[1]
        roles = [m["role"] for m in kwargs["messages"]]
        assert roles == ["system", "user"]
        assert kwargs["messages"][1]["content"] == "hello"

    @pytest.mark.asyncio
    async def test_achat_through_full_chain(self) -> None:
        """异步链路：service → client.achat → fallback_policy.execute_async → backend.achat。"""
        from apps.core.llm.backends.base import BackendConfig

        backend_configs: dict[str, BackendConfig] = {
            "openai_compatible": BackendConfig(
                name="openai_compatible",
                enabled=True,
                priority=1,
                default_model="kimi26",
                base_url="http://mock/v1",
                api_key="sk-mock",  # pragma: allowlist secret
            )
        }
        service = self._build_service(backend_configs)

        mock_backend = MagicMock()
        mock_backend.achat = AsyncMock(return_value=_make_response("async-done"))
        mock_backend.is_available.return_value = True

        with (
            patch.object(
                service._router, "get_backends_by_priority", return_value=[("openai_compatible", mock_backend)]
            ),
            patch.object(service._router, "get_backend", return_value=mock_backend),
        ):
            response = await service.achat(
                messages=[{"role": "user", "content": "hi"}],
                model="kimi26",
                caller="test",
            )

        assert response.content == "async-done"
        mock_backend.achat.assert_called_once()
        kwargs = mock_backend.achat.call_args[1]
        assert kwargs["messages"] == [{"role": "user", "content": "hi"}]
        assert kwargs["model"] == "kimi26"

    def test_fallback_policy_wiring_uses_router(self) -> None:
        """service 构造时 router/fallback_policy/client 三者正确接线。"""
        service = self._build_service({})
        assert service._router is not None
        assert service._fallback_policy.router is service._router
        assert service._client._default_backend == "openai_compatible"

    def test_chat_records_audit_on_success(self) -> None:
        """链路成功时 tracking 记录被触发（验证 service→tracking 未断）。"""
        from apps.core.llm.backends.base import BackendConfig

        backend_configs: dict[str, BackendConfig] = {
            "openai_compatible": BackendConfig(
                name="openai_compatible",
                enabled=True,
                priority=1,
                default_model="kimi26",
                base_url="http://mock/v1",
                api_key="sk-mock",  # pragma: allowlist secret
            )
        }
        service = self._build_service(backend_configs)

        mock_backend = MagicMock()
        mock_backend.chat.return_value = _make_response()
        mock_backend.is_available.return_value = True

        with (
            patch.object(
                service._router, "get_backends_by_priority", return_value=[("openai_compatible", mock_backend)]
            ),
            patch.object(service._router, "get_backend", return_value=mock_backend),
            patch("apps.core.llm.client.record_llm_call") as mock_record,
        ):
            service.chat(messages=[{"role": "user", "content": "x"}], model="kimi26", caller="t")

        assert mock_record.called
        assert mock_record.call_args[1]["success"] is True

    def test_real_router_builds_openai_compatible_backend(self) -> None:
        """真实 router（不 mock）能按 backend name 实例化后端（get_backend_class 注册表未坏）。"""
        service = self._build_service({})
        backend = service.get_backend("openai_compatible")
        assert type(backend).__name__ == "OpenAICompatibleBackend"
        assert backend.is_available() in (True, False)  # 不报异常即链路 OK

    def test_get_llm_service_singleton(self) -> None:
        """模块级 get_llm_service() 返回同一单例。"""
        from apps.core.llm import service as service_module
        from apps.core.llm.service import get_llm_service

        with (
            patch("apps.core.llm.config.LLMConfig.get_backend_configs", return_value={}),
            patch("apps.core.llm.config.LLMConfig.get_default_backend", return_value="openai_compatible"),
        ):
            service_module._llm_service = None  # 隔离：避免其他测试写入的单例影响
            try:
                assert get_llm_service() is get_llm_service()
            finally:
                service_module._llm_service = None


# ── 场景 4：model_list_service 日志修复 ───────────────────────────────────────


class TestModelListServiceLogging:
    """Ollama context_window 获取失败时记录 warning 且优雅返回（原 ``except: pass``）。"""

    @pytest.mark.django_db
    def test_generic_failure_logs_warning_and_degrades(self, caplog: pytest.LogCaptureFixture) -> None:
        from apps.core.llm.model_list_service import ModelListService

        with (
            patch("apps.core.llm.model_list_service.LLMConfig") as mock_cfg,
            patch("apps.core.llm.model_list_service.httpx") as mock_httpx,
        ):
            mock_cfg.get_ollama_base_url.return_value = "http://localhost:11434"
            mock_cfg.get_ollama_model.return_value = "qwen3:0.6b"
            mock_httpx.ConnectError = ConnectionError
            mock_httpx.TimeoutException = TimeoutError
            mock_httpx.post.side_effect = ValueError("bad json")

            with caplog.at_level(logging.WARNING, logger=LOGGER_MODEL_LIST):
                result = ModelListService._fetch_ollama_models()

        # 优雅返回：不抛异常，仍返回模型（context_window 兜底为 0）
        assert len(result) == 1
        assert result[0]["id"] == "qwen3:0.6b"
        assert result[0]["context_window"] == 0
        # 记录 warning（本分支修复点）
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert warnings, "Ollama context_window 获取失败应记录 warning"
        assert any("context_window" in r.getMessage() for r in warnings)
        assert any(r.exc_info for r in warnings), "warning 应带 exc_info"

    @pytest.mark.django_db
    def test_connection_error_silent_by_design(self, caplog: pytest.LogCaptureFixture) -> None:
        """连接失败（Ollama 未启动）按设计静默返回空，且不产生 warning 噪音。"""
        from apps.core.llm.model_list_service import ModelListService

        with (
            patch("apps.core.llm.model_list_service.LLMConfig") as mock_cfg,
            patch("apps.core.llm.model_list_service.httpx") as mock_httpx,
        ):
            mock_cfg.get_ollama_base_url.return_value = "http://localhost:11434"
            mock_cfg.get_ollama_model.return_value = "qwen3:0.6b"
            mock_httpx.ConnectError = type("ConnectError", (Exception,), {})
            mock_httpx.TimeoutException = type("TimeoutException", (Exception,), {})
            mock_httpx.post.side_effect = mock_httpx.ConnectError()

            with caplog.at_level(logging.WARNING, logger=LOGGER_MODEL_LIST):
                result = ModelListService._fetch_ollama_models()

        assert result == []
        assert not [r for r in caplog.records if r.levelno == logging.WARNING]

    @pytest.mark.django_db
    def test_context_length_parsed(self) -> None:
        from apps.core.llm.model_list_service import ModelListService

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"model_info": {"llama.context_length": 4096}}
        mock_resp.raise_for_status = MagicMock()

        with (
            patch("apps.core.llm.model_list_service.LLMConfig") as mock_cfg,
            patch("apps.core.llm.model_list_service.httpx") as mock_httpx,
        ):
            mock_cfg.get_ollama_base_url.return_value = "http://localhost:11434"
            mock_cfg.get_ollama_model.return_value = "qwen3:0.6b"
            mock_httpx.post.return_value = mock_resp

            result = ModelListService._fetch_ollama_models()

        assert result[0]["context_window"] == 4096


# ── 场景 5：删除项无残留 ───────────────────────────────────────────────────────


class TestDeletedModulesGone:
    """验证删除的模块/符号确实不存在（删干净了）。"""

    def test_costs_module_removed(self) -> None:
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module("apps.core.llm.costs")

    def test_costs_symbols_not_importable(self) -> None:
        for symbol in ("price_for_model", "estimate_cost", "aggregate_costs", "aaggregate_costs", "DEFAULT_PRICING"):
            with pytest.raises(ModuleNotFoundError):
                exec(f"from apps.core.llm.costs import {symbol}")

    def test_event_bus_module_removed(self) -> None:
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module("apps.core.infrastructure.event_bus")

    def test_event_bus_symbol_not_importable(self) -> None:
        with pytest.raises(ModuleNotFoundError):
            exec("from apps.core.infrastructure.event_bus import EventBus")

    def test_events_module_removed(self) -> None:
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module("apps.core.infrastructure.events")

    def test_events_symbol_not_importable(self) -> None:
        with pytest.raises(ModuleNotFoundError):
            exec("from apps.core.infrastructure.events import Events")

    def test_infrastructure_has_no_event_bus_attribute(self) -> None:
        """``apps.core.infrastructure.EventBus`` 作为属性也不应存在。"""
        from apps.core import infrastructure

        assert not hasattr(infrastructure, "EventBus")
        assert not hasattr(infrastructure, "Events")

    def test_source_files_absent(self) -> None:
        llm_costs = importlib.util.find_spec("apps.core.llm.costs")
        assert llm_costs is None

    def test_infrastructure_init_still_imports(self) -> None:
        """删除后 infrastructure 包的公开 API 仍正常（无断裂 re-export）。"""
        from apps.core import infrastructure

        assert hasattr(infrastructure, "CacheKeys")
        assert hasattr(infrastructure, "HealthChecker")
        assert hasattr(infrastructure, "PerformanceMonitor")

    def test_no_production_references_to_deleted_symbols(self) -> None:
        """apps/ 与 plugins 下不再引用已删除符号。"""
        import re
        from pathlib import Path

        backend_dir = Path(__file__).resolve().parents[4]
        pattern = re.compile(r"(from|import)\s+apps\.core\.(llm\.costs|infrastructure\.(event_bus|events))")
        targets = [backend_dir / "apps", backend_dir / "plugins"]
        for target in targets:
            assert target.exists(), f"扫描目标不存在: {target}"
        found: list[str] = []
        for target in targets:
            for py in target.rglob("*.py"):
                if "__pycache__" in py.parts:
                    continue
                for lineno, line in enumerate(py.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                    if pattern.search(line):
                        found.append(f"{py}:{lineno}: {line.strip()}")
        assert not found, f"发现已删除模块的残留引用:\n{chr(10).join(found)}"

    def test_grep_pattern_actually_matches_a_real_reference(self) -> None:
        """自我校验：上面的 pattern 确实能匹配 import 语句（防止 pattern 写错导致假绿）。"""
        import re

        pattern = re.compile(r"(from|import)\s+apps\.core\.(llm\.costs|infrastructure\.(event_bus|events))")
        samples = [
            "from apps.core.llm.costs import estimate_cost",
            "from apps.core.infrastructure.event_bus import EventBus",
            "from apps.core.infrastructure.events import Events",
            "import apps.core.llm.costs",
        ]
        matched = [s for s in samples if pattern.search(s)]
        assert len(matched) == len(samples), matched


# ── 场景 6：回归 ──────────────────────────────────────────────────────────────


class TestRegressionsAroundDeletions:
    """LLM 链路周边在删除 costs 后的回归探针。"""

    def test_llm_package_exports_intact(self) -> None:
        from apps.core import llm

        assert hasattr(llm, "LLMService")
        assert hasattr(llm, "get_llm_service")

    def test_llm_provider_service_import_path(self) -> None:
        from apps.core.services.llm_provider_service import LLMProviderService as S

        assert S._CACHE_TTL_SECONDS == 300.0

    def test_class_var_annotations_present(self) -> None:
        """ClassVar 注解保留（classmethod 改动未破坏类型语义）。"""
        llm_anns = LLMProviderService.__annotations__
        assert "_CACHE_TTL_SECONDS" in llm_anns
        assert "_cache" in llm_anns

        parse_anns = ParseProviderService.__annotations__
        assert "_CACHE_TTL_SECONDS" in parse_anns
        assert "_cache" in parse_anns

    def test_parse_provider_service_class_var(self) -> None:
        from apps.core.services.document_parse_provider_service import ParseProviderService as S

        assert S._CACHE_TTL_SECONDS == 300.0
