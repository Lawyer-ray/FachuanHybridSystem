"""文档解析 Ninja API 接口"""

import logging
from pathlib import Path

from asgiref.sync import sync_to_async
from django.conf import settings
from django.http import HttpRequest
from ninja import File, Router, UploadedFile

from apps.core.filesystem.upload_paths import MediaEntity
from apps.core.security.admin_access import get_request_user
from apps.core.security.auth import JWTOrSessionAuth
from apps.core.services.storage_service import save_uploaded_file
from apps.document_parsing.schemas.parsing_schemas import (
    DocumentParsingRecordDetailOut,
    DocumentParsingRecordListOut,
    DocumentParsingRecordOut,
    ExtractTextRequest,
    ExtractTextResponse,
    ParseDocumentRequest,
    ParseDocumentResponse,
    TaskStatusResponse,
)
from apps.document_parsing.services import get_document_parser
from apps.document_parsing.services.task_dispatch_service import DocumentParsingTaskDispatchService

logger = logging.getLogger(__name__)

router = Router()

# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------


def _get_task_dispatch_service() -> DocumentParsingTaskDispatchService:
    """工厂函数：创建异步解析任务调度服务实例"""
    return DocumentParsingTaskDispatchService()


def _needs_async(backend: str) -> bool:
    """判断是否需要异步执行。

    通过查询后端的 requires_async_execution 属性决定（后端自描述能力），
    而非在此处硬编码后端名称集合。auto 模式会先解析出实际后端再查询。

    Args:
        backend: 后端名称（mineru / textin / local / auto）

    Returns:
        True 表示该后端需要异步执行（云端含 HTTP 上传 + 轮询）

    注意:
        本函数内部调用 get_document_parser,会触发 SystemConfig ORM 读取。
        在 async 视图中必须通过 sync_to_async 调用本函数。
    """
    parser = get_document_parser(backend=backend)
    return getattr(parser, "requires_async_execution", False)


# 上传白名单：覆盖解析后端（local/mineru/textin）的核心能力——文档 pdf/docx/doc + 常见图片
_ALLOWED_UPLOAD_EXTENSIONS = [".pdf", ".docx", ".doc", ".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp", ".gif"]
_MAX_UPLOAD_SIZE_BYTES = 50 * 1024 * 1024


def _save_upload(file: UploadedFile) -> tuple[str, Path]:
    """保存上传文件，返回 (saved_name, file_path)。

    委托 storage_service.save_uploaded_file：清洗文件名、校验扩展名白名单与大小上限，
    统一落入 MediaEntity.DOCUMENT_PARSING_UPLOADS 目录。
    """
    saved_name, _ = save_uploaded_file(
        uploaded_file=file,
        rel_dir=MediaEntity.DOCUMENT_PARSING_UPLOADS,
        allowed_extensions=_ALLOWED_UPLOAD_EXTENSIONS,
        max_size_bytes=_MAX_UPLOAD_SIZE_BYTES,
    )
    file_path = Path(settings.MEDIA_ROOT) / saved_name
    return saved_name, file_path


def _form_str(request: HttpRequest, key: str, default: str) -> str:
    """从 multipart form 字段读取字符串，缺省返回 default。"""
    val = request.POST.get(key)
    if val is None:
        return default
    val = val.strip()
    return val if val else default


def _form_bool(request: HttpRequest, key: str, default: bool) -> bool:
    """从 multipart form 字段解析布尔值，缺省返回 default。"""
    val = request.POST.get(key)
    if val is None:
        return default
    val = val.strip().lower()
    if val in ("true", "1", "yes", "on"):
        return True
    if val in ("false", "0", "no", "off"):
        return False
    return default


