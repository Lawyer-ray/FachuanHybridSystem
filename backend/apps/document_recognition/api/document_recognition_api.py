"""
法院文书智能识别 API

提供文书上传、异步识别和状态查询的 API 端点。

Requirements: 2.1, 2.2, 2.3, 8.1, 8.2, 8.3, 8.4
手动绑定 Requirements: 1.3, 2.3, 3.1
"""

import logging
from pathlib import Path
from typing import Any, Literal, cast

from asgiref.sync import sync_to_async
from django.conf import settings
from ninja import File, Form, Router
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
    """保存上传的文件（委托给 storage_service）"""
    from apps.core.services.storage_service import save_uploaded_file

    rel_path, _ = save_uploaded_file(file, rel_dir="document_recognition")
    saved_path = str(Path(settings.MEDIA_ROOT) / rel_path)
    logger.info("文件已保存: %s", saved_path)
    return saved_path


# 未绑定任务的推荐缓存 TTL（秒）：状态接口被前端轮询，避免每次全库评分
RECOMMENDATION_CACHE_TTL = 300


def _recommendation_rows(task: Any) -> list[dict[str, Any]]:
    """未绑定任务的推荐候选（带短 TTL 缓存）。"""
    from django.core.cache import cache

    from apps.document_recognition.services.case_matching_service import DocumentCaseMatchingService

    cache_key = f"docrec:reco:{task.id}"
    rows = cache.get(cache_key)
    if rows is None:
        rows = DocumentCaseMatchingService().get_recommendations(
            case_number=task.case_number,
            party_names=list(task.party_names or []),
            raw_text=task.raw_text or "",
        )
        cache.set(cache_key, rows, RECOMMENDATION_CACHE_TTL)
    return rows


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
    llm_model: str | None = Field(None, description="使用的 LLM 模型")
    llm_backend: str | None = Field(None, description="使用的 LLM 后端")
    llm_latency_ms: int | None = Field(None, description="LLM 分析耗时（毫秒）")
    degraded: bool | None = Field(None, description="是否降级识别（LLM 不可用时仅用关键词+正则）")


class BindingResultSchema(BaseModel):
    """绑定结果"""

    success: bool | None = Field(None, description="是否成功")
    case_id: int | None = Field(None, description="案件ID")
    case_name: str | None = Field(None, description="案件名称")
    case_log_id: int | None = Field(None, description="日志ID")
    message: str | None = Field(None, description="消息")
    error_code: str | None = Field(None, description="错误码")


class DateCandidateOutSchema(BaseModel):
    """日期候选"""

    id: int = Field(..., description="候选ID")
    due_at: str = Field(..., description="候选日期时间")
    reminder_type: str = Field(..., description="提醒类型")
    reminder_type_label: str = Field(..., description="提醒类型名称")
    context_text: str = Field("", description="原文上下文")
    source: str = Field("regex", description="提取来源 llm/regex/merged")
    confidence: float | None = Field(None, description="置信度")
    status: str = Field("pending", description="确认状态 pending/confirmed/skipped")
    reminder_id: int | None = Field(None, description="已写入的提醒ID")
    confirmed_at: str | None = Field(None, description="确认时间")


class CaseRecommendationOutSchema(BaseModel):
    """案件绑定推荐候选"""

    case_id: int = Field(..., description="案件ID")
    case_name: str = Field(..., description="案件名称")
    score: int = Field(..., description="相关度评分")
    reasons: list[str] = Field(default_factory=list, description="评分理由")
    case_numbers: list[str] = Field(default_factory=list, description="案号列表")
    parties: list[str] = Field(default_factory=list, description="当事人列表")
    status: str = Field("", description="案件状态")


