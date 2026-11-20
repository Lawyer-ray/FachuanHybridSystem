"""judge 的默认调用必须走 **async 安全** 的 ``LLMService.create()``。

## 来历（真机实测，单测原本测不出来）

合并 B2/B2.5 后用真实三栏会话跑 ``POST /agent/sessions/{id}/review``：
**21 条判定全部 ``judge_error``，每栏 ``valid=0``**，而单测全绿——因为单测注入了
``call_judge``，绕过了生产实现 ``_llm_judge``。

日志里是 ``apps.core.llm.service fallback_policy ... 后端不可用,跳过`` ×N。
直接复现后拿到真因：

    django.core.exceptions.SynchronousOnlyOperation:
        You cannot call this from an async context - use a thread or sync_to_async.

``get_llm_service()`` 是**同步**构造的，在 async 上下文里首次解析 provider 会走同步 ORM；
异常被 fallback 策略吞成「后端不可用」，于是每一条判定都变成 ``judge_error``。
这正是 ``docs/harness/backend/agent-runtime.md``「SyncToAsync 边界」那一节记的坑。

修法：``_llm_judge`` 改走 ``LLMService.create()``（官方异步工厂，会预热配置缓存），
进程内缓存一份。本文件锁住三件事：**不碰同步单例**、**缓存复用**、**并发只建一次**。
"""

from __future__ import annotations

import asyncio

import pytest

from apps.agent.services.review import judge_client as jc


class _FakeReply:
    content = '{"criteria_met": true, "explanation": "看起来满足"}'
    model = "fake-judge"
    prompt_tokens = 11
    completion_tokens = 7
    total_tokens = 18


class _FakeService:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def achat(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeReply()


@pytest.fixture(autouse=True)
def _reset_service_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """每个用例都从"还没建过 service"开始，否则缓存会串场。"""
    monkeypatch.setattr(jc, "_async_service", None, raising=False)
    monkeypatch.setattr(jc, "_async_service_lock", None, raising=False)


class TestDefaultJudgeCall:
    @pytest.mark.asyncio
    async def test_default_path_never_touches_sync_singleton(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """哪怕同步单例炸掉，默认判定也必须能跑——这就是当初全 ``judge_error`` 的回归锁。"""
        fake = _FakeService()
        monkeypatch.setattr(jc, "_async_service", fake, raising=False)

        def _boom():  # pragma: no cover - 被调用即失败
            raise AssertionError("judge 不许用同步 get_llm_service()")

        monkeypatch.setattr("apps.core.llm.service.get_llm_service", _boom)

        reply = await jc._llm_judge("prompt", "judge-model")

        assert "criteria_met" in reply.content
        assert (reply.prompt_tokens, reply.completion_tokens, reply.total_tokens) == (11, 7, 18)
        assert fake.calls[0]["temperature"] == 0.0, "判官必须确定性：temperature 只能是 0"
        assert fake.calls[0]["caller"] == "agent.review.judge", "成本要能归因到评审"

    @pytest.mark.asyncio
    async def test_service_is_created_once_and_cached(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """``LLMService.create()`` 会读库预热，不能每条判定都建一次。"""
        created: list[int] = []

        class _FakeLLMService:
            @classmethod
            async def create(cls):
                created.append(1)
                return _FakeService()

        monkeypatch.setattr("apps.core.llm.service.LLMService", _FakeLLMService)

        await jc._llm_judge("p", "m")
        await jc._llm_judge("p", "m")

        assert len(created) == 1

    @pytest.mark.asyncio
    async def test_concurrent_first_calls_build_service_once(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """并发首调（jury 的 Semaphore=8）不能各建一份 service。"""
        created: list[int] = []

        class _SlowFakeService(_FakeService):
            pass

        class _FakeLLMService:
            @classmethod
            async def create(cls):
                created.append(1)
                await asyncio.sleep(0)  # 让出执行权，制造真实竞争窗口
                return _SlowFakeService()

        monkeypatch.setattr("apps.core.llm.service.LLMService", _FakeLLMService)

        await asyncio.gather(*(jc._llm_judge("p", "m") for _ in range(8)))

        assert len(created) == 1
