"""综合结论的读写存储层（API 层不直接碰 ORM）。

四层结构里 ``api/*`` 不允许出现 ``Model.objects``：轮次候选的读取、合成模型的
解析、``AgentSynthesis`` 的落库与回放都在这里。

## 候选正文为什么不自己再查一遍

轮次的定义（第 N 条 user 消息到第 N+1 条之前）只能有一处口径，已经在
``review/store.load_turn_answers`` 里；这里复用它取正文，只额外查一次本轮助手
行的 ``metadata``——**模型名**不在正文里，而来源头 ``【栏名 · 模型】`` 没有它
就只能写"未标注模型"（见 ``chat/aggregate.py``）。

## ``failed`` 与 ``empty`` 怎么分

``AgentMessage`` 只在有正文时才落行（失败栏根本不落），所以：

- 本轮**没有**该栏的 assistant 行 → ``Candidate.text=None`` → ``failed``；
- 有行但正文空白 → ``text=""`` → ``empty``。

**不读** ``metadata["finish_reason"]`` 判失败：多答收尾会把它改写成**轮级**结论
（``chat/multi.py`` 的 ``_stamp_finish_reason``），"另一栏炸了"会让好栏也带上
``degraded``——拿它当栏级失败证据会把正常回答误判成失败。
"""

from __future__ import annotations

from collections.abc import Sequence

from ...models import AgentMessage, AgentSession, AgentSynthesis
from ..adjudication.contracts import Synthesis
from ..chat.aggregate import Candidate
from ..review.store import load_turn_answers


async def _turn_assistant_rows(session: AgentSession, turn: int) -> list[AgentMessage]:
    """第 ``turn`` 轮的助手消息（按 id 升序）。

    区间口径与 ``review/store.load_turn_answers`` **逐字一致**（第 ``turn`` 条
    user 消息之后、第 ``turn+1`` 条之前）：同一轮必须切出同一批行，否则"评审看
    的那份答案"与"综合的那份答案"会在续写过的轮次里对不上。
    不用 ``AgentMessage.turn_no``：引入该字段之前的旧数据是 0，靠它会切空。

    Raises:
        LookupError: 该轮次不存在（没有第 ``turn`` 条 user 消息）。
    """
    user_ids = [
        pk
        async for pk in AgentMessage.objects.filter(session=session, role=AgentMessage.Role.USER)
        .order_by("id")
        .values_list("pk", flat=True)
    ]
    if turn > len(user_ids):
        raise LookupError("该轮次不存在")

    rows = AgentMessage.objects.filter(
        session=session,
        role=AgentMessage.Role.ASSISTANT,
        id__gt=user_ids[turn - 1],
    )
    if turn < len(user_ids):
        rows = rows.filter(id__lt=user_ids[turn])
    return [row async for row in rows.order_by("id")]


async def load_turn_candidates(
    session: AgentSession,
    turn: int,
    lanes: Sequence[str],
) -> tuple[str, list[Candidate]]:
    """取第 ``turn`` 轮的问题与各栏候选（含模型名与"有没有正文"）。

    Args:
        session: 已按归属校验过的会话。
        turn: 会话内第几轮（从 1 起，与 ``/review`` 同口径）。
        lanes: 请求的栏（``agent_kind``）；返回的候选顺序 = 这个顺序。

    Returns:
        ``(本轮 user 消息正文, 候选列表)``；``Candidate.text is None`` 表示该栏
        本轮没有正文（``failed``），空串表示有行但没内容（``empty``）。

    Raises:
        LookupError: 该轮次不存在。
        ValueError: 候选数超过 ``MAX_CANDIDATES``（由 ``partition_candidates`` 拦）。
    """
    task, answers = await load_turn_answers(session, turn, list(lanes))
    rows = await _turn_assistant_rows(session, turn)

    present: set[str] = set()
    models: dict[str, str] = {}
    for row in rows:
        if row.agent_kind not in lanes:
            continue
        present.add(row.agent_kind)
        model = str((row.metadata or {}).get("model") or "").strip()
        if model:
            # 同栏多条（继续生成 / 重试）时以**最后一条**留下的模型为准：
            # 律师看到的是最后一版，来源头也该指向真正产出它的模型。
            models[row.agent_kind] = model

    candidates = [
        Candidate(
            lane=lane,
            model=models.get(lane, ""),
            text=answers.get(lane, "") if lane in present else None,
        )
        for lane in lanes
    ]
    return task, candidates


async def resolve_model(session: AgentSession, turn: int, requested: str) -> str:
    """解析本次合成用哪个模型：请求指定优先，否则取本轮各栏实际模型去重的第一个。

    **不许猜模型名**（如写死某个默认模型）：平台没有可用模型时应当明确失败，
    由 API 转 422，让律师看到"未配置综合模型"而不是一条来路不明的调用账单。

    Raises:
        ValueError: 请求没指定，且本轮各栏都没留下模型名。
        LookupError: 该轮次不存在。
    """
    model = (requested or "").strip()
    if model:
        return model

    rows = await _turn_assistant_rows(session, turn)
    seen: list[str] = []
    for row in rows:
        name = str((row.metadata or {}).get("model") or "").strip()
        if name and name not in seen:
            seen.append(name)
    if not seen:
        raise ValueError("未配置综合模型：请求里没有指定，本轮各栏也没有留下模型名")
    return seen[0]


async def save_synthesis(*, session: AgentSession, user_id: int | None, synthesis: Synthesis) -> AgentSynthesis:
    """把一次综合结论的完整快照落库（**不**写 assistant 消息，见 ``models/synthesis.py``）。"""
    return await AgentSynthesis.objects.acreate(
        session=session,
        user_id=user_id,
        synthesis_id=synthesis.synthesis_id,
        turn=synthesis.turn,
        model=synthesis.model,
        text=synthesis.text,
        lanes_used=list(synthesis.lanes_used),
        dropped=[item.model_dump() for item in synthesis.dropped],
        citations=[item.model_dump() for item in synthesis.citations],
        unverified=list(synthesis.unverified),
        tokens=dict(synthesis.tokens),
    )


async def latest_synthesis(session: AgentSession, turn: int | None) -> AgentSynthesis | None:
    """取该会话（可选指定轮次）最近一次综合结论，供刷新后回放。"""
    records = AgentSynthesis.objects.select_related("session").filter(session=session)
    if turn is not None:
        records = records.filter(turn=turn)
    return await records.order_by("-created_at", "-id").afirst()
