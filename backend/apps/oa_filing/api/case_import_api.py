"""案件导入 API。"""

from __future__ import annotations

import logging
import os
from typing import Any

from django.http import HttpRequest
from ninja import Router, UploadedFile

from apps.oa_filing.schemas.case_import_schemas import CaseImportSessionOut, CasePreviewItem, CasePreviewResponse

logger = logging.getLogger("apps.oa_filing.api.case_import")
router = Router()

# Django-Q 默认 timeout=600 秒；OA 案件导入通常需要更长时间。
# 保持小于默认 retry(1200) 以降低重复执行风险。
CASE_IMPORT_TASK_TIMEOUT_SECONDS = int(os.environ.get("OA_CASE_IMPORT_TASK_TIMEOUT_SECONDS", "1100") or "1100")


@router.post("/case-import", response=CaseImportSessionOut)
def trigger_case_import(request: HttpRequest) -> Any:  # pragma: no cover
    """触发从OA导入案件（预览模式）。

    接收上传的Excel文件，解析案件编号，预览匹配结果。
    路由挂载时已带 JWTOrSessionAuth，进入本函数即已认证。
    """
    from apps.core.exceptions import ValidationException
    from apps.oa_filing.services.import_session_service import get_credential

    lawyer_id = getattr(request.user, "id", None)
    if lawyer_id is None:  # pragma: no cover — 路由已认证，防御性分支
        raise ValidationException("无效用户", code="INVALID_USER")

    # 查找用户的 OA 凭证
    credential = get_credential(lawyer_id, "金诚同达OA")

    if not credential:
        raise ValidationException("未找到OA账号凭证", code="OA_CREDENTIAL_NOT_FOUND")

    # 获取上传的文件
    file: UploadedFile | None = request.FILES.get("file")  # type: ignore[assignment]
    if not file:
        raise ValidationException("未上传文件", code="FILE_REQUIRED")

    # 保存上传的文件
    import uuid
    from pathlib import Path

    from django.conf import settings
    from django.core.files.storage import default_storage

    filename = f"{uuid.uuid4().hex}_{file.name}"
    saved_name = default_storage.save(f"oa_imports/{filename}", file)
    file_path = Path(settings.MEDIA_ROOT) / saved_name

    # 创建导入会话
    from apps.oa_filing.services.import_session_service import create_case_session, get_lawyer

    lawyer = get_lawyer(lawyer_id)
    session = create_case_session(lawyer=lawyer, credential=credential, uploaded_filename=file.name or "")

    logger.info("创建案件导入会话: session_id=%d filename=%s", session.id, file.name)

    # 启动后台任务进行预览
    from apps.core.tasking import submit_task

    submit_task(
        "apps.oa_filing.tasks.run_case_import_preview_task",
        session.id,
        str(file_path),
        timeout=CASE_IMPORT_TASK_TIMEOUT_SECONDS,
        task_name=f"oa_case_import_preview_{session.id}",
    )

    return session


@router.get("/case-import/{session_id}", response=CaseImportSessionOut)
def get_case_import_session(request: HttpRequest, session_id: int) -> Any:  # pragma: no cover
    """查询案件导入会话状态。"""
    from apps.core.security.admin_access import get_request_user
    from apps.oa_filing.services.import_session_service import get_case_session_or_none

    session = get_case_session_or_none(session_id, lawyer_id=getattr(get_request_user(request), "id", None))
    if session is None:
        from django.http import Http404

        raise Http404("会话不存在")
    return session


