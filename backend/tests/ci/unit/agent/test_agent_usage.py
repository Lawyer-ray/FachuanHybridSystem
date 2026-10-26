"""AgentRun 成本/耗时可观测（P1-2）。

只记成功路径等于把「最贵的失败」藏起来：用户按停止时模型可能已跑了大半
token，网关超时重试三次也是真金白银。这里覆盖三态落库与聚合口径。
"""

from __future__ import annotations

from typing import Any

import pytest

from apps.agent.models import AgentRun, AgentSession

TEST_PASSWORD = "x-test-12345678"  # pragma: allowlist secret


def _make_session() -> AgentSession:
    return AgentSession.objects.create(title="统计测试")


def _run(session: AgentSession, **kwargs: Any) -> AgentRun:
    defaults: dict[str, Any] = {
        "session": session,
        "model": "kimi-2.6",
        "status": AgentRun.Status.OK,
        "input_tokens": 100,
        "output_tokens": 20,
        "tool_calls": 1,
        "duration_ms": 1000,
    }
    defaults.update(kwargs)
    return AgentRun.objects.create(**defaults)


@pytest.mark.django_db
class TestAgentRunModel:
    def test_defaults(self) -> None:
        run = AgentRun.objects.create(session=_make_session(), model="m")
        assert run.status == AgentRun.Status.OK
        assert run.input_tokens == 0
        assert run.error_kind == ""

    def test_indexes_declared(self) -> None:
        """按用户/会话/状态的时间查询都有索引（否则大表下统计会拖垮库）。"""
        names = {idx.name for idx in AgentRun._meta.indexes}
        assert {"agent_run_user_idx", "agent_run_session_idx", "agent_run_status_idx"} <= names


@pytest.mark.django_db
class TestCacheTokens:
    """缓存 token 账目（本轮改造核心）。

    法穿的核心设计之一是「AGENTS.md 逐轮字节稳定 → 命中 provider prompt
    cache」。改造前账上完全看不到它有没有生效（``input_tokens`` 只装未命中
    部分），这两列就是那个缺失的仪表盘。

    口径已经定得很死，测试就是守这个口径不被后来人「顺手改成更直观的算法」：

    - ``cacheRead`` **不计**入成本（它是重读的累计前缀，计进去会虚高数倍）
    - ``cacheWrite`` **计**入成本（它是真实计费的，且通常比普通输入更贵）
    """

    def test_defaults_to_zero(self) -> None:
        """历史行与新行默认都是 0——不用 null 以免所有查询多一层空值分支。"""
        run = AgentRun.objects.create(session=_make_session(), model="m")
        assert run.cache_read_tokens == 0
        assert run.cache_write_tokens == 0

    def test_total_excludes_cache_read(self) -> None:
        """总计**不含** cacheRead，但**含** cacheWrite。"""
        run = _run(
            _make_session(),
            input_tokens=100,
            output_tokens=20,
            cache_read_tokens=5000,
            cache_write_tokens=300,
        )
        assert run.total_tokens == 100 + 20 + 300
        assert run.total_tokens != 100 + 20 + 300 + 5000, "cacheRead 被误计入成本口径"

    def test_hit_rate_formula(self) -> None:
        """命中率 = cacheRead / (input + cacheRead + cacheWrite)。"""
        run = _run(
            _make_session(),
            input_tokens=100,
            output_tokens=999,  # output 不参与命中率
            cache_read_tokens=800,
            cache_write_tokens=100,
        )
        # 800 / (100 + 800 + 100) = 0.8
        assert run.cache_hit_rate == 0.8

    def test_hit_rate_zero_when_no_input(self) -> None:
        """什么都没有时返回 0.0 而不是除零。"""
        run = AgentRun.objects.create(session=_make_session(), model="m")
        assert run.cache_hit_rate == 0.0

    def test_hit_rate_full_cache(self) -> None:
        """纯命中（没新 input、没写入）时是 1.0。"""
        run = _run(_make_session(), input_tokens=0, output_tokens=10, cache_read_tokens=900)
        assert run.cache_hit_rate == 1.0

    def test_hit_rate_no_cache_at_all_is_zero(self) -> None:
        """有 input 但完全没命中 → 0.0（这时是真的没命中，不是没数据）。"""
        run = _run(_make_session(), input_tokens=500, output_tokens=10)
        assert run.cache_hit_rate == 0.0


