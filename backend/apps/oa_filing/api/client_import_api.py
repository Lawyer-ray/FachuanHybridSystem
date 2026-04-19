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
def trigger_client_import(request: HttpRequest) -> Any:
    """触发从OA导入客户。"""
    import json

    from django.db.models import Q

    from apps.oa_filing.models import ClientImportSession
    from apps.organization.models import AccountCredential

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
                            parsed_limit = int(raw_limit)
                        except (TypeError, ValueError):
                            return {"error": "导入数量必须是大于 0 的整数"}
                        if parsed_limit <= 0:
                            return {"error": "导入数量必须是大于 0 的整数"}
                        limit = parsed_limit
        except Exception:
            # 非 JSON 请求体时使用默认值
            headless = True
            limit = None

    # 查找用户的 jtn.com 凭证
    credential = AccountCredential.objects.filter(
        Q(account__icontains="jtn.com") | Q(url__icontains="jtn.com"),
        lawyer_id=lawyer_id,
    ).first()

    if not credential:
        return {"error": "未找到金诚同达OA账号凭证"}

    # 创建导入会话
    from apps.organization.models import Lawyer

    lawyer = Lawyer.objects.get(pk=lawyer_id)
    session = ClientImportSession.objects.create(
        lawyer=lawyer,
        credential=credential,
        status="pending",
    )

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
def get_client_import_session(request: HttpRequest, session_id: int) -> Any:
    """查询客户导入会话状态。"""
    from apps.oa_filing.models import ClientImportSession

    return ClientImportSession.objects.get(pk=session_id)


@router.post("/client-import/{session_id}/batch-create")
def batch_create_clients(request: HttpRequest, session_id: int) -> dict[str, Any]:
    """批量创建客户（通过API调用避免异步上下文问题）。

    接收一个客户数据列表，在新的HTTP请求中处理，不受Django-Q异步上下文影响。
    对于企业客户且id_number为空的，自动调用企业数据API补全信息。
    """
    from django.http import JsonResponse

    from apps.client.models import Client
    from apps.oa_filing.models import ClientImportSession

    # 获取会话
    try:
        session = ClientImportSession.objects.get(pk=session_id)
    except ClientImportSession.DoesNotExist:
        return JsonResponse({"error": "会话不存在"}, status=404)

    # 解析请求体
    import json

    try:
        body = json.loads(request.body)
        customers = body.get("customers", [])
    except Exception:
        return JsonResponse({"error": "无效的请求数据"}, status=400)

    success_count = 0
    skip_count = 0
    error_count = 0
    enriched_count = 0  # 通过企业数据API补全的数量
    errors = []

    for i, customer in enumerate(customers):
        try:
            name = customer.get("name", "").strip()
            client_type = customer.get("client_type", "natural")
            phone = customer.get("phone") or ""
            address = customer.get("address") or ""
            id_number_raw = customer.get("id_number")
            # 空字符串转为None，避免唯一约束冲突
            id_number = id_number_raw if id_number_raw and id_number_raw.strip() else None
            legal_representative = customer.get("legal_representative") or ""

            if not name:
                continue

            logger.info("[%d/%d] 处理: %s (type=%s)", i + 1, len(customers), name, client_type)

            # 检查是否已存在（按名称去重）
            if Client.objects.filter(name=name).exists():
                skip_count += 1
                continue

            # 对于自然人，还要检查id_number是否已存在（避免身份证号冲突）
            if client_type == "natural" and id_number:
                if Client.objects.filter(id_number=id_number).exists():
                    skip_count += 1
                    continue

            # 对于企业客户且id_number为空的，调用企业数据API补全（暂时禁用，加快导入速度）
            # if client_type == "legal" and not id_number:
            #     prefill = _enrich_enterprise_data(name)
            #     if prefill:
            #         phone = prefill.get("phone") or phone
            #         address = prefill.get("address") or address
            #         id_number = prefill.get("id_number") or id_number
            #         legal_representative = prefill.get("legal_representative") or legal_representative
            #         enriched_count += 1
            #         logger.info("  -> 企业数据补全成功: phone=%s, address=%s", phone, address)

            # 创建客户
            Client.objects.create(
                name=name,
                client_type=client_type,
                phone=phone,
                address=address,
                id_number=id_number,
                legal_representative=legal_representative,
                is_our_client=True,
            )
            success_count += 1

        except Exception as exc:
            error_count += 1
            errors.append({"name": customer.get("name", ""), "error": str(exc)})
            logger.warning("  -> 创建客户失败: %s", exc)

    # 更新会话状态
    session.success_count = success_count
    session.skip_count = skip_count
    session.save()

    logger.info(
        "导入完成: 成功=%d, 跳过=%d, 错误=%d, 企业数据补全=%d", success_count, skip_count, error_count, enriched_count
    )

    return JsonResponse(
        {
            "success_count": success_count,
            "skip_count": skip_count,
            "error_count": error_count,
            "enriched_count": enriched_count,
            "errors": errors[:10],  # 最多返回10个错误
        }
    )


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

        return prefill

    except Exception as exc:
        logger.warning("  -> 企业数据查询失败: %s", exc)
        return None
