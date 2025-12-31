"""
法院文书智能识别 API

提供文书上传、异步识别和状态查询的 API 端点。

Requirements: 2.1, 2.2, 2.3, 8.1, 8.2, 8.3, 8.4
手动绑定 Requirements: 1.3, 2.3, 3.1
"""
import os
import uuid
import logging
from datetime import datetime
from typing import Optional, List

from ninja import Router, File
from ninja.files import UploadedFile
from pydantic import BaseModel, Field

from apps.core.exceptions import ValidationException, NotFoundError

logger = logging.getLogger("apps.automation")

router = Router(tags=["法院文书识别"])

# 支持的文件格式
SUPPORTED_EXTENSIONS = {'.pdf', '.jpg', '.jpeg', '.png'}


def _validate_file_format(filename: str) -> str:
    """验证文件格式"""
    if not filename:
        raise ValidationException(
            message="文件名不能为空",
            code="EMPTY_FILENAME",
            errors={"file": "请提供有效的文件"}
        )
    
    ext = os.path.splitext(filename)[1].lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValidationException(
            message="不支持的文件格式",
            code="UNSUPPORTED_FILE_FORMAT",
            errors={"file": f"不支持 {ext} 格式，请上传 PDF 或图片"}
        )
    return ext


def _save_uploaded_file(file: UploadedFile) -> str:
    """保存上传的文件"""
    from django.conf import settings
    
    ext = os.path.splitext(file.name)[1].lower()
    unique_name = f"{uuid.uuid4().hex}{ext}"
    
    upload_dir = os.path.join(settings.MEDIA_ROOT, 'automation', 'document_recognition')
    os.makedirs(upload_dir, exist_ok=True)
    
    file_path = os.path.join(upload_dir, unique_name)
    with open(file_path, 'wb') as f:
        for chunk in file.chunks():
            f.write(chunk)
    
    logger.info(f"文件已保存: {file_path}")
    return file_path


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
    document_type: Optional[str] = Field(None, description="文书类型")
    case_number: Optional[str] = Field(None, description="案号")
    key_time: Optional[str] = Field(None, description="关键时间")
    confidence: Optional[float] = Field(None, description="置信度")
    extraction_method: Optional[str] = Field(None, description="提取方式")


class BindingResultSchema(BaseModel):
    """绑定结果"""
    success: Optional[bool] = Field(None, description="是否成功")
    case_id: Optional[int] = Field(None, description="案件ID")
    case_name: Optional[str] = Field(None, description="案件名称")
    case_log_id: Optional[int] = Field(None, description="日志ID")
    message: Optional[str] = Field(None, description="消息")
    error_code: Optional[str] = Field(None, description="错误码")


class TaskStatusResponseSchema(BaseModel):
    """任务状态响应"""
    task_id: int
    status: str
    file_path: Optional[str] = None
    recognition: Optional[RecognitionResultSchema] = None
    binding: Optional[BindingResultSchema] = None
    error_message: Optional[str] = None
    created_at: str
    finished_at: Optional[str] = None


# ============================================================================
# 手动绑定 Schemas (Requirements: 1.3, 2.3, 3.1)
# ============================================================================

class CaseSearchResultSchema(BaseModel):
    """案件搜索结果"""
    id: int = Field(..., description="案件ID")
    name: str = Field(..., description="案件名称")
    case_numbers: List[str] = Field(default_factory=list, description="案号列表")
    parties: List[str] = Field(default_factory=list, description="当事人列表")
    created_at: Optional[str] = Field(None, description="创建时间")


class ManualBindingRequestSchema(BaseModel):
    """手动绑定请求"""
    case_id: int = Field(..., gt=0, description="案件ID")


class ManualBindingResponseSchema(BaseModel):
    """手动绑定响应"""
    success: bool = Field(..., description="是否成功")
    case_id: Optional[int] = Field(None, description="案件ID")
    case_name: Optional[str] = Field(None, description="案件名称")
    case_log_id: Optional[int] = Field(None, description="日志ID")
    message: str = Field(..., description="消息")
    error_code: Optional[str] = Field(None, description="错误码")


class UpdateInfoRequestSchema(BaseModel):
    """更新识别信息请求"""
    case_number: Optional[str] = Field(None, description="案号")
    key_time: Optional[str] = Field(None, description="关键时间（ISO格式）")


class UpdateInfoResponseSchema(BaseModel):
    """更新识别信息响应"""
    success: bool = Field(..., description="是否成功")
    message: str = Field(..., description="消息")
    case_number: Optional[str] = Field(None, description="更新后的案号")
    key_time: Optional[str] = Field(None, description="更新后的关键时间")


# ============================================================================
# API Endpoints
# ============================================================================

