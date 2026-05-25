"""工作台 API 路由"""

from __future__ import annotations

import asyncio
import io
import json
import logging
from typing import Any, Literal
from uuid import UUID

from asgiref.sync import sync_to_async
from django.http import FileResponse, StreamingHttpResponse
from ninja import File, Form, Router, Schema
from ninja.files import UploadedFile

from apps.core.dto.request_context import extract_request_context
from apps.core.infrastructure.service_locator import ServiceLocator
from apps.core.security.auth import JWTOrSessionAuth

from ..models import BatchJobItem, BatchJobStatus
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

logger = logging.getLogger(__name__)

router = Router(auth=JWTOrSessionAuth())


# ─── 会话 API ────────────────────────────────────────────────────────────────


@router.post("/sessions", response=SessionOut)
def create_session(request: Any, payload: SessionCreateIn) -> Any:
    """创建工作台会话"""
    ctx = extract_request_context(request)
    service = ServiceLocator.get_workbench_session_service()
    return service.create_session(
        title=payload.title,
        llm_model=payload.llm_model,
        user=ctx.user,
        org_access=ctx.org_access,
        perm_open_access=ctx.perm_open_access,
    )


@router.get("/sessions")
def list_sessions(request: Any, page: int = 1) -> dict[str, Any]:
    """获取当前用户的工作台会话列表"""
    ctx = extract_request_context(request)
    service = ServiceLocator.get_workbench_session_service()
    return service.list_sessions(  # type: ignore[no-any-return]
        page=page,
        user=ctx.user,
        org_access=ctx.org_access,
        perm_open_access=ctx.perm_open_access,
    )


@router.get("/sessions/{session_id}", response=SessionOut)
def get_session(request: Any, session_id: int) -> Any:
    """获取会话详情"""
    ctx = extract_request_context(request)
    service = ServiceLocator.get_workbench_session_service()
    return service.get_session(
        session_id,
        user=ctx.user,
        org_access=ctx.org_access,
        perm_open_access=ctx.perm_open_access,
    )


@router.patch("/sessions/{session_id}", response=SessionOut)
def update_session(request: Any, session_id: int, payload: SessionUpdateIn) -> Any:
    """更新会话"""
    ctx = extract_request_context(request)
    service = ServiceLocator.get_workbench_session_service()
    return service.update_session(
        session_id,
        title=payload.title,
        llm_model=payload.llm_model,
        status=payload.status,
        user=ctx.user,
        org_access=ctx.org_access,
        perm_open_access=ctx.perm_open_access,
    )


@router.delete("/sessions/{session_id}")
def delete_session(request: Any, session_id: int) -> dict[str, str]:
    """删除会话"""
    ctx = extract_request_context(request)
    service = ServiceLocator.get_workbench_session_service()
    service.delete_session(
        session_id,
        user=ctx.user,
        org_access=ctx.org_access,
        perm_open_access=ctx.perm_open_access,
    )
    return {"message": "已删除"}


# ─── 消息 API ────────────────────────────────────────────────────────────────


@router.get("/sessions/{session_id}/messages")
def list_messages(
    request: Any,
    session_id: int,
    page: int = 1,
    before_id: int | None = None,
) -> dict[str, Any]:
    """获取会话的消息列表"""
    ctx = extract_request_context(request)
    service = ServiceLocator.get_workbench_message_service()
    return service.list_messages(  # type: ignore[no-any-return]
        session_id,
        page=page,
        before_id=before_id,
        user=ctx.user,
        org_access=ctx.org_access,
        perm_open_access=ctx.perm_open_access,
    )


@router.delete("/sessions/{session_id}/messages/from/{message_id}")
def truncate_messages(request: Any, session_id: int, message_id: int) -> dict[str, str]:
    """删除指定消息及其之后的所有消息（用于编辑重发）"""
    ctx = extract_request_context(request)
    service = ServiceLocator.get_workbench_message_service()
    service.truncate_messages(
        session_id,
        message_id,
        user=ctx.user,
        org_access=ctx.org_access,
        perm_open_access=ctx.perm_open_access,
    )
    return {"message": "已截断"}