@router.post("/case-import/{session_id}/execute")
def execute_case_import(request: HttpRequest, session_id: int) -> dict[str, Any]:  # pragma: no cover
    """执行案件导入。

    对预览阶段标记为 unmatched 的案件，从OA提取数据并创建/更新合同。
    """
    import json

    from apps.core.exceptions import ValidationException

    # 获取会话
    from apps.core.security.admin_access import get_request_user
    from apps.oa_filing.services.import_session_service import get_case_session_or_none

    session = get_case_session_or_none(session_id, lawyer_id=getattr(get_request_user(request), "id", None))
    if session is None:
        from apps.core.exceptions import NotFoundError

        raise NotFoundError(message="会话不存在", code="SESSION_NOT_FOUND", errors={})

    # 解析请求体
    try:
        body = json.loads(request.body)
        case_nos = body.get("case_nos", [])
        matched_case_nos = body.get("matched_case_nos", [])
    except json.JSONDecodeError:
        raise ValidationException("无效的请求数据", code="INVALID_BODY")

    if not case_nos:
        raise ValidationException("案件编号列表为空", code="EMPTY_CASE_NOS")

    # 启动后台任务执行导入
    from apps.core.tasking import submit_task

    submit_task(
        "apps.oa_filing.tasks.run_case_import_task",
        session.id,
        case_nos,
        kwargs={"matched_case_nos": matched_case_nos},
        timeout=CASE_IMPORT_TASK_TIMEOUT_SECONDS,
        task_name=f"oa_case_import_{session.id}",
    )

    logger.info("启动案件导入任务: session_id=%d case_nos=%d", session_id, len(case_nos))

    return {
        "message": "导入任务已启动",
        "session_id": session_id,
    }


@router.get("/case-import/{session_id}/preview", response=CasePreviewResponse)
def get_case_import_preview(request: HttpRequest, session_id: int) -> Any:  # pragma: no cover
    """获取案件导入预览结果。"""
    from apps.core.security.admin_access import get_request_user
    from apps.oa_filing.services.import_session_service import get_case_session_or_none

    session = get_case_session_or_none(session_id, lawyer_id=getattr(get_request_user(request), "id", None))
    if session is None:
        from apps.core.exceptions import NotFoundError

        raise NotFoundError(message="会话不存在", code="SESSION_NOT_FOUND", errors={})

    result_data = session.result_data or {}
    preview_list = result_data.get("preview", [])

    preview_items = [
        CasePreviewItem(
            case_no=item.get("case_no", ""),
            status=item.get("status", "error"),
            existing_contract_id=item.get("existing_contract_id"),
            customer_names=item.get("customer_names", []),
            error_message=item.get("error_message", ""),
        )
        for item in preview_list
    ]

    total = len(preview_items)
    matched = sum(1 for item in preview_items if item.status == "matched")
    unmatched = sum(1 for item in preview_items if item.status == "unmatched")

    return CasePreviewResponse(
        total_cases=total,
        matched=matched,
        unmatched=unmatched,
        preview=preview_items,
    )


@router.post("/case-import/{session_id}/batch-create")
def batch_create_cases(request: HttpRequest, session_id: int) -> Any:  # pragma: no cover
    """批量创建案件。

    同步校验请求数据后，将实际的批量处理逻辑提交给后台任务执行，避免大批次请求阻塞 HTTP 线程。
    """
    import json

    from apps.core.exceptions import NotFoundError, ValidationException

    # 获取会话
    from apps.core.security.admin_access import get_request_user
    from apps.oa_filing.services.import_session_service import get_case_session_or_none

    session = get_case_session_or_none(session_id, lawyer_id=getattr(get_request_user(request), "id", None))
    if session is None:
        raise NotFoundError(message="会话不存在", code="SESSION_NOT_FOUND", errors={})

    # 解析请求体
    try:
        body = json.loads(request.body)
        cases = body.get("cases", [])
    except json.JSONDecodeError:
        raise ValidationException("无效的请求数据", code="INVALID_BODY")

    if not cases:
        raise ValidationException("案件列表为空", code="EMPTY_CASES")

    # 提交后台任务
    from apps.core.tasking import submit_task

    task_id = submit_task(
        "apps.oa_filing.tasks.run_batch_create_cases_task",
        session_id,
        cases,
        timeout=CASE_IMPORT_TASK_TIMEOUT_SECONDS,
        task_name=f"oa_batch_create_cases_{session_id}",
    )

    logger.info("启动批量创建案件任务: session_id=%d cases=%d task_id=%s", session_id, len(cases), task_id)

    return {
        "message": "批量创建任务已启动",
        "task_id": task_id,
        "session_id": session_id,
        "total": len(cases),
    }