@pytest.mark.django_db(transaction=True)
class TestCacheTokenWiring:
    """链路：bridge 解析 pi 的 cacheRead/cacheWrite → chat_service 累加 → 落库。

    2026-10-25 真机 fixture（``tests/ci/fixtures/agent/*.jsonl``）实测 pi 的
    usage 字段就是 camelCase 的 ``cacheRead`` / ``cacheWrite``。如果哪天上游
    改成 snake_case，这里会红灯。
    """

    def test_bridge_emits_cache_fields(self) -> None:
        from apps.agent.pi.bridge import translate_all
        from apps.agent.pi.rpc_client import PiEvent

        record = {
            "type": "message_end",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "好的"}],
                "usage": {
                    "input": 100,
                    "output": 20,
                    "cacheRead": 5000,
                    "cacheWrite": 300,
                },
            },
        }
        events = translate_all(PiEvent("event", record))
        usage = [e for e in events if e.get("type") == "usage"]
        assert usage, f"没有产出 usage 事件: {events}"
        assert usage[-1]["cache_read_tokens"] == 5000
        assert usage[-1]["cache_write_tokens"] == 300

    def test_bridge_missing_cache_fields_default_zero(self) -> None:
        """旧版 pi / 某些 provider 不上报缓存字段时给 0，不能 KeyError。"""
        from apps.agent.pi.bridge import translate_all
        from apps.agent.pi.rpc_client import PiEvent

        record = {
            "type": "message_end",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "好"}],
                "usage": {"input": 10, "output": 2},
            },
        }
        events = translate_all(PiEvent("event", record))
        usage = [e for e in events if e.get("type") == "usage"]
        assert usage
        assert usage[-1]["cache_read_tokens"] == 0
        assert usage[-1]["cache_write_tokens"] == 0

    def test_summarize_totals_cache_and_hit_rate(self) -> None:
        from apps.agent.services.usage_stats import summarize

        session = _make_session()
        _run(session, input_tokens=100, output_tokens=10, cache_read_tokens=800, cache_write_tokens=100)
        _run(session, input_tokens=100, output_tokens=10, cache_read_tokens=200, cache_write_tokens=0)

        summary = summarize(days=30)
        assert summary.cache_read_tokens == 1000
        assert summary.cache_write_tokens == 100
        # 1000 / (200 + 1000 + 100) = 0.7692...
        assert summary.cache_hit_rate == pytest.approx(0.7692, abs=1e-3)
        # 成本口径：input + output + cacheWrite，不含 cacheRead
        assert summary.total_tokens == 200 + 20 + 100

    def test_by_model_reports_hit_rate(self) -> None:
        from apps.agent.services.usage_stats import by_model

        session = _make_session()
        _run(session, model="cheap", input_tokens=100, cache_read_tokens=900, cache_write_tokens=0)
        _run(session, model="pricey", input_tokens=1000, cache_read_tokens=0, cache_write_tokens=0)

        rows = {row["model"]: row for row in by_model(days=30)}
        assert rows["cheap"]["cache_hit_rate"] == 0.9
        assert rows["pricey"]["cache_hit_rate"] == 0.0
        assert rows["cheap"]["cache_read_tokens"] == 900

    def test_admin_hit_rate_shows_dash_when_no_data(self) -> None:
        """Admin 对「没上报数据」显示 ``—`` 而不是 ``0%``。

        后者会被误读成「缓存完全没命中」，而真相是「这一轮没上报缓存字段」
        ——两个结论后续动作完全不同（前者要查前缀漂移，后者只需等升级）。
        """
        from apps.agent.admin import AgentRunAdmin

        admin_view = AgentRunAdmin(AgentRun, None)  # type: ignore[arg-type]
        blank = AgentRun.objects.create(session=_make_session(), model="m")
        assert admin_view.cache_hit_rate_display(blank) == "—"

        cached = _run(_make_session(), input_tokens=100, cache_read_tokens=900)
        assert admin_view.cache_hit_rate_display(cached) == "90.0%"


