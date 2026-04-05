"""
法院文书智能识别 API

提供文书上传、异步识别和状态查询的 API 端点。

Requirements: 2.1, 2.2, 2.3, 8.1, 8.2, 8.3, 8.4
手动绑定 Requirements: 1.3, 2.3, 3.1
"""

import logging
from pathlib import Path
from typing import Any

from ninja import File, Router
from ninja.files import UploadedFile
from pydantic import BaseModel, Field

from apps.core.exceptions import ValidationException

logger = logging.getLogger("apps.document_recognition")

router = Router(tags=["法院文书识别"])

# 支持的文件格式
SUPPORTED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}


def _validate_file_format(filename: str) -> str:
    """验证文件格式"""
    if not filename:
        raise ValidationException(message="文件名不能为空", code="EMPTY_FILENAME", errors={"file": "请提供有效的文件"})

    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValidationException(
            message="不支持的文件格式",
            code="UNSUPPORTED_FILE_FORMAT",
            errors={"file": f"不支持 {ext} 格式，请上传 PDF 或图片"},
        )
    return ext


def _save_uploaded_file(file: UploadedFile) -> str:
    """保存上传的文件（委托给 FileUploadService）"""
    from apps.core.services.file_upload_service import FileUploadService

    upload_service = FileUploadService()
    saved_path = upload_service.save_file(file, base_dir="document_recognition")
    logger.info("文件已保存: %s", saved_path)
    return str(saved_path)


# ============================================================================
# Response Schemas
# ============================================================================


class TaskSubmitResponseSchema(BaseModel):
    """任务提交响应"""

    task_id: int = Field(..., description="任务ID")
    status: str = Field(..., description="任务状态")
    message: str = Field(..., description="提示消息")


class RecognitionResultSchema(BaseModel):
    """识别结果"""

    document_type: str | None = Field(None, description="文书类型")
    case_number: str | None = Field(None, description="案号")
    key_time: str | None = Field(None, description="关键时间")
    confidence: float | None = Field(None, description="置信度")
    extraction_method: str | None = Field(None, description="提取方式")


class BindingResultSchema(BaseModel):
    """绑定结果"""

    success: bool | None = Field(None, description="是否成功")
    case_id: int | None = Field(None, description="案件ID")
    case_name: str | None = Field(None, description="案件名称")
    case_log_id: int | None = Field(None, description="日志ID")
    message: str | None = Field(None, description="消息")
    error_code: str | None = Field(None, description="错误码")


class TaskStatusResponseSchema(BaseModel):
    """任务状态响应"""

    task_id: int
    status: str
    file_path: str | None = None
    recognition: RecognitionResultSchema | None = None
    binding: BindingResultSchema | None = None
    error_message: str | None = None
    created_at: str
    finished_at: str | None = None


# ============================================================================
# 手动绑定 Schemas (Requirements: 1.3, 2.3, 3.1)
# ============================================================================


class CaseSearchResultSchema(BaseModel):
    """案件搜索结果"""

    id: int = Field(..., description="案件ID")
    name: str = Field(..., description="案件名称")
    case_numbers: list[str] = Field(default_factory=list, description="案号列表")
    parties: list[str] = Field(default_factory=list, description="当事人列表")
    created_at: str | None = Field(None, description="创建时间")


class ManualBindingRequestSchema(BaseModel):
    """手动绑定请求"""

    case_id: int = Field(..., gt=0, description="案件ID")


class ManualBindingResponseSchema(BaseModel):
    """手动绑定响应"""

    success: bool = Field(..., description="是否成功")
    case_id: int | None = Field(None, description="案件ID")
    case_name: str | None = Field(None, description="案件名称")
    case_log_id: int | None = Field(None, description="日志ID")
    message: str = Field(..., description="消息")
    error_code: str | None = Field(None, description="错误码")


class UpdateInfoRequestSchema(BaseModel):
    """更新识别信息请求"""

    case_number: str | None = Field(None, description="案号")
    key_time: str | None = Field(None, description="关键时间（ISO格式）")


class UpdateInfoResponseSchema(BaseModel):
    """更新识别信息响应"""

    success: bool = Field(..., description="是否成功")
    message: str = Field(..., description="消息")
    case_number: str | None = Field(None, description="更新后的案号")
    key_time: str | None = Field(None, description="更新后的关键时间")


# ============================================================================
# API Endpoints
# ============================================================================


@router.post("/court-document/recognize", response=TaskSubmitResponseSchema)
def recognize_document(request: Any, file: UploadedFile = File(...)) -> TaskSubmitResponseSchema:
    """
    提交文书识别任务（异步）

    上传文书后立即返回任务ID，识别在后台异步执行。
    使用 GET /court-document/task/{task_id} 查询结果。
    """
    from django_q.tasks import async_task

    filename = str(file.name)
    logger.info("收到文书识别请求: %s, 大小: %s", filename, file.size)

    # 1. 验证文件格式
    _validate_file_format(filename)

    # 2. 保存文件
    file_path = _save_uploaded_file(file)

    # 3. 创建任务记录
    task = _get_task_service().create_task(file_path=file_path, original_filename=filename)

    # 4. 提交异步任务
    async_task(
        "apps.document_recognition.tasks.execute_document_recognition_task",
        task.id,
        task_name=f"document_recognition_{task.id}",
    )

    logger.info("文书识别任务已提交: task_id=%s", task.id)

    return TaskSubmitResponseSchema(task_id=task.id, status="pending", message="任务已提交，正在后台处理")


