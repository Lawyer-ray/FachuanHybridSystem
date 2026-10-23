"""Agent API —— 会话管理与对话入口。

端点前缀：``/api/v1/agent``

- 会话：创建 / 列表 / 详情 / 消息历史 / 删除
- 对话：SSE 流式（事件契约见 services/chat_service.py）
- 审批：extension 回调入口 + 前端决定入口
"""

from __future__ import annotations

import hmac
import json
import logging
import os
from collections.abc import AsyncIterator
from typing import Any

from django.http import StreamingHttpResponse
from ninja import Router, Schema
from ninja.errors import HttpError

from apps.core.security.auth import JWTOrSessionAuth

from ..models import AgentApproval, AgentAttachment, AgentMessage, AgentSession
from ..pi.rpc_client import PiError
from ..services.approval import classify_risk, decide_approval, get_approval_for_decision
from ..services.approval import list_approvals as list_approval_records
from ..services.approval import list_pending_for_user as list_pending_approvals
from ..services.approval import request_approval
from ..services.attachments import create_attachment, get_attachment_for_user, read_attachment_content
from ..services.chat_service import (
    SessionNotLiveError,
    clear_queue_session,
    follow_up_session,
    steer_session,
    stream_chat,
)
from ..services.session_service import create_session as create_session_record
from ..services.session_service import delete_session as delete_session_record
from ..services.session_service import get_session as get_session_record
from ..services.session_service import list_messages as list_message_records
from ..services.session_service import list_sessions as list_session_records
from ..services.session_service import rename_session as rename_session_record
from ..services.usage_stats import UsageSummary
from ..services.usage_stats import by_model as usage_by_model
from ..services.usage_stats import daily_series as usage_daily_series
from ..services.usage_stats import summarize as usage_summarize

logger = logging.getLogger(__name__)

router = Router(tags=["Agent"], auth=JWTOrSessionAuth())


# ─── Schemas ─────────────────────────────────────────────────────────────────


class SessionIn(Schema):
    """创建会话请求体。

    不接受模型参数：模型由服务端按 LLMProvider 配置解析，客户端传了也不会生效，
    所以不在契约里留这个诱饵（``SessionOut.llm_model`` 回报的是实际使用的模型）。
    """

    title: str = ""
    #: 来源入口：chat（对话页）/ case（案件内）/ contract（合同内）/ task（任务式）
    origin: str = "chat"
    case_id: int | None = None
    contract_id: int | None = None


class SessionOut(Schema):
    """会话输出。``llm_model`` 为最近一轮对话实际使用的模型（未对话过为空）。"""

    session_id: str
    title: str
    status: str
    llm_model: str
    origin: str
    case_id: int | None = None
    contract_id: int | None = None
    #: 任务式会话的进度（queued/running/succeeded/failed/cancelled）；
    #: 非 task 会话为空串。
    task_state: str = ""
    task_id: str = ""
    task_error: str = ""
    task_finished_at: str = ""
    created_at: str
    updated_at: str


class MessageIn(Schema):
    """发消息请求体。"""

    message: str


class SessionRenameIn(Schema):
    """重命名会话请求体。"""

    title: str


class MessageOut(Schema):
    """会话消息（历史回放）。``metadata`` 含 ``model`` / ``truncated``（中断的回答）等。"""

    message_id: int
    role: str
    content: str
    tool_name: str
    created_at: str
    metadata: dict[str, Any] = {}


class ApprovalDecideIn(Schema):
    """前端审批决定。"""

    approved: bool


class TaskIn(Schema):
    """提交后台任务。"""

    message: str
    title: str = ""
    case_id: int | None = None
    contract_id: int | None = None


class TaskOut(Schema):
    """后台任务的受理/状态回执。"""

    session_id: str
    task_id: str
    task_state: str
    title: str = ""


class SteerIn(Schema):
    """运行中插话 / 追加一轮的请求体。"""

    message: str


class SteerOut(Schema):
    """插话结果。``disposition`` 为 queued（已排队）或 handled（被扩展消费）。"""

    success: bool
    disposition: str


class ClearQueueOut(Schema):
    """撤回排队消息的结果；``messages`` 是被撤回的原文。"""

    success: bool
    messages: list[str]


class UsageOut(Schema):
    """成本 / 耗时汇总。``error_rate`` 为小数（0.05 = 5%）。"""

    runs: int
    ok_runs: int
    error_runs: int
    cancelled_runs: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    tool_calls: int
    avg_duration_ms: int
    error_rate: float


