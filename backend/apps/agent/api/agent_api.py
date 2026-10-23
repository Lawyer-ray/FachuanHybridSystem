"""Agent API —— 会话管理与对话入口。

端点前缀：``/api/v1/agent``

- 会话：创建 / 列表 / 详情 / 消息历史 / 删除
- 对话：SSE 流式（事件契约见 services/chat_service.py）
- 审批：extension 回调入口 + 前端决定入口
"""

from __future__ import annotations

import base64
import hmac
import json
import logging
import os
import re
from collections.abc import AsyncIterator
from typing import Any, Literal

from asgiref.sync import sync_to_async
from django.http import StreamingHttpResponse
from ninja import Router, Schema
from ninja.errors import HttpError

from apps.core.exceptions import NotFoundError, ValidationException
from apps.core.infrastructure.throttling import get_rate_limit_config, rate_limit
from apps.core.security import get_request_access_context
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
from ..services.folder_refs import create_folder_ref, read_folder_file_content, render_folder_file_pages
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

#: 分页渲染的编排门面在 services/attachments.py（读物理文件 → 按 mime 分流 → 渲染 → 审计）。
#: 模块缺席时不让整个 agent 路由导入失败（那会让所有对话端点 500），而是仅在
#: /pages 端点调用时返回 503，测试据 IMPORT_ERROR 跳过。
try:
    from ..services.attachments import render_attachment_pages
except ImportError as _render_import_error:  # pragma: no cover —— 依赖落盘后不再触发
    render_attachment_pages = None  # type: ignore[assignment]
    _RENDER_IMPORT_ERROR: str = str(_render_import_error)
else:
    _RENDER_IMPORT_ERROR = ""

logger = logging.getLogger(__name__)

router = Router(tags=["Agent"], auth=JWTOrSessionAuth())

#: 发消息限流（P1-8a）：每用户 20 次/分钟；RATE_LIMIT['AGENT_SEND_*'] 可覆盖
_AGENT_SEND_RATE_LIMIT = get_rate_limit_config("AGENT_SEND", fallback_requests=20, fallback_window=60)


def _send_rate_key(request: Any) -> str:
    """限流键按用户（JWT 的 auth 或 session 的 user），匿名回退 IP 由基类兜底。"""
    user = getattr(request, "auth", None) or getattr(request, "user", None)
    pk = getattr(user, "pk", None)
    return f"agent_send:user:{pk if pk is not None else 'anon'}"


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
    #: 业务范围名（案件名 / 委托人客户名），由列表接口批量注水，
    #: 供前端按业务分组展示；通用与任务会话为空串。
    scope_name: str = ""
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
    #: 拒绝理由（可空）：回传给模型，引导换更安全的路径而不是干巴巴的「用户拒绝」
    reason: str = ""


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
    #: 本月累计 token（预算口径）
    month_tokens: int = 0
    #: 月度预算（FACHUAN_AGENT_MONTHLY_TOKEN_BUDGET，0=未配置）
    budget_tokens: int = 0
    #: 已用超预算 80% 时为真（前端黄条提醒）
    budget_warn: bool = False


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
    """附件上传回执：消息里以 [已上传附件：name (attachment_id=…)] 引用。

    引用型（拖拽绑定文件夹文件）带 ``ref_owner_kind`` / ``ref_contract_id``（归属 id，合同或案件）/ ``ref_subpath``，
    上传型两者为空——前端据此渲染不同 chip。
    """

    attachment_id: str
    filename: str
    size: int
    mime: str = ""
    ref_owner_kind: str = "contract"
    ref_contract_id: int | None = None
    ref_subpath: str = ""


class FolderRefIn(Schema):
    """拖拽引用入参：指向合同/案件绑定文件夹内的一个文件（不复制字节）。"""

    kind: Literal["contract", "case"] = "contract"
    owner_id: int
    subpath: str


