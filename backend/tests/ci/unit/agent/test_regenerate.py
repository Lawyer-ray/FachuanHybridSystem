"""重生成 / 续写：定位口径、审计不删档、列表过滤。

本文件钉四件事，每一条对应一种"看起来正常但律师会被坑"的失败：

1. **复用原提问**：重生成不能新落用户消息（否则历史里同一条提问出现两次），
   也不能自增轮次号（否则「第几轮」这个口径当场废掉）；
2. **旧回答不删档**：只打 ``metadata.superseded``，行还在，审计能回溯；
3. **幂等**：连点两次重生成不刷新 ``superseded_at``（否则"何时被取代"变成
   "最后一次点击时间"）；
4. **过滤用键存在性语义**：没有这个键的老消息必须照常显示——写成
   ``filter(metadata__superseded=False)`` 会让它们整批消失。
"""

from __future__ import annotations

import uuid

import pytest
from asgiref.sync import sync_to_async

from apps.agent.models import AgentMessage, AgentSession
from apps.agent.services.chat.regenerate import (
    MODE_CONTINUE,
    MODE_REGENERATE,
    continuation_prompt,
    mark_superseded,
    resolve_target,
)
from apps.agent.services.session_service import list_messages
from apps.organization.models import LawFirm, Lawyer

pytestmark = pytest.mark.django_db


def _make_user(username: str = "regen_user") -> Lawyer:
    firm = LawFirm.objects.create(name=f"重生成测试所-{username}")
    return Lawyer.objects.create_user(
        username=username,
        password="x-test-12345678",  # pragma: allowlist secret（测试固定口令，非真实凭证）
        law_firm=firm,
    )


async def _session(**kwargs: object) -> AgentSession:
    # 每个会话一个独立用户：Lawyer.username 唯一，测试之间不能复用。
    # 建用户是**同步** ORM（create_user 走密码哈希），async 上下文里必须过线程。
    user = await sync_to_async(_make_user)(f"regen_{uuid.uuid4().hex[:10]}")
    return await AgentSession.objects.acreate(user=user, **(kwargs or {"title": "重生成用例"}))


async def _msg(
    session: AgentSession,
    role: str,
    content: str,
    *,
    turn_no: int = 1,
    agent_kind: str = "",
    metadata: dict | None = None,
) -> AgentMessage:
    return await AgentMessage.objects.acreate(
        session=session,
        role=role,
        content=content,
        turn_no=turn_no,
        agent_kind=agent_kind,
        metadata=metadata or {},
    )


class TestResolveTarget:
    @pytest.mark.asyncio
    async def test_answer_points_back_to_its_prompt_and_lane(self) -> None:
        session = await _session()
        prompt = await _msg(session, AgentMessage.Role.USER, "合同解除条件是什么？", turn_no=3)
        answer = await _msg(
            session,
            AgentMessage.Role.ASSISTANT,
            "第563条……",
            turn_no=3,
            agent_kind="dsh",
            metadata={"model": "glm53"},
        )

        target = await resolve_target(session=session, from_message_id=answer.pk)

        assert target.prompt == prompt.content
        assert target.turn_no == 3
        assert target.lane == "dsh"
        assert target.model == "glm53"
        assert target.mode == MODE_REGENERATE
        assert target.prefix == ""

    @pytest.mark.asyncio
    async def test_any_message_in_the_turn_resolves_the_same_prompt(self) -> None:
        """点工具行 / 点提问本身，都要定位到同一轮同一个提问。"""
        session = await _session()
        prompt = await _msg(session, AgentMessage.Role.USER, "帮我查一下这个条款", turn_no=2)
        tool = await _msg(session, AgentMessage.Role.TOOL, "{}", turn_no=2, agent_kind="dsh")
        answer = await _msg(
            session, AgentMessage.Role.ASSISTANT, "结论", turn_no=2, agent_kind="dsh", metadata={"model": "glm53"}
        )

        from_tool = await resolve_target(session=session, from_message_id=tool.pk)
        from_prompt = await resolve_target(session=session, from_message_id=prompt.pk)
        from_answer = await resolve_target(session=session, from_message_id=answer.pk)

        assert {from_tool.prompt, from_prompt.prompt, from_answer.prompt} == {prompt.content}
        assert {from_tool.turn_no, from_prompt.turn_no, from_answer.turn_no} == {2}

    @pytest.mark.asyncio
    async def test_legacy_rows_without_turn_no_fall_back_to_previous_user_message(self) -> None:
        """``turn_no=0`` 的老数据：按 id 回退到最近一条 user，而不是报错。"""
        session = await _session()
        prompt = await _msg(session, AgentMessage.Role.USER, "老提问", turn_no=0)
        answer = await _msg(session, AgentMessage.Role.ASSISTANT, "老回答", turn_no=0, agent_kind="pi")

        target = await resolve_target(session=session, from_message_id=answer.pk)

        assert target.prompt == prompt.content

    @pytest.mark.asyncio
    async def test_continue_requires_an_answer_with_text(self) -> None:
        session = await _session()
        await _msg(session, AgentMessage.Role.USER, "问题", turn_no=1)
        tool = await _msg(session, AgentMessage.Role.TOOL, "{}", turn_no=1, agent_kind="pi")

        with pytest.raises(ValueError, match="已有正文"):
            await resolve_target(session=session, from_message_id=tool.pk, mode=MODE_CONTINUE)

    @pytest.mark.asyncio
    async def test_continue_carries_the_prefix(self) -> None:
        session = await _session()
        await _msg(session, AgentMessage.Role.USER, "问题", turn_no=1)
        answer = await _msg(session, AgentMessage.Role.ASSISTANT, "写到一半", turn_no=1, agent_kind="pi")

        target = await resolve_target(session=session, from_message_id=answer.pk, mode=MODE_CONTINUE)

        assert target.is_continuation
        assert target.prefix == "写到一半"

    @pytest.mark.asyncio
    async def test_message_from_another_session_is_lookup_error(self) -> None:
        mine = await _session()
        other = await _session(title="别人的会话")
        foreign = await _msg(other, AgentMessage.Role.USER, "别人的提问")

        with pytest.raises(LookupError):
            await resolve_target(session=mine, from_message_id=foreign.pk)

    @pytest.mark.asyncio
    async def test_unknown_mode_is_rejected(self) -> None:
        session = await _session()
        prompt = await _msg(session, AgentMessage.Role.USER, "问题", turn_no=1)

        with pytest.raises(ValueError, match="未知的重放模式"):
            await resolve_target(session=session, from_message_id=prompt.pk, mode="rewrite")


