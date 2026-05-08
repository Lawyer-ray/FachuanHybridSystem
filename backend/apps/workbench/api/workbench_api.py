"""工作台 API 路由"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any
from uuid import UUID

from asgiref.sync import sync_to_async
from django.http import FileResponse, Http404, StreamingHttpResponse
from ninja import File, Form, Router, Schema
from ninja.files import UploadedFile

from apps.core.security.auth import JWTOrSessionAuth

from ..models import BatchJob, BatchJobItem, WorkbenchMessage, WorkbenchSession
from ..schemas import (
    BatchItemOut,
    BatchJobOut,
    BatchProgressOut,
    MessageIn,
    MessageOut,
    SessionCreateIn,
    SessionOut,
    SessionUpdateIn,
)
from ..services import BatchAnalysisService, WorkbenchChatService

logger = logging.getLogger(__name__)

router = Router(auth=JWTOrSessionAuth())

# 全局服务实例（用于审批回调共享状态）
_chat_service = WorkbenchChatService()


def _get_user_session(user: Any, session_id: int) -> WorkbenchSession:
    """获取用户的会话，不存在或无权限时抛 404"""
    try:
        return WorkbenchSession.objects.get(id=session_id, user=user)
    except WorkbenchSession.DoesNotExist:
        raise Http404("会话不存在")


# ─── 会话 API ────────────────────────────────────────────────────────────────


@router.post("/sessions", response=SessionOut)
def create_session(request: Any, payload: SessionCreateIn) -> WorkbenchSession:
    """创建工作台会话"""
    user = request.user
    session = WorkbenchSession.objects.create(
        user=user if user.is_authenticated else None,
        title=payload.title,
        llm_model=payload.llm_model,
    )
    return session


@router.get("/sessions")
def list_sessions(request: Any, page: int = 1) -> dict[str, Any]:
    """获取当前用户的工作台会话列表"""
    from django.db.models import OuterRef, Subquery, Value
    from django.db.models.functions import Left

    user = request.user
    if user.is_authenticated:
        qs = WorkbenchSession.objects.filter(user=user).order_by("-updated_at")
    else:
        qs = WorkbenchSession.objects.none()

    page_size = 20
    offset = (page - 1) * page_size
    total = qs.count()

    # 获取每个会话的最后一条消息摘要
    last_msg_subquery = (
        WorkbenchMessage.objects.filter(session_id=OuterRef("id"), role="assistant")
        .order_by("-created_at")
        .values("content")[:1]
    )
    items = list(
        qs[offset : offset + page_size].annotate(
            _last_msg=Subquery(last_msg_subquery),
        )
    )

    result = []
    for item in items:
        data = SessionOut.model_validate(item).model_dump()
        raw = getattr(item, "_last_msg", None) or ""
        data["last_message_preview"] = raw[:50] if raw else ""
        result.append(data)

    return {"items": result, "count": total}


@router.get("/sessions/{session_id}", response=SessionOut)
def get_session(request: Any, session_id: int) -> WorkbenchSession:
    """获取会话详情"""
    return _get_user_session(request.user, session_id)


@router.patch("/sessions/{session_id}", response=SessionOut)
def update_session(request: Any, session_id: int, payload: SessionUpdateIn) -> WorkbenchSession:
    """更新会话"""
    session = _get_user_session(request.user, session_id)
    if payload.title is not None:
        session.title = payload.title
    if payload.llm_model is not None:
        session.llm_model = payload.llm_model
    if payload.status is not None:
        session.status = payload.status
    session.save()
    return session


@router.delete("/sessions/{session_id}")
def delete_session(request: Any, session_id: int) -> dict[str, str]:
    """删除会话"""
    session = _get_user_session(request.user, session_id)
    session.delete()
    return {"message": "已删除"}


# ─── 消息 API ────────────────────────────────────────────────────────────────


@router.get("/sessions/{session_id}/messages")
def list_messages(request: Any, session_id: int, page: int = 1) -> dict[str, Any]:
    """获取会话的消息列表"""
    _get_user_session(request.user, session_id)
    qs = WorkbenchMessage.objects.filter(session_id=session_id).order_by("created_at")
    page_size = 50
    offset = (page - 1) * page_size
    total = qs.count()
    items = list(qs[offset : offset + page_size])

    return {
        "items": [MessageOut.model_validate(item).model_dump() for item in items],
        "count": total,
    }


@router.delete("/sessions/{session_id}/messages/from/{message_id}")
def truncate_messages(request: Any, session_id: int, message_id: int) -> dict[str, str]:
    """删除指定消息及其之后的所有消息（用于编辑重发）"""
    _get_user_session(request.user, session_id)
    try:
        msg = WorkbenchMessage.objects.get(id=message_id, session_id=session_id)
    except WorkbenchMessage.DoesNotExist:
        raise Http404("消息不存在")
    WorkbenchMessage.objects.filter(
        session_id=session_id,
        created_at__gte=msg.created_at,
    ).delete()
    return {"message": "已截断"}


class FeedbackIn(Schema):
    """消息反馈请求体"""

    rating: str  # 'good' | 'bad'
    comment: str = ""


@router.patch("/messages/{message_id}/feedback")
def submit_feedback(request: Any, message_id: int, payload: FeedbackIn) -> dict[str, Any]:
    """提交消息反馈（好评/差评）"""
    if payload.rating not in ("good", "bad"):
        return {"success": False, "message": "rating 必须是 good 或 bad"}

    try:
        msg = WorkbenchMessage.objects.get(id=message_id)
    except WorkbenchMessage.DoesNotExist:
        raise Http404("消息不存在")

    # 校验消息属于当前用户的会话
    _get_user_session(request.user, msg.session_id)

    meta = dict(msg.metadata or {})
    meta["feedback"] = {"rating": payload.rating, "comment": payload.comment}
    msg.metadata = meta
    msg.save(update_fields=["metadata"])

    return {"success": True, "message": "反馈已提交"}


# ─── 对话 API（SSE 流式） ────────────────────────────────────────────────────


@router.post("/sessions/{session_id}/messages/stream")
async def stream_chat(request: Any, session_id: int, payload: MessageIn) -> StreamingHttpResponse:
    """SSE 流式对话 - 发送消息并获取 AI 流式响应"""
    try:
        await WorkbenchSession.objects.aget(id=session_id, user=request.user)
    except WorkbenchSession.DoesNotExist:
        raise Http404("会话不存在")

    async def event_generator() -> Any:
        async for event in _chat_service.stream_chat(
            session_id=session_id,
            user_message=payload.content,
            llm_model=payload.llm_model or "",
            agent_type=payload.agent_type or "",
        ):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingHttpResponse(
        event_generator(),
        content_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ─── 审批 API（Phase 2） ─────────────────────────────────────────────────────


class ApprovalIn(Schema):
    """审批请求体"""

    approval_id: str
    approved: bool


@router.post("/approval")
def respond_approval(request: Any, payload: ApprovalIn) -> dict[str, Any]:
    """响应审批请求（Phase 2: Human-in-the-Loop）"""
    user_id = request.user.id if request.user.is_authenticated else None
    success = _chat_service.resolve_approval(payload.approval_id, payload.approved, user_id=user_id)
    return {
        "success": success,
        "message": "审批已处理" if success else "审批 ID 不存在或已过期",
    }


# ─── 批量分析 API ────────────────────────────────────────────────────────────


_batch_service = BatchAnalysisService()


@router.post("/batch/analyze", response=BatchJobOut)
def submit_batch_analysis(
    request: Any,
    session_id: int = Form(...),
    prompt: str = Form(...),
    llm_model: str = Form(""),
    concurrency: int = Form(50),
    files: list[UploadedFile] = File(...),
) -> BatchJob:
    """提交批量文档分析任务

    接受 multipart form 数据：session_id, prompt, llm_model, concurrency, files
    支持 .doc、.docx、.xls、.xlsx 格式。Excel 文件会按行拆分为独立分析任务。
    """
    # 验证会话
    _get_user_session(request.user, session_id)

    # 验证文件
    if not files:
        raise Http404("请上传至少一个文件")

    allowed_extensions = {".doc", ".docx", ".xls", ".xlsx"}
    for f in files:
        ext = f.name.rsplit(".", 1)[-1].lower() if f.name and "." in f.name else ""
        if f".{ext}" not in allowed_extensions:
            raise Http404(f"不支持的文件格式: {f.name}，支持 .doc、.docx、.xls、.xlsx")

    job = _batch_service.create_job(
        session_id=session_id,
        prompt=prompt,
        llm_model=llm_model,
        files=files,
        concurrency=min(max(concurrency, 1), 100),
    )
    return job


@router.get("/batch/{job_id}/progress", response=BatchProgressOut)
def get_batch_progress(request: Any, job_id: UUID) -> dict[str, Any]:
    """查询批量分析任务进度"""
    job, items = _batch_service.get_job_progress(job_id)
    # 验证权限：job 关联的 session 必须属于当前用户
    _get_user_session(request.user, job.session_id)
    failed_detail = _batch_service.get_failed_items_detail(job_id)
    return {
        "job": BatchJobOut.model_validate(job),
        "items": [BatchItemOut.model_validate(item) for item in items],
        "failed_items_detail": failed_detail,
    }


@router.post("/batch/{job_id}/cancel")
def cancel_batch_analysis(request: Any, job_id: UUID) -> dict[str, Any]:
    """取消批量分析任务"""
    job = _batch_service.get_job_progress(job_id)[0]
    _get_user_session(request.user, job.session_id)
    job = _batch_service.request_cancel(job_id)
    return {
        "success": True,
        "status": job.status,
        "message": "取消请求已提交" if job.cancel_requested else "任务已完成或已取消",
    }


@router.get("/batch/{job_id}/download")
def download_batch_summary(request: Any, job_id: UUID) -> FileResponse:
    """下载批量分析汇总 CSV 文件"""
    try:
        job = BatchJob.objects.get(id=job_id)
    except BatchJob.DoesNotExist:
        raise Http404("任务不存在")
    _get_user_session(request.user, job.session_id)

    if not job.summary_file:
        raise Http404("汇总文件不存在")

    return FileResponse(
        job.summary_file.open("rb"),
        as_attachment=True,
        filename=job.summary_file.name.split("/")[-1] if job.summary_file.name else "summary.csv",
        content_type="text/csv; charset=utf-8",
    )


@router.get("/batch/{job_id}/download-detail")
def download_batch_detail_zip(request: Any, job_id: UUID) -> FileResponse:
    """下载批量分析详情 ZIP 文件（每个案例一个 .md 文件）"""
    from ..tasks import build_detail_zip_sync

    try:
        job = BatchJob.objects.get(id=job_id)
    except BatchJob.DoesNotExist:
        raise Http404("任务不存在")
    _get_user_session(request.user, job.session_id)

    if not job.detail_zip_file:
        # 兼容旧任务：按需生成 ZIP
        if not build_detail_zip_sync(job_id):
            raise Http404("分析详情文件不存在")
        job.refresh_from_db()

    return FileResponse(
        job.detail_zip_file.open("rb"),
        as_attachment=True,
        filename=job.detail_zip_file.name.split("/")[-1] if job.detail_zip_file.name else "detail.zip",
        content_type="application/zip",
    )


class BatchMessageItemIn(Schema):
    """批量消息持久化请求体"""

    file_name: str
    content: str
    metadata: dict[str, Any] = {}


@router.post("/batch/{job_id}/messages")
def save_batch_messages(request: Any, job_id: UUID, payload: list[BatchMessageItemIn]) -> dict[str, Any]:
    """将批量分析结果持久化为工作台消息"""
    try:
        job = BatchJob.objects.get(id=job_id)
    except BatchJob.DoesNotExist:
        raise Http404("任务不存在")
    _get_user_session(request.user, job.session_id)

    created = []
    for item in payload:
        msg = WorkbenchMessage.objects.create(
            session_id=job.session_id,
            role="assistant",
            content=item.content,
            metadata={**item.metadata, "job_id": str(job_id)},
        )
        created.append(msg.id)

    return {"success": True, "created_count": len(created)}


# ─── 批量分析增强 API ────────────────────────────────────────────────────────


@router.get("/batch/{job_id}/stream")
async def stream_batch_progress(request: Any, job_id: UUID) -> StreamingHttpResponse:
    """SSE 流式推送批量分析进度

    前端通过此端点实时获取 item 完成事件和进度更新，替代轮询。
    """
    try:
        job = await BatchJob.objects.aget(id=job_id)
    except BatchJob.DoesNotExist:
        raise Http404("任务不存在")
    await sync_to_async(_get_user_session)(request.user, job.session_id)

    async def event_generator() -> Any:
        from django.core.cache import cache

        last_event_idx = 0
        while True:
            events = await sync_to_async(cache.get)(f"batch_sse:{job_id}") or []
            # 发送新事件
            for event in events[last_event_idx:]:
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            last_event_idx = len(events)

            # 检查终态
            status = await sync_to_async(lambda: BatchJob.objects.values_list("status", flat=True).get(id=job_id))()
            if status in ("completed", "failed", "cancelled"):
                yield f"data: {json.dumps({'type': 'done', 'status': status})}\n\n"
                break

            await asyncio.sleep(0.5)

    return StreamingHttpResponse(
        event_generator(),
        content_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/batch/{job_id}/retry")
def retry_failed_items(request: Any, job_id: UUID) -> dict[str, Any]:
    """重试批量分析中失败的文件"""
    job = _batch_service.get_job_progress(job_id)[0]
    _get_user_session(request.user, job.session_id)
    result = _batch_service.retry_failed(job_id)
    return result


@router.get("/sessions/{session_id}/batch-jobs")
def list_batch_jobs(request: Any, session_id: int, page: int = 1) -> dict[str, Any]:
    """获取会话的批量分析任务历史"""
    _get_user_session(request.user, session_id)
    qs = BatchJob.objects.filter(session_id=session_id).order_by("-created_at")
    page_size = 20
    offset = (page - 1) * page_size
    total = qs.count()
    items = list(qs[offset : offset + page_size])
    return {
        "items": [BatchJobOut.model_validate(j).model_dump() for j in items],
        "count": total,
    }


# ─── 模型列表 API ────────────────────────────────────────────────────────────


@router.get("/models")
def list_models(request: Any) -> dict[str, Any]:
    """获取可用的 LLM 模型列表（默认模型取列表第一个）"""
    from apps.core.llm.model_list_service import ModelListService

    service = ModelListService()
    result = service.get_result()

    default_model = result.models[0]["id"] if result.models else ""

    return {
        "models": result.models,
        "default_model": default_model,
        "is_fallback": result.is_fallback,
        "error_message": result.error_message,
    }