@router.get("/court-document/task/{task_id}", response=TaskStatusResponseSchema)
def get_task_status(request: Any, task_id: int) -> TaskStatusResponseSchema:
    """
    查询识别任务状态和结果
    """
    task = _get_task_service().get_task(task_id, select_case=True)

    # 构建响应
    recognition = None
    binding = None

    if task.status == "success":
        recognition = RecognitionResultSchema(
            document_type=task.document_type,
            case_number=task.case_number,
            key_time=task.key_time.isoformat() if task.key_time else None,
            confidence=task.confidence,
            extraction_method=task.extraction_method,
        )

        if task.binding_success is not None:
            binding = BindingResultSchema(
                success=task.binding_success,
                case_id=task.case_id,
                case_name=task.case.name if task.case else None,
                case_log_id=task.case_log_id,
                message=task.binding_message,
                error_code=task.binding_error_code,
            )

    return TaskStatusResponseSchema(
        task_id=task.id,
        status=task.status,
        file_path=task.renamed_file_path or task.file_path,
        recognition=recognition,
        binding=binding,
        error_message=task.error_message,
        created_at=task.created_at.isoformat(),
        finished_at=task.finished_at.isoformat() if task.finished_at else None,
    )


# ============================================================================
# 手动绑定 API Endpoints (Requirements: 1.3, 2.3, 3.1)
# ============================================================================


def _get_case_binding_service() -> Any:
    """工厂函数：获取案件绑定服务"""
    from apps.document_recognition.services import CaseBindingService

    return CaseBindingService()


def _get_task_service() -> Any:
    """工厂函数：获取任务管理服务"""
    from apps.document_recognition.services.task_service import DocumentRecognitionTaskService

    return DocumentRecognitionTaskService()


@router.get("/court-document/search-cases", response=list[CaseSearchResultSchema])
def search_cases_for_binding(request: Any, q: str = "", limit: int = 20) -> list[CaseSearchResultSchema]:
    """
    搜索可绑定的案件

    支持按案件名称、案号、当事人搜索。

    Args:
        q: 搜索关键词（案件名称、案号、当事人）
        limit: 返回结果数量限制，默认20，最大20

    Returns:
        匹配的案件列表

    Requirements: 1.3, 2.3
    """
    limit = min(limit, 20)
    task_service = _get_task_service()
    raw_results = task_service.search_cases_for_binding(search_term=q.strip() if q else "", limit=limit)

    results = [
        CaseSearchResultSchema(
            id=r["id"],
            name=r["name"],
            case_numbers=r.get("case_numbers", []),
            parties=r.get("parties", []),
            created_at=r.get("created_at"),
        )
        for r in raw_results
    ]

    logger.info("案件搜索完成", extra={"action": "search_cases_for_binding", "query": q, "result_count": len(results)})

    return results


@router.post("/court-document/task/{task_id}/bind", response=ManualBindingResponseSchema)
def manual_bind_case(request: Any, task_id: int, payload: ManualBindingRequestSchema) -> ManualBindingResponseSchema:
    """
    手动绑定案件

    将识别任务手动绑定到指定案件，触发后续流程（创建日志、设置提醒、通知）。

    Args:
        task_id: 识别任务ID
        payload: 包含 case_id 的请求体

    Returns:
        绑定结果，包含成功状态、案件信息、日志ID等

    Requirements: 3.1
    """
    # 1. 获取任务
    task = _get_task_service().get_task(task_id, select_case=True)

    # 2. 检查任务是否已绑定
    if task.binding_success:
        return ManualBindingResponseSchema(
            success=False,
            case_id=task.case_id,
            case_name=task.case.name if task.case else None,
            case_log_id=task.case_log_id,
            message="任务已绑定到案件",
            error_code="ALREADY_BOUND",
        )

    # 3. 调用服务层执行手动绑定
    binding_service = _get_case_binding_service()
    result = binding_service.manual_bind_document_to_case(
        task_id=task_id, case_id=payload.case_id, user=getattr(request, "user", None)
    )

    return ManualBindingResponseSchema(
        success=result.success,
        case_id=result.case_id,
        case_name=result.case_name,
        case_log_id=result.case_log_id,
        message=result.message,
        error_code=result.error_code,
    )


@router.post("/court-document/task/{task_id}/update-info", response=UpdateInfoResponseSchema)
def update_task_info(request: Any, task_id: int, payload: UpdateInfoRequestSchema) -> UpdateInfoResponseSchema:
    """
    手动更新识别信息（案号、关键时间）

    用户发现识别结果不正确时，可手动修改案号和关键时间。

    Args:
        task_id: 识别任务ID
        payload: 包含 case_number 和/或 key_time 的请求体

    Returns:
        更新结果
    """

    task = _get_task_service().update_task_info(
        task_id,
        case_number=payload.case_number,
        key_time=payload.key_time,
    )

    return UpdateInfoResponseSchema(
        success=True,
        message="保存成功",
        case_number=task.case_number,
        key_time=task.key_time.isoformat() if task.key_time else None,
    )