@pytest.mark.django_db(transaction=True)
class TestRecordRun:
    """stream_chat 的 _record_run：三态判定 + 字段落库。

    transaction=True：_record_run 是 async，走 asgiref 执行器线程的独立连接，
    普通事务包裹下测试里创建的 session 它看不见（外键会报不存在）。
    """

    def _record(self, **kwargs: Any) -> AgentRun:
        import asyncio

        from apps.agent.services.chat_service import _record_run

        session = _make_session()
        params: dict[str, Any] = {
            "session": session,
            "user_id": None,
            "model": "kimi-2.6",
            "cancelled": False,
            "error_kind": "",
            "input_tokens": 486,
            "output_tokens": 4,
            "tool_calls": 2,
            "duration_ms": 260,
        }
        params.update(kwargs)
        asyncio.run(_record_run(**params))
        return AgentRun.objects.get(session=session)

    def test_ok_run_records_tokens_and_duration(self) -> None:
        run = self._record()
        assert run.status == AgentRun.Status.OK
        assert (run.input_tokens, run.output_tokens) == (486, 4)
        assert run.tool_calls == 2
        assert run.duration_ms == 260

    def test_cancelled_run_recorded(self) -> None:
        """用户按停止：已消耗的 token 必须留痕。"""
        run = self._record(cancelled=True, output_tokens=900)
        assert run.status == AgentRun.Status.CANCELLED
        assert run.output_tokens == 900

    def test_error_run_records_kind(self) -> None:
        run = self._record(error_kind="queue_timeout")
        assert run.status == AgentRun.Status.ERROR
        assert run.error_kind == "queue_timeout"

    def test_negative_values_clamped(self) -> None:
        """上游异常计数不能把统计带成负数。"""
        run = self._record(input_tokens=-5, output_tokens=-1, duration_ms=-9)
        assert run.input_tokens == 0
        assert run.output_tokens == 0
        assert run.duration_ms == 0

    def test_persist_failure_does_not_raise(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """统计落库失败绝不能把已成功的对话变成报错。"""
        import asyncio

        from apps.agent.services import chat_service

        def boom(*a: Any, **k: Any) -> Any:
            raise RuntimeError("db down")

        monkeypatch.setattr(chat_service.AgentRun.objects, "acreate", boom)
        asyncio.run(
            chat_service._record_run(
                session=_make_session(),
                user_id=None,
                model="m",
                cancelled=False,
                error_kind="",
                input_tokens=1,
                output_tokens=1,
                tool_calls=0,
                duration_ms=1,
            )
        )


@pytest.mark.django_db
class TestUsageStats:
    def test_summarize_counts_and_tokens(self) -> None:
        from apps.agent.services.usage_stats import summarize

        session = _make_session()
        _run(session, input_tokens=100, output_tokens=10)
        _run(session, input_tokens=200, output_tokens=20, status=AgentRun.Status.ERROR)
        _run(session, input_tokens=50, output_tokens=5, status=AgentRun.Status.CANCELLED)

        summary = summarize(days=30)
        assert summary.runs == 3
        assert summary.ok_runs == 1
        assert summary.error_runs == 1
        assert summary.cancelled_runs == 1
        assert summary.input_tokens == 350
        assert summary.output_tokens == 35
        assert summary.total_tokens == 385

    def test_error_rate(self) -> None:
        from apps.agent.services.usage_stats import summarize

        session = _make_session()
        _run(session)
        _run(session, status=AgentRun.Status.ERROR)
        summary = summarize(days=30)
        assert summary.error_rate == 0.5

    def test_avg_duration(self) -> None:
        from apps.agent.services.usage_stats import summarize

        session = _make_session()
        _run(session, duration_ms=1000)
        _run(session, duration_ms=3000)
        assert summarize(days=30).avg_duration_ms == 2000

    def test_empty_window_is_zero_not_crash(self) -> None:
        from apps.agent.services.usage_stats import summarize

        summary = summarize(days=30)
        assert summary.runs == 0
        assert summary.total_tokens == 0
        assert summary.error_rate == 0.0
        assert summary.avg_duration_ms == 0

    def test_scoped_by_user(self) -> None:
        from apps.agent.services.usage_stats import summarize
        from apps.organization.models import LawFirm, Lawyer

        firm = LawFirm.objects.create(name="统计律所")
        alice = Lawyer.objects.create_user(username="usage-alice", password=TEST_PASSWORD, law_firm=firm)
        bob = Lawyer.objects.create_user(username="usage-bob", password=TEST_PASSWORD, law_firm=firm)

        session = _make_session()
        _run(session, user=alice, input_tokens=100)
        _run(session, user=bob, input_tokens=999)

        assert summarize(user_id=alice.pk, days=30).input_tokens == 100
        assert summarize(user_id=bob.pk, days=30).input_tokens == 999

    def test_daily_series(self) -> None:
        from apps.agent.services.usage_stats import daily_series

        session = _make_session()
        _run(session, input_tokens=10)
        _run(session, input_tokens=20)
        series = daily_series(days=30)
        assert len(series) == 1
        assert series[0]["runs"] == 2
        assert series[0]["input_tokens"] == 30

    def test_by_model(self) -> None:
        from apps.agent.services.usage_stats import by_model

        session = _make_session()
        _run(session, model="a")
        _run(session, model="a")
        _run(session, model="b")
        rows = by_model(days=30)
        assert rows[0]["model"] == "a"
        assert rows[0]["runs"] == 2


class TestStreamChatRecordsRun:
    """端到端：一轮真实 stream_chat 必须落一条 AgentRun（成功与出错都要）。"""

    @staticmethod
    def _patch(monkeypatch: pytest.MonkeyPatch, events: list[dict[str, Any]]) -> None:
        from apps.agent.services import chat_service
        from apps.agent.services.event_bus import EventBus

        class _Acquire:
            async def __aenter__(self) -> Any:
                class _S:
                    async def prompt(self, m: str) -> None:
                        return None

                return _S()

            async def __aexit__(self, *exc: object) -> bool:
                return False

        class _Pool:
            waiting = 0
            saturated = False

            def acquire(self, **kwargs: Any) -> _Acquire:
                return _Acquire()

        async def fake_stream(pi_session: Any, *, agent: str = "pi") -> Any:
            for event in events:
                yield event

        async def fake_pool() -> Any:
            return _Pool()

        async def fake_model() -> str | None:
            return "kimi-2.6"

        monkeypatch.setattr(chat_service, "get_pool", fake_pool)
        monkeypatch.setattr(chat_service, "_resolve_model", fake_model)
        monkeypatch.setattr(chat_service, "stream_events", fake_stream)
        monkeypatch.setattr(EventBus, "_ensure_relay", lambda self: None)

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_successful_run_recorded_with_tokens(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from apps.agent.services import chat_service

        self._patch(
            monkeypatch,
            [
                {"type": "delta", "content": "答"},
                {"type": "tool_call", "tool_call_id": "c1", "name": "read", "arguments": {}},
                {"type": "usage", "input_tokens": 486, "output_tokens": 4},
                {"type": "done"},
            ],
        )
        session = await AgentSession.objects.acreate(title="e2e")
        async for _ in chat_service.stream_chat(session=session, user_message="q", user_id=None):
            pass

        run = await AgentRun.objects.filter(session=session).afirst()
        assert run is not None, "对话结束没有落 AgentRun"
        assert run.status == AgentRun.Status.OK
        assert run.input_tokens == 486
        assert run.output_tokens == 4
        assert run.tool_calls == 1
        assert run.model == "kimi-2.6"
        assert run.duration_ms >= 0

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_queue_timeout_records_error_kind(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """排队超时也要留痕（否则看不出「忙」导致的失败率）。"""
        from apps.agent.pi.pool import PoolQueueTimeoutError
        from apps.agent.services import chat_service
        from apps.agent.services.event_bus import EventBus

        class _Pool:
            waiting = 0
            saturated = False

            def acquire(self, **kwargs: Any) -> Any:
                raise PoolQueueTimeoutError("满了")

        async def fake_pool() -> Any:
            return _Pool()

        async def fake_model() -> str | None:
            return "m"

        monkeypatch.setattr(chat_service, "get_pool", fake_pool)
        monkeypatch.setattr(chat_service, "_resolve_model", fake_model)
        monkeypatch.setattr(EventBus, "_ensure_relay", lambda self: None)

        session = await AgentSession.objects.acreate(title="e2e-err")
        async for _ in chat_service.stream_chat(session=session, user_message="q", user_id=None):
            pass

        run = await AgentRun.objects.filter(session=session).afirst()
        assert run is not None
        assert run.status == AgentRun.Status.ERROR
        assert run.error_kind == "queue_timeout"