class AttachmentPageOut(Schema):
    """附件的一页渲染图（base64）。

    ``has_text_layer`` 是「这页可选出文字」的事实陈述：扫描件为 false，
    调用方据此决定是否走 OCR，而不是把空白渲染当成功文本。

    文字层页（``has_text_layer=true``）**不渲染图**：``b64`` 为空、``bytes=0``，
    调用方应改走文本通道（省视觉 token）。``error`` 是该页粒度的错误码
    （如 encrypted / too_large），成功为空；``detail`` 是可读原因。
    """

    page: int
    mime: str
    b64: str
    bytes: int
    width: int
    height: int
    has_text_layer: bool
    text: str = ""
    error: str = ""
    detail: str = ""


class AttachmentPagesOut(Schema):
    """附件分页渲染结果（MCP 取页面图给模型看）。字段名与 T1 的 RenderResult 一一对应。

    失败时 ``pages_returned`` 为空、``error`` 给出错误码——**不用空图冒充
    成功**：一页空 base64 会让模型以为「这页是空白」而不是「渲染失败」。
    """

    attachment_id: str
    filename: str = ""
    mime: str = ""
    total_pages: int = 0
    pages_returned: list[AttachmentPageOut] = []
    #: text / image / mixed
    strategy: str = ""
    #: not_found / forbidden / parse_empty / encrypted / unsupported_mime /
    #: too_large / page_out_of_range 之一；空串表示成功
    error: str = ""
    #: 与 error 配套的可读原因（MCP 侧直接转给模型看）
    detail: str = ""
    notices: list[str] = []
    #: 请求的页数超过 max_pages 被截断时为 true（与 notices 同时给出）
    truncated_pages: bool = False


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
        # annotate_scope_names 透传属性；未注水的单会话端点 getattr 兜底空串
        scope_name=getattr(session, "scope_name", "") or "",
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
async def list_messages(
    request: Any, session_id: str, limit: int = 200, before_id: int | None = None
) -> list[MessageOut]:  # pragma: no cover
    """会话消息历史（旧→新），前端重开会话时据此回放转录。

    ``before_id``：游标分页——取该消息 id 之前的 ``limit`` 条（加载更早），
    不传为最新一页。返回条数等于 limit 时大概率还有更早消息，由前端
    用最后一条的 message_id 作为下一页游标。
    """
    messages = await list_message_records(
        session_id=session_id, user_id=_user_id(request), limit=limit, before_id=before_id
    )
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
    seq = payload.pop("_seq", None)
    id_line = f"id: {seq}\n" if seq else ""
    return f"{id_line}data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode()


@router.get("/sessions/{session_id}/events/replay")
async def replay_sse_events(
    request: Any, session_id: str, last_event_id: int = 0
) -> list[dict[str, Any]]:  # pragma: no cover
    """P2-1 SSE 断线重连：回放 last_event_id 之后的事件。

    前端断线重连时先调此端点取缺失事件再续 SSE。Redis 不可用返回空。
    """
    from ..services.event_bus import replay_events

    return replay_events(session_id, last_event_id)


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


