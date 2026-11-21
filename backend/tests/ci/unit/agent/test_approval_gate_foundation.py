"""三闸门地基：run_id 归因 / 双入口去重 / 驳回理由回传 / 取消态。

背景（2026-11 审计）：审批要同时服务三个入口——pi 扩展（后端钩子）、
MCP 服务端闸门（覆盖 dsh / openai-agents / 未来新后端）、写端点兜底。
三个入口共用一张卡，因此这一层必须先成立：

1. ``run_id`` / ``tool_call_id`` / ``dedupe_key`` 必须落库（否则多栏无法归因）；
2. 同一 (会话, 工具, 参数) 已在等待时，第二个入口**不能再建一张卡**；
3. 驳回理由必须回到调用方（原来被另一 ORM 实例写、等待方不回读，恒为兜底文案）；
4. 客户端断开取消时必须显式置 ``cancelled``，不能留 PENDING 等 7200 秒懒清理。
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from apps.agent.models import AgentApproval, AgentSession
from apps.agent.services import approval as approval_mod

#: 等待审批落库的上限（秒）。理由同 test_agent_multi_entry：冷启动实测 ~550ms，
#: 固定短睡会误报成「审批没落库」。
_LANDING_TIMEOUT = 5.0


async def _wait_approval_landed(session: AgentSession) -> AgentApproval | None:
    deadline = asyncio.get_running_loop().time() + _LANDING_TIMEOUT
    while asyncio.get_running_loop().time() < deadline:
        record = await AgentApproval.objects.filter(session=session).order_by("-created_at").afirst()
        if record is not None:
            return record
        await asyncio.sleep(0.02)
    return None


async def _wait_status(approval_id: Any, status: str) -> AgentApproval | None:
    deadline = asyncio.get_running_loop().time() + _LANDING_TIMEOUT
    while asyncio.get_running_loop().time() < deadline:
        record = await AgentApproval.objects.filter(approval_id=approval_id).afirst()
        if record is not None and record.status == status:
            return record
        await asyncio.sleep(0.02)
    return record


class TestAttribution:
    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_run_id_and_dedupe_key_persisted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """多栏归因：run_id / tool_call_id / dedupe_key 必须落库。"""
        monkeypatch.setattr("apps.agent.services.approval.flow.redis_cache_enabled", lambda: False)
        monkeypatch.setattr("apps.agent.services.approval.waiter.redis_cache_enabled", lambda: False)
        session = await AgentSession.objects.acreate(title="归因", origin="chat")

        task = asyncio.ensure_future(
            approval_mod.request_approval(
                tool_name="mcp__fachuan__delete_case",
                tool_args={"case_id": 7},
                session_id=str(session.session_id),
                run_id=f"{session.session_id}:pi:3",
                tool_call_id="call-abc",
                offline_timeout=5.0,
            )
        )
        record = await _wait_approval_landed(session)
        assert record is not None, "审批记录未落库（等待超时）"
        assert record.run_id == f"{session.session_id}:pi:3"
        assert record.tool_call_id == "call-abc"
        assert record.dedupe_key, "去重键必须落库（三入口共用一张卡）"
        assert record.expires_at is not None, "过期时间必须落库，不能靠 created_at 推断"

        await approval_mod.decide_approval(str(record.approval_id), True)
        approved, _, _ = await asyncio.wait_for(task, timeout=5.0)
        assert approved is True

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_event_carries_run_id_and_agent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """审批卡要能挂到正确那一栏：事件必须带 run_id / agent。"""
        published: list[dict[str, Any]] = []

        class _Bus:
            async def has_subscribers(self, sid: str) -> bool:
                return True

            async def publish(self, sid: str, event: dict[str, Any]) -> int:
                published.append(event)
                return 1

        monkeypatch.setattr("apps.agent.services.event_bus.get_bus", lambda: _Bus())
        monkeypatch.setattr("apps.agent.services.approval.flow.redis_cache_enabled", lambda: False)
        monkeypatch.setattr("apps.agent.services.approval.waiter.redis_cache_enabled", lambda: False)

        await approval_mod.request_approval(
            tool_name="mcp__fachuan__clear_all_data",
            tool_args={},
            session_id="sess-run-scoped",
            run_id="sess-run-scoped:openai-agents:2",
            timeout=0.05,
        )
        assert published, "没有推送审批事件"
        assert published[0]["run_id"] == "sess-run-scoped:openai-agents:2"
        assert published[0]["agent"] == "openai-agents"


class TestDedupe:
    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_second_identical_call_reuses_pending_card(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """第二个入口（MCP 闸门）不能为同一调用再建一张卡。"""
        monkeypatch.setattr("apps.agent.services.approval.flow.redis_cache_enabled", lambda: False)
        monkeypatch.setattr("apps.agent.services.approval.waiter.redis_cache_enabled", lambda: False)
        session = await AgentSession.objects.acreate(title="去重", origin="chat")
        sid = str(session.session_id)

        task = asyncio.ensure_future(
            approval_mod.request_approval(
                tool_name="mcp__fachuan__delete_case",
                tool_args={"case_id": 9},
                session_id=sid,
                run_id=f"{sid}:pi:1",
                offline_timeout=5.0,
            )
        )
        first = await _wait_approval_landed(session)
        assert first is not None

        approved, second_id, reason = await approval_mod.request_approval(
            tool_name="mcp__fachuan__delete_case",
            tool_args={"case_id": 9},
            session_id=sid,
            run_id=f"{sid}:dsh:1",
            offline_timeout=5.0,
        )
        assert approved is False
        assert second_id == first.approval_id.hex, "应复用既有审批单而不是新建"
        assert "已在等待审批" in reason
        assert await AgentApproval.objects.filter(session=session).acount() == 1

        await approval_mod.decide_approval(str(first.approval_id), True)
        ok, _, _ = await asyncio.wait_for(task, timeout=5.0)
        assert ok is True

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_different_args_gets_its_own_card(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """参数不同就是两次操作，不能合并成一张卡。"""
        monkeypatch.setattr("apps.agent.services.approval.flow.redis_cache_enabled", lambda: False)
        monkeypatch.setattr("apps.agent.services.approval.waiter.redis_cache_enabled", lambda: False)
        session = await AgentSession.objects.acreate(title="去重-参数", origin="chat")
        sid = str(session.session_id)

        task = asyncio.ensure_future(
            approval_mod.request_approval(
                tool_name="mcp__fachuan__delete_case",
                tool_args={"case_id": 1},
                session_id=sid,
                offline_timeout=5.0,
            )
        )
        first = await _wait_approval_landed(session)
        assert first is not None

        approved, second_id, _ = await approval_mod.request_approval(
            tool_name="mcp__fachuan__delete_case",
            tool_args={"case_id": 2},
            session_id=sid,
            offline_timeout=5.0,
        )
        assert approved is False
        assert second_id != first.approval_id.hex
        assert await AgentApproval.objects.filter(session=session).acount() == 2

        # 收尾：放掉两个等待者，避免后台任务泄漏到下一个用例
        await approval_mod.decide_approval(str(first.approval_id), False)
        await approval_mod.decide_approval(second_id, False)
        await asyncio.wait_for(task, timeout=5.0)


class TestDecisionReason:
    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_rejection_reason_reaches_caller(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """驳回理由必须回到模型侧（原来恒为「用户拒绝或超时」）。"""
        monkeypatch.setattr("apps.agent.services.approval.flow.redis_cache_enabled", lambda: False)
        monkeypatch.setattr("apps.agent.services.approval.waiter.redis_cache_enabled", lambda: False)
        session = await AgentSession.objects.acreate(title="驳回理由", origin="chat")

        task = asyncio.ensure_future(
            approval_mod.request_approval(
                tool_name="mcp__fachuan__delete_case",
                tool_args={},
                session_id=str(session.session_id),
                reason="用户要求删除本案",
                offline_timeout=5.0,
            )
        )
        record = await _wait_approval_landed(session)
        assert record is not None
        assert record.reason == "用户要求删除本案", "请求理由要原样落库"

        await approval_mod.decide_approval(str(record.approval_id), False, reason="改用 patch 草案")
        approved, _, reason_out = await asyncio.wait_for(task, timeout=5.0)

        assert approved is False
        assert reason_out == "改用 patch 草案", "驳回理由要回传给调用方"
        refreshed = await AgentApproval.objects.aget(pk=record.pk)
        # 两列各存各的：请求理由不被驳回理由覆盖
        assert refreshed.reason == "用户要求删除本案"
        assert refreshed.decision_reason == "改用 patch 草案"


class TestCancel:
    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_cancel_marks_record_cancelled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """客户端断开 → 取消等待任务时，记录必须变 cancelled，不能留 PENDING。"""
        monkeypatch.setattr("apps.agent.services.approval.flow.redis_cache_enabled", lambda: False)
        monkeypatch.setattr("apps.agent.services.approval.waiter.redis_cache_enabled", lambda: False)
        session = await AgentSession.objects.acreate(title="取消", origin="chat")

        task = asyncio.ensure_future(
            approval_mod.request_approval(
                tool_name="mcp__fachuan__delete_case",
                tool_args={},
                session_id=str(session.session_id),
                offline_timeout=30.0,
            )
        )
        record = await _wait_approval_landed(session)
        assert record is not None

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        refreshed = await _wait_status(record.approval_id, AgentApproval.Status.CANCELLED)
        assert refreshed is not None
        assert refreshed.status == AgentApproval.Status.CANCELLED
        assert refreshed.decided_at is not None