class FeedbackIn(Schema):
    """消息反馈请求体"""

    rating: Literal["good", "bad"]
    comment: str = ""


@router.patch("/messages/{message_id}/feedback")
def submit_feedback(request: Any, message_id: int, payload: FeedbackIn) -> dict[str, Any]:
    """提交消息反馈（好评/差评）"""
    ctx = extract_request_context(request)
    service = ServiceLocator.get_workbench_message_service()
    service.submit_feedback(
        message_id,
        rating=payload.rating,
        comment=payload.comment,
        user=ctx.user,
        org_access=ctx.org_access,
        perm_open_access=ctx.perm_open_access,
    )
    return {"success": True, "message": "反馈已提交"}


# ─── 对话 API（SSE 流式） ────────────────────────────────────────────────────


@router.post("/sessions/{session_id}/messages/stream")
async def stream_chat(request: Any, session_id: int, payload: MessageIn) -> StreamingHttpResponse:
    """SSE 流式对话 - 发送消息并获取 AI 流式响应"""
    ctx = extract_request_context(request)
    session_service = ServiceLocator.get_workbench_session_service()
    await sync_to_async(session_service.get_user_session)(ctx.user, session_id)

    chat_service = ServiceLocator.get_workbench_chat_service()

    async def event_generator() -> Any:
        async for event in chat_service.stream_chat(
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


# ─── 审批 API ────────────────────────────────────────────────────────────────


class ApprovalIn(Schema):
    """审批请求体"""

    approval_id: str
    approved: bool


@router.post("/approval")
def respond_approval(request: Any, payload: ApprovalIn) -> dict[str, Any]:
    """响应审批请求（Human-in-the-Loop）"""
    ctx = extract_request_context(request)
    chat_service = ServiceLocator.get_workbench_chat_service()
    user_id = ctx.user.id if ctx.user and getattr(ctx.user, "is_authenticated", False) else None
    success = chat_service.resolve_approval(payload.approval_id, payload.approved, user_id=user_id)
    return {
        "success": success,
        "message": "审批已处理" if success else "审批 ID 不存在或已过期",
    }


# ─── 批量分析 API ────────────────────────────────────────────────────────────


@router.post("/batch/analyze", response=BatchJobOut)
def submit_batch_analysis(
    request: Any,
    session_id: int = Form(...),
    prompt: str = Form(...),
    llm_model: str = Form(""),
    concurrency: int = Form(50),
    files: list[UploadedFile] = File(...),
) -> Any:
    """提交批量文档分析任务"""
    ctx = extract_request_context(request)
    session_service = ServiceLocator.get_workbench_session_service()
    session_service.get_user_session(ctx.user, session_id)

    batch_service = ServiceLocator.get_workbench_batch_service()
    batch_service.validate_files(files)

    job = batch_service.create_job(
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
    ctx = extract_request_context(request)
    batch_service = ServiceLocator.get_workbench_batch_service()
    session_service = ServiceLocator.get_workbench_session_service()

    job, items = batch_service.get_job_progress(job_id)
    session_service.get_user_session(ctx.user, job.session_id)

    failed_detail = [
        {"id": str(item.id), "file_name": item.file_name, "error": item.error}
        for item in items
        if item.status == BatchJobStatus.FAILED
    ]
    return {
        "job": BatchJobOut.model_validate(job),
        "items": [BatchItemOut.model_validate(item) for item in items],
        "failed_items_detail": failed_detail,
    }


@router.post("/batch/{job_id}/cancel")
def cancel_batch_analysis(request: Any, job_id: UUID) -> dict[str, Any]:
    """取消批量分析任务"""
    ctx = extract_request_context(request)
    batch_service = ServiceLocator.get_workbench_batch_service()
    session_service = ServiceLocator.get_workbench_session_service()

    job, _ = batch_service.get_job_progress(job_id)
    session_service.get_user_session(ctx.user, job.session_id)

    job = batch_service.request_cancel(job_id)
    return {
        "success": True,
        "status": job.status,
        "message": "取消请求已提交" if job.cancel_requested else "任务已完成或已取消",
    }


@router.get("/batch/{job_id}/download")
def download_batch_summary(request: Any, job_id: UUID, relevant_only: bool = False) -> FileResponse:
    """下载批量分析汇总 CSV 文件"""
    from ..tasks.parsing import parse_llm_result

    ctx = extract_request_context(request)
    batch_service = ServiceLocator.get_workbench_batch_service()
    session_service = ServiceLocator.get_workbench_session_service()

    job = batch_service.get_job_by_id(job_id)
    session_service.get_user_session(ctx.user, job.session_id)

    if relevant_only:
        csv_content = _generate_filtered_csv(job_id, only_relevant=True)
        filename = f"案例分析汇总_相关_{job_id.hex[:8]}.csv"
        return FileResponse(
            io.BytesIO(csv_content.encode("utf-8-sig")),
            as_attachment=True,
            filename=filename,
            content_type="text/csv; charset=utf-8",
        )

    if not job.summary_file:
        from apps.core.exceptions import NotFoundError

        raise NotFoundError("汇总文件不存在")

    return FileResponse(
        job.summary_file.open("rb"),
        as_attachment=True,
        filename=job.summary_file.name.split("/")[-1] if job.summary_file.name else "summary.csv",
        content_type="text/csv; charset=utf-8",
    )


def _generate_filtered_csv(job_id: UUID, *, only_relevant: bool) -> str:
    """生成过滤后的 CSV 内容（仅返回字符串）"""
    import csv as csv_mod

    from ..tasks.parsing import parse_llm_result

    batch_service = ServiceLocator.get_workbench_batch_service()
    items = list(batch_service.get_completed_items(job_id))
    rows: list[dict[str, str]] = []
    for item in items:
        if not item.result:
            continue
        parsed = parse_llm_result(item.result, item.file_name)
        if only_relevant:
            if not parsed["is_relevant"]:
                continue
            if (
                parsed["parse_method"] == "regex"
                and parsed["case_number"] == "未注明"
                and parsed["conclusion"] == "未注明"
            ):
                continue
        rows.append(
            {
                "文件名": item.file_name,
                "案号": parsed["case_number"],
                "案由": parsed["cause"],
                "审理法院": parsed["court"],
                "法官": parsed["judge"],
                "书记员": parsed["clerk"],
                "与研究问题相关": "是" if parsed["is_relevant"] else "否",
                "结论": parsed["conclusion"],
                "详细分析": parsed["analysis"],
            }
        )

    output = io.StringIO()
    fieldnames = ["文件名", "案号", "案由", "审理法院", "法官", "书记员", "与研究问题相关", "结论", "详细分析"]
    writer = csv_mod.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def _generate_filtered_zip(job_id: UUID, *, only_relevant: bool) -> bytes:
    """生成过滤后的 ZIP 内容"""
    import re
    import zipfile

    from ..tasks.parsing import parse_llm_result

    batch_service = ServiceLocator.get_workbench_batch_service()
    items = list(batch_service.get_completed_items(job_id))
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        seen_names: dict[str, int] = {}
        for item in items:
            if not item.result:
                continue
            parsed = parse_llm_result(item.result, item.file_name)
            if only_relevant:
                if not parsed["is_relevant"]:
                    continue
                if (
                    parsed["parse_method"] == "regex"
                    and parsed["case_number"] == "未注明"
                    and parsed["conclusion"] == "未注明"
                ):
                    continue

            md_parts = [
                "# 案例分析报告\n",
                "## 基本信息\n",
                f"- **文件名**：{item.file_name}",
                f"- **案号**：{parsed['case_number']}",
                f"- **案由**：{parsed['cause']}",
                f"- **审理法院**：{parsed['court']}",
                f"- **法官**：{parsed['judge']}",
                f"- **书记员**：{parsed['clerk']}",
                f"- **与研究问题相关**：{'是' if parsed['is_relevant'] else '否'}",
                "",
                "## 结论\n",
                parsed["conclusion"],
                "",
                "## 详细分析\n",
                parsed["analysis"],
            ]
            md_content = "\n".join(md_parts)

            base_name = item.file_name
            if "." in base_name:
                base_name = base_name.rsplit(".", 1)[0]
            base_name = re.sub(r"[^0-9A-Za-z一-鿿._-]+", "_", base_name)
            base_name = re.sub(r"_+", "_", base_name).strip("_") or "unnamed"
            md_filename = f"{base_name}.md"
            if md_filename in seen_names:
                seen_names[md_filename] += 1
                md_filename = f"{base_name}_{seen_names[md_filename]}.md"
            else:
                seen_names[md_filename] = 0
            zf.writestr(md_filename, md_content.encode("utf-8"))

    zip_buffer.seek(0)
    return zip_buffer.getvalue()


@router.get("/batch/{job_id}/download-detail")
def download_batch_detail_zip(request: Any, job_id: UUID, relevant_only: bool = False) -> FileResponse:
    """下载批量分析详情 ZIP 文件"""
    from ..tasks import build_detail_zip_sync

    ctx = extract_request_context(request)
    batch_service = ServiceLocator.get_workbench_batch_service()
    session_service = ServiceLocator.get_workbench_session_service()

    job = batch_service.get_job_by_id(job_id)
    session_service.get_user_session(ctx.user, job.session_id)

    if relevant_only:
        zip_content = _generate_filtered_zip(job_id, only_relevant=True)
        filename = f"案例分析详情_相关_{job_id.hex[:8]}.zip"
        return FileResponse(
            io.BytesIO(zip_content),
            as_attachment=True,
            filename=filename,
            content_type="application/zip",
        )

    if not job.detail_zip_file:
        if not build_detail_zip_sync(job_id):
            from apps.core.exceptions import NotFoundError

            raise NotFoundError("分析详情文件不存在")
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
    ctx = extract_request_context(request)
    batch_service = ServiceLocator.get_workbench_batch_service()
    session_service = ServiceLocator.get_workbench_session_service()

    job = batch_service.get_job_by_id(job_id)
    session_service.get_user_session(ctx.user, job.session_id)

    created_count = batch_service.save_batch_messages(
        job_id,
        [{"content": item.content, "metadata": item.metadata} for item in payload],
        user=ctx.user,
        org_access=ctx.org_access,
        perm_open_access=ctx.perm_open_access,
    )
    return {"success": True, "created_count": created_count}


# ─── 批量分析增强 API ────────────────────────────────────────────────────────


@router.get("/batch/{job_id}/stream")
async def stream_batch_progress(request: Any, job_id: UUID) -> StreamingHttpResponse:
    """SSE 流式推送批量分析进度"""
    ctx = extract_request_context(request)
    batch_service = ServiceLocator.get_workbench_batch_service()
    session_service = ServiceLocator.get_workbench_session_service()

    job = await sync_to_async(batch_service.get_job_by_id)(job_id)
    await sync_to_async(session_service.get_user_session)(ctx.user, job.session_id)

    async def event_generator() -> Any:
        reported_items: set[str] = set()
        started_items: set[str] = set()
        last_progress = -1

        while True:
            # 合并为单次查询：running + completed/failed items
            all_items = await sync_to_async(
                lambda: list(
                    batch_service.get_active_items(job_id).values(
                        "id", "file_name", "status", "duration_ms", "error", "result"
                    )
                )
            )()

            for item in all_items:
                item_id = str(item["id"])
                if item["status"] == BatchJobStatus.RUNNING and item_id not in started_items:
                    started_items.add(item_id)
                    if item_id not in reported_items:
                        yield f"data: {json.dumps({'type': 'item_started', 'data': {'item_id': item_id, 'file_name': item['file_name']}}, ensure_ascii=False)}\n\n"
                elif (
                    item["status"] in (BatchJobStatus.COMPLETED, BatchJobStatus.FAILED)
                    and item_id not in reported_items
                ):
                    reported_items.add(item_id)
                    event_type = "item_completed" if item["status"] == BatchJobStatus.COMPLETED else "item_failed"
                    data: dict[str, Any] = {
                        "item_id": item_id,
                        "file_name": item["file_name"],
                        "status": item["status"],
                    }
                    if item.get("result"):
                        data["result"] = item["result"]
                    if item["duration_ms"] is not None:
                        data["duration_ms"] = item["duration_ms"]
                    if item["error"]:
                        data["error"] = item["error"][:200]
                    yield f"data: {json.dumps({'type': event_type, 'data': data}, ensure_ascii=False)}\n\n"

            job_data = await sync_to_async(lambda: batch_service.get_job_by_id(job_id))()

            if job_data.progress != last_progress:
                last_progress = job_data.progress
                yield f"data: {json.dumps({'type': 'progress', 'data': {'completed_items': job_data.completed_items, 'failed_items': job_data.failed_items, 'total_items': job_data.total_items, 'progress': job_data.progress}}, ensure_ascii=False)}\n\n"

            if job_data.status in (BatchJobStatus.COMPLETED, BatchJobStatus.FAILED, BatchJobStatus.CANCELLED):
                yield f"data: {json.dumps({'type': 'done', 'status': job_data.status})}\n\n"
                break

            await asyncio.sleep(1.0)

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
    ctx = extract_request_context(request)
    batch_service = ServiceLocator.get_workbench_batch_service()
    session_service = ServiceLocator.get_workbench_session_service()

    job, _ = batch_service.get_job_progress(job_id)
    session_service.get_user_session(ctx.user, job.session_id)

    return batch_service.retry_failed(job_id)  # type: ignore[no-any-return]


@router.get("/sessions/{session_id}/batch-jobs")
def list_batch_jobs(request: Any, session_id: int, page: int = 1) -> dict[str, Any]:
    """获取会话的批量分析任务历史"""
    ctx = extract_request_context(request)
    session_service = ServiceLocator.get_workbench_session_service()
    session_service.get_user_session(ctx.user, session_id)

    batch_service = ServiceLocator.get_workbench_batch_service()
    return batch_service.list_batch_jobs(  # type: ignore[no-any-return]
        session_id,
        page=page,
        user=ctx.user,
        org_access=ctx.org_access,
        perm_open_access=ctx.perm_open_access,
    )


# ─── Prompt 优化 API ─────────────────────────────────────────────────────────


class OptimizePromptIn(Schema):
    """Prompt 优化请求体"""

    prompt: str


class OptimizePromptOut(Schema):
    """Prompt 优化响应体"""

    optimized_prompt: str


@router.post("/optimize-prompt", response=OptimizePromptOut)
def optimize_prompt(request: Any, payload: OptimizePromptIn) -> dict[str, str]:
    """使用 AI 优化批量分析的 prompt"""
    from apps.core.llm.service import get_llm_service

    llm = get_llm_service()

    system_prompt = """你是一个法律文书分析专家。用户会给你一个批量文档分析的需求描述，你需要帮用户优化这个需求，使其更加清晰、具体、专业。

优化规则：
1. 保持用户的核心意图不变
2. 添加更具体的分析维度（如争议焦点、裁判要旨、法律适用、证据认定等）
3. 明确输出要求（如需要总结哪些内容、以什么格式输出）
4. 使用专业的法律术语
5. 不要添加用户没有提到的新需求
6. 优化后的 prompt 应该直接可以用于批量文档分析

请直接输出优化后的 prompt，不要有任何解释或前缀。"""

    result = llm.chat(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"请优化以下批量文档分析需求：\n\n{payload.prompt}"},
        ],
        temperature=0.7,
    )

    return {"optimized_prompt": result.content.strip()}


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
