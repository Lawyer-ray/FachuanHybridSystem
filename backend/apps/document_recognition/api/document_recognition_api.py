"""
法院文书智能识别 API

提供文书上传、异步识别和状态查询的 API 端点。

Requirements: 2.1, 2.2, 2.3, 8.1, 8.2, 8.3, 8.4
手动绑定 Requirements: 1.3, 2.3, 3.1
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, cast
from urllib.parse import quote

from asgiref.sync import sync_to_async
from django.conf import settings
from django.utils import timezone
from ninja import File, Form, Router
from ninja.files import UploadedFile
from pydantic import BaseModel, Field

from apps.core.exceptions import ValidationException
from apps.core.security.admin_access import get_request_user
from apps.core.services.storage_service import validate_upload

logger = logging.getLogger("apps.document_recognition")

router = Router(tags=["法院文书识别"])

# 支持的文件格式
SUPPORTED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}

# 任务疑似僵死的阈值（秒）。
#
# 正常识别 1-3 秒；即使 LLM 慢到 90 秒也能在 timeout=600 的 q 任务里跑完。
# 取 180 秒：足够覆盖“网关抖动 + 重试”，又能在真的卡住时比前端 10 分钟硬
# 超时早得多地告知用户。教训（2026-10-28）：本机 Clash 把内网网关当成外网
# 走代理，LLM 持续 502 重试，单次识别实测 439 秒，而界面全程只显示“识别中”。
STALLED_THRESHOLD_SECONDS = 180


def _as_datetime(value: Any) -> datetime | None:
    """把字段值收窄为 datetime；非 datetime（None / 测试替身）一律当缺失。

    为什么要这层：本模块的集成测试会 `patch` task service 返回 MagicMock，
    直接调 `.isoformat()` 会抛 AttributeError，接口从 200 变成 500
    （CI `backend-integration-smoke` 真实踩到）。诊断字段是**附加**信息，
    拿不到就该退化成 None，绝不能让主接口挂掉。
    """
    return value if isinstance(value, datetime) else None


def _elapsed_seconds(task: Any) -> int | None:
    """任务已耗时（秒）。时间字段不可用时返回 None（不抛异常）。"""
    start = _as_datetime(getattr(task, "started_at", None)) or _as_datetime(getattr(task, "created_at", None))
    if start is None:
        return None
    end = _as_datetime(getattr(task, "finished_at", None)) or timezone.now()
    # timezone-aware 与 naive 可能混存（旧数据），统一后再算差
    try:
        delta = end - start
    except TypeError:
        delta = end.replace(tzinfo=None) - start.replace(tzinfo=None)
    return max(0, int(delta.total_seconds()))


def _started_at_iso(task: Any) -> str | None:
    """worker 拉起时刻的 ISO 串；取不到（未开始 / 非 datetime）则 None。"""
    started = _as_datetime(getattr(task, "started_at", None))
    return started.isoformat() if started else None


def _is_stalled(task: Any) -> bool:
    """processing 且已耗时超过阈值 → 疑似僵死。

    只对 processing 判：pending 是正常排队，success/failed 是终态。
    """
    if getattr(task, "status", None) != "processing":
        return False
    elapsed = _elapsed_seconds(task)
    return elapsed is not None and elapsed >= STALLED_THRESHOLD_SECONDS


def _validate_file_format(file: UploadedFile) -> str:
    """验证文件格式。

    解耦（2026-10-19）：扩展名校验委托 ``storage_service.validate_upload``；
    本端点既有的错误码 / 文案（``EMPTY_FILENAME`` / ``UNSUPPORTED_FILE_FORMAT``）
    在边界转换保留，对外 HTTP 行为不变。
    """
    filename = str(getattr(file, "name", "") or "")
    if not filename:
        raise ValidationException(message="文件名不能为空", code="EMPTY_FILENAME", errors={"file": "请提供有效的文件"})

    try:
        validate_upload(file, allowed_extensions=SUPPORTED_EXTENSIONS, max_size_bytes=None)
    except ValidationException as exc:
        if exc.code != "INVALID_FILE_TYPE":
            raise
        ext = Path(filename).suffix.lower()
        raise ValidationException(
            message="不支持的文件格式",
            code="UNSUPPORTED_FILE_FORMAT",
            errors={"file": f"不支持 {ext} 格式，请上传 PDF 或图片"},
        ) from None
    return Path(filename).suffix.lower()


def _save_uploaded_file(file: UploadedFile) -> str:
    """保存上传的文件（委托给 storage_service）"""
    from apps.core.services.storage_service import save_uploaded_file

    rel_path, _ = save_uploaded_file(file, rel_dir="document_recognition")
    saved_path = str(Path(settings.MEDIA_ROOT) / rel_path)
    logger.info("文件已保存: %s", saved_path)
    return saved_path


# 未绑定任务的推荐缓存 TTL（秒）：状态接口被前端轮询，避免每次全库评分
RECOMMENDATION_CACHE_TTL = 300


def _file_media_url(path: str | None) -> str | None:
    """文书文件在 MEDIA_ROOT 下时返回可预览的 media URL（文件名含中文需转义）。"""
    if not path:
        return None
    try:
        rel = Path(path).resolve().relative_to(Path(settings.MEDIA_ROOT).resolve())
    except ValueError:
        return None
    return settings.MEDIA_URL + quote(rel.as_posix())


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


def _suppressed_candidate_rows(task: Any) -> list["SuppressedCandidateOutSchema"]:
    """任务上被日期闸门过滤掉的候选（只做字段装配，判定已在 service 层完成）。

    留痕的意义：律师问「这份文书为什么没生成日期提醒」时，能直接展开看到
    「锚点在尚未产生的裁判文书」这类人话原因，而不是去翻日志。
    """
    from apps.document_recognition.services.date_candidate_service import _reminder_type_label

    rows: list[SuppressedCandidateOutSchema] = []
    for item in task.suppressed_candidates or []:
        if not isinstance(item, dict):
            continue
        rows.append(
            SuppressedCandidateOutSchema(
                due_at=str(item.get("due_at") or ""),
                reminder_type=str(item.get("reminder_type") or ""),
                reminder_type_label=_reminder_type_label(str(item.get("reminder_type") or "other")),
                anchor_document=str(item.get("anchor_document") or ""),
                reason=str(item.get("reason") or ""),
                context_text=str(item.get("context_text") or ""),
            )
        )
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
    # —— 出处（让律师一眼看出这条日期凭什么存在，见 date_candidate_policy）——
    anchor_kind: str = Field(
        "", description="起算锚类型 service_of_self/issue_date_of_self/effective_date/foreign_document/unknown"
    )
    anchor_at: str | None = Field(None, description="起算锚日期（YYYY-MM-DD）")
    anchor_document: str = Field("", description="锚点文书归属 self/other_in_batch/future_document/other_case")
    derivation: str = Field("", description="推算方式 llm_absolute/rule_absolute/rule_period/rule_relative")
    derivation_label: str = Field("", description="推算方式中文标签（后端单一来源，前端直接显示）")
    review_flags: list[str] = Field(default_factory=list, description="复核标记；空列表才允许默认勾选")
    default_checked: bool = Field(False, description="后端算好的默认勾选（前端不再按置信度自行判断）")
    anchor_note: str = Field("", description="起算点人话说明，如「起算点：本份文书送达日 2026-11-24 + 7 天」")
    duplicate_of_id: int | None = Field(None, description="批内去重时指向的权威候选ID")


class SuppressedCandidateOutSchema(BaseModel):
    """被日期闸门过滤掉的候选（留痕，供「为什么没提醒」追问）。"""

    due_at: str = Field("", description="当年算出的日期")
    reminder_type: str = Field("", description="提醒类型")
    reminder_type_label: str = Field("", description="提醒类型名称")
    anchor_document: str = Field("", description="锚点文书归属")
    reason: str = Field("", description="过滤原因（人话）")
    context_text: str = Field("", description="原文上下文")


class CaseRecommendationOutSchema(BaseModel):
    """案件绑定推荐候选"""

    case_id: int = Field(..., description="案件ID")
    case_name: str = Field(..., description="案件名称")
    score: int = Field(..., description="相关度评分")
    reasons: list[str] = Field(default_factory=list, description="评分理由")
    case_numbers: list[str] = Field(default_factory=list, description="案号列表")
    parties: list[str] = Field(default_factory=list, description="当事人列表")
    status: str = Field("", description="案件状态")


class ContactOutSchema(BaseModel):
    """文书联系人（读时从原文提取）"""

    role: str = Field("", description="角色标签（联系人/承办法官等）")
    name: str = Field("", description="联系人姓名（多人以、分隔）")
    phone: str | None = Field(None, description="联系电话")


class TaskStatusResponseSchema(BaseModel):
    """任务状态响应"""

    task_id: int
    status: str
    file_path: str | None = None
    file_url: str | None = Field(None, description="文书预览 URL（media，用于页面内嵌预览）")
    recognition: RecognitionResultSchema | None = None
    binding: BindingResultSchema | None = None
    date_candidates: list[DateCandidateOutSchema] = Field(default_factory=list, description="日期候选列表")
    contacts: list[ContactOutSchema] = Field(
        default_factory=list, description="文书联系人（联系人/联系电话，读时从原文提取）"
    )
    address: str | None = Field(None, description="文书标注地址（读时从原文提取）")
    recommendations: list[CaseRecommendationOutSchema] = Field(
        default_factory=list, description="案件绑定推荐（未绑定时返回）"
    )
    binding_mode: str = Field("standalone", description="绑定模式 standalone/pipeline")
    date_confirmation_status: str | None = Field(None, description="日期确认进度 none/pending/partial/complete")
    suppressed_count: int = Field(0, description="被过滤的候选数（通用文书/锚点指向他文书/选择性申请等）")
    suppressed_items: list[SuppressedCandidateOutSchema] = Field(
        default_factory=list, description="被过滤候选明细（留痕，可展开查看）"
    )
    error_message: str | None = None
    created_at: str
    finished_at: str | None = None
    started_at: str | None = Field(
        None,
        description="任务被 worker 拉起的时刻；processing 但 started_at 为空 = 还排着没跑",
    )
    elapsed_seconds: int | None = Field(
        None,
        description="已耗时（成功用 finished_at，未结束用当前时间）。前端据此显示时长并判定僵死",
    )
    stalled: bool = Field(
        False,
        description="任务疑似僵死：processing 且已耗时超过阈值。前端据此提前给重试出口而不是干等满 10 分钟",
    )


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
# 日期捕获旁线 Schemas（法院短信 → 记一笔）
# ============================================================================


class DateCaptureItemOutSchema(BaseModel):
    """单份文书的送识别结果"""

    document_path: str = ""
    document_name: str = ""
    task_id: int | None = None
    status: str = ""
    action: str = ""
    candidate_count: int = 0
    pending_count: int = 0
    date_confirmation_status: str | None = None
    error_message: str = ""
    reason: str = ""


class DateCaptureOutSchema(BaseModel):
    """法院短信送记一笔的结果（逐份文书）"""

    source_court_sms_id: int
    items: list[DateCaptureItemOutSchema] = Field(default_factory=list)


class SourceTaskOutSchema(BaseModel):
    """来源短信派生出的识别任务摘要（轮询 / 「继续确认」入口用）"""

    task_id: int
    document_path: str = ""
    document_name: str = ""
    status: str = ""
    error_message: str = ""
    classification_hint: str = ""
    document_type: str = ""
    case_number: str = ""
    candidate_count: int = 0
    pending_count: int = 0
    confirmed_count: int = 0
    skipped_count: int = 0
    date_confirmation_status: str = ""


class SourceTasksOutSchema(BaseModel):
    """某条法院短派生出的全部识别任务"""

    source_court_sms_id: int
    tasks: list[SourceTaskOutSchema] = Field(default_factory=list)


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
    llm_model: str | None = Form(None),
) -> TaskSubmitResponseSchema:  # pragma: no cover
    """
    提交文书识别任务（异步）

    上传文书后立即返回任务ID，识别在后台异步执行。
    使用 GET /court-document/task/{task_id} 查询结果。

    source_court_sms_id（管线模式，可选）：来自法院短信管线的文书，
    案件已由短信第一轮绑定，识别只做提取+日期候选，不重复建日志/通知。
    llm_model（可选）：指定识别模型，须在可用模型列表内（GET /llm/models），
    缺省走系统默认模型。
    """
    from apps.core.tasking import submit_task

    filename = str(file.name)
    logger.info("收到文书识别请求: %s, 大小: %s", filename, file.size)

    # 1. 验证文件格式
    _validate_file_format(file)

    # 1.1 验证用户指定模型在可用列表内（列表不可得时放行，交给 LLM 层降级）
    requested_model = (llm_model or "").strip() or None
    if requested_model:
        requested_model = await sync_to_async(_validate_llm_model)(requested_model)

    # 2. 保存文件
    file_path = await sync_to_async(_save_uploaded_file)(file)

    # 3. 创建任务记录 + 提交异步任务
    # timeout 覆盖 LLM 分析（最坏 ~90s）+ 文本提取 + 绑定通知，防止慢识别被 qcluster 默认超时误杀
    task_creator = get_request_user(request)
    prebound = None
    if source_court_sms_id:

        @sync_to_async
        def _load_prebound() -> dict[str, int | None]:
            # 安全（第4轮）：短信绑定案件时按案件 ACL 校验（与法院短信读端点同口径）
            from apps.core.dependencies.business import resolve_request_org_access

            org_access = resolve_request_org_access(request, task_creator)
            return _load_pipeline_prebinding(source_court_sms_id, user=task_creator, org_access=org_access)

        prebound = await _load_prebound()

    def _create_and_submit() -> Any:
        task = _get_task_service().create_task(
            file_path=file_path,
            original_filename=filename,
            source_court_sms_id=source_court_sms_id,
            case_id=prebound["case_id"] if prebound else None,
            case_log_id=prebound["case_log_id"] if prebound else None,
            llm_model=requested_model,
            created_by=task_creator,
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


def _validate_llm_model(model: str) -> str:  # pragma: no cover
    """校验用户指定的模型在可用列表内（列表不可得时放行，交给 LLM 层降级）。"""
    from apps.core.llm.model_list_service import ModelListService

    models = ModelListService().get_models()
    if models and model not in {str(m.get("id", "")) for m in models}:
        raise ValidationException(
            message="不支持的识别模型",
            code="UNKNOWN_LLM_MODEL",
            errors={"llm_model": f"模型 {model} 不在可用模型列表中"},
        )
    return model[:100]


def _load_pipeline_prebinding(
    source_court_sms_id: int,
    *,
    user: Any = None,
    org_access: dict[str, Any] | None = None,
) -> dict[str, int | None]:  # pragma: no cover
    """读取法院短信已完成的绑定（案件+日志），作为识别任务的预绑定。

    短信不存在时 NotFoundError 由全局异常处理器转为 404。
    传入 user 时按案件 ACL 校验（安全审计第4轮：防止借管线模式读取
    无权案件的短信绑定信息）。
    """
    from apps.core.interfaces import ServiceLocator

    court_sms_service = ServiceLocator.get_court_sms_service()
    sms = court_sms_service.get_sms_detail(source_court_sms_id, user=user, org_access=org_access)
    if not getattr(sms, "case_log_id", None):
        raise ValidationException(
            message="该法院短信尚未完成案件绑定，不能走管线模式",
            code="COURT_SMS_NOT_BOUND",
            errors={},
        )
    return {"case_id": sms.case_id, "case_log_id": sms.case_log_id}


@router.post("/court-document/task/{task_id}/retry", response=TaskStatusResponseSchema)
async def retry_task(request: Any, task_id: int) -> TaskStatusResponseSchema:  # pragma: no cover
    """重跑一次识别任务（同一个已上传文件，不重新上传）。

    为什么需要它（2026-10-28 教训）：识别可能因外部因长期挂起或失败
    （当时是代理把内网 LLM 网关当外网，持续 502 重试，单次耗时 439 秒），
    而用户手里只剩“失败/卡死”——原来只能关闭弹窗重新传文件，
    白丢一次上传，也看不出问题到底出在哪。

    只允许重跑 failed / 疑似僵死的 processing 任务：
    - success：结果已落库，重跑会覆盖用户可能已确认的日期候选，拒绝；
    - pending / 正常 processing：它还在正常跑或者排着，重跑会产生双跑，拒绝。

    重跑复用同一个 task 行与同一个已存文件（execute_document_recognition_task
    按 task_id 重新执行），所以不会在库里堆垃圾任务、也不重传字节。
    """
    from apps.core.tasking import submit_task
    from apps.document_recognition.models import DocumentRecognitionStatus

    def _do() -> int:
        task = _get_task_service().get_task(task_id, select_case=True, user=get_request_user(request))

        if task.status == DocumentRecognitionStatus.SUCCESS:
            raise ValidationException(
                message="该任务已识别成功，无需重跑",
                code="TASK_ALREADY_SUCCESS",
                errors={},
            )
        # failed 或 processing-但疑似僵死 → 可重跑；其余（pending / 正常 processing）拒绝
        if task.status == DocumentRecognitionStatus.PROCESSING and not _is_stalled(task):
            raise ValidationException(
                message="任务正在识别中，请等待完成",
                code="TASK_STILL_RUNNING",
                errors={},
            )

        # 重置为 pending：worker 拉起时会自己置回 processing
        # 2026-11-23 审计修复：error_message 是 NOT NULL CharField，写 None 会让这次
        # task.save() 抛 IntegrityError → 「重跑失败任务」接口直接 500。空值用空串
        # （与 services/date_capture_service.py:217 的正确写法同口径）。
        task.status = DocumentRecognitionStatus.PENDING
        task.error_message = ""
        task.started_at = None
        task.finished_at = None
        task.save(update_fields=["status", "error_message", "started_at", "finished_at"])

        submit_task(
            "apps.document_recognition.tasks.execute_document_recognition_task",
            task.id,
            task_name=f"document_recognition_{task.id}_retry",
            timeout=600,
        )
        # task.id 在 ORM 上仍是 Any（get_task 返回 Any），显式 int() 收窄，
        # 否则 mypy 报 no-any-return
        return int(task.id)

    await sync_to_async(_do)()
    # 回读一次：让前端直接拿到重置后的状态，不必自己猜
    return await get_task_status(request, task_id)


@router.get("/court-document/task/{task_id}", response=TaskStatusResponseSchema)
async def get_task_status(request: Any, task_id: int) -> TaskStatusResponseSchema:  # pragma: no cover
    """
    查询识别任务状态和结果

    响应含日期候选（date_candidates）、日期确认进度（date_confirmation_status）；
    任务识别成功且未绑定时附案件绑定推荐（recommendations）。
    归属过滤：普通用户仅可见自己创建的与存量 NULL 的任务，否则 404。
    """

    def _do() -> Any:
        from apps.document_recognition.services import date_candidate_service

        task = _get_task_service().get_task(task_id, select_case=True, user=get_request_user(request))

        # 构建响应
        recognition = None
        binding = None
        date_candidates: list[DateCandidateOutSchema] = []
        suppressed_items: list[SuppressedCandidateOutSchema] = []
        recommendations: list[CaseRecommendationOutSchema] = []
        contacts: list[ContactOutSchema] = []
        address: str | None = None

        if task.status == "success":
            from apps.document_recognition.services.contact_extraction_service import extract_address, extract_contacts

            contacts = [
                ContactOutSchema(role=str(row["role"]), name=str(row["name"]), phone=row["phone"])
                for row in extract_contacts(task.raw_text)
            ]
            address = extract_address(task.raw_text)
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
            suppressed_items = _suppressed_candidate_rows(task)
            if not task.case_log_id:
                reco_rows = _recommendation_rows(task)
                recommendations = [CaseRecommendationOutSchema(**row) for row in reco_rows]

        return TaskStatusResponseSchema(
            task_id=task.id,
            status=task.status,
            started_at=_started_at_iso(task),
            elapsed_seconds=_elapsed_seconds(task),
            stalled=_is_stalled(task),
            file_path=task.renamed_file_path or task.file_path,
            file_url=_file_media_url(task.renamed_file_path or task.file_path),
            recognition=recognition,
            binding=binding,
            date_candidates=date_candidates,
            contacts=contacts,
            address=address,
            recommendations=recommendations,
            binding_mode="pipeline" if task.source_court_sms_id else "standalone",
            date_confirmation_status=task.date_confirmation_status,
            suppressed_count=len(suppressed_items),
            suppressed_items=suppressed_items,
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
    归属过滤：普通用户仅可见自己创建的与存量 NULL 的任务，否则 404。
    """
    from apps.document_recognition.services import date_candidate_service

    def _do() -> Any:
        user = get_request_user(request)
        results = date_candidate_service.confirm_candidates(
            task_id,
            [item.model_dump() for item in payload.items],
            user=user,
        )
        # 确认会刷新任务级状态，重新读取避免返回旧值。重读必须带同一 user：
        # get_task 对 user=None 按普通用户口径只放行存量 NULL 归属的任务，
        # 自己创建的任务会在提醒已写入后被 404 掉
        task = _get_task_service().get_task(task_id, user=user)
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
    归属过滤：普通用户仅可见自己创建的与存量 NULL 的任务，否则 404。
    """
    from apps.document_recognition.services import date_candidate_service

    def _do() -> Any:
        result = date_candidate_service.revoke_confirmation(task_id, candidate_id, user=get_request_user(request))
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
    """待确认日期的识别任务（工作台侧栏，按归属过滤：自己的 + 存量 NULL；管理员全量）"""
    limit = min(limit, 50)

    def _do() -> list[dict[str, Any]]:
        raw: list[dict[str, Any]] = _get_task_service().pending_tasks(limit=limit, user=get_request_user(request))
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
# 日期捕获旁线 API（法院短信 → 记一笔）
# ============================================================================


async def _load_sms_date_capture_source(request: Any, sms_id: int) -> Any:
    """从法院短信取日期捕获上下文（案件/日志/已归档文书路径）。

    读端点口径与法院短信一致：按 CaseAccessPolicy 校验短信所绑案件的访问权
    （docs/harness 安全审计第4轮口径），未绑案件的公共短信全员可读。
    短信不存在 / 无权访问 → NotFoundError → 404。
    """
    from apps.core.dependencies.business import resolve_request_org_access
    from apps.core.interfaces import ServiceLocator
    from apps.document_recognition.services.date_capture_service import DateCaptureSource

    user = get_request_user(request)

    def _do() -> Any:
        # org_access 的解析会查团队关系（ORM），必须在同步线程里做：
        # 直接在 async 视图里调会抛 SynchronousOnlyOperation（真实踩到）。
        org_access = resolve_request_org_access(request, user)
        service = ServiceLocator.get_court_sms_service()
        sms = service.get_sms_detail(sms_id, user=user, org_access=org_access)
        return DateCaptureSource(
            sms_id=int(sms_id),
            case_id=getattr(sms, "case_id", None),
            case_log_id=getattr(sms, "case_log_id", None),
            document_paths=_resolved_document_paths(sms),
        )

    return await sync_to_async(_do)(), user


def _resolved_document_paths(sms: Any) -> list[str]:
    """**这条短信自己的**文书绝对路径，供送识别使用（已排除模板类文书）。

    两个必须与详情接口区分开的点：

    1. ``include_case_log_attachments=False``：案件日志会累积同一案件多次送达的全部
       附件，算进来就会把**别的短信**的判决书当成本短信文书去识别（2026-11-14 实测
       57/63 条短信被错配成同一份判决书），提取出的上诉期会写进错误的上下文。
    2. 排除模板类文书（廉政监督卡 / 送达地址确认书 / 退费申请书…）：它们结构固定、
       从不含期限，送识别只是白烧一次 LLM。

    排除只针对**识别**；详情页仍展示全部文书（律师要看得到）。
    """
    from apps.automation.services.sms.court_sms_document_reference_service import CourtSMSDocumentReferenceService
    from apps.document_recognition.services.document_template_filter import is_template_document

    refs = CourtSMSDocumentReferenceService().collect(sms, include_case_log_attachments=False)
    return [ref.file_path for ref in refs if ref.file_path and not is_template_document(ref.display_name)]


@router.post("/court-document/sms/{sms_id}/capture-dates", response=DateCaptureOutSchema)
async def capture_dates_from_court_sms(
    request: Any, sms_id: int, force: bool = False
) -> DateCaptureOutSchema:  # pragma: no cover
    """把某条法院短信的文书送去「记一笔」识别关键日期（幂等）。

    只产出日期候选，不写入日历——写入必须走 ``/court-document/task/{id}/dates/confirm``
    的人工确认（法律日期错一天的代价不可接受，这是设计底线）。

    - ``force=false``（默认）：已有 pending/processing/success 任务直接复用，
      已有 failed 任务原地重跑——即「打开短信就自动送一次」不会重复烧 LLM。
    - ``force=true``：无条件新建任务（「重新识别」按钮）。

    权限：读短信按案件 ACL（与法院短信详情接口同口径），普通律师即可用；
    写入日历的权限由确认接口按案件 ACL 兜底。

    **旁线纪律**：本接口不修改 CourtSMS 任何字段，识别失败/超时不会影响
    法院短信主线的状态机。
    """
    from apps.document_recognition.services import date_capture_service

    source, user = await _load_sms_date_capture_source(request, sms_id)

    def _do() -> list[Any]:
        return date_capture_service.capture_dates_for_source(source, user=user, force=force)

    items = await sync_to_async(_do)()
    return DateCaptureOutSchema(
        source_court_sms_id=sms_id,
        items=[DateCaptureItemOutSchema(**item.__dict__) for item in items],
    )


@router.get("/court-document/sms/{sms_id}/capture-status", response=SourceTasksOutSchema)
async def get_court_sms_capture_status(request: Any, sms_id: int) -> SourceTasksOutSchema:  # pragma: no cover
    """某条法院短信派生出的识别任务列表（轮询 + 「继续确认」入口）。

    按任务归属过滤：普通律师只看自己创建的（与短信 ACL 叠加），管理员看全量。
    短信本身无权访问时 404。
    """
    from apps.document_recognition.services import date_capture_service

    _, user = await _load_sms_date_capture_source(request, sms_id)

    def _do() -> list[dict[str, Any]]:
        return date_capture_service.list_source_tasks(sms_id, user=user)

    rows = await sync_to_async(_do)()
    return SourceTasksOutSchema(
        source_court_sms_id=sms_id,
        tasks=[SourceTaskOutSchema(**row) for row in rows],
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
async def search_cases_for_binding(
    request: Any, q: str = "", limit: int = 20
) -> list[CaseSearchResultSchema]:  # pragma: no cover
    """
    搜索可绑定的案件

    支持按案件名称、案号、当事人搜索；空关键词返回全部在办案件（创建时间倒序）。

    Args:
        q: 搜索关键词（案件名称、案号、当事人）
        limit: 返回结果数量限制，默认20，默认列表最大200

    Returns:
        匹配的案件列表

    Requirements: 1.3, 2.3
    """
    limit = min(limit, 200)
    task_service = _get_task_service()
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        user = getattr(request, "auth", None)
    from apps.core.security import get_request_access_context

    ctx = get_request_access_context(request)
    raw_results = await sync_to_async(task_service.search_cases_for_binding)(
        search_term=q.strip() if q else "",
        limit=limit,
        user=user,
        org_access=ctx.org_access,
        perm_open_access=ctx.perm_open_access,
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

    归属过滤：普通用户仅可绑定自己创建的与存量 NULL 的任务，否则 404。

    Args:
        task_id: 识别任务ID
        payload: 包含 case_id 的请求体

    Returns:
        绑定结果，包含成功状态、案件信息、日志ID等

    Requirements: 3.1
    """
    task_owner = get_request_user(request)

    # 1. 获取任务并检查是否已绑定（在 sync 上下文中）
    def _check_bound() -> Any:
        task = _get_task_service().get_task(task_id, select_case=True, user=task_owner)
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
        task_id=task_id, case_id=payload.case_id, user=task_owner
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

    归属过滤：普通用户仅可改写自己创建的与存量 NULL 的任务，否则 404。

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
            user=get_request_user(request),
        )
        return UpdateInfoResponseSchema(
            success=True,
            message="保存成功",
            case_number=task.case_number,
            key_time=task.key_time.isoformat() if task.key_time else None,
        )

    return cast(UpdateInfoResponseSchema, await sync_to_async(_do)())
