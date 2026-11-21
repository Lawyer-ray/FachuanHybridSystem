"""``services/synthesis/store.py``：候选读取、合成模型解析、快照落库与回放。

三条必须成立的口径（对应契约 §C4）：

1. ``resolve_model`` 的三条分支：请求给了就用它 / 没给取本轮各栏实际模型的
   去重第一个 / 都没有则 **ValueError**（API 转 422），**绝不猜模型名**；
2. ``load_turn_candidates`` 必须把"没跑成"（无正文行 → ``failed``）与"跑了没
   说话"（有行但空白 → ``empty``）区分开——两者对律师的信息完全不同；
3. 落库只走 ``AgentSynthesis``，**不**写 assistant 消息（否则转录里凭空多一栏）。

异步 ORM 走 ``async_to_sync``（与 ``review/test_adoption.py`` 同法），不联网。
"""

from __future__ import annotations

from typing import Any

import pytest
from asgiref.sync import async_to_sync

from apps.agent.models import AgentMessage, AgentSession, AgentSynthesis
from apps.agent.services.adjudication.contracts import DroppedCandidate, Synthesis, SynthesisCitation
from apps.agent.services.synthesis import store
from apps.organization.models import LawFirm, Lawyer

_TASK = "对方逾期付款，我方能否主张解除合同？"


def _make_user(username: str = "synthesis_store_user") -> Any:
    firm = LawFirm.objects.create(name=f"综合测试所-{username}")
    return Lawyer.objects.create_user(
        username=username,
        password="x-test-12345678",  # pragma: allowlist secret（测试固定口令，非真实凭证）
        law_firm=firm,
    )


def _make_session(user: Any) -> AgentSession:
    return AgentSession.objects.create(user=user, title="综合结论存储")


def _add_answer(session: AgentSession, lane: str, content: str, *, model: str = "", turn_no: int = 1) -> AgentMessage:
    return AgentMessage.objects.create(
        session=session,
        role=AgentMessage.Role.ASSISTANT,
        agent_kind=lane,
        content=content,
        metadata={"model": model},
        turn_no=turn_no,
    )


def _add_turn_one(session: AgentSession) -> None:
    AgentMessage.objects.create(session=session, role=AgentMessage.Role.USER, content=_TASK, turn_no=1)


@pytest.mark.django_db
def test_resolve_model_returns_requested_value() -> None:
    """请求指定了模型就用它——即使本轮各栏留下的是别的模型名。"""
    user = _make_user()
    session = _make_session(user)
    _add_turn_one(session)
    _add_answer(session, "pi", "回答", model="glm53")

    resolved = async_to_sync(store.resolve_model)(session, 1, "kimi-2.6")

    assert resolved == "kimi-2.6"


@pytest.mark.django_db
def test_resolve_model_falls_back_to_first_distinct_lane_model() -> None:
    """没指定模型时取本轮各栏实际模型去重后的第一个（按消息顺序，不猜）。"""
    user = _make_user("synthesis_store_user_b")
    session = _make_session(user)
    _add_turn_one(session)
    _add_answer(session, "pi", "回答一", model="glm53")
    _add_answer(session, "dsh", "回答二", model="kimi-2.6")
    _add_answer(session, "openai-agents", "回答三", model="glm53")

    resolved = async_to_sync(store.resolve_model)(session, 1, "")

    assert resolved == "glm53"


@pytest.mark.django_db
def test_resolve_model_raises_when_no_lane_left_a_model() -> None:
    """本轮没有留下任何模型名 → ValueError（API 转 422），不回落到写死的默认模型。"""
    user = _make_user("synthesis_store_user_c")
    session = _make_session(user)
    _add_turn_one(session)
    _add_answer(session, "pi", "回答", model="")

    with pytest.raises(ValueError, match="未配置综合模型"):
        async_to_sync(store.resolve_model)(session, 1, "")


@pytest.mark.django_db
def test_load_turn_candidates_separates_failed_and_empty() -> None:
    """无正文行的栏是 ``failed``，有行但空白的栏是 ``empty``；模型取最后一条。"""
    user = _make_user("synthesis_store_user_d")
    session = _make_session(user)
    _add_turn_one(session)
    _add_answer(session, "pi", "旧版回答", model="old-model")
    _add_answer(session, "pi", "《民法典》第五百八十四条：损失赔偿额……", model="kimi-2.6")
    _add_answer(session, "dsh", "   ", model="glm53")
    # openai-agents 本轮没有任何 assistant 行（跑了但失败，不落行）

    task, candidates = async_to_sync(store.load_turn_candidates)(session, 1, ("pi", "dsh", "openai-agents"))

    assert task == _TASK
    assert [(candidate.lane, candidate.model, candidate.text) for candidate in candidates] == [
        ("pi", "kimi-2.6", "《民法典》第五百八十四条：损失赔偿额……"),
        # 有行但空白的回答在 load_turn_answers 里就是空串（``empty`` 的判据）
        ("dsh", "glm53", ""),
        ("openai-agents", "", None),
    ]


@pytest.mark.django_db
def test_load_turn_candidates_missing_turn_raises_lookup_error() -> None:
    user = _make_user("synthesis_store_user_e")
    session = _make_session(user)
    _add_turn_one(session)

    with pytest.raises(LookupError):
        async_to_sync(store.load_turn_candidates)(session, 2, ("pi",))


@pytest.mark.django_db
def test_save_then_latest_round_trip_and_no_assistant_message() -> None:
    """落 ``AgentSynthesis`` 一行，可回放；转录里**不**多出 assistant 消息。"""
    user = _make_user("synthesis_store_user_f")
    session = _make_session(user)
    _add_turn_one(session)
    _add_answer(session, "pi", "回答", model="kimi-2.6")
    synthesis = Synthesis(
        synthesis_id="a" * 32,
        session_id=str(session.session_id),
        turn=1,
        text="综合结论 [来源：pi]",
        model="kimi-2.6",
        lanes_used=["pi"],
        dropped=[DroppedCandidate(lane="dsh", reason="failed")],
        citations=[SynthesisCitation(lane="pi", quote="《民法典》第五百八十四条")],
        unverified=[],
        tokens={"prompt": 11, "completion": 7, "total": 18},
    )

    saved = async_to_sync(store.save_synthesis)(session=session, user_id=user.pk, synthesis=synthesis)
    found = async_to_sync(store.latest_synthesis)(session, 1)

    assert found is not None
    assert found.pk == saved.pk
    assert found.text == "综合结论 [来源：pi]"
    assert found.dropped == [{"lane": "dsh", "reason": "failed"}]
    assert found.citations == [{"lane": "pi", "quote": "《民法典》第五百八十四条"}]
    assert found.tokens == {"prompt": 11, "completion": 7, "total": 18}
    # 综合结论不是"某一栏的回答"：不能落成 assistant 消息
    assert AgentMessage.objects.filter(session=session, role=AgentMessage.Role.ASSISTANT).count() == 1
    assert AgentSynthesis.objects.filter(session=session).count() == 1