class TaskStatusResponseSchema(BaseModel):
    """任务状态响应"""

    task_id: int
    status: str
    file_path: str | None = None
    recognition: RecognitionResultSchema | None = None
    binding: BindingResultSchema | None = None
    date_candidates: list[DateCandidateOutSchema] = Field(default_factory=list, description="日期候选列表")
    recommendations: list[CaseRecommendationOutSchema] = Field(
        default_factory=list, description="案件绑定推荐（未绑定时返回）"
    )
    binding_mode: str = Field("standalone", description="绑定模式 standalone/pipeline")
    date_confirmation_status: str | None = Field(None, description="日期确认进度 none/pending/partial/complete")
    error_message: str | None = None
    created_at: str
    finished_at: str | None = None


class DateConfirmItemInSchema(BaseModel):
    """单条日期确认请求"""

    candidate_id: int = Field(..., description="候选ID")
    action: Literal["confirm", "skip"] = Field("confirm", description="确认或忽略")
    due_at: str | None = Field(None, description="编辑后的时间（naive 本地 ISO，如 2026-10-15T09:30）")
    reminder_type: str | None = Field(None, description="编辑后的提醒类型")


class DateConfirmItemOutSchema(BaseModel):
    """单条日期确认结果"""

    candidate_id: int
    status: str
    reminder_id: int | None = None
    message: str = ""
    error_code: str | None = None


class DateConfirmRequestSchema(BaseModel):
    """日期确认请求"""

    items: list[DateConfirmItemInSchema] = Field(..., min_length=1, description="确认项列表")


class DateConfirmResponseSchema(BaseModel):
    """日期确认响应"""

    success: bool
    date_confirmation_status: str | None = None
    results: list[DateConfirmItemOutSchema] = Field(default_factory=list)


class DateRevokeResponseSchema(BaseModel):
    """撤销确认响应"""

    success: bool
    candidate_id: int
    status: str
    reminder_id: int | None = None
    message: str = ""


class PendingTaskOutSchema(BaseModel):
    """待确认任务摘要"""

    task_id: int
    original_filename: str
    document_type: str | None = None
    date_confirmation_status: str
    candidate_count: int = 0
    case_name: str | None = None
    created_at: str


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
async def recognize_document(
    request: Any,
    file: UploadedFile = File(...),
    source_court_sms_id: int | None = Form(None),
) -> TaskSubmitResponseSchema:  # pragma: no cover
    """
    提交文书识别任务（异步）

    上传文书后立即返回任务ID，识别在后台异步执行。
    使用 GET /court-document/task/{task_id} 查询结果。

    source_court_sms_id（管线模式，可选）：来自法院短信管线的文书，
    案件已由短信第一轮绑定，识别只做提取+日期候选，不重复建日志/通知。
    """
    from apps.core.tasking import submit_task

    filename = str(file.name)
    logger.info("收到文书识别请求: %s, 大小: %s", filename, file.size)

    # 1. 验证文件格式
    _validate_file_format(filename)

    # 2. 保存文件
    file_path = await sync_to_async(_save_uploaded_file)(file)

    # 3. 创建任务记录 + 提交异步任务
    # timeout 覆盖 LLM 分析（最坏 ~90s）+ 文本提取 + 绑定通知，防止慢识别被 qcluster 默认超时误杀
    prebound = None
    if source_court_sms_id:
        prebound = await sync_to_async(_load_pipeline_prebinding)(source_court_sms_id)

    def _create_and_submit() -> Any:
        task = _get_task_service().create_task(
            file_path=file_path,
            original_filename=filename,
            source_court_sms_id=source_court_sms_id,
            case_id=prebound["case_id"] if prebound else None,
            case_log_id=prebound["case_log_id"] if prebound else None,
        )
        submit_task(
            "apps.document_recognition.tasks.execute_document_recognition_task",
            task.id,
            task_name=f"document_recognition_{task.id}",
            timeout=600,
        )
        return task.id

    task_id = await sync_to_async(_create_and_submit)()

    logger.info("文书识别任务已提交: task_id=%s", task_id)

    return TaskSubmitResponseSchema(task_id=task_id, status="pending", message="任务已提交，正在后台处理")


