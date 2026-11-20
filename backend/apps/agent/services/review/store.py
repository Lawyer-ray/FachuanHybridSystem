"""评审的读写存储层（API 层不直接碰 ORM）。

四层结构里 ``api/*`` 不允许出现 ``Model.objects``：查询与落库都在这里。
"""

from __future__ import annotations

from ..adjudication.contracts import Review
from ...models import AgentMessage, AgentReview, AgentSession


async def load_turn_answers(session: AgentSession, turn: int, lanes: list[str]) -> tuple[str, dict[str, str]]:
    """取第 ``turn`` 轮的问题与各栏最终回答。

    轮次按 user 消息顺序定义：第 ``turn`` 条 user 消息到第 ``turn+1`` 条
    之前的 assistant 消息属于本轮。同一栏有多条（继续生成/重试）时取最后
    一条——评审看的是律师最终看到的那一版回答。

    Returns:
        ``(本轮 user 消息正文, {lane: 回答正文})``；轮次不存在时抛 ``LookupError``。
    """
    user_messages = [
        message
        async for message in AgentMessage.objects.filter(session=session, role=AgentMessage.Role.USER).order_by("id")
    ]
    if turn > len(user_messages):
        raise LookupError("该轮次不存在")

    anchor = user_messages[turn - 1]
    rows = AgentMessage.objects.filter(
        session=session,
        role=AgentMessage.Role.ASSISTANT,
        agent_kind__in=lanes,
        id__gt=anchor.pk,
    )
    if turn < len(user_messages):
        rows = rows.filter(id__lt=user_messages[turn].pk)

    latest: dict[str, str] = {}
    async for row in rows.order_by("id"):
        if row.content.strip():
            latest[row.agent_kind] = row.content
    return anchor.content, {lane: latest.get(lane, "") for lane in lanes}


async def save_review(
    *,
    session: AgentSession,
    user_id: int | None,
    rubric_id: str,
    judge_models: list[str],
    review: Review,
) -> AgentReview:
    """把一次评审的完整快照落库（逐条 verdict 存 JSON）。"""
    return await AgentReview.objects.acreate(
        session=session,
        user_id=user_id,
        review_id=review.review_id,
        turn=review.turn,
        rubric_id=rubric_id,
        stage=review.stage,
        judge_models=list(judge_models),
        lanes=[lane.model_dump() for lane in review.lanes],
        verdicts=[verdict.model_dump() for verdict in review.verdicts],
        headline=review.headline,
        unverified=list(review.unverified),
        tokens=dict(review.tokens),
    )


async def latest_review(session: AgentSession, turn: int | None) -> AgentReview | None:
    """取该会话（可选指定轮次）最近一次评审，供刷新后回放。"""
    records = AgentReview.objects.select_related("session").filter(session=session)
    if turn is not None:
        records = records.filter(turn=turn)
    return await records.order_by("-created_at", "-id").afirst()