class PiApprovalIn(Schema):
    """pi extension 发来的审批请求。

    ``risk_level`` 由 extension 预判后一并送来（仅作参考与日志），
    服务端以 ``classify_risk`` 的判定为准——extension 可以被绕过，
    不能让客户端决定自己要不要审批。
    """

    tool: str
    args: dict[str, Any] | None = None
    user_id: int = 0
    session_id: str = ""
    risk_level: str = ""


class PiApprovalOut(Schema):
    """审批结果（只有 approved=true 放行）。"""

    approved: bool
    approval_id: str = ""
    reason: str = ""
    risk_level: str = ""


class AttachmentOut(Schema):
    """附件上传回执：消息里以 [已上传附件：name (attachment_id=…)] 引用。"""

    attachment_id: str
    filename: str
    size: int
    mime: str = ""


def _current_user(request: Any) -> Any:
    user = getattr(request, "auth", None) or getattr(request, "user", None)
    if user is not None and getattr(user, "is_authenticated", False):
        return user
    return None


def _user_id(request: Any) -> int | None:
    user = _current_user(request)
    return int(user.pk) if user is not None else None


def _to_out(session: AgentSession) -> SessionOut:
    return SessionOut(
        session_id=str(session.session_id),
        title=session.title,
        status=session.status,
        llm_model=session.llm_model,
        origin=session.origin,
        case_id=session.case_id,
        contract_id=session.contract_id,
        task_state=session.task_state,
        task_id=session.task_id,
        task_error=session.task_error,
        task_finished_at=session.task_finished_at.isoformat() if session.task_finished_at else "",
        created_at=session.created_at.isoformat(),
        updated_at=session.updated_at.isoformat(),
    )


def _message_out(message: AgentMessage) -> MessageOut:
    return MessageOut(
        message_id=message.pk,
        role=message.role,
        content=message.content,
        tool_name=message.tool_name,
        created_at=message.created_at.isoformat(),
        metadata=message.metadata or {},
    )


# ─── 会话 ───────────────────────────────────────────────────────────────────


@router.post("/sessions", response=SessionOut)
async def create_session(request: Any, payload: SessionIn) -> SessionOut:  # pragma: no cover
    """新建会话。"""
    session = await create_session_record(
        title=payload.title,
        user_id=_user_id(request),
        origin=payload.origin,
        case_id=payload.case_id,
        contract_id=payload.contract_id,
    )
    return _to_out(session)


@router.get("/sessions", response=list[SessionOut])
async def list_sessions(  # pragma: no cover
    request: Any,
    limit: int = 50,
    origin: str | None = None,
    case_id: int | None = None,
    contract_id: int | None = None,
) -> list[SessionOut]:
    """列出当前用户的会话。

    可按入口（origin）与案件 / 合同过滤。归属始终按当前用户过滤——
    ``case_id`` 只用于缩小范围，不能借它看到别人的会话。
    """
    sessions = await list_session_records(
        user_id=_user_id(request),
        limit=limit,
        origin=origin,
        case_id=case_id,
        contract_id=contract_id,
    )
    return [_to_out(s) for s in sessions]


@router.get("/sessions/{session_id}", response=SessionOut)
async def get_session_detail(request: Any, session_id: str) -> SessionOut:  # pragma: no cover
    """会话详情（不归属当前用户时同样 404，不泄露存在性）。"""
    session = await get_session_record(session_id=session_id, user_id=_user_id(request))
    if session is None:
        raise HttpError(404, "会话不存在")
    return _to_out(session)


@router.get("/sessions/{session_id}/messages", response=list[MessageOut])
async def list_messages(request: Any, session_id: str, limit: int = 200) -> list[MessageOut]:  # pragma: no cover
    """会话消息历史（旧→新），前端重开会话时据此回放转录。"""
    messages = await list_message_records(session_id=session_id, user_id=_user_id(request), limit=limit)
    if messages is None:
        raise HttpError(404, "会话不存在")
    return [_message_out(m) for m in messages]


@router.delete("/sessions/{session_id}")
async def delete_session(request: Any, session_id: str) -> dict[str, Any]:  # pragma: no cover
    """删除会话（级联删除消息与审批）。"""
    deleted = await delete_session_record(session_id=session_id, user_id=_user_id(request))
    return {"deleted": deleted}


@router.patch("/sessions/{session_id}", response=SessionOut)
async def update_session_title(
    request: Any, session_id: str, payload: SessionRenameIn
) -> SessionOut:  # pragma: no cover
    """重命名会话（侧边栏会话列表的改名入口）。"""
    if not payload.title.strip():
        raise HttpError(400, "标题不能为空")
    session = await rename_session_record(
        session_id=session_id,
        user_id=_user_id(request),
        title=payload.title,
    )
    if session is None:
        raise HttpError(404, "会话不存在")
    return _to_out(session)