@router.delete("/tasks/{session_id}")
async def cancel_task(request: Any, session_id: str) -> dict[str, Any]:  # pragma: no cover
    """取消后台任务（P1-4）。

    排队中：从 django-q 队列移除并置 cancelled；
    运行中：诚实告知暂不支持中途终止（pi 子进程在 worker 内，无跨进程
    abort 通道——见差距报告 P2），任务会跑到自然结束；
    已结束：如实返回终态。
    """
    session = await get_session_record(session_id=session_id, user_id=_user_id(request))
    if session is None:
        raise HttpError(404, "任务不存在")
    if session.origin != AgentSession.Origin.TASK or not session.task_id:
        raise HttpError(400, "该会话不是后台任务")
    if session.task_state not in (AgentSession.TaskState.QUEUED, AgentSession.TaskState.RUNNING):
        return {"success": False, "task_state": session.task_state, "message": "任务已结束，无需取消"}

    from ..services.task_runner import cancel_agent_task

    result = await sync_to_async(cancel_agent_task, thread_sensitive=True)(session)
    if not result["success"]:
        raise HttpError(409, result["message"])
    return result


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

    P2-3 跨 Worker：Redis 路由表发现会话在其他 worker → HTTP 转发。
    用于「agent 写到一半发现要改方向」，不必停止重发。
    """
    session = await get_session_record(session_id=session_id, user_id=_user_id(request))
    if session is None:
        raise HttpError(404, "会话不存在")
    if not payload.message.strip():
        raise HttpError(400, "插话内容不能为空")

    # P2-3：跨 worker 转发（Redis 路由表发现目标 worker）
    from ..services.live_sessions import get_live_worker

    target = get_live_worker(session_id)
    if target:
        import httpx

        internal_token = os.environ.get("FACHUAN_INTERNAL_TOKEN", "")
        try:
            async with httpx.AsyncClient(timeout=5.0) as http:
                resp = await http.post(
                    f"http://{target}/api/v1/agent/sessions/{session_id}/steer",
                    json={"message": payload.message},
                    headers={"X-Internal-Token": internal_token} if internal_token else {},
                )
                if resp.status_code == 200:
                    return SteerOut(**resp.json())
        except httpx.HTTPError:
            logger.warning("跨 worker steer 转发失败（%s），回退本 worker", target)

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
async def upload_attachment(request: Any, session_id: str) -> Any:
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
    try:
        attachment = await sync_to_async(create_attachment, thread_sensitive=True)(
            session=session, user_id=_user_id(request), uploaded_file=uploaded
        )
    except ValidationException as exc:
        # 只翻译校验类异常（超大/白名单外）为可读 4xx；
        # 其余异常如实走全局 5xx，不吞不降级
        raise HttpError(400, str(exc) or "附件保存失败") from exc
    return AttachmentOut(
        attachment_id=str(attachment.attachment_id),
        filename=attachment.filename,
        size=attachment.size,
        mime=attachment.mime,
    )


@router.get("/attachments/{attachment_id}/content")
async def get_attachment_content(request: Any, attachment_id: str) -> Any:
    """读附件原始内容（base64）——**mcp_server 专用**（用户 token 鉴权）。

    返回内容只用于服务端转投 /document-parsing 提取正文，不会直接进入模型
    上下文；前端不需要也不应消费本端点。
    """
    user = _current_user(request)
    if user is None:
        raise HttpError(401, "未登录")
    attachment = await sync_to_async(get_attachment_for_user, thread_sensitive=True)(
        attachment_id=attachment_id, user_id=_user_id(request)
    )
    if attachment is None:
        # 不区分「不存在」与「不属于你」，避免校验式枚举
        raise HttpError(404, "附件不存在")
    return await sync_to_async(read_attachment_content, thread_sensitive=True)(attachment)


#: 页面图 dpi 钳制区间：低于 72 字迹糊成色块，高于 300 单页就几十 MB base64
_PAGES_DPI_MIN = 72
_PAGES_DPI_MAX = 300
_PAGES_DPI_DEFAULT = 150
#: 单次最多取几页（上限即默认值）：一张页面图进模型上下文要几百到上千 token，
#: 放开会让一次调用吃满上下文
_PAGES_MAX_PAGES = 10
#: 单个页范围 token：``3`` 或 ``1-3``（与 T1 parse_pages 的接受面一致）
_PAGES_TOKEN_RE = re.compile(r"^\d+(-\d+)?$")


def _reject_unsyntactic_pages(spec: str) -> None:
    """只挡「不是合法页范围语法」的入参（越界不在这里判，交给渲染门面）。

    允许的形态与 T1 ``parse_pages`` 对齐：``all`` / ``3`` / ``1-3`` / ``1,3,5``。
    """
    raw = (spec or "").strip().lower()
    if raw == "all":
        return
    tokens = [piece.strip() for piece in raw.replace("，", ",").split(",")]
    tokens = [piece for piece in tokens if piece]
    if not tokens or not all(_PAGES_TOKEN_RE.match(piece) for piece in tokens):
        raise HttpError(400, f"pages 不合法：{spec!r}（示例：1-3 / 7 / all）")


def _parse_max_pages(raw: str) -> int:
    """``max_pages`` 钳到 [1, 10]；非数字直接 400（不静默当成默认值）。

    静默回落会让调用方以为「要了 20 页却只给了 10 页是文档问题」——实际是
    参数写错。这里宁可报错。
    """
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise HttpError(400, f"max_pages 须为整数，收到：{raw!r}") from exc
    return max(1, min(value, _PAGES_MAX_PAGES))


def _parse_dpi(raw: str) -> int:
    """``dpi`` 钳到 [72, 300]；非数字 400。

    越界只钳不报错：调用方要的是能看的图，把 600 压到 300 比报错更有用。
    """
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise HttpError(400, f"dpi 须为整数，收到：{raw!r}") from exc
    return max(_PAGES_DPI_MIN, min(value, _PAGES_DPI_MAX))


@router.get("/attachments/{attachment_id}/pages", response=AttachmentPagesOut)
async def get_attachment_pages(
    request: Any,
    attachment_id: str,
    pages: str = "all",
    dpi: str = str(_PAGES_DPI_DEFAULT),
    #: 对外查询参数名（MCP 侧已按 format 写死）；函数内立刻重命名为 fmt，
    #: 避免与内置 format() 混淆
    format: str = "png",
    max_pages: str = str(_PAGES_MAX_PAGES),
) -> AttachmentPagesOut:
    """把附件按页渲染成图片（base64）——**mcp_server 专用**（用户 token 鉴权）。

    PDF 走 PyMuPDF 逐页渲染：扫描件的文本提取为空，但页面图里是真实内容，
    模型看图仍能读——这是「解析为空」的附件需要的另一条腿。

    三段状态严格分开，不让调用方猜：

    - 参数非法（pages 语法错 / dpi 非数字 / format 不认识）→ 400
    - 归属不符或不存在 → 404（不区分，防枚举 attachment_id）
    - 渲染失败（encrypted / too_large / unsupported_mime / page_out_of_range /
      parse_empty）→ **200 + error 错误码**：mcp_server 要把错误码翻译成模型
      看得懂的原因，500 会让它只剩「服务端错误」

    权限与 /content 端点同一口径：``get_attachment_for_user``（只认会话所有者，
    超管同样 fail-closed），这里不放宽也不跳过。
    """
    user = _current_user(request)
    if user is None:
        raise HttpError(401, "未登录")
    attachment = await sync_to_async(get_attachment_for_user, thread_sensitive=True)(
        attachment_id=attachment_id, user_id=_user_id(request)
    )
    if attachment is None:
        # 与 /content 同文案：不区分「不存在」与「不属于你」，避免校验式枚举
        raise HttpError(404, "附件不存在")
    if render_attachment_pages is None:  # pragma: no cover —— T1 落盘后不再触发
        # 依赖缺席时报 503 而不是把「渲染器不存在」包装成 unsupported_mime：
        # 后者会让调用方以为文件格式不支持，去换文件而非查部署
        logger.error("分页渲染依赖缺失：%s", _RENDER_IMPORT_ERROR)
        raise HttpError(503, f"分页渲染服务未就绪：{_RENDER_IMPORT_ERROR}")

    requested_format = format
    fmt = (requested_format or "png").strip().lower()
    if fmt == "jpg":
        fmt = "jpeg"
    if fmt not in ("png", "jpeg"):
        raise HttpError(400, f"format 仅支持 png / jpeg，收到：{requested_format!r}")
    requested_dpi = _parse_dpi(dpi)
    requested_max = _parse_max_pages(max_pages)
    pages_spec = (pages or "").strip()
    if not pages_spec:
        raise HttpError(400, "pages 不能为空（示例：1-3 / 7 / all）")
    # 语法错误在进渲染前就挡成 400：门面把 ValueError（语法错与越界）统一折成
    # page_out_of_range 的 200 响应，调用方会误以为「页码写对了但文档没这些页」，
    # 实际是参数本身不合语法——这两种情况的下一步动作完全不同。
    # ；越界仍交给门面返回 page_out_of_range（需要真实页数才知道）；
    _reject_unsyntactic_pages(pages_spec)

    outcome = await sync_to_async(render_attachment_pages, thread_sensitive=True)(
        attachment,
        pages=pages_spec,
        dpi=requested_dpi,
        format=fmt,
        max_pages=requested_max,
        user_id=_user_id(request),
    )
    payload = AttachmentPagesOut(
        attachment_id=outcome.attachment_id,
        filename=outcome.filename,
        mime=outcome.mime,
        total_pages=outcome.total_pages,
        pages_returned=[_to_page_out(page) for page in outcome.pages],
        strategy=_summarize_strategy(outcome.pages),
        error=_error_code(outcome.error),
        detail=outcome.detail,
        notices=_build_notices(outcome, requested_max=requested_max),
        truncated_pages=outcome.truncated_pages > 0,
    )
    # 审计由 T1 的 log_render 在门面内完成（who/attachment_id/pages/strategy/bytes）；
    # 这里再记一条端点级日志，带上请求参数原文——排查「为什么只给了 2 页」要看
    # 调用方当时到底要了什么，而门面只看到解析后的页码。
    logger.info(
        "附件分页端点 user=%s attachment_id=%s pages=%r dpi=%d format=%s returned=%d error=%s",
        _user_id(request),
        payload.attachment_id,
        pages_spec,
        requested_dpi,
        fmt,
        len(payload.pages_returned),
        payload.error or "-",
    )
    return payload


@router.post("/sessions/{session_id}/folder-refs", response=AttachmentOut)
async def create_session_folder_ref(request: Any, session_id: str, data: FolderRefIn) -> Any:
    """拖拽引用落库：引用合同绑定文件夹内的原文件（不复制字节、storage_path 留空）。

    归属：会话必须属于当前用户；合同侧走行级 ACL（与 folder-entries 目录树
    同口径——团队共享合同，协办律师同样可引用）。文件名/MIME/大小为创建时快照。
    """
    session = await get_session_record(session_id=session_id, user_id=_user_id(request))
    if session is None:
        raise HttpError(404, "会话不存在")
    ctx = get_request_access_context(request)
    try:
        ref = await sync_to_async(create_folder_ref, thread_sensitive=True)(
            session=session,
            user_id=_user_id(request),
            user=ctx.user,
            org_access=ctx.org_access,
            perm_open_access=ctx.perm_open_access,
            owner_kind=data.kind,
            owner_id=data.owner_id,
            subpath=data.subpath,
        )
    except NotFoundError as exc:
        # 无权/未绑定/云存储绑定/文件不存在 → 同一 404 文案（不区分，防枚举探测）
        raise HttpError(404, str(exc) or "文件不存在") from exc
    except ValidationException as exc:
        raise HttpError(400, str(exc) or "subpath 非法") from exc
    return AttachmentOut(
        attachment_id=str(ref.attachment_id),
        filename=ref.filename,
        size=ref.size,
        mime=ref.mime,
        ref_owner_kind=ref.ref_owner_kind,
        ref_contract_id=ref.ref_contract_id,
        ref_subpath=ref.ref_subpath,
    )


@router.get("/folder-refs/content")
async def get_folder_ref_content(request: Any, kind: str = "contract", owner_id: int = 0, subpath: str = "") -> Any:
    """读绑定文件夹内原文件（base64）——**mcp_server 专用**（用户 token 鉴权）。

    与 /attachments/{id}/content 同构：内容只用于服务端转投 /document-parsing
    提取正文，不直接进模型上下文。权限与 folder-entries 同口径（行级 ACL）；
    kind=contract/case 决定走合同还是案件的绑定文件夹。
    """
    user = _current_user(request)
    if user is None:
        raise HttpError(401, "未登录")
    if kind not in ("contract", "case") or owner_id <= 0:
        raise HttpError(400, "kind 仅支持 contract/case 且 owner_id 必须为正整数")
    ctx = get_request_access_context(request)
    try:
        return await sync_to_async(read_folder_file_content, thread_sensitive=True)(
            owner_kind=kind,
            owner_id=owner_id,
            subpath=subpath,
            user=ctx.user,
            org_access=ctx.org_access,
            perm_open_access=ctx.perm_open_access,
        )
    except NotFoundError as exc:
        raise HttpError(404, str(exc) or "文件不存在（可能已被移动或移入删除区）") from exc
    except ValidationException as exc:
        raise HttpError(400, str(exc) or "subpath 非法") from exc


@router.get("/folder-refs/pages", response=AttachmentPagesOut)
async def get_folder_ref_pages(
    request: Any,
    kind: str = "contract",
    owner_id: int = 0,
    subpath: str = "",
    pages: str = "all",
    dpi: str = str(_PAGES_DPI_DEFAULT),
    format: str = "png",
    max_pages: str = str(_PAGES_MAX_PAGES),
) -> AttachmentPagesOut:
    """把绑定文件夹内文件按页渲染成图（base64）——**mcp_server 专用**。

    与 /attachments/{id}/pages 同构（三段状态：参数非法 400 / 无权或不存在
    404 / 渲染失败 200 + error 错误码）；页图缓存键含源文件 size/mtime 指纹，
    文件被替换后旧缓存自动失效。
    """
    user = _current_user(request)
    if user is None:
        raise HttpError(401, "未登录")
    if kind not in ("contract", "case") or owner_id <= 0:
        raise HttpError(400, "kind 仅支持 contract/case 且 owner_id 必须为正整数")
    requested_format = format
    fmt = (requested_format or "png").strip().lower()
    if fmt == "jpg":
        fmt = "jpeg"
    if fmt not in ("png", "jpeg"):
        raise HttpError(400, f"format 仅支持 png / jpeg，收到：{requested_format!r}")
    requested_dpi = _parse_dpi(dpi)
    requested_max = _parse_max_pages(max_pages)
    pages_spec = (pages or "").strip()
    if not pages_spec:
        raise HttpError(400, "pages 不能为空（示例：1-3 / 7 / all）")
    _reject_unsyntactic_pages(pages_spec)

    ctx = get_request_access_context(request)
    try:
        outcome = await sync_to_async(render_folder_file_pages, thread_sensitive=True)(
            owner_kind=kind,
            owner_id=owner_id,
            subpath=subpath,
            user=ctx.user,
            org_access=ctx.org_access,
            perm_open_access=ctx.perm_open_access,
            pages=pages_spec,
            dpi=requested_dpi,
            fmt=fmt,
            max_pages=requested_max,
            user_id=_user_id(request),
        )
    except NotFoundError as exc:
        raise HttpError(404, str(exc) or "文件不存在（可能已被移动或移入删除区）") from exc
    except ValidationException as exc:
        raise HttpError(400, str(exc) or "subpath 非法") from exc
    payload = AttachmentPagesOut(
        attachment_id=outcome.attachment_id,
        filename=outcome.filename,
        mime=outcome.mime,
        total_pages=outcome.total_pages,
        pages_returned=[_to_page_out(page) for page in outcome.pages],
        strategy=_summarize_strategy(outcome.pages),
        error=_error_code(outcome.error),
        detail=outcome.detail,
        notices=_build_notices(outcome, requested_max=requested_max),
        truncated_pages=outcome.truncated_pages > 0,
    )
    logger.info(
        "folder_refs_pages user=%s kind=%s owner_id=%s subpath=%r pages=%r dpi=%d format=%s returned=%d error=%s",
        _user_id(request),
        kind,
        owner_id,
        subpath,
        pages_spec,
        requested_dpi,
        fmt,
        len(payload.pages_returned),
        payload.error or "-",
    )
    return payload


def _to_page_out(page: Any) -> AttachmentPageOut:
    """T1 的 RenderedPage → 对外页图 schema（字段名翻译集中在这里，别散落到调用点）。

    ``has_text_layer`` 在 T1 里没有独立字段：它的判定口径就是「文字层够长，
    走文本策略」，所以 ``strategy is TEXT`` 或 ``text`` 非空即视为有文字层。
    """
    strategy_is_text = _strategy_value(page.strategy) == "text"
    image_bytes = page.image_bytes or b""
    return AttachmentPageOut(
        page=int(page.page_no),
        mime=str(page.mime or ""),
        # 二进制 → base64 只在这一处做；空字节绝不编码成「看起来正常」的空串
        b64=base64.b64encode(image_bytes).decode("ascii") if image_bytes else "",
        bytes=len(image_bytes),
        width=int(page.width),
        height=int(page.height),
        has_text_layer=strategy_is_text or bool((page.text or "").strip()),
        # 文字层页不出图（b64 为空），但**必须把文字带出去**：
        # 否则调用方只知道「这页有文字」却拿不到文字——解析服务一旦转异步
        # 就会卡成「有字但读不到」，实测踩到过（扫描件/正常 PDF 都会中）。
        text=str(page.text or "") if strategy_is_text or (page.text or "").strip() else "",
        error=_error_code(page.error),
        detail=str(page.detail or ""),
    )


def _strategy_value(strategy: Any) -> str:
    """``RenderStrategy`` → 字符串值（``StrEnum`` 的 value；普通字符串原样返回）。"""
    value = getattr(strategy, "value", strategy)
    return str(value)


def _summarize_strategy(pages: list[Any]) -> str:
    """整次结果的形态汇总：全 text / 全 image / mixed（MCP 据此决定要不要走视觉通道）。"""
    kinds = {_strategy_value(page.strategy) for page in pages}
    if not kinds:
        return ""
    if kinds <= {"text"}:
        return "text"
    if kinds <= {"page_image", "source_image"}:
        return "image"
    return "mixed"


def _error_code(error: Any) -> str:
    """RenderError（StrEnum）→ 错误码字符串；成功时为 ""。"""
    if error is None:
        return ""
    return str(getattr(error, "value", error))


def _build_notices(outcome: Any, *, requested_max: int) -> list[str]:
    """把「被截断 / 整份失败」这类必须让调用方知道的事写进 notices。

    截断一定要说：静默少给页会让模型把「后面那些页不存在」当成文档事实。
    """
    notices: list[str] = []
    if outcome.truncated_pages > 0:
        notices.append(
            f"超过 max_pages={requested_max} 限制，还有 {outcome.truncated_pages} 页未渲染（可用 pages 参数分段取）"
        )
    if outcome.error is not None and outcome.detail:
        notices.append(f"{_error_code(outcome.error)}：{outcome.detail}")
    return notices


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
    approved, approval_id, reason_out = await request_approval(
        tool_name=payload.tool,
        tool_args=payload.args or {},
        user_id=payload.user_id or None,
        session_id=payload.session_id or None,
    )
    return PiApprovalOut(
        approved=approved,
        approval_id=approval_id,
        # 拒绝时带用户填写的理由（无则兜底文案）——模型据此换路径
        reason=reason_out,
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

    ok = await decide_approval(approval_id, payload.approved, user_id=_user_id(request), reason=payload.reason)
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
        month_tokens=summary.month_tokens,
        budget_tokens=summary.budget_tokens,
        budget_warn=summary.budget_warn,
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
    from ..services.approval import _waiter_is_alive

    return [
        {
            "approval_id": str(a.approval_id),
            "session_id": str(a.session.session_id) if a.session is not None else "",
            "tool_name": a.tool_name,
            "tool_args": a.tool_args or {},
            "risk_level": a.risk_level,
            "created_at": a.created_at.isoformat(),
            # P2-4：等待进程已死（心跳键过期）——前端可提示「该审批可能已失效」
            "waiter_dead": not _waiter_is_alive(str(a.approval_id)),
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
