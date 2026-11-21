"""Agent 对话 API —— SSE 流式发消息、断线回放、运行中插话/追加/撤回。

端点前缀：``/api/v1/agent``（对话子域）。事件契约见 ``apps.agent.sse_types``。
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any, Literal

from django.http import StreamingHttpResponse
from ninja import Router, Schema
from ninja.errors import HttpError

from apps.core.infrastructure.throttling import get_rate_limit_config, rate_limit
from apps.core.security.auth import JWTOrSessionAuth

from ..errors import SessionNotFoundError, TooManyAgentsError, project, project_message
from ..models import AgentMessage
from ..pi.rpc_client import PiError
from ..schemas import ClearQueueOut, MessageIn, MessageOut, SteerIn, SteerOut
from ..services.chat.regenerate import MODE_CONTINUE, REPLAY_MODES, continuation_prompt, mark_superseded, resolve_target
from ..services.chat_service import (
    MAX_ANSWERS,
    SessionNotLiveError,
    clear_queue_session,
    follow_up_session,
    normalize_agents,
    steer_session,
    stream_chat,
    stream_multi,
)
from ..services.event_bus import replay_events
from ..services.live_sessions import forward_steer_to_worker, get_live_worker
from ..services.message_rating import RATING_METADATA_KEY, set_message_rating
from ..services.session_service import get_session as get_session_record
from ..services.session_service import list_messages as list_message_records
from ._helpers import _user_id

logger = logging.getLogger(__name__)

router = Router(tags=["Agent 对话"], auth=JWTOrSessionAuth())

#: 发消息限流（P1-8a）：每用户 20 次/分钟；RATE_LIMIT['AGENT_SEND_*'] 可覆盖
_AGENT_SEND_RATE_LIMIT = get_rate_limit_config("AGENT_SEND", fallback_requests=20, fallback_window=60)


def _send_rate_key(request: Any) -> str:
    """限流键按用户（JWT 的 auth 或 session 的 user），匿名回退 IP 由基类兜底。"""
    user = getattr(request, "auth", None) or getattr(request, "user", None)
    pk = getattr(user, "pk", None)
    return f"agent_send:user:{pk if pk is not None else 'anon'}"


def _sse(payload: dict[str, Any]) -> bytes:
    seq = payload.pop("_seq", None)
    id_line = f"id: {seq}\n" if seq else ""
    return f"{id_line}data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode()


def _live_session_error(exc: Exception) -> HttpError:
    """把 service 层异常转成前端能理解的 HTTP 错误。"""
    if isinstance(exc, PiError):
        # pi 拒绝：通常是本轮已 settle（ran 完），插话无对象
        return HttpError(409, "对话已结束，无法插话")
    return HttpError(409, "会话当前没有运行中的对话")


def _message_out(message: AgentMessage) -> MessageOut:
    return MessageOut(
        message_id=message.pk,
        role=message.role,
        content=message.content,
        tool_name=message.tool_name,
        # 空串 = 引入双答之前的旧数据：前端渲染时当 pi 处理（历史口径）
        agent_kind=getattr(message, "agent_kind", "") or "",
        # 反馈存在 metadata 里（撤销=删键），回放时提升为顶层字段：
        # 空串 = 未评分 / 已撤销
        rating=str((message.metadata or {}).get(RATING_METADATA_KEY, "")),
        created_at=message.created_at.isoformat(),
        metadata=message.metadata or {},
    )


@router.get("/sessions/{session_id}/messages", response=list[MessageOut])
async def list_messages(
    request: Any, session_id: str, limit: int = 200, before_id: int | None = None
) -> list[MessageOut]:  # pragma: no cover
    """会话消息历史（旧→新），前端重开会话时据此回放转录。

    ``before_id``：游标分页——取该消息 id 之前的 ``limit`` 条（加载更早），
    不传为最新一页。返回条数等于 limit 时大概率还有更早消息，由前端
    用最后一条的 message_id 作为下一页游标。

    与 POST /messages（send_message）同路径，必须登记在同一路由器，
    否则 Ninja 会按子路由各自建 URL pattern，GET 先匹配导致 POST 405。
    """
    messages = await list_message_records(
        session_id=session_id, user_id=_user_id(request), limit=limit, before_id=before_id
    )
    if messages is None:
        raise HttpError(404, "会话不存在")
    return [_message_out(m) for m in messages]


@router.get("/sessions/{session_id}/events/replay")
async def replay_sse_events(
    request: Any, session_id: str, last_event_id: int = 0
) -> list[dict[str, Any]]:  # pragma: no cover
    """P2-1 SSE 断线重连：回放 last_event_id 之后的事件。

    前端断线重连时先调此端点取缺失事件再续 SSE。Redis 不可用返回空。
    """
    return replay_events(session_id, last_event_id)


class RegenerateIn(Schema):
    """重生成 / 续写的请求体。

    ``from_message_id`` 可以是这一轮里的**任意一条**（提问 / 回答 / 工具行）：
    服务端按"同一轮"定位，不要求前端先算出是哪一栏。
    """

    #: 被操作的那条消息（点哪一栏就传哪一条）
    from_message_id: int
    #: ``regenerate`` = 重跑同一提问；``continue`` = 接着被中断的前缀继续写
    mode: str = "regenerate"
    #: 显式指定栏（只允许 1 个；不传则沿用它自己的 agent_kind）
    agents: list[str] | None = None


@router.post("/sessions/{session_id}/regenerate")
@rate_limit(
    requests=_AGENT_SEND_RATE_LIMIT[0],
    window=_AGENT_SEND_RATE_LIMIT[1],
    key_func=_send_rate_key,
)
async def regenerate_message(request: Any, session_id: str, payload: RegenerateIn) -> Any:  # pragma: no cover
    """重生成 / 续写（SSE，与发消息同形）。

    **不新落用户消息**：复用原提问（``user_message_recorded=True``），轮次号也不增
    （``turn=target.turn_no``）——否则同一个问题会变成两轮，「第几轮」这个口径当场废掉。

    开流前先把这一轮同栏的旧回答标 ``metadata.superseded``（幂等），列表接口据此
    隐藏它们；消息行本身不删，审计仍能回溯「AI 当时说过什么」。
    """
    user_id = _user_id(request)
    lanes = [lane.strip() for lane in (payload.agents or []) if lane.strip()]
    if len(lanes) > 1:
        return StreamingHttpResponse(
            iter([_sse(project_message("regenerate_multi_lane", message="重生成一次只能跑一栏，请点具体那一栏"))]),
            content_type="text/event-stream",
        )
    if payload.mode not in REPLAY_MODES:
        return StreamingHttpResponse(
            iter([_sse(project_message("regenerate_bad_mode", message=f"未知的重放模式：{payload.mode}"))]),
            content_type="text/event-stream",
        )

    async def generator() -> AsyncIterator[bytes]:
        current = await get_session_record(session_id=session_id, user_id=user_id)
        if current is None:
            yield _sse(project(SessionNotFoundError(session_id=session_id)))
            return
        try:
            target = await resolve_target(
                session=current,
                from_message_id=payload.from_message_id,
                mode=payload.mode,
                lane=lanes[0] if lanes else "",
            )
        except LookupError:
            # 定位失败是**可操作**的错误，但**不能把异常文本放进响应**（同上：CodeQL
            # 判 stack-trace-exposure）。这里按分支给固定文案，细节进日志。
            logger.info("重生成：消息不存在（session=%s msg=%s）", session_id, payload.from_message_id)
            yield _sse(project_message("regenerate_target_missing", message="找不到这条消息或它对应的提问"))
            return
        except ValueError:
            logger.info("重生成：请求不可执行（session=%s msg=%s）", session_id, payload.from_message_id)
            yield _sse(project_message("regenerate_target_invalid", message="续写需要一条已有正文的回答"))
            return

        marked = await mark_superseded(session=current, turn_no=target.turn_no, lane=target.lane)
        logger.info(
            "重生成：session=%s turn=%s lane=%s mode=%s superseded=%s",
            session_id,
            target.turn_no,
            target.lane or "(无栏)",
            target.mode,
            len(marked),
        )
        prompt = continuation_prompt(target.prompt, target.prefix) if target.mode == MODE_CONTINUE else target.prompt
        try:
            async for event in stream_chat(
                session=current,
                user_message=prompt,
                user_id=user_id,
                agent_kind=target.lane,
                model=target.model or None,
                # 复用原提问：不落用户消息、不重算标题
                user_message_recorded=True,
                # 同轮：新回答挂在原来的轮次下，不制造新的一轮
                turn=target.turn_no,
            ):
                yield _sse(event)
        except SessionNotLiveError:
            # 与 ``send_message`` 同一条红线：**异常文本不进响应**。
            # 只要异常对象参与构造响应，CodeQL 的 py/stack-trace-exposure 就判 error
            # （本仓库已被拦过三次）；堆栈与分类由 logger 留档，律师只需要一句结论。
            logger.warning("重生成：会话已不在运行中（session=%s）", session_id, exc_info=True)
            yield _sse(project_message("session_not_live", message="本轮已结束，无法继续写入"))
        except PiError:
            logger.warning("重生成：模型进程异常（session=%s）", session_id, exc_info=True)
            yield _sse(project_message("pi_error", message="模型调用失败，请稍后重试"))

    return StreamingHttpResponse(generator(), content_type="text/event-stream")


@router.post("/sessions/{session_id}/messages")
@rate_limit(
    requests=_AGENT_SEND_RATE_LIMIT[0],
    window=_AGENT_SEND_RATE_LIMIT[1],
    key_func=_send_rate_key,
)
async def send_message(  # pragma: no cover
    request: Any,
    session_id: str,
    payload: MessageIn,
) -> Any:
    """发消息并流式返回（SSE）。限流：每用户 20 次/分钟（RATE_LIMIT['AGENT_SEND_*'] 可覆盖）。"""
    user_id = _user_id(request)
    session = await get_session_record(session_id=session_id, user_id=_user_id(request))
    if session is None:
        return StreamingHttpResponse(
            # 必须传可迭代对象：直接传 bytes 会被逐字节迭代成 int，
            # 前端收到的是一串十进制数字
            iter([_sse(project(SessionNotFoundError(session_id=session_id)))]),
            content_type="text/event-stream",
        )

    async def generator() -> AsyncIterator[bytes]:
        # 会话对象在流式阶段重新取：ORM 实例带着数据库连接状态，
        # 跨到 StreamingHttpResponse 的异步迭代阶段可能已失效。
        current = await get_session_record(session_id=session_id, user_id=user_id)
        if current is None:
            yield _sse(project(SessionNotFoundError(session_id=session_id)))
            return
        # 本轮参与方：``agents`` 显式优先，否则退回旧前端的 ``dual`` 开关。
        #
        # 编排层不认识具体 kind —— 加第 4、5 个 agent 时这里不需要改，注册进来
        # 就能选。两种请求体形态（``["pi"]`` / ``[{kind,model}]``）在这里归一成
        # ``AgentSpec``，下游只见一种形状（含每栏模型）。
        specs = normalize_agents(payload.agents)

        if len(specs) > MAX_ANSWERS:
            # 不静默截断：静默截断会让用户以为选中的都跑了，实际少跑了几个还看不出来。
            # ``detail`` 带上两个数：前端能直接说「最多 4 栏，你选了 6 栏」，
            # 不用从中文文案里再抠数字。
            yield _sse(
                project(
                    TooManyAgentsError(
                        f"一次最多同时问 {MAX_ANSWERS} 个 agent，本轮收到 {len(specs)} 个",
                        requested=len(specs),
                        max=MAX_ANSWERS,
                    )
                )
            )
            return

        # 单栏直接走 stream_chat（少绕一层，且 done 的形态只有一处定义）。
        if len(specs) == 1:
            events = stream_chat(
                session=current,
                user_message=payload.message,
                user_id=user_id,
                agent_kind=specs[0].kind,
                model=specs[0].model,
            )
        elif specs or payload.dual:
            # ``specs=None`` + ``dual`` 走「会话默认 + 次选」（老客户端只发
            # ``dual: true``，见 ``multi.resolve_specs`` 的回落口径）。
            events = stream_multi(
                session=current,
                user_message=payload.message,
                user_id=user_id,
                specs=specs or None,
            )
        else:
            events = stream_chat(session=current, user_message=payload.message, user_id=user_id)
        try:
            async for event in events:
                yield _sse(event)
        except Exception as exc:
            # 走到这里说明异常穿过了整层编排（stream / multi 自己已把可预期错误
            # 转成 error 帧）——仍用投影而不是手写：来的是 ``LookupError``
            # （未知后端）还是上游 SDK 错误，前端需要那个 ``code`` 才能给出
            # 「换一栏」还是「稍后重试」的可执行建议。
            logger.exception("SSE 生成器异常")
            # 用 ``project_message``（吃**字符串**）而不是 ``project(exc)``：
            # 只要异常对象参与构造响应，CodeQL 的 py/stack-trace-exposure 就判成
            # "堆栈可能进响应"（error 级，实测两次都被拦）；而这条路径也不需要细分类——
            # 能走到这里说明异常已穿过 stream/multi 的全部兜底，对律师只有一个结论：
            # 这一轮没跑成，稍后重试。分类与堆栈由上面的 logger.exception 完整留档。
            yield _sse(project_message("stream_failed", message="流处理异常，请稍后重试"))

    response = StreamingHttpResponse(generator(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


@router.post("/sessions/{session_id}/steer", response=SteerOut)
async def steer_running_session(  # pragma: no cover
    request: Any,
    session_id: str,
    payload: SteerIn,
) -> Any:
    """运行中插话：在当前 assistant turn 的工具调用之后、下次模型调用之前生效。

    P2-3 跨 Worker：Redis 路由表发现会话在其他 worker → HTTP 转发。
    用于「agent 写到一半发现要改方向」，不必停止重发。
    """
    session = await get_session_record(session_id=session_id, user_id=_user_id(request))
    if session is None:
        raise HttpError(404, "会话不存在")
    if not payload.message.strip():
        raise HttpError(400, "插话内容不能为空")

    # P2-3：跨 worker 转发（路由表发现目标 worker，转发逻辑在 live_sessions）
    target = get_live_worker(session_id)
    if target:
        forwarded = await forward_steer_to_worker(session_id, payload.message, target)
        if forwarded is not None:
            return SteerOut(**forwarded)

    try:
        disposition = await steer_session(session_id=session_id, message=payload.message)
    except (SessionNotLiveError, PiError) as exc:
        raise _live_session_error(exc) from exc
    return SteerOut(success=True, disposition=disposition)


@router.post("/sessions/{session_id}/follow-up", response=SteerOut)
async def follow_up_running_session(  # pragma: no cover
    request: Any,
    session_id: str,
    payload: SteerIn,
) -> Any:
    """追加一轮：agent 干完当前所有活后再跑这条。"""
    session = await get_session_record(session_id=session_id, user_id=_user_id(request))
    if session is None:
        raise HttpError(404, "会话不存在")
    if not payload.message.strip():
        raise HttpError(400, "追加内容不能为空")
    try:
        disposition = await follow_up_session(session_id=session_id, message=payload.message)
    except (SessionNotLiveError, PiError) as exc:
        raise _live_session_error(exc) from exc
    return SteerOut(success=True, disposition=disposition)


@router.delete("/sessions/{session_id}/queue", response=ClearQueueOut)
async def clear_session_queue(request: Any, session_id: str) -> Any:  # pragma: no cover
    """撤回已排队但尚未生效的插话 / 追加消息（「撤销」按钮）。"""
    session = await get_session_record(session_id=session_id, user_id=_user_id(request))
    if session is None:
        raise HttpError(404, "会话不存在")
    messages = await clear_queue_session(session_id=session_id)
    return ClearQueueOut(success=True, messages=messages)


class MessageRatingIn(Schema):
    """律师对一条消息的反馈：``up`` / ``down``；``none`` = 撤销（删键）。"""

    rating: Literal["up", "down", "none"]


class MessageRatingOut(Schema):
    """反馈回执。``rating`` 是落库后的值，空串 = 已撤销（``metadata`` 里无该键）。"""

    message_id: int
    rating: str = ""


@router.post("/messages/{message_id}/rating", response=MessageRatingOut)
async def rate_message(request: Any, message_id: int, payload: MessageRatingIn) -> Any:
    """给一条已落库的消息点赞 / 点踩（``none`` 撤销）。

    归属看**消息所属会话**：别人的会话一律 404，不是 403——403 等于承认
    「这条消息存在」，是无成本的存在性探测。
    """
    message = await set_message_rating(message_id=message_id, user_id=_user_id(request), rating=payload.rating)
    if message is None:
        raise HttpError(404, "消息不存在")
    return MessageRatingOut(message_id=message.pk, rating=str((message.metadata or {}).get(RATING_METADATA_KEY, "")))