class TestMarkSuperseded:
    @pytest.mark.asyncio
    async def test_marks_only_that_turn_and_lane_and_keeps_the_rows(self) -> None:
        session = await _session()
        await _msg(session, AgentMessage.Role.USER, "问题", turn_no=1)
        mine = await _msg(session, AgentMessage.Role.ASSISTANT, "我的回答", turn_no=1, agent_kind="dsh")
        other_lane = await _msg(session, AgentMessage.Role.ASSISTANT, "别栏回答", turn_no=1, agent_kind="pi")
        other_turn = await _msg(session, AgentMessage.Role.ASSISTANT, "上一轮", turn_no=0, agent_kind="dsh")

        marked = await mark_superseded(session=session, turn_no=1, lane="dsh")

        assert marked == [mine.pk]
        await mine.arefresh_from_db()
        assert mine.metadata["superseded"] is True
        assert mine.metadata["superseded_reason"] == "regenerated"
        assert mine.content == "我的回答", "不删档：正文原样保留"
        # 别的栏 / 别的轮次不受影响
        for row in (other_lane, other_turn):
            await row.arefresh_from_db()
            assert "superseded" not in (row.metadata or {})

    @pytest.mark.asyncio
    async def test_is_idempotent_and_keeps_the_original_timestamp(self) -> None:
        session = await _session()
        await _msg(session, AgentMessage.Role.USER, "问题", turn_no=1)
        answer = await _msg(session, AgentMessage.Role.ASSISTANT, "回答", turn_no=1, agent_kind="dsh")

        await mark_superseded(session=session, turn_no=1, lane="dsh")
        await answer.arefresh_from_db()
        first_at = (answer.metadata or {}).get("superseded_at")

        again = await mark_superseded(session=session, turn_no=1, lane="dsh")

        assert again == [], "第二次没有新行可标"
        await answer.arefresh_from_db()
        assert (answer.metadata or {}).get("superseded_at") == first_at


class TestListMessagesFilter:
    @pytest.mark.asyncio
    async def test_superseded_rows_hidden_but_legacy_rows_kept(self) -> None:
        session = await _session()
        legacy = await _msg(session, AgentMessage.Role.USER, "老消息（没有 superseded 键）", turn_no=0)
        answer = await _msg(session, AgentMessage.Role.ASSISTANT, "旧回答", turn_no=1, agent_kind="dsh")
        await mark_superseded(session=session, turn_no=1, lane="dsh")
        fresh = await _msg(session, AgentMessage.Role.ASSISTANT, "新回答", turn_no=1, agent_kind="dsh")

        rows = await list_messages(session_id=str(session.session_id), user_id=session.user_id)

        assert rows is not None
        ids = [row.pk for row in rows]
        assert legacy.pk in ids, "键缺失的老消息必须保留（写成 filter(superseded=False) 会整批消失）"
        assert answer.pk not in ids, "被取代的回答不展示"
        assert fresh.pk in ids


class TestContinuationPrompt:
    def test_prefix_and_anti_restart_instruction(self) -> None:
        text = continuation_prompt("原问题", "前半段正文")

        assert "原问题" in text
        assert "前半段正文" in text
        assert "不要重新开头" in text

    def test_empty_prefix_returns_prompt_unchanged(self) -> None:
        assert continuation_prompt("原问题", "   ") == "原问题"
