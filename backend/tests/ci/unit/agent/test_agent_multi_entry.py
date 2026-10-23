"""多入口（origin / case_id）与任务式离线审批（P2-2）。

四个验收点：

1. 按 case_id 列会话，且越权不可见；
2. 任务式运行无订阅者时高危工具进入 **pending** 而不是 rejected；
3. 离线审批通过后工具继续执行；
4. 「完成后通知」可达（审批决策能被等待方读到）。
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from apps.agent.models import AgentApproval, AgentSession
from apps.agent.services import approval as approval_mod

TEST_PASSWORD = "x-test-12345678"  # pragma: allowlist secret


class TestOriginAndScoping:
    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_create_with_origin_and_case(self) -> None:
        from apps.agent.services.session_service import create_session

        session = await create_session(title="案件内对话", user_id=None, origin="case", case_id=42)
        assert session.origin == "case"
        assert session.case_id == 42

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_list_by_case_scoped_to_user(self) -> None:
        """按 case_id 过滤，但归属仍按 user——传别人的 case_id 看不到别人会话。"""
        from asgiref.sync import sync_to_async

        from apps.agent.services.session_service import create_session, list_sessions
        from apps.organization.models import LawFirm, Lawyer

        def _mk(name: str) -> Any:
            firm = LawFirm.objects.create(name=f"multi-{name}")
            return Lawyer.objects.create_user(username=f"multi-{name}", password=TEST_PASSWORD, law_firm=firm)

        alice = await sync_to_async(_mk)("alice")
        bob = await sync_to_async(_mk)("bob")

        await create_session(title="a1", user_id=alice.pk, origin="case", case_id=7)
        await create_session(title="a2", user_id=alice.pk, origin="case", case_id=8)
        await create_session(title="b1", user_id=bob.pk, origin="case", case_id=7)

        alice_case7 = await list_sessions(user_id=alice.pk, limit=50, case_id=7)
        assert [s.title for s in alice_case7] == ["a1"]

        bob_case8 = await list_sessions(user_id=bob.pk, limit=50, case_id=8)
        assert bob_case8 == [], "越权看到了他人案件的会话"

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_list_by_origin(self) -> None:
        from asgiref.sync import sync_to_async

        from apps.agent.services.session_service import create_session, list_sessions
        from apps.organization.models import LawFirm, Lawyer

        def _mk() -> Any:
            firm = LawFirm.objects.create(name="multi-origin")
            return Lawyer.objects.create_user(username="multi-origin", password=TEST_PASSWORD, law_firm=firm)

        user = await sync_to_async(_mk)()
        await create_session(title="chat1", user_id=user.pk, origin="chat")
        await create_session(title="task1", user_id=user.pk, origin="task")

        tasks = await list_sessions(user_id=user.pk, limit=50, origin="task")
        assert [s.title for s in tasks] == ["task1"]

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_none_user_sees_nothing(self) -> None:
        """无身份不得列出任何会话（防越权）。"""
        from apps.agent.services.session_service import create_session, list_sessions

        await create_session(title="someone", user_id=None, origin="chat")
        assert await list_sessions(user_id=None, limit=50) == []

    @pytest.mark.django_db
    def test_origin_indexes_declared(self) -> None:
        names = {idx.name for idx in AgentSession._meta.indexes}
        assert {"agent_session_case_idx", "agent_session_origin_idx"} <= names


class TestOfflineApproval:
    """任务式运行没有 SSE 连接，高危工具不能因此永远用不了。"""

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_no_subscriber_pends_instead_of_rejecting(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FACHUAN_APPROVAL_OFFLINE", "1")
        monkeypatch.setattr(approval_mod, "redis_cache_enabled", lambda: False)
        session = await AgentSession.objects.acreate(title="任务式", origin="task")

        task = asyncio.ensure_future(
            approval_mod.request_approval(
                tool_name="mcp__fachuan__delete_case",
                tool_args={},
                session_id=str(session.session_id),
                offline_timeout=5.0,
            )
        )
        # 让等待方登记并落库
        await asyncio.sleep(0.15)

        record = await AgentApproval.objects.filter(session=session).afirst()
        assert record is not None
        assert record.status == AgentApproval.Status.PENDING, "无订阅者时不应直接 rejected"

        # 用户回来点同意 → 工具继续执行
        await approval_mod.decide_approval(str(record.approval_id), True)
        approved, _ = await asyncio.wait_for(task, timeout=5.0)
        assert approved is True

        refreshed = await AgentApproval.objects.aget(pk=record.pk)
        assert refreshed.status == AgentApproval.Status.APPROVED
        assert refreshed.decided_by_id == record.decided_by_id  # 未被覆盖

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_offline_rejection_blocks_tool(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FACHUAN_APPROVAL_OFFLINE", "1")
        monkeypatch.setattr(approval_mod, "redis_cache_enabled", lambda: False)
        session = await AgentSession.objects.acreate(title="任务式-拒", origin="task")

        task = asyncio.ensure_future(
            approval_mod.request_approval(
                tool_name="mcp__fachuan__delete_case",
                tool_args={},
                session_id=str(session.session_id),
                offline_timeout=5.0,
            )
        )
        await asyncio.sleep(0.15)
        record = await AgentApproval.objects.filter(session=session).afirst()
        assert record is not None
        await approval_mod.decide_approval(str(record.approval_id), False)
        approved, _ = await asyncio.wait_for(task, timeout=5.0)
        assert approved is False

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_offline_timeout_still_fail_closed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """离线也没人管：超时后必须拒绝（不能默默放行）。"""
        monkeypatch.setenv("FACHUAN_APPROVAL_OFFLINE", "1")
        monkeypatch.setattr(approval_mod, "redis_cache_enabled", lambda: False)
        session = await AgentSession.objects.acreate(title="任务式-超时", origin="task")

        approved, _ = await approval_mod.request_approval(
            tool_name="mcp__fachuan__delete_case",
            tool_args={},
            session_id=str(session.session_id),
            offline_timeout=0.3,
        )
        assert approved is False
        record = await AgentApproval.objects.filter(session=session).afirst()
        assert record is not None
        assert record.status == AgentApproval.Status.TIMEOUT

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_offline_disabled_falls_back_to_reject(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """``FACHUAN_APPROVAL_OFFLINE=0`` 回到原 fail-closed 行为。"""
        monkeypatch.setenv("FACHUAN_APPROVAL_OFFLINE", "0")
        monkeypatch.setattr(approval_mod, "redis_cache_enabled", lambda: False)
        session = await AgentSession.objects.acreate(title="保守部署", origin="task")

        approved, _ = await approval_mod.request_approval(
            tool_name="mcp__fachuan__delete_case",
            tool_args={},
            session_id=str(session.session_id),
            offline_timeout=5.0,
        )
        assert approved is False
        record = await AgentApproval.objects.filter(session=session).afirst()
        assert record is not None
        assert record.status == AgentApproval.Status.REJECTED

    def test_default_is_offline_enabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("FACHUAN_APPROVAL_OFFLINE", raising=False)
        assert approval_mod.allow_offline_approval() is True
        for value in ("0", "false", "no"):
            monkeypatch.setenv("FACHUAN_APPROVAL_OFFLINE", value)
            assert approval_mod.allow_offline_approval() is False


class TestPendingDiscovery:
    """用户回来要能发现待审批（否则离线审批=默默超时）。"""

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_list_pending_for_user(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from asgiref.sync import sync_to_async

        from apps.organization.models import LawFirm, Lawyer

        def _mk() -> Any:
            firm = LawFirm.objects.create(name="pending-律所")
            return Lawyer.objects.create_user(username="pending-u", password=TEST_PASSWORD, law_firm=firm)

        user = await sync_to_async(_mk)()
        session = await AgentSession.objects.acreate(title="p", user=user, origin="task")
        await AgentApproval.objects.acreate(
            session=session,
            tool_name="mcp__fachuan__delete_case",
            status=AgentApproval.Status.PENDING,
            risk_level="high",
        )
        # 已决的不该出现在待审列表
        await AgentApproval.objects.acreate(
            session=session,
            tool_name="mcp__fachuan__delete_contract",
            status=AgentApproval.Status.APPROVED,
            risk_level="high",
        )

        pending = await approval_mod.list_pending_for_user(user_id=user.pk)
        assert [p.tool_name for p in pending] == ["mcp__fachuan__delete_case"]

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_list_pending_lazy_times_out_zombies(self) -> None:
        """僵尸 pending（等待进程已死）在列表时被懒清理成 timeout，不再骚扰用户。

        场景：离线审批挂起后 worker 崩溃/重启，waiter 消失，记录永远停在
        pending（差距分析 B2-4）——每个页面都弹「已超时」卡且无法消除。
        """
        from datetime import timedelta

        from asgiref.sync import sync_to_async
        from django.utils import timezone

        from apps.organization.models import LawFirm, Lawyer

        def _mk() -> Any:
            firm = LawFirm.objects.create(name="zombie-律所")
            return Lawyer.objects.create_user(username="zombie-u", password=TEST_PASSWORD, law_firm=firm)

        user = await sync_to_async(_mk)()
        session = await AgentSession.objects.acreate(title="z", user=user, origin="task")
        # 僵尸：创建时间已超出 OFFLINE_TIMEOUT（7200s）窗口
        zombie = await AgentApproval.objects.acreate(
            session=session,
            tool_name="mcp__fachuan__delete_reminder",
            tool_args={"reminder_id": 999999},
            status=AgentApproval.Status.PENDING,
            risk_level="high",
        )
        await AgentApproval.objects.filter(pk=zombie.pk).aupdate(
            created_at=timezone.now() - timedelta(seconds=approval_mod.OFFLINE_TIMEOUT + 60)
        )
        # 活着的：窗口内，必须保留
        await AgentApproval.objects.acreate(
            session=session,
            tool_name="mcp__fachuan__delete_case",
            status=AgentApproval.Status.PENDING,
            risk_level="high",
        )

        pending = await approval_mod.list_pending_for_user(user_id=user.pk)
        assert [p.tool_name for p in pending] == ["mcp__fachuan__delete_case"]
        zombie = await AgentApproval.objects.aget(pk=zombie.pk)
        assert zombie.status == AgentApproval.Status.TIMEOUT
        assert zombie.decided_at is not None

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_pending_scoped_by_user(self) -> None:
        """不能看到别人的待审批（含工具参数里的业务数据）。"""
        from asgiref.sync import sync_to_async

        from apps.organization.models import LawFirm, Lawyer

        def _mk(name: str) -> Any:
            firm = LawFirm.objects.create(name=f"pending-{name}")
            return Lawyer.objects.create_user(username=f"pending-{name}", password=TEST_PASSWORD, law_firm=firm)

        alice = await sync_to_async(_mk)("alice")
        bob = await sync_to_async(_mk)("bob")
        s_alice = await AgentSession.objects.acreate(title="a", user=alice)
        await AgentApproval.objects.acreate(session=s_alice, tool_name="delete_x", status="pending")

        assert await approval_mod.list_pending_for_user(user_id=bob.pk) == []
        assert await approval_mod.list_pending_for_user(user_id=None) == []
