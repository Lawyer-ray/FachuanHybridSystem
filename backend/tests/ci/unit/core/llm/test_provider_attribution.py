"""成本归属：模型 → 平台名的解析，以及按平台聚合（TECH-DEBT ①）。

## 守的是什么

报表要能回答「钱花在哪个平台」。旧的 `LLMCallRecord` / `AgentRun` 只有模型名，
同一个模型可能由多个平台提供 → 按模型聚合分不清钱是谁花的。

这里钉两条：
1. **解析口径必须与真实路由一致**（复用 `_pick_provider`），否则报表归属会和实际
   发请求的平台分叉——那种分叉比没有数据更糟；
2. **解析不出来就是空串**（报表显示「未知」），绝不按默认平台硬塞。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest import mock

import pytest

from apps.core.llm import provider_lookup


def _provider(name: str, models: list[str], priority: int = 10) -> Any:
    return SimpleNamespace(
        name=name,
        priority=priority,
        enabled=True,
        extra_models=models,
        default_model=models[0],
        all_models=models,
    )


class TestResolveProviderName:
    def test_matches_by_model_whitelist(self, monkeypatch: pytest.MonkeyPatch) -> None:
        providers = [_provider("平台甲", ["m1"], priority=1), _provider("平台乙", ["m2"], priority=2)]
        monkeypatch.setattr(
            "apps.core.services.llm_provider_service.LLMProviderService.get_providers", lambda: providers
        )

        assert provider_lookup.resolve_provider_name("m2") == "平台乙"

    def test_falls_back_to_highest_priority(self, monkeypatch: pytest.MonkeyPatch) -> None:
        providers = [_provider("平台甲", ["m1"], priority=5)]
        monkeypatch.setattr(
            "apps.core.services.llm_provider_service.LLMProviderService.get_providers", lambda: providers
        )

        # 未知模型 → 与真实路由同口径：回落优先级最高的启用平台
        assert provider_lookup.resolve_provider_name("不存在的模型") == "平台甲"

    def test_empty_when_no_provider(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("apps.core.services.llm_provider_service.LLMProviderService.get_providers", list)

        assert provider_lookup.resolve_provider_name("m1") == ""

    def test_never_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _boom() -> list[Any]:
            raise RuntimeError("db down")

        monkeypatch.setattr("apps.core.services.llm_provider_service.LLMProviderService.get_providers", _boom)

        # 统计旁路：解析失败不能拖垮调用记录写入
        assert provider_lookup.resolve_provider_name("m1") == ""


class TestAResolveProviderName:
    """async 链路护栏：必须走 ``aget_providers``，绝不能碰同步访问器。

    真机回归（2026-11-21）：agent 运行落库 ``_record_run`` 在事件循环里调
    ``resolve_provider_name``，同步 ``get_providers()`` 读库抛
    ``SynchronousOnlyOperation``，被 ``_load_from_db`` 吞成空列表——成本归属
    静默变「未知」，日志只剩一条 warning。
    """

    @pytest.mark.asyncio
    async def test_uses_aget_providers_and_never_calls_sync_accessor(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from apps.core.services.llm_provider_service import LLMProviderService

        providers = [_provider("平台甲", ["m1"], priority=1), _provider("平台乙", ["m2"], priority=2)]

        def _sync_access_forbidden() -> list[Any]:
            raise AssertionError("async 链路调用了同步 get_providers（会触发 SynchronousOnlyOperation）")

        monkeypatch.setattr(LLMProviderService, "get_providers", _sync_access_forbidden)
        monkeypatch.setattr(LLMProviderService, "_cache", None)
        monkeypatch.setattr(LLMProviderService, "_load_from_db", staticmethod(lambda: providers), raising=True)

        # aget_providers 是真实实现（内部 sync_to_async(_load_from_db)），必须正常返回
        assert await provider_lookup.aresolve_provider_name("m2") == "平台乙"

    @pytest.mark.asyncio
    async def test_empty_when_no_provider(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def _aget() -> list[Any]:
            return []

        monkeypatch.setattr("apps.core.services.llm_provider_service.LLMProviderService.aget_providers", _aget)

        assert await provider_lookup.aresolve_provider_name("m1") == ""

    @pytest.mark.asyncio
    async def test_never_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def _boom() -> list[Any]:
            raise RuntimeError("db down")

        monkeypatch.setattr("apps.core.services.llm_provider_service.LLMProviderService.aget_providers", _boom)

        # 与同步版同一纪律：统计旁路失败只影响归属字段，不拖垮调用记录写入
        assert await provider_lookup.aresolve_provider_name("m1") == ""


class TestRecordCarriesProvider:
    def test_llm_call_record_written_with_provider(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict[str, Any] = {}

        monkeypatch.setattr("apps.core.llm.tracking.is_tracking_enabled", lambda: True)
        monkeypatch.setattr("apps.core.llm.tracking._write_record", lambda **fields: captured.update(fields))
        monkeypatch.setattr("apps.core.llm.provider_lookup.resolve_provider_name", lambda model: "平台乙")

        from apps.core.llm.tracking import record_llm_call

        record_llm_call(backend="openai-compatible", model="m2", duration_ms=1.0)

        assert captured["provider"] == "平台乙"
        assert captured["model"] == "m2"
