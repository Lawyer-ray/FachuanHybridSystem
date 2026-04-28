"""案件导入 API。"""

from __future__ import annotations

import logging
import os
from typing import Any

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.utils import timezone
from ninja import Router, UploadedFile

from apps.oa_filing.models import CaseImportSession
from apps.oa_filing.schemas.case_import_schemas import (
    CaseImportResponse,
    CaseImportResult,
    CaseImportSessionOut,
    CasePreviewItem,
    CasePreviewResponse,
)

logger = logging.getLogger("apps.oa_filing.api.case_import")
router = Router()

# Django-Q 默认 timeout=600 秒；OA 案件导入通常需要更长时间。
# 保持小于默认 retry(1200) 以降低重复执行风险。
CASE_IMPORT_TASK_TIMEOUT_SECONDS = int(os.environ.get("OA_CASE_IMPORT_TASK_TIMEOUT_SECONDS", "1100") or "1100")


@router.post("/case-import", response=CaseImportSessionOut)
def trigger_case_import(request: HttpRequest) -> Any:
    """触发从OA导入案件（预览模式）。

    接收上传的Excel文件，解析案件编号，预览匹配结果。
    """
    import json

    from django.db.models import Q

    from apps.organization.models import AccountCredential

    if not request.user.is_authenticated:
        return {"error": "未登录"}

    lawyer_id = getattr(request.user, "id", None)
    if lawyer_id is None:
        return {"error": "无效用户"}

    # 查找用户的 jtn.com 凭证
    credential = AccountCredential.objects.filter(
        Q(account__icontains="jtn.com") | Q(url__icontains="jtn.com"),
        lawyer_id=lawyer_id,
    ).first()

    if not credential:
        return {"error": "未找到金诚同达OA账号凭证"}

    # 获取上传的文件
    file: UploadedFile | None = request.FILES.get("file")  # type: ignore[assignment]
    if not file:
        return {"error": "未上传文件"}

    # 保存上传的文件
    import uuid
    from pathlib import Path

    from django.conf import settings

    upload_dir = Path(settings.BASE_DIR) / "media" / "oa_imports"  # type: ignore[misc]
    upload_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{uuid.uuid4().hex}_{file.name}"
    file_path = upload_dir / filename

    with open(file_path, "wb") as f:
        for chunk in file.chunks():
            f.write(chunk)

    # 创建导入会话
    from apps.organization.models import Lawyer

    lawyer = Lawyer.objects.get(pk=lawyer_id)
    session = CaseImportSession.objects.create(
        lawyer=lawyer,
        credential=credential,
        status="pending",
        uploaded_filename=file.name or "",
    )

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
def get_case_import_session(request: HttpRequest, session_id: int) -> Any:
    """查询案件导入会话状态。"""
    return CaseImportSession.objects.get(pk=session_id)


@router.post("/case-import/{session_id}/execute")
def execute_case_import(request: HttpRequest, session_id: int) -> HttpResponse:
    """执行案件导入。

    对预览阶段标记为 unmatched 的案件，从OA提取数据并创建/更新合同。
    """
    import json

    if not request.user.is_authenticated:
        return JsonResponse({"error": "未登录"}, status=401)

    lawyer_id = getattr(request.user, "id", None)
    if lawyer_id is None:
        return JsonResponse({"error": "无效用户"}, status=400)

    # 获取会话
    try:
        session = CaseImportSession.objects.get(pk=session_id)
    except CaseImportSession.DoesNotExist:
        return JsonResponse({"error": "会话不存在"}, status=404)

    # 解析请求体
    try:
        body = json.loads(request.body)
        case_nos = body.get("case_nos", [])
        matched_case_nos = body.get("matched_case_nos", [])
    except Exception:
        return JsonResponse({"error": "无效的请求数据"}, status=400)

    if not case_nos:
        return JsonResponse({"error": "案件编号列表为空"}, status=400)

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

    return JsonResponse(
        {
            "message": "导入任务已启动",
            "session_id": session_id,
        }
    )


@router.get("/case-import/{session_id}/preview")
def get_case_import_preview(request: HttpRequest, session_id: int) -> JsonResponse:
    """获取案件导入预览结果。"""
    try:
        session = CaseImportSession.objects.get(pk=session_id)
    except CaseImportSession.DoesNotExist:
        return JsonResponse({"error": "会话不存在"}, status=404)

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

    response = CasePreviewResponse(
        total_cases=total,
        matched=matched,
        unmatched=unmatched,
        preview=preview_items,
    )

    return JsonResponse(response.model_dump())


@router.post("/case-import/{session_id}/batch-create")
def batch_create_cases(request: HttpRequest, session_id: int) -> Any:
    """批量创建案件（通过API调用避免异步上下文问题）。

    接收案件数据列表，在新的HTTP请求中处理，不受Django-Q异步上下文影响。
    """
    import json

    from apps.oa_filing.models import CaseImportSession

    # 获取会话
    try:
        session = CaseImportSession.objects.get(pk=session_id)
    except CaseImportSession.DoesNotExist:
        return {"error": "会话不存在"}

    # 解析请求体
    try:
        body = json.loads(request.body)
        cases = body.get("cases", [])
    except Exception:
        return {"error": "无效的请求数据"}

    from apps.oa_filing.services.case_import_service import CaseImportService

    service = CaseImportService(session)

    results: list[CaseImportResult] = []
    success_count = 0
    skip_count = 0
    error_count = 0

    for case_data in cases:
        case_no = case_data.get("case_no", "")
        try:
            from apps.oa_filing.services.oa_scripts.jtn_case_import import OACaseData

            # 构造 OACaseData
            oa_data = OACaseData(case_no=case_no, keyid="")

            # 创建/更新
            contract_id = service._create_or_update_case(oa_data)

            if contract_id:
                results.append(
                    CaseImportResult(
                        case_no=case_no,
                        status="created",
                        contract_id=contract_id,
                    )
                )
                success_count += 1
            else:
                results.append(
                    CaseImportResult(
                        case_no=case_no,
                        status="error",
                        message="创建合同失败",
                    )
                )
                error_count += 1

        except Exception as exc:
            logger.warning("批量创建案件异常 %s: %s", case_no, exc)
            results.append(
                CaseImportResult(
                    case_no=case_no,
                    status="error",
                    message=str(exc),
                )
            )
            error_count += 1

    # 更新会话
    session.success_count = success_count
    session.skip_count = skip_count
    session.error_count = error_count
    session.save()

    return CaseImportResponse(
        success=success_count,
        failed=error_count,
        skipped=skip_count,
        total=len(cases),
        details=results,
    ).model_dump()