@router.post("/court-document/recognize", response=TaskSubmitResponseSchema)
def recognize_document(request, file: UploadedFile = File(...)):
    """
    提交文书识别任务（异步）
    
    上传文书后立即返回任务ID，识别在后台异步执行。
    使用 GET /court-document/task/{task_id} 查询结果。
    """
    from django_q.tasks import async_task
    from apps.automation.models import DocumentRecognitionTask, DocumentRecognitionStatus
    
    logger.info(f"收到文书识别请求: {file.name}, 大小: {file.size}")
    
    # 1. 验证文件格式
    _validate_file_format(file.name)
    
    # 2. 保存文件
    file_path = _save_uploaded_file(file)
    
    # 3. 创建任务记录
    task = DocumentRecognitionTask.objects.create(
        file_path=file_path,
        original_filename=file.name,
        status=DocumentRecognitionStatus.PENDING
    )
    
    # 4. 提交异步任务
    async_task(
        'apps.automation.tasks.execute_document_recognition_task',
        task.id,
        task_name=f"document_recognition_{task.id}"
    )
    
    logger.info(f"文书识别任务已提交: task_id={task.id}")
    
    return TaskSubmitResponseSchema(
        task_id=task.id,
        status="pending",
        message="任务已提交，正在后台处理"
    )


@router.get("/court-document/task/{task_id}", response=TaskStatusResponseSchema)
def get_task_status(request, task_id: int):
    """
    查询识别任务状态和结果
    """
    from apps.automation.models import DocumentRecognitionTask
    
    try:
        task = DocumentRecognitionTask.objects.select_related('case').get(id=task_id)
    except DocumentRecognitionTask.DoesNotExist:
        raise NotFoundError(
            message="任务不存在",
            code="TASK_NOT_FOUND",
            errors={"task_id": f"任务 {task_id} 不存在"}
        )
    
    # 构建响应
    recognition = None
    binding = None
    
    if task.status == "success":
        recognition = RecognitionResultSchema(
            document_type=task.document_type,
            case_number=task.case_number,
            key_time=task.key_time.isoformat() if task.key_time else None,
            confidence=task.confidence,
            extraction_method=task.extraction_method
        )
        
        if task.binding_success is not None:
            binding = BindingResultSchema(
                success=task.binding_success,
                case_id=task.case_id,
                case_name=task.case.name if task.case else None,
                case_log_id=task.case_log_id,
                message=task.binding_message,
                error_code=task.binding_error_code
            )
    
    return TaskStatusResponseSchema(
        task_id=task.id,
        status=task.status,
        file_path=task.renamed_file_path or task.file_path,
        recognition=recognition,
        binding=binding,
        error_message=task.error_message,
        created_at=task.created_at.isoformat(),
        finished_at=task.finished_at.isoformat() if task.finished_at else None
    )


# ============================================================================
# 手动绑定 API Endpoints (Requirements: 1.3, 2.3, 3.1)
# ============================================================================

def _get_case_binding_service():
    """工厂函数：获取案件绑定服务"""
    from ..services.court_document_recognition import CaseBindingService
    return CaseBindingService()


def _get_recognition_service():
    """工厂函数：获取识别服务"""
    from ..services.court_document_recognition import CourtDocumentRecognitionService
    return CourtDocumentRecognitionService()


@router.get("/court-document/search-cases", response=List[CaseSearchResultSchema])
def search_cases_for_binding(request, q: str = "", limit: int = 20):
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
    from django.db.models import Q
    from apps.cases.models import Case, CaseNumber, CaseParty
    
    # 限制返回数量
    limit = min(limit, 20)
    
    if not q or not q.strip():
        # 无搜索词时返回最近的案件
        cases = Case.objects.select_related().prefetch_related(
            'case_numbers', 'parties__client'
        ).order_by('-id')[:limit]
    else:
        search_term = q.strip()
        
        # 构建搜索条件：案件名称、案号、当事人
        # 1. 按案件名称搜索
        name_query = Q(name__icontains=search_term)
        
        # 2. 按案号搜索
        case_ids_by_number = CaseNumber.objects.filter(
            number__icontains=search_term
        ).values_list('case_id', flat=True)
        
        # 3. 按当事人搜索
        case_ids_by_party = CaseParty.objects.filter(
            client__name__icontains=search_term
        ).values_list('case_id', flat=True)
        
        # 合并查询
        cases = Case.objects.filter(
            name_query |
            Q(id__in=case_ids_by_number) |
            Q(id__in=case_ids_by_party)
        ).select_related().prefetch_related(
            'case_numbers', 'parties__client'
        ).distinct().order_by('-id')[:limit]
    
    # 构建响应
    results = []
    for case in cases:
        case_numbers = [cn.number for cn in case.case_numbers.all()]
        parties = [p.client.name for p in case.parties.all() if p.client]
        
        results.append(CaseSearchResultSchema(
            id=case.id,
            name=case.name,
            case_numbers=case_numbers,
            parties=parties,
            created_at=case.start_date.isoformat() if case.start_date else None
        ))
    
    logger.info(
        f"案件搜索完成",
        extra={
            "action": "search_cases_for_binding",
            "query": q,
            "result_count": len(results)
        }
    )
    
    return results


