"""综合结论改走 agent：prompt 装配、输出校验、转录落库的口径。

守三件事：

1. **prompt 装配**：问题 + 评审结论 + 五栏全文（不截断），评审结论必须在候选**之前**
   ——先给"哪栏更可靠"，再让它读原文。
2. **输出校验**：空正文 / 缺来源锚点都不许当综合稿（缺锚点意味着"看不出谁说的"，
   那正是综合的立身之本）。
3. **转录落库**：写 ``agent_kind="synthesis"`` 的一条 assistant 消息，同一轮重复
   生成**覆盖**而不是堆积——否则转录里会出现三条综合稿。
"""

from __future__ import annotations

import uuid

import pytest

from apps.agent.services.chat.aggregate import AGGREGATE_SYSTEM_PROMPT, Candidate
from apps.agent.services.synthesis import agent_runner


def _cand(lane: str, text: str, model: str = "kimi-2.6") -> Candidate:
    return Candidate(lane=lane, model=model, text=text)


# ── 1. prompt 装配 ────────────────────────────────────────────────────


def test_prompt_contains_task_and_every_candidate() -> None:
    prompt = agent_runner.build_synthesis_prompt(
        "民法典874条在计算机犯罪中的适用",
        [_cand("pi", "甲观点"), _cand("dsh", "乙观点")],
    )
    assert "民法典874条在计算机犯罪中的适用" in prompt
    assert "1. 【pi · kimi-2.6】" in prompt
    assert "2. 【dsh · kimi-2.6】" in prompt
    assert "甲观点" in prompt and "乙观点" in prompt


def test_prompt_puts_review_before_candidates() -> None:
    """评审结论先于候选：先给取舍依据，再让它读原文。"""
    prompt = agent_runner.build_synthesis_prompt("问题", [_cand("pi", "甲")], review_summary="pi 得分最高｜依据更充分")
    assert prompt.index("pi 得分最高") < prompt.index("1. 【pi · kimi-2.6】")


def test_prompt_has_no_review_section_when_absent() -> None:
    prompt = agent_runner.build_synthesis_prompt("问题", [_cand("pi", "甲")])
    assert "评审结论" not in prompt


def test_prompt_does_not_truncate_long_candidates() -> None:
    """1M 窗口下不截断：截断会让聚合者读不到后文论证，且不报错。"""
    huge = "甲" * 100_000
    prompt = agent_runner.build_synthesis_prompt("问题", [_cand("pi", huge)])
    assert "甲" * 100_000 in prompt


def test_system_prompt_is_the_aggregator_prompt() -> None:
    """换运行时不该换规则：MoA aggregator 的口径全仓只有一份。"""
    assert agent_runner.synthesis_system_prompt() == AGGREGATE_SYSTEM_PROMPT
    assert "批判性评估" in agent_runner.synthesis_system_prompt()


# ── 2. 输出校验 ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", "empty"),
        ("   \n  ", "empty"),
        ("民法典874条讲技术转让合同的内部责任。", "no_anchor"),
        ("结论[来源：pi]就是这样。", ""),
    ],
)
def test_validate_synthesis_text(text: str, expected: str) -> None:
    assert agent_runner.validate_synthesis_text(text) == expected


def test_default_kind_is_pi() -> None:
    """默认 pi：注册表里最稳的一个；改它要同步改前端 default（见 use-review-actions）。"""
    assert agent_runner.DEFAULT_SYNTHESIS_KIND == "pi"


# ── 3. 转录落库（写 agent_kind="synthesis"，一轮一条）──────────────────


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_synthesis_writes_one_transcript_message_and_overwrites() -> None:
    from apps.agent.models import AgentMessage, AgentSession
    from apps.agent.services.adjudication.contracts import Synthesis
    from apps.agent.services.synthesis.store import SYNTHESIS_AGENT_KIND, save_synthesis_message

    sid = str(uuid.uuid4())
    session = await AgentSession.objects.acreate(session_id=sid, agent_kind="pi")

    def _synth(text: str, sid: str) -> Synthesis:
        return Synthesis(
            synthesis_id=sid,
            session_id=sid,
            turn=1,
            text=text,
            model="kimi-2.6",
            lanes_used=["pi", "dsh"],
        )

    await save_synthesis_message(session=session, synthesis=_synth("第一版[来源：pi]", "a"))
    await save_synthesis_message(session=session, synthesis=_synth("第二版[来源：dsh]", "b"))

    rows = [m async for m in AgentMessage.objects.filter(session=session, agent_kind=SYNTHESIS_AGENT_KIND)]
    assert len(rows) == 1, "同一轮重复生成必须覆盖，不能在转录里堆出多条综合稿"
    assert rows[0].content == "第二版[来源：dsh]"
    assert rows[0].role == AgentMessage.Role.ASSISTANT
    assert (rows[0].metadata or {})["synthesis_id"] == "b"