def _load_pipeline_prebinding(source_court_sms_id: int) -> dict[str, int | None]:  # pragma: no cover
    """读取法院短信已完成的绑定（案件+日志），作为识别任务的预绑定。

    短信不存在时 NotFoundError 由全局异常处理器转为 404。
    """
    from apps.core.interfaces import ServiceLocator

    court_sms_service = ServiceLocator.get_court_sms_service()
    sms = court_sms_service.get_sms_detail(source_court_sms_id)
    if not getattr(sms, "case_log_id", None):
        raise ValidationException(
            message="该法院短信尚未完成案件绑定，不能走管线模式",
            code="COURT_SMS_NOT_BOUND",
            errors={},
        )
    return {"case_id": sms.case_id, "case_log_id": sms.case_log_id}


@router.get("/court-document/task/{task_id}", response=TaskStatusResponseSchema)
async def get_task_status(request: Any, task_id: int) -> TaskStatusResponseSchema:  # pragma: no cover
    """
    查询识别任务状态和结果

    响应含日期候选（date_candidates）、日期确认进度（date_confirmation_status）；
    任务识别成功且未绑定时附案件绑定推荐（recommendations）。
    """

    def _do() -> Any:
        from apps.document_recognition.services import date_candidate_service

        task = _get_task_service().get_task(task_id, select_case=True)

        # 构建响应
        recognition = None
        binding = None
        date_candidates: list[DateCandidateOutSchema] = []
        recommendations: list[CaseRecommendationOutSchema] = []

        if task.status == "success":
            recognition = RecognitionResultSchema(
                document_type=task.document_type,
                case_number=task.case_number,
                key_time=task.key_time.isoformat() if task.key_time else None,
                confidence=task.confidence,
                extraction_method=task.extraction_method,
                llm_model=task.llm_model,
                llm_backend=task.llm_backend,
                llm_latency_ms=task.llm_latency_ms,
                degraded=task.degraded,
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

            date_candidates = [DateCandidateOutSchema(**row) for row in date_candidate_service.list_candidates(task)]
            if not task.case_log_id:
                reco_rows = _recommendation_rows(task)
                recommendations = [CaseRecommendationOutSchema(**row) for row in reco_rows]

        return TaskStatusResponseSchema(
            task_id=task.id,
            status=task.status,
            file_path=task.renamed_file_path or task.file_path,
            recognition=recognition,
            binding=binding,
            date_candidates=date_candidates,
            recommendations=recommendations,
            binding_mode="pipeline" if task.source_court_sms_id else "standalone",
            date_confirmation_status=task.date_confirmation_status,
            error_message=task.error_message,
            created_at=task.created_at.isoformat(),
            finished_at=task.finished_at.isoformat() if task.finished_at else None,
        )

    return cast(TaskStatusResponseSchema, await sync_to_async(_do)())


# ============================================================================
# 日期候选确认 API（人工确认后才写入重要日期提醒）
# ============================================================================


@router.post("/court-document/task/{task_id}/dates/confirm", response=DateConfirmResponseSchema)
async def confirm_date_candidates(
    request: Any, task_id: int, payload: DateConfirmRequestSchema
) -> DateConfirmResponseSchema:  # pragma: no cover
    """
    批量确认/忽略日期候选

    只有确认过的候选才会写入重要日期提醒；任务已绑定时提醒挂案件日志，
    未绑定时创建独立提醒（记一笔快捕获场景）。已确认项幂等返回原提醒。
    """
    from apps.document_recognition.services import date_candidate_service

    def _do() -> Any:
        results = date_candidate_service.confirm_candidates(
            task_id,
            [item.model_dump() for item in payload.items],
            user=getattr(request, "user", None),
        )
        # 确认会刷新任务级状态，重新读取避免返回旧值
        task = _get_task_service().get_task(task_id)
        return DateConfirmResponseSchema(
            success=all(r["status"] != "error" for r in results),
            date_confirmation_status=task.date_confirmation_status,
            results=[DateConfirmItemOutSchema(**r) for r in results],
        )

    return cast(DateConfirmResponseSchema, await sync_to_async(_do)())


@router.post("/court-document/task/{task_id}/dates/{candidate_id}/revoke", response=DateRevokeResponseSchema)
async def revoke_date_candidate(
    request: Any, task_id: int, candidate_id: int
) -> DateRevokeResponseSchema:  # pragma: no cover
    """
    撤销日期确认

    删除由文书识别创建的提醒（metadata.source=document_recognition），
    候选回到待确认状态；非本功能创建的提醒拒绝撤销。
    """
    from apps.document_recognition.services import date_candidate_service

    def _do() -> Any:
        result = date_candidate_service.revoke_confirmation(task_id, candidate_id)
        return DateRevokeResponseSchema(
            success=True,
            candidate_id=result["candidate_id"],
            status=result["status"],
            reminder_id=result["reminder_id"],
            message=result["message"],
        )

    return cast(DateRevokeResponseSchema, await sync_to_async(_do)())


@router.get("/court-document/tasks/pending", response=list[PendingTaskOutSchema])
async def list_pending_tasks(request: Any, limit: int = 10) -> list[PendingTaskOutSchema]:  # pragma: no cover
    """待确认日期的识别任务（工作台侧栏）"""
    limit = min(limit, 50)

    def _do() -> list[dict[str, Any]]:
        raw: list[dict[str, Any]] = _get_task_service().pending_tasks(limit=limit)
        return raw

    raw = await sync_to_async(_do)()
    return [
        PendingTaskOutSchema(
            task_id=r["task_id"],
            original_filename=r["original_filename"],
            document_type=r["document_type"],
            date_confirmation_status=r["date_confirmation_status"],
            candidate_count=r["candidate_count"],
            case_name=r["case_name"],
            created_at=r["created_at"],
        )
        for r in raw
    ]


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
async def search_cases_for_binding(
    request: Any, q: str = "", limit: int = 20
) -> list[CaseSearchResultSchema]:  # pragma: no cover
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
    raw_results = await sync_to_async(task_service.search_cases_for_binding)(
        search_term=q.strip() if q else "", limit=limit
    )

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
async def manual_bind_case(
    request: Any, task_id: int, payload: ManualBindingRequestSchema
) -> ManualBindingResponseSchema:  # pragma: no cover
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

    # 1. 获取任务并检查是否已绑定（在 sync 上下文中）
    def _check_bound() -> Any:
        task = _get_task_service().get_task(task_id, select_case=True)
        if task.binding_success:
            return ManualBindingResponseSchema(
                success=False,
                case_id=task.case_id,
                case_name=task.case.name if task.case else None,
                case_log_id=task.case_log_id,
                message="任务已绑定到案件",
                error_code="ALREADY_BOUND",
            )
        return None

    already_bound = await sync_to_async(_check_bound)()
    if already_bound:
        return cast(ManualBindingResponseSchema, already_bound)

    # 2. 调用服务层执行手动绑定（返回的是 dataclass，非 ORM 对象）
    binding_service = _get_case_binding_service()
    result = await sync_to_async(binding_service.manual_bind_document_to_case)(
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
async def update_task_info(
    request: Any, task_id: int, payload: UpdateInfoRequestSchema
) -> UpdateInfoResponseSchema:  # pragma: no cover
    """
    手动更新识别信息（案号、关键时间）

    用户发现识别结果不正确时，可手动修改案号和关键时间。

    Args:
        task_id: 识别任务ID
        payload: 包含 case_number 和/或 key_time 的请求体

    Returns:
        更新结果
    """

    def _do() -> Any:
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

    return cast(UpdateInfoResponseSchema, await sync_to_async(_do)())
