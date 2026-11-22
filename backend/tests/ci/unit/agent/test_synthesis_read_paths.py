"""综合结论消息（``agent_kind="synthesis"``）在转录各条读路径上的口径。

它是"律师点一次按钮"写进转录的一条 assistant 消息，**不是任何一栏的回答**：

- 评审取候选 / 取 judge 模型：不能算进去（否则「评审综合稿自己」）；
- 重生成 / 续写：不能以它为目标（它没有可重跑的运行时，且不能先被标成「已被取代」）；
- 记忆抽取：排掉（各栏回答的二次合并，不含律师表达的新信息，只挤占字数预算）；
- 历史回放（列表接口）与上下文回放：**要能看到**——这是写转录的目的；上下文里标明
  「综合结论」，模型才不会把它当成上一句话的直接回答。
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from asgiref.sync import sync_to_async

from apps.agent.models import AgentMessage, AgentSession
from apps.agent.services.chat.regenerate import SynthesisNotReplayableError, resolve_target
from apps.agent.services.history import render_transcript
from apps.agent.services.memory.extraction import _render_transcript
from apps.agent.services.review.store import load_turn_answers, load_turn_models
from apps.agent.services.session_service import list_messages
from apps.agent.services.synthesis.kinds import SYNTHESIS_AGENT_KIND
from apps.agent.services.synthesis.store import SYNTHESIS_AGENT_KIND as STORE_SYNTHESIS_AGENT_KIND
from apps.organization.models import LawFirm, Lawyer

pytestmark = pytest.mark.django_db

_TASK = "对方逾期付款，我方能否主张解除合同？"


def _make_user(username: str) -> Lawyer:
    firm = LawFirm.objects.create(name=f"综合读路径测试所-{username}")
    return Lawyer.objects.create_user(
        username=username,
        password="x-test-12345678",  # pragma: allowlist secret（测试固定口令，非真实凭证）
        law_firm=firm,
    )


def _sync_session() -> AgentSession:
    user = _make_user(f"synth_read_{uuid.uuid4().hex[:10]}")
    return AgentSession.objects.create(user=user, title="综合读路径")


async def _session() -> AgentSession:
    return await sync_to_async(_sync_session)()


async def _msg(
    session: AgentSession,
    role: str,
    content: str,
    *,
    agent_kind: str = "",
    model: str = "",
    turn_no: int = 1,
) -> AgentMessage:
    return await AgentMessage.objects.acreate(
        session=session,
        role=role,
        content=content,
        agent_kind=agent_kind,
        metadata={"model": model} if model else {},
        turn_no=turn_no,
    )


async def _turn_with_synthesis(session: AgentSession) -> AgentMessage:
    """一轮两栏 + 一条综合结论；返回综合结论那条消息。"""
    await _msg(session, AgentMessage.Role.USER, _TASK)
    await _msg(session, AgentMessage.Role.ASSISTANT, "pi 的回答", agent_kind="pi", model="glm53")
    await _msg(session, AgentMessage.Role.ASSISTANT, "dsh 的回答", agent_kind="dsh", model="kimi-2.6")
    return await _msg(
        session,
        AgentMessage.Role.ASSISTANT,
        "综合稿[来源：pi]",
        agent_kind=SYNTHESIS_AGENT_KIND,
        model="synth-model",
    )


def test_store_reexports_the_single_definition() -> None:
    """``store.SYNTHESIS_AGENT_KIND`` 是 ``kinds`` 的再导出，不是第二份定义。"""
    assert STORE_SYNTHESIS_AGENT_KIND is SYNTHESIS_AGENT_KIND
    assert SYNTHESIS_AGENT_KIND == "synthesis"


class TestReviewCandidates:
    @pytest.mark.asyncio
    async def test_synthesis_never_becomes_a_review_candidate(self) -> None:
        """请求里即便带了 synthesis 这个 kind，评审也拿不到综合稿当候选。"""
        session = await _session()
        await _turn_with_synthesis(session)

        task, answers = await load_turn_answers(session, 1, ["pi", "dsh", SYNTHESIS_AGENT_KIND])

        assert task == _TASK
        assert answers == {"pi": "pi 的回答", "dsh": "dsh 的回答", SYNTHESIS_AGENT_KIND: ""}

    @pytest.mark.asyncio
    async def test_synthesis_model_is_not_a_judge_fallback(self) -> None:
        """judge 模型兜底只看各栏实际用过的模型，综合稿的模型不算。"""
        session = await _session()
        await _turn_with_synthesis(session)

        models = await load_turn_models(session, 1, ["pi", "dsh", SYNTHESIS_AGENT_KIND])

        assert models == ["glm53", "kimi-2.6"]


class TestRegenerate:
    @pytest.mark.asyncio
    async def test_cannot_regenerate_from_synthesis_message(self) -> None:
        session = await _session()
        synthesis = await _turn_with_synthesis(session)

        with pytest.raises(SynthesisNotReplayableError):
            await resolve_target(session=session, from_message_id=synthesis.pk)

    @pytest.mark.asyncio
    async def test_cannot_target_synthesis_lane_explicitly(self) -> None:
        session = await _session()
        await _turn_with_synthesis(session)
        pi_answer = await AgentMessage.objects.filter(session=session, agent_kind="pi").afirst()
        assert pi_answer is not None

        with pytest.raises(SynthesisNotReplayableError):
            await resolve_target(session=session, from_message_id=pi_answer.pk, lane=SYNTHESIS_AGENT_KIND)

    @pytest.mark.asyncio
    async def test_regular_lane_still_regenerates(self) -> None:
        session = await _session()
        await _turn_with_synthesis(session)
        dsh_answer = await AgentMessage.objects.filter(session=session, agent_kind="dsh").afirst()
        assert dsh_answer is not None

        target = await resolve_target(session=session, from_message_id=dsh_answer.pk)

        assert target.lane == "dsh"


class TestReplayStillSeesIt:
    @pytest.mark.asyncio
    async def test_history_list_includes_synthesis(self) -> None:
        """历史回放能看到综合结论（写转录的目的）；前端负责不把它渲染成一栏。"""
        session = await _session()
        synthesis = await _turn_with_synthesis(session)

        rows = await list_messages(session_id=str(session.session_id), user_id=session.user_id)

        assert rows is not None
        assert synthesis.pk in [row.pk for row in rows]

    def test_context_transcript_labels_synthesis(self) -> None:
        """上下文回放带上综合结论，但标成「助手（综合结论）」，与各栏的「助手」区分开。"""
        history = [
            SimpleNamespace(role="user", content=_TASK, tool_name="", agent_kind=""),
            SimpleNamespace(role="assistant", content="pi 的回答", tool_name="", agent_kind="pi"),
            SimpleNamespace(role="assistant", content="综合稿", tool_name="", agent_kind=SYNTHESIS_AGENT_KIND),
        ]

        prompt = render_transcript(history, "继续追问")

        assert "助手: pi 的回答" in prompt
        assert "助手（综合结论）: 综合稿" in prompt


class TestMemoryExtraction:
    def test_memory_transcript_skips_synthesis(self) -> None:
        session = _sync_session()
        AgentMessage.objects.create(session=session, role=AgentMessage.Role.USER, content=_TASK, turn_no=1)
        AgentMessage.objects.create(
            session=session, role=AgentMessage.Role.ASSISTANT, content="pi 的回答", agent_kind="pi", turn_no=1
        )
        AgentMessage.objects.create(
            session=session,
            role=AgentMessage.Role.ASSISTANT,
            content="综合稿不该进记忆抽取",
            agent_kind=SYNTHESIS_AGENT_KIND,
            turn_no=1,
        )

        transcript = _render_transcript(session)

        assert "pi 的回答" in transcript
        assert "综合稿不该进记忆抽取" not in transcript
