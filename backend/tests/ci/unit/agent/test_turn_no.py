"""轮次号落表：同轮各栏共享、跨轮递增、成本可按轮聚合。"""

from __future__ import annotations

from typing import Any

import pytest

from apps.agent.models import AgentMessage, AgentRun, AgentSession
from apps.agent.services.chat import stream as stream_mod


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_two_turns_get_increasing_turn_no() -> None:
    session = await AgentSession.objects.acreate(title="轮次", origin="chat")
    sid = str(session.session_id)

    first = await stream_mod.next_run_turn(sid)
    second = await stream_mod.next_run_turn(sid)
    assert second == first + 1, "同一会话内轮次号必须递增（Redis INCR 口径）"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_user_message_carries_turn_no() -> None:
    session = await AgentSession.objects.acreate(title="轮次-用户", origin="chat")
    await stream_mod.record_user_message(session, "第一问", turn_no=3)
    row = await AgentMessage.objects.filter(session=session).afirst()
    assert row is not None and row.turn_no == 3


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_run_and_assistant_share_turn_no_for_cost_grouping() -> None:
    """同一轮的 AgentRun 与助手消息必须同号——「这一轮三栏花多少」靠它聚合。"""
    from apps.agent.services.chat import persist

    session = await AgentSession.objects.acreate(title="轮次-成本", origin="chat")
    await persist._record_run(
        session=session,
        user_id=None,
        model="m",
        agent_kind="pi",
        cancelled=False,
        error_kind="",
        input_tokens=10,
        output_tokens=5,
        tool_calls=0,
        duration_ms=1,
        turn_no=7,
    )
    await AgentMessage.objects.acreate(
        session=session, role=AgentMessage.Role.ASSISTANT, content="答", agent_kind="pi", turn_no=7
    )
    run = await AgentRun.objects.filter(session=session).afirst()
    msg = await AgentMessage.objects.filter(session=session).afirst()
    assert run is not None and run.turn_no == 7
    assert msg is not None and msg.turn_no == 7