@router.post("/court-document/task/{task_id}/bind", response=ManualBindingResponseSchema)
def manual_bind_case(request, task_id: int, payload: ManualBindingRequestSchema):
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
    from apps.automation.models import DocumentRecognitionTask
    
    # 1. 获取任务
    try:
        task = DocumentRecognitionTask.objects.select_related('case').get(id=task_id)
    except DocumentRecognitionTask.DoesNotExist:
        raise NotFoundError(
            message="任务不存在",
            code="TASK_NOT_FOUND",
            errors={"task_id": f"任务 {task_id} 不存在"}
        )
    
    # 2. 检查任务是否已绑定
    if task.binding_success:
        return ManualBindingResponseSchema(
            success=False,
            case_id=task.case_id,
            case_name=task.case.name if task.case else None,
            case_log_id=task.case_log_id,
            message="任务已绑定到案件",
            error_code="ALREADY_BOUND"
        )
    
    # 3. 调用服务层执行手动绑定
    binding_service = _get_case_binding_service()
    
    try:
        result = binding_service.manual_bind_document_to_case(
            task_id=task_id,
            case_id=payload.case_id,
            user=getattr(request, 'user', None)
        )
        
        return ManualBindingResponseSchema(
            success=result.success,
            case_id=result.case_id,
            case_name=result.case_name,
            case_log_id=result.case_log_id,
            message=result.message,
            error_code=result.error_code
        )
        
    except NotFoundError as e:
        return ManualBindingResponseSchema(
            success=False,
            case_id=None,
            case_name=None,
            case_log_id=None,
            message=str(e),
            error_code="CASE_NOT_FOUND"
        )
    except Exception as e:
        logger.error(
            f"手动绑定失败：{e}",
            extra={
                "action": "manual_bind_case",
                "task_id": task_id,
                "case_id": payload.case_id,
                "error": str(e)
            }
        )
        return ManualBindingResponseSchema(
            success=False,
            case_id=None,
            case_name=None,
            case_log_id=None,
            message=f"绑定失败：{str(e)}",
            error_code="BINDING_ERROR"
        )


@router.post("/court-document/task/{task_id}/update-info", response=UpdateInfoResponseSchema)
def update_task_info(request, task_id: int, payload: UpdateInfoRequestSchema):
    """
    手动更新识别信息（案号、关键时间）
    
    用户发现识别结果不正确时，可手动修改案号和关键时间。
    
    Args:
        task_id: 识别任务ID
        payload: 包含 case_number 和/或 key_time 的请求体
        
    Returns:
        更新结果
    """
    from apps.automation.models import DocumentRecognitionTask
    from datetime import datetime
    
    # 1. 获取任务
    try:
        task = DocumentRecognitionTask.objects.get(id=task_id)
    except DocumentRecognitionTask.DoesNotExist:
        raise NotFoundError(
            message="任务不存在",
            code="TASK_NOT_FOUND",
            errors={"task_id": f"任务 {task_id} 不存在"}
        )
    
    # 2. 更新字段
    updated_fields = []
    
    if payload.case_number is not None:
        task.case_number = payload.case_number if payload.case_number else None
        updated_fields.append('case_number')
    
    if payload.key_time is not None:
        if payload.key_time:
            try:
                # 解析 ISO 格式时间
                task.key_time = datetime.fromisoformat(payload.key_time.replace('Z', '+00:00'))
            except ValueError:
                raise ValidationException(
                    message="时间格式不正确",
                    code="INVALID_TIME_FORMAT",
                    errors={"key_time": "请使用正确的时间格式"}
                )
        else:
            task.key_time = None
        updated_fields.append('key_time')
    
    if updated_fields:
        task.save(update_fields=updated_fields)
        logger.info(
            f"识别信息已更新",
            extra={
                "action": "update_task_info",
                "task_id": task_id,
                "updated_fields": updated_fields,
                "case_number": task.case_number,
                "key_time": str(task.key_time) if task.key_time else None
            }
        )
    
    return UpdateInfoResponseSchema(
        success=True,
        message="保存成功",
        case_number=task.case_number,
        key_time=task.key_time.isoformat() if task.key_time else None
    )
