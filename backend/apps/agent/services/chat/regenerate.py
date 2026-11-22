"""重生成 / 续写：复用原提问，**旧回答不删档**，只标「已被取代」。

## 为什么不是「删掉旧回答再重跑」

律师的工作留痕诉求比"界面干净"重要得多：AI 昨天说过什么、今天被谁重跑过，是复盘
（以及"这条意见到底是谁给的"）的依据。所以旧行照原样留在 ``AgentMessage`` 里，
只在 ``metadata`` 上打三个键：``superseded`` / ``superseded_at`` /
``superseded_reason``；列表接口按 ``metadata__superseded=True`` 把它们滤掉。

**过滤必须用 JSON 键存在性语义**：``NOT (NULL = true)`` 在 SQL 里仍是 NULL，所以
"键缺失"的老消息会被 ``.exclude(metadata__superseded=True)`` 正确处理（Django 生成
的是 ``NOT (metadata -> 'superseded' = true)``，键缺失时子表达式为 NULL，行被保留）。
反过来若写成 ``filter(metadata__superseded=False)``，所有没有这个键的历史消息会一起
消失——那是真正的数据事故。

## 为什么续写用 prompt 而不是「从断点续吐 token」

后端契约只有「一条 prompt 进、事件流出」，pi / dsh / openai-agents 都没有续写入口。
退化成「已生成前缀 + 明确续写指令」，代价是前缀重新计入输入 token（同会话通常命中
prompt cache）。这条取舍写在 :func:`continuation_prompt` 的注释里。

## 一次只跑一栏

点哪一栏重跑哪一栏。多栏重跑会重复落用户消息（``stream_multi`` 自己写提问），所以
调用方必须把栏数限制为 1；本模块只管"定位这一栏"，不做多栏编排。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from django.utils import timezone

from ...models import AgentMessage, AgentSession
from ..synthesis.kinds import SYNTHESIS_AGENT_KIND

#: 两种重放模式。``regenerate`` = 重跑同一提问；``continue`` = 接着被中断的前缀写。
MODE_REGENERATE = "regenerate"
MODE_CONTINUE = "continue"
REPLAY_MODES: frozenset[str] = frozenset({MODE_REGENERATE, MODE_CONTINUE})

ReplayMode = Literal["regenerate", "continue"]


class SynthesisNotReplayableError(ValueError):
    """综合结论不能从转录里重生成 / 续写。

    它不是某一栏的回答，没有对应的运行时可重跑（``agent_kind="synthesis"`` 不在后端
    注册表里）；更不能先把它标成「已被取代」再失败。要重新生成，走综合工具条。
    """


#: 写进 ``metadata.superseded_reason`` 的封闭取值（前端/日志据此区分原因）。
REASON_REGENERATED = "regenerated"
REASON_CONTINUED = "continued"


@dataclass(frozen=True)
class RegenTarget:
    """一次重放要的全部上下文（定位完就不再碰 ORM）。"""

    #: 原始提问正文（``stream_chat`` 的 ``user_message``）
    prompt: str
    #: 原轮次号（新回答与它同轮，不允许自增——否则同一提问会变成两轮）
    turn_no: int
    #: 这条回答属于哪一栏
    lane: str
    #: 这一栏当时用的模型（空 = 平台默认）
    model: str
    #: ``continue`` 模式下要接着写的前缀；``regenerate`` 为空串
    prefix: str
    #: 被重放的那条消息 id（``continue`` 时就是被截断的那条回答）
    from_message_id: int
    mode: ReplayMode

    @property
    def is_continuation(self) -> bool:
        return self.mode == MODE_CONTINUE


async def _prompt_for(session: AgentSession, message: AgentMessage) -> AgentMessage | None:
    """这条消息所属那一轮的**用户提问**。

    优先按 ``turn_no`` 找（``0024`` 之后的消息都有）；老数据 ``turn_no = 0``，退回
    「id 小于它的最近一条 user」——两者的判据都是"同一轮"，只是老数据没有轮次号。
    """
    # 传 session 而不是 ``message.session``：后者是懒加载 FK，在 async 上下文里
    # 会触发同步查询（SynchronousOnlyOperation），而且它根本不需要重新查一遍会话。
    queryset = AgentMessage.objects.filter(session=session, role=AgentMessage.Role.USER)
    if message.turn_no:
        return await queryset.filter(turn_no=message.turn_no).order_by("id").afirst()
    return await queryset.filter(id__lt=message.pk).order_by("-id").afirst()


async def resolve_target(
    *,
    session: AgentSession,
    from_message_id: int,
    mode: str = MODE_REGENERATE,
    lane: str = "",
    model: str = "",
) -> RegenTarget:
    """定位"要重放哪一轮、哪一栏"。

    Args:
        session: 目标会话（已校验归属）。
        from_message_id: 可以是这一轮里的**任意一条**（提问 / 回答 / 工具行）。
        mode: 见 :data:`REPLAY_MODES`。
        lane / model: 显式覆盖；空则沿用它自己的 ``agent_kind`` / ``metadata.model``。

    Raises:
        SynthesisNotReplayableError: 目标是综合结论（``ValueError`` 子类）。
        ValueError: ``mode`` 不合法，或 ``continue`` 指向的不是一条有正文的回答。
        LookupError: 消息不属于该会话，或找不到它对应的提问。
    """
    if mode not in REPLAY_MODES:
        raise ValueError(f"未知的重放模式：{mode}")

    message = await AgentMessage.objects.filter(session=session, id=from_message_id).afirst()
    if message is None:
        raise LookupError("消息不存在")
    if SYNTHESIS_AGENT_KIND in (lane, message.agent_kind):
        raise SynthesisNotReplayableError("综合结论请在综合工具条里重新生成")

    prompt_row = message if message.role == AgentMessage.Role.USER else await _prompt_for(session, message)
    if prompt_row is None:
        raise LookupError("找不到这条回答对应的提问")

    prefix = ""
    if mode == MODE_CONTINUE:
        # 续写的对象只能是「有正文的回答」：拿一条空的工具行做续写没有前缀可接
        if message.role != AgentMessage.Role.ASSISTANT or not message.content.strip():
            raise ValueError("续写需要一条已有正文的回答")
        prefix = message.content

    metadata = message.metadata or {}
    return RegenTarget(
        prompt=prompt_row.content,
        turn_no=prompt_row.turn_no or message.turn_no,
        lane=lane or (message.agent_kind or ""),
        model=model or str(metadata.get("model") or ""),
        prefix=prefix,
        from_message_id=message.pk,
        mode="continue" if mode == MODE_CONTINUE else "regenerate",
    )


async def mark_superseded(*, session: AgentSession, turn_no: int, lane: str) -> list[int]:
    """把该轮**同栏**的回答与工具行标成「已被取代」，返回被标的消息 id。

    幂等：重复点重生成不刷新 ``superseded_at``（否则"什么时候被取代"每次都变，
    等于把审计时间戳变成"最后一次点击时间"）。
    """
    queryset = AgentMessage.objects.filter(
        session=session,
        turn_no=turn_no,
        role__in=[AgentMessage.Role.ASSISTANT, AgentMessage.Role.TOOL],
    )
    if lane:
        queryset = queryset.filter(agent_kind=lane)
    else:
        # 没指定栏 = 重放的是"提问那一条"，此时只取代没有 agent 归属的行（老数据）
        queryset = queryset.filter(agent_kind="")

    now = timezone.now().isoformat()
    marked: list[int] = []
    async for row in queryset.order_by("id"):
        metadata = dict(row.metadata or {})
        if metadata.get("superseded") is True:
            continue
        metadata["superseded"] = True
        metadata["superseded_at"] = now
        metadata["superseded_reason"] = REASON_REGENERATED
        row.metadata = metadata
        await row.asave(update_fields=["metadata"])
        marked.append(row.pk)
    return marked


def continuation_prompt(prompt: str, prefix: str) -> str:
    """续写用的 prompt：原提问 + 已生成前缀 + 明确的续写指令。

    指令必须同时禁掉三件模型很爱做的事：重新开头、复述问题、总结前文。否则
    "续写"会变成"重写一遍但更短"——那正是律师最不想要的结果。
    """
    if not prefix.strip():
        return prompt
    return (
        f"{prompt}\n\n"
        f"以下是这个问题**已经生成的回答**（中途被用户中断，请从断点继续，不要重复）：\n"
        f"-----\n{prefix}\n-----\n\n"
        f"请紧接着上文继续写下去：不要重新开头，不要复述问题，不要总结上面已经写过的内容。"
    )
