"""客户导入 API。"""

from __future__ import annotations

import logging
import os
from typing import Any

from django.http import HttpRequest
from ninja import Router

from apps.oa_filing.schemas.client_import_schemas import ClientImportSessionOut

logger = logging.getLogger("apps.oa_filing.api.client_import")
router = Router()

# Django-Q 默认 timeout=600 秒；OA 客户导入通常需要更长时间。
# 保持小于默认 retry(1200) 以降低重复执行风险。
CLIENT_IMPORT_TASK_TIMEOUT_SECONDS = int(os.environ.get("OA_CLIENT_IMPORT_TASK_TIMEOUT_SECONDS", "1100") or "1100")


@router.post("/client-import", response=ClientImportSessionOut)
def trigger_client_import(request: HttpRequest) -> Any:  # pragma: no cover
    """触发从OA导入客户。"""
    import json

    from apps.oa_filing.services.import_session_service import get_jtn_credential

    if not request.user.is_authenticated:
        return {"error": "未登录"}

    lawyer_id = getattr(request.user, "id", None)
    if lawyer_id is None:
        return {"error": "无效用户"}

    headless = True
    limit: int | None = None
    raw_body = (request.body or b"").strip()
    if raw_body:
        try:
            payload = json.loads(raw_body)
            if isinstance(payload, dict):
                if "headless" in payload:
                    headless = bool(payload.get("headless"))
                if "limit" in payload:
                    raw_limit = payload.get("limit")
                    if raw_limit not in (None, "", 0, "0"):
                        try:
                            parsed_limit = int(raw_limit)  # type: ignore[arg-type]
                        except (TypeError, ValueError):
                            return {"error": "导入数量必须是大于 0 的整数"}
                        if parsed_limit <= 0:
                            return {"error": "导入数量必须是大于 0 的整数"}
                        limit = parsed_limit
        except json.JSONDecodeError:
            # 非 JSON 请求体时使用默认值
            headless = True
            limit = None

    # 查找用户的 jtn.com 凭证
    credential = get_jtn_credential(lawyer_id)

    if not credential:
        return {"error": "未找到金诚同达OA账号凭证"}

    # 创建导入会话
    from apps.oa_filing.services.import_session_service import create_client_session, get_lawyer

    lawyer = get_lawyer(lawyer_id)
    session = create_client_session(lawyer=lawyer, credential=credential)

    # 启动后台任务
    from apps.core.tasking import submit_task

    submit_task(
        "apps.oa_filing.tasks.run_client_import_task",
        session.id,
        kwargs={"headless": headless, "limit": limit},
        timeout=CLIENT_IMPORT_TASK_TIMEOUT_SECONDS,
        task_name=f"oa_client_import_{session.id}",
    )

    logger.info("创建客户导入会话: session_id=%d headless=%s limit=%s", session.id, headless, limit)
    return session


@router.get("/client-import/{session_id}", response=ClientImportSessionOut)
def get_client_import_session(request: HttpRequest, session_id: int) -> Any:  # pragma: no cover
    """查询客户导入会话状态。"""
    from apps.oa_filing.services.import_session_service import get_client_session_or_none

    session = get_client_session_or_none(session_id)
    if session is None:
        from django.http import Http404

        raise Http404("会话不存在")
    return session


@router.post("/client-import/{session_id}/batch-create")
def batch_create_clients(request: HttpRequest, session_id: int) -> dict[str, Any]:  # pragma: no cover
    """批量创建客户。

    同步校验请求数据后，将实际的批量处理逻辑提交给后台任务执行，避免大批次请求阻塞 HTTP 线程。
    """
    from django.http import JsonResponse

    from apps.oa_filing.services.import_session_service import get_client_session_or_none

    # 获取会话
    session = get_client_session_or_none(session_id)
    if session is None:
        return JsonResponse({"error": "会话不存在"}, status=404)  # type: ignore[return-value]

    # 解析请求体
    import json

    try:
        body = json.loads(request.body)
        customers = body.get("customers", [])
    except json.JSONDecodeError:
        return JsonResponse({"error": "无效的请求数据"}, status=400)  # type: ignore[return-value]

    if not customers:
        return JsonResponse({"error": "客户列表为空"}, status=400)  # type: ignore[return-value]

    # 提交后台任务
    from apps.core.tasking import submit_task

    task_id = submit_task(
        "apps.oa_filing.tasks.run_batch_create_clients_task",
        session_id,
        customers,
        timeout=CLIENT_IMPORT_TASK_TIMEOUT_SECONDS,
        task_name=f"oa_batch_create_clients_{session_id}",
    )

    logger.info("启动批量创建客户任务: session_id=%d customers=%d task_id=%s", session_id, len(customers), task_id)

    return {  # type: ignore[return-value]
        "message": "批量创建任务已启动",
        "task_id": task_id,
        "session_id": session_id,
        "total": len(customers),
    }


def _enrich_enterprise_data(company_name: str) -> dict[str, Any] | None:
    """调用企业数据API补全企业信息。"""
    from apps.client.services.client_enterprise_prefill_service import ClientEnterprisePrefillService

    try:
        service = ClientEnterprisePrefillService()

        # 1. 搜索企业获取company_id
        search_result = service.search_companies(keyword=company_name, limit=5)
        items = search_result.get("items", [])

        if not items:
            logger.info("  -> 未找到企业: %s", company_name)
            return None

        # 2. 找到最匹配的企业
        matched_item = None
        for item in items:
            item_name = item.get("company_name", "")
            if item_name == company_name:
                matched_item = item
                break

        if not matched_item:
            # 如果没有精确匹配，取第一个
            matched_item = items[0]
            logger.info("  -> 未精确匹配，使用第一个候选: %s", matched_item.get("company_name"))

        company_id = matched_item.get("company_id")
        if not company_id:
            return None

        # 3. 获取企业详细信息
        prefill_result = service.build_prefill(company_id=company_id)
        prefill = prefill_result.get("prefill", {})

        logger.info(
            "  -> 获取到企业信息: %s, id_number=%s, phone=%s",
            prefill.get("name"),
            prefill.get("id_number"),
            prefill.get("phone"),
        )

        return prefill  # type: ignore[no-any-return]

    except Exception as exc:
        logger.warning("  -> 企业数据查询失败: %s", exc)
        return None
