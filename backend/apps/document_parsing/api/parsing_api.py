"""文档解析 Ninja API 接口"""

import logging
from pathlib import Path

from asgiref.sync import sync_to_async
from django.conf import settings
from django.core.files.storage import default_storage
from ninja import File, Router, UploadedFile

from apps.core.security.auth import JWTOrSessionAuth
from apps.document_parsing.schemas.parsing_schemas import (
    ExtractTextRequest,
    ExtractTextResponse,
    ParseDocumentRequest,
    ParseDocumentResponse,
    TaskStatusResponse,
)
from apps.document_parsing.services import get_document_parser

logger = logging.getLogger(__name__)

router = Router()

# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------

_ASYNC_BACKENDS = {"mineru"}
"""需要异步执行的后端集合 —— MinerU 含 HTTP 上传 + 轮询，阻塞时间长。"""


def _needs_async(backend: str) -> bool:
    """判断是否需要异步执行。

    当 backend 为 "auto" 时，如果 auto 解析最终会走 mineru 也需要异步，
    但这里无法预知 auto 选择结果，保守起见 auto 走同步（如果选到 mineru
    仍然由 mineru_backend 内部处理，最多阻塞）。只有显式指定 mineru 时才异步。
    """
    return backend in _ASYNC_BACKENDS


def _save_upload(file: UploadedFile) -> tuple[str, Path]:
    """保存上传文件，返回 (saved_name, file_path)。"""
    file_name = file.name or "uploaded"
    saved_name = default_storage.save(f"document_parsing/uploads/{file_name}", file)
    file_path = Path(settings.MEDIA_ROOT) / saved_name
    return saved_name, file_path


# ---------------------------------------------------------------------------
# POST /parse — 解析文档
# ---------------------------------------------------------------------------


@router.post(
    "/parse",
    response=ParseDocumentResponse,
    summary="解析文档",
    auth=JWTOrSessionAuth(),
)
async def parse_document(
    request: object, file: UploadedFile = File(...), body: ParseDocumentRequest | None = None
) -> ParseDocumentResponse:
    """解析上传的文档，返回结构化的解析结果。

    当 backend 显式设为 "mineru" 时，解析在后台异步执行，
    立即返回 task_id；客户端可通过 GET /task/{task_id} 轮询结果。
    """
    try:
        saved_name, file_path = await sync_to_async(_save_upload)(file)
        file_name = file.name or "uploaded"

        backend = body.backend if body else "auto"
        extract_tables = body.extract_tables if body is not None else True
        extract_images = body.extract_images if body is not None else False
        return_markdown = body.return_markdown if body is not None else True

        # --- 异步路径 ---
        if _needs_async(backend):
            from apps.core.tasking import submit_task

            task_id = await sync_to_async(submit_task, thread_sensitive=False)(
                "apps.document_parsing.tasks.execute_parse_document",
                str(file_path),
                Path(file_name).suffix.lstrip("."),
                backend,
                extract_tables,
                extract_images,
                return_markdown,
                task_name=f"parse_document_{saved_name}",
                hook="apps.document_parsing.tasks.document_parsing_hook",
                timeout=600,
            )
            logger.info("文档解析任务已提交: task_id=%s, file=%s", task_id, saved_name)
            return ParseDocumentResponse(
                success=True,
                task_id=task_id,
                status="pending",
            )

        # --- 同步路径 ---
        parser = get_document_parser(backend=backend)
        result = await sync_to_async(parser.parse_document, thread_sensitive=False)(
            file_path=str(file_path),
            file_type=Path(file_name).suffix.lstrip("."),
            extract_tables=extract_tables,
            extract_images=extract_images,
            return_markdown=return_markdown,
        )

        return ParseDocumentResponse(
            success=True,
            text=result.text,
            markdown=result.markdown,
            metadata=result.metadata or {},
            parse_method=result.parse_method,
        )

    except Exception as e:
        logger.error("文档解析失败: %s", str(e))
        return ParseDocumentResponse(
            success=False,
            error=str(e),
        )


# ---------------------------------------------------------------------------
# POST /extract-text — 提取文档文本
# ---------------------------------------------------------------------------


@router.post(
    "/extract-text",
    response=ExtractTextResponse,
    summary="提取文档文本",
    auth=JWTOrSessionAuth(),
)
async def extract_text(
    request: object, file: UploadedFile = File(...), body: ExtractTextRequest | None = None
) -> ExtractTextResponse:
    """提取文档的纯文本内容。

    当 backend 显式设为 "mineru" 时，提取在后台异步执行。
    """
    try:
        saved_name, file_path = await sync_to_async(_save_upload)(file)

        backend = body.backend if body else "auto"
        max_length = body.max_length if body is not None else None

        # --- 异步路径 ---
        if _needs_async(backend):
            from apps.core.tasking import submit_task

            task_id = await sync_to_async(submit_task, thread_sensitive=False)(
                "apps.document_parsing.tasks.execute_extract_text",
                str(file_path),
                backend,
                max_length,
                task_name=f"extract_text_{saved_name}",
                timeout=600,
            )
            logger.info("文本提取任务已提交: task_id=%s, file=%s", task_id, saved_name)
            return ExtractTextResponse(
                success=True,
                task_id=task_id,
                status="pending",
                text="",
            )

        # --- 同步路径 ---
        parser = get_document_parser(backend=backend)
        result = await sync_to_async(parser.extract_text, thread_sensitive=False)(
            file_path=str(file_path),
            max_length=max_length,
        )

        return ExtractTextResponse(
            success=result.success,
            text=result.text,
            method=result.method,
            metadata=result.metadata or {},
        )

    except Exception as e:
        logger.error("文本提取失败: %s", str(e))
        return ExtractTextResponse(
            success=False,
            text="",
            error=str(e),
        )


# ---------------------------------------------------------------------------
# GET /task/{task_id} — 查询异步任务状态
# ---------------------------------------------------------------------------


@router.get(
    "/task/{task_id}",
    response=TaskStatusResponse,
    summary="查询解析任务状态",
    auth=JWTOrSessionAuth(),
)
def get_task_status(request: object, task_id: str) -> TaskStatusResponse:
    """查询异步解析任务的状态和结果。

    轮询此端点直到 status 为 "success" 或 "failure"，
    成功时 result 字段包含完整的解析结果。
    """
    from apps.core.tasking.query import TaskQueryService

    svc = TaskQueryService()
    info = svc.get_task_status(task_id)

    return TaskStatusResponse(
        task_id=info["task_id"],
        status=info["status"],
        result=info["result"] if isinstance(info["result"], dict) else None,
        started_at=info["started_at"],
        finished_at=info["finished_at"],
    )