def _form_int(request: HttpRequest, key: str, default: int | None) -> int | None:
    """从 multipart form 字段解析整数，缺省返回 default。"""
    val = request.POST.get(key)
    if val is None:
        return default
    val = val.strip()
    if not val.lstrip("-").isdigit():
        return default
    return int(val)


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
    request: HttpRequest, file: UploadedFile = File(...), body: ParseDocumentRequest | None = None
) -> ParseDocumentResponse:
    """解析上传的文档，返回结构化的解析结果。

    当 backend 显式设为 "mineru" 或 "textin" 时，解析在后台异步执行，
    立即返回 task_id；客户端可通过 GET /task/{task_id} 轮询结果。
    """
    try:
        saved_name, file_path = await sync_to_async(_save_upload)(file)
        file_name = file.name or "uploaded"

        # 参数解析：multipart 调用从 request.POST 读取（与 admin upload_view 一致），
        # JSON 调用从 body 读取。form 字段优先，body 其次，默认值兜底。
        backend = _form_str(request, "backend", body.backend if body else "auto")
        extract_tables = _form_bool(request, "extract_tables", body.extract_tables if body else True)
        extract_images = _form_bool(request, "extract_images", body.extract_images if body else False)
        return_markdown = _form_bool(request, "return_markdown", body.return_markdown if body else True)

        # --- 异步路径 ---
        # _needs_async 内部调用 get_document_parser 会触发 SystemConfig ORM 读取,
        # 在 async 视图中必须通过 sync_to_async 调用,否则触发 SynchronousOnlyOperation
        if await sync_to_async(_needs_async, thread_sensitive=False)(backend):
            # 与 admin upload_view 同款模式：建 DocumentParsingTask 记录 + 约定的
            # task_name（document_parsing_{id}），document_parsing_hook 才能把
            # 成功/失败状态回写——前端报错文案引导用户去后台「解析任务」查看，
            # 没有这条记录那里就什么都看不到（此前 task_name 用文件名，hook 全部跳过）。
            # created_by 记录归属人（审计 P1 修复），records 列表/详情按其过滤。
            task_id = await _get_task_dispatch_service().submit_parse_task(
                file_name=file_name,
                file_path=file_path,
                file_size=file.size or 0,
                backend=backend,
                extract_tables=extract_tables,
                extract_images=extract_images,
                return_markdown=return_markdown,
                created_by=get_request_user(request),
            )
            logger.info("文档解析任务已提交: task_id=%s, file=%s", task_id, saved_name)
            return ParseDocumentResponse(
                success=True,
                task_id=task_id,
                status="pending",
            )

        # --- 同步路径 ---
        # get_document_parser 内部通过 ParserFactory 读取 SystemConfig(ORM),
        # 必须在 sync_to_async 中执行,否则在 async 视图里触发 SynchronousOnlyOperation
        parser = await sync_to_async(get_document_parser, thread_sensitive=False)(backend=backend)
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
    request: HttpRequest, file: UploadedFile = File(...), body: ExtractTextRequest | None = None
) -> ExtractTextResponse:
    """提取文档的纯文本内容。

    当 backend 显式设为 "mineru" 或 "textin" 时，提取在后台异步执行。
    """
    try:
        saved_name, file_path = await sync_to_async(_save_upload)(file)

        # 参数解析：multipart 调用从 request.POST 读取，JSON 调用从 body 读取。
        backend = _form_str(request, "backend", body.backend if body else "auto")
        max_length = _form_int(request, "max_length", body.max_length if body else None)

        # --- 异步路径 ---
        if await sync_to_async(_needs_async, thread_sensitive=False)(backend):
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
        # get_document_parser 内部通过 ParserFactory 读取 SystemConfig(ORM),
        # 必须在 sync_to_async 中执行,否则在 async 视图里触发 SynchronousOnlyOperation
        parser = await sync_to_async(get_document_parser, thread_sensitive=False)(backend=backend)
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
def get_task_status(request: HttpRequest, task_id: str) -> TaskStatusResponse:
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


# ---------------------------------------------------------------------------
# GET /records — 历史解析记录（列表 + 详情）
# ---------------------------------------------------------------------------


@router.get(
    "/records",
    response=DocumentParsingRecordListOut,
    summary="历史解析记录列表",
    auth=JWTOrSessionAuth(),
)
def list_records(
    request: HttpRequest, status: str | None = None, page: int = 1, page_size: int = 20
) -> DocumentParsingRecordListOut:
    """分页列出历史解析记录（最新在前），供前端历史弹窗浏览。

    status 可选值：pending / processing / completed / failed。
    归属过滤：普通用户仅见自己的记录与存量 NULL 记录；管理员全量。
    """
    from apps.document_parsing.services.record_service import DocumentParsingRecordService

    items, count, num_pages = DocumentParsingRecordService().list_records(
        status=status, page=page, page_size=page_size, user=get_request_user(request)
    )
    return DocumentParsingRecordListOut(
        items=[DocumentParsingRecordOut(**item) for item in items],
        count=count,
        page=page,
        num_pages=num_pages,
    )


@router.get(
    "/records/{record_id}",
    response=DocumentParsingRecordDetailOut,
    summary="解析记录详情",
    auth=JWTOrSessionAuth(),
)
def get_record(request: HttpRequest, record_id: int) -> DocumentParsingRecordDetailOut:
    """按记录 id 取解析全文（text / markdown / metadata），历史点开查看用。

    归属过滤：普通用户仅可读自己的记录与存量 NULL 记录，否则 404。
    """
    from apps.document_parsing.services.record_service import DocumentParsingRecordService

    return DocumentParsingRecordDetailOut(
        **DocumentParsingRecordService().get_record(record_id, user=get_request_user(request))
    )