# ─── 对话 ───────────────────────────────────────────────────────────────────


def _sse(payload: dict[str, Any]) -> bytes:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode()


@router.post("/sessions/{session_id}/messages")
async def send_message(  # pragma: no cover
    request: Any,
    session_id: str,
    payload: MessageIn,
) -> Any:
    """发消息并流式返回（SSE）。"""
    user_id = _user_id(request)
    session = await get_session_record(session_id=session_id, user_id=_user_id(request))
    if session is None:
        return StreamingHttpResponse(
            # 必须传可迭代对象：直接传 bytes 会被逐字节迭代成 int，
            # 前端收到的是一串十进制数字
            iter([_sse({"type": "error", "message": "会话不存在"})]),
            content_type="text/event-stream",
        )

    async def generator() -> AsyncIterator[bytes]:
        # 会话对象在流式阶段重新取：ORM 实例带着数据库连接状态，
        # 跨到 StreamingHttpResponse 的异步迭代阶段可能已失效。
        current = await get_session_record(session_id=session_id, user_id=user_id)
        if current is None:
            yield _sse({"type": "error", "message": "会话不存在"})
            return
        try:
            async for event in stream_chat(
                session=current,
                user_message=payload.message,
                user_id=user_id,
            ):
                yield _sse(event)
        except Exception:
            logger.exception("SSE 生成器异常")
            yield _sse({"type": "error", "message": "流处理异常，请稍后重试"})

    response = StreamingHttpResponse(generator(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


# ─── 任务式（后台）入口 ───


@router.post("/tasks", response=TaskOut)
async def submit_task(request: Any, payload: TaskIn) -> Any:  # pragma: no cover
    """提交一个后台任务：立即返回，agent 在后台跑，跑完通知。

    适合「这个案子帮我把材料梳理一遍」这类要跑几分钟、人不可能一直盯着的活。
    任务式运行没有 SSE 连接，因此高危工具会**挂起等离线审批**（见
    `GET /approvals/pending`），而不是被直接拒绝。
    """
    if not payload.message.strip():
        raise HttpError(400, "任务内容不能为空")
    from ..services.task_runner import submit_task_async

    session = await create_session_record(
        title=payload.title.strip() or payload.message.strip()[:30],
        user_id=_user_id(request),
        origin=AgentSession.Origin.TASK,
        case_id=payload.case_id,
        contract_id=payload.contract_id,
    )
    # 入队并在 service 层回写 task_id（API 层不碰 ORM）
    task_id = await submit_task_async(
        session=session,
        user_message=payload.message,
        user_id=_user_id(request),
    )
    return TaskOut(
        session_id=str(session.session_id),
        task_id=task_id,
        task_state=AgentSession.TaskState.QUEUED,
        title=session.title,
    )


@router.get("/tasks/{session_id}", response=TaskOut)
async def get_task_status(request: Any, session_id: str) -> Any:  # pragma: no cover
    """查询后台任务进度（前端轮询用）。"""
    session = await get_session_record(session_id=session_id, user_id=_user_id(request))
    if session is None:
        raise HttpError(404, "任务不存在")
    return TaskOut(
        session_id=str(session.session_id),
        task_id=session.task_id,
        task_state=session.task_state,
        title=session.title,
    )


# ─── 运行中插话 ───


def _live_session_error(exc: Exception) -> HttpError:
    """把 service 层异常转成前端能理解的 HTTP 错误。"""
    from ..pi.rpc_client import PiError

    if isinstance(exc, PiError):
        # pi 拒绝：通常是本轮已 settle（ran 完），插话无对象
        return HttpError(409, "对话已结束，无法插话")
    return HttpError(409, "会话当前没有运行中的对话")


@router.post("/sessions/{session_id}/steer", response=SteerOut)
async def steer_running_session(  # pragma: no cover
    request: Any,
    session_id: str,
    payload: SteerIn,
) -> Any:
    """运行中插话：在当前 assistant turn 的工具调用之后、下次模型调用之前生效。

    用于「agent 写到一半发现要改方向」，不必停止重发。
    """
    session = await get_session_record(session_id=session_id, user_id=_user_id(request))
    if session is None:
        raise HttpError(404, "会话不存在")
    if not payload.message.strip():
        raise HttpError(400, "插话内容不能为空")
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


# ── 附件（拖拽/选择上传，服务端提取正文，base64 不进模型上下文）────


@router.post("/sessions/{session_id}/attachments", response=AttachmentOut)
async def upload_attachment(request: Any, session_id: str) -> Any:  # pragma: no cover
    """上传一个对话附件（multipart 字段名 ``file``；白名单/20MB 限额见 service）。

    归属：会话必须属于当前用户。上传后前端在消息里附
    「[已上传附件：name (attachment_id=…)]」，模型用 read_agent_attachment 读正文。
    """
    session = await get_session_record(session_id=session_id, user_id=_user_id(request))
    if session is None:
        raise HttpError(404, "会话不存在")
    uploaded = request.FILES.get("file")
    if uploaded is None:
        raise HttpError(400, "缺少 file 字段")
    from asgiref.sync import sync_to_async

    from ..services.attachments import create_attachment as create_attachment_record

    try:
        attachment = await sync_to_async(create_attachment_record, thread_sensitive=True)(
            session=session, user_id=_user_id(request), uploaded_file=uploaded
        )
    except Exception as exc:
        # 校验类异常（超大/白名单外）翻译成可读 4xx，不吐内部细节
        message = str(exc) or "附件保存失败"
        raise HttpError(400, message) from exc
    return AttachmentOut(
        attachment_id=str(attachment.attachment_id),
        filename=attachment.filename,
        size=attachment.size,
        mime=attachment.mime,
    )


@router.get("/attachments/{attachment_id}/content")
async def get_attachment_content(request: Any, attachment_id: str) -> Any:  # pragma: no cover
    """读附件原始内容（base64）——**mcp_server 专用**（用户 token 鉴权）。

    返回内容只用于服务端转投 /document-parsing 提取正文，不会直接进入模型
    上下文；前端不需要也不应消费本端点。
    """
    user = _current_user(request)
    if user is None:
        raise HttpError(401, "未登录")
    from asgiref.sync import sync_to_async

    from ..services.attachments import get_attachment_for_user, read_attachment_content

    attachment = await sync_to_async(get_attachment_for_user, thread_sensitive=True)(
        attachment_id=attachment_id, user_id=_user_id(request)
    )
    if attachment is None:
        # 不区分「不存在」与「不属于你」，避免校验式枚举
        raise HttpError(404, "附件不存在")
    return await sync_to_async(read_attachment_content, thread_sensitive=True)(attachment)


# ─── 审批 ───────────────────────────────────────────────────────────────────


def _internal_token_ok(request: Any) -> bool:
    """extension 回调的服务间鉴权。

    - 配置了 ``FACHUAN_INTERNAL_TOKEN``：常数时间比对（防时序侧信道）。
    - 未配置：**仅 DEBUG 开发态放行**并告警；非 DEBUG 一律拒绝（fail-closed）。
      extension 没有用户会话，这个 token 是该端点唯一的鉴权手段。
    """
    expected = os.environ.get("FACHUAN_INTERNAL_TOKEN", "").strip()
    headers = getattr(request, "headers", None)
    provided = headers.get("X-Internal-Token", "") if headers is not None else ""
    if not expected:
        from django.conf import settings as dj_settings

        if getattr(dj_settings, "DEBUG", False):
            logger.warning("FACHUAN_INTERNAL_TOKEN 未配置，审批回调未鉴权（仅限开发环境）")
            return True
        logger.error("生产环境未配置 FACHUAN_INTERNAL_TOKEN，审批回调已拒绝")
        return False
    return hmac.compare_digest(str(provided).encode(), expected.encode())


@router.post("/approval/request", auth=None, response=PiApprovalOut)
async def pi_approval_request(request: Any, payload: PiApprovalIn) -> Any:  # pragma: no cover
    """pi extension 的工具调用审批闸门（同步阻塞等用户回答）。

    鉴权：``X-Internal-Token`` 头（extension 没有用户会话，不走 JWT）。
    """
    if not _internal_token_ok(request):
        return PiApprovalOut(approved=False, reason="鉴权失败")

    level = classify_risk(payload.tool, payload.args)
    if payload.risk_level and payload.risk_level != level.value:
        # extension 与服务端判定不一致：以服务端为准，但记下来便于排查
        # 「为什么一个该拦的操作没弹窗」。
        logger.warning(
            "审批等级不一致 tool=%s extension=%s server=%s",
            payload.tool,
            payload.risk_level,
            level.value,
        )
    approved, approval_id = await request_approval(
        tool_name=payload.tool,
        tool_args=payload.args or {},
        user_id=payload.user_id or None,
        session_id=payload.session_id or None,
    )
    return PiApprovalOut(
        approved=approved,
        approval_id=approval_id,
        reason="用户同意" if approved else "用户拒绝或超时",
        risk_level=level.value,
    )


@router.post("/approval/{approval_id}/decide")
async def submit_approval_decision(  # pragma: no cover
    request: Any,
    approval_id: str,
    payload: ApprovalDecideIn,
) -> dict[str, Any]:
    """前端提交审批决定（仅会话所有者或超级用户可决定）。"""
    user = _current_user(request)
    record = await get_approval_for_decision(approval_id)

    if record is not None and not _may_decide(user, record):
        return {"success": False, "approved": payload.approved, "error": "无权审批该请求"}

    ok = await decide_approval(approval_id, payload.approved, user_id=_user_id(request))
    return {"success": ok, "approved": payload.approved}


def _may_decide(user: Any, record: AgentApproval) -> bool:
    """审批归属判定：会话所有者或超级用户；无主会话仅超级用户。"""
    if user is not None and getattr(user, "is_superuser", False):
        return True
    owner_id = getattr(record.session, "user_id", None) if record.session is not None else None
    return user is not None and owner_id is not None and int(owner_id) == int(user.pk)


@router.get("/usage", response=UsageOut)
async def get_usage(request: Any, days: int = 30) -> UsageOut:  # pragma: no cover
    """当前用户的成本与耗时汇总（超级用户可加 ``?all=true`` 看全所）。

    口径：token 由 pi 上报，一轮内工具循环的多段 assistant 逐段累加；
    取消与出错的轮次同样计入（那些轮也消耗了 token）。
    """
    user = _current_user(request)
    is_super = user is not None and getattr(user, "is_superuser", False)
    scope_user = None if (is_super and getattr(request, "GET", {}).get("all") == "true") else _user_id(request)
    summary = _to_usage(await _summarize_bg(scope_user, days))
    return summary


@router.get("/usage/daily", response=list[dict[str, Any]])
async def get_usage_daily(request: Any, days: int = 30) -> list[dict[str, Any]]:  # pragma: no cover
    """按天的成本趋势（前端画折线用）。"""
    from asgiref.sync import sync_to_async

    return await sync_to_async(usage_daily_series, thread_sensitive=True)(user_id=_user_id(request), days=days)


@router.get("/usage/by-model", response=list[dict[str, Any]])
async def get_usage_by_model(request: Any, days: int = 30) -> list[dict[str, Any]]:  # pragma: no cover
    """按模型的用量分布。"""
    from asgiref.sync import sync_to_async

    return await sync_to_async(usage_by_model, thread_sensitive=True)(user_id=_user_id(request), days=days)


def _to_usage(summary: UsageSummary) -> UsageOut:
    return UsageOut(
        runs=summary.runs,
        ok_runs=summary.ok_runs,
        error_runs=summary.error_runs,
        cancelled_runs=summary.cancelled_runs,
        input_tokens=summary.input_tokens,
        output_tokens=summary.output_tokens,
        total_tokens=summary.total_tokens,
        tool_calls=summary.tool_calls,
        avg_duration_ms=summary.avg_duration_ms,
        error_rate=summary.error_rate,
    )


async def _summarize_bg(user_id: int | None, days: int) -> UsageSummary:
    from asgiref.sync import sync_to_async

    return await sync_to_async(usage_summarize, thread_sensitive=True)(user_id=user_id, days=days)


@router.get("/approvals/pending", response=list[dict[str, Any]])
async def list_pending_approvals_endpoint(request: Any) -> list[dict[str, Any]]:  # pragma: no cover
    """当前用户**仍待处理**的审批（离线审批入口）。

    任务式后台运行没有 SSE 连接，高危工具会挂起等决定。用户下次打开
    对话页时调这个接口，把待审批卡片摆出来——而不是让那次运行默默超时。
    """
    records = await list_pending_approvals(user_id=_user_id(request))
    return [
        {
            "approval_id": str(a.approval_id),
            "session_id": str(a.session.session_id) if a.session is not None else "",
            "tool_name": a.tool_name,
            "tool_args": a.tool_args or {},
            "risk_level": a.risk_level,
            "created_at": a.created_at.isoformat(),
        }
        for a in records
    ]


@router.get("/approvals", response=list[dict[str, Any]])
async def list_approvals(request: Any, limit: int = 50) -> list[dict[str, Any]]:  # pragma: no cover
    """列出审批记录（审计用；非超级用户仅见自己会话的记录）。"""
    records = await list_approval_records(user=_current_user(request), limit=limit)
    return [
        {
            "approval_id": str(a.approval_id),
            "tool_name": a.tool_name,
            "risk_level": a.risk_level,
            "status": a.status,
            "created_at": a.created_at.isoformat(),
        }
        for a in records
    ]
