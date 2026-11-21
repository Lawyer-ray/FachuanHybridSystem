"""评审的读写存储层（API 层不直接碰 ORM）。

四层结构里 ``api/*`` 不允许出现 ``Model.objects``：查询与落库都在这里。
"""

from __future__ import annotations

from ...models import AgentMessage, AgentReview, AgentSession
from ..adjudication.contracts import EquivalenceCluster, Review


async def _turn_window(session: AgentSession, turn: int, lanes: list[str]) -> tuple[AgentMessage, list[AgentMessage]]:
    """取本轮锚点（user 消息）与该轮各栏 assistant 消息（按 id 升序）。

    轮次按 user 消息顺序定义：第 ``turn`` 条 user 消息到第 ``turn+1`` 条
    之前的 assistant 消息属于本轮。

    Raises:
        LookupError: 轮次不存在（超过 user 消息条数）。
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
    return anchor, [row async for row in rows.order_by("id")]


async def load_turn_answers(session: AgentSession, turn: int, lanes: list[str]) -> tuple[str, dict[str, str]]:
    """取第 ``turn`` 轮的问题与各栏最终回答。

    同一栏有多条（继续生成/重试）时取最后一条——评审看的是律师最终看到的那一版回答。

    Returns:
        ``(本轮 user 消息正文, {lane: 回答正文})``；轮次不存在时抛 ``LookupError``。
    """
    anchor, rows = await _turn_window(session, turn, lanes)
    latest: dict[str, str] = {}
    for row in rows:
        if row.content.strip():
            latest[row.agent_kind] = row.content
    return anchor.content, {lane: latest.get(lane, "") for lane in lanes}


async def load_turn_models(session: AgentSession, turn: int, lanes: list[str]) -> list[str]:
    """取本轮各栏实际用过的模型（``AgentMessage.metadata["model"]`` 去重保序）。

    这是 judge 模型解析的第 3 条兜底（契约 §C2）：平台自己派下去的模型一定在
    白名单里，拿它当 judge 不会出现"猜一个不存在的模型名"。空正文的栏也算——
    那一栏可能跑失败，但模型名照样记录了。

    Raises:
        LookupError: 轮次不存在。
    """
    _, rows = await _turn_window(session, turn, lanes)
    models = [str((row.metadata or {}).get("model") or "").strip() for row in rows]
    return list(dict.fromkeys(model for model in models if model))


def _cluster_row(cluster: EquivalenceCluster) -> dict[str, object]:
    """``EquivalenceCluster`` → JSON 列值（``member_ids`` 存 list：列里没有 tuple）。"""
    return {
        "member_ids": list(cluster.member_ids),
        "representative_id": cluster.representative_id,
        "tie": cluster.tie,
    }


async def save_review(
    *,
    session: AgentSession,
    user_id: int | None,
    rubric_id: str,
    judge_models: list[str],
    review: Review,
) -> AgentReview:
    """把一次评审的完整快照落库（逐条 verdict / 立场成团都存 JSON）。

    ``clusters_error`` 与 ``clusters`` 必须一起落：只存空的 ``clusters`` 会让回放时
    把"成团失败"看成"三份全异"（两者在 ``clusters`` 上都是空列表）。
    """
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
        clusters=[_cluster_row(cluster) for cluster in review.clusters],
        clusters_error=review.clusters_error,
    )


async def latest_review(session: AgentSession, turn: int | None) -> AgentReview | None:
    """取该会话（可选指定轮次）最近一次评审，供刷新后回放。"""
    records = AgentReview.objects.select_related("session").filter(session=session)
    if turn is not None:
        records = records.filter(turn=turn)
    return await records.order_by("-created_at", "-id").afirst()
