"""
诉讼文书生成 API

提供起诉状和答辩状的生成接口.
"""

import logging

from django.utils.translation import gettext_lazy as _
import time
from typing import Any

from ninja import Router, Schema

from apps.core.auth import JWTOrSessionAuth
from apps.core.exceptions import ValidationException
from apps.core.infrastructure.throttling import rate_limit_from_settings

logger = logging.getLogger("apps.documents.api")
router = Router(auth=JWTOrSessionAuth())


def _get_litigation_generation_service() -> Any:
    """工厂函数:创建 LitigationGenerationService 实例"""
    from apps.documents.services.generation.litigation_generation_service import LitigationGenerationService

    return LitigationGenerationService()


class ComplaintRequest(Schema):
    """起诉状生成请求"""

    cause_of_action: str
    plaintiff: str
    defendant: str
    litigation_request: str
    facts_and_reasons: str
    case_id: int | None = None


class DefenseRequest(Schema):
    """答辩状生成请求"""

    cause_of_action: str
    plaintiff: str
    defendant: str
    defense_opinion: str
    defense_reasons: str
    case_id: int | None = None


@router.post("/litigation/complaint/generate", response=dict[str, Any])
def generate_complaint(request: Any, data: ComplaintRequest) -> Any:
    """
    生成起诉状

    使用 LangChain LCEL 链生成起诉状文书.

    Args:
        data: 起诉状生成请求数据

    Returns:
        起诉状生成结果(JSON 格式)

    Requirements: 7.1, 2.3, 4.4
    """
    start_time = time.time()
    service = _get_litigation_generation_service()

    case_data = {
        "cause_of_action": data.cause_of_action,
        "plaintiff": data.plaintiff,
        "defendant": data.defendant,
        "litigation_request": data.litigation_request,
        "facts_and_reasons": data.facts_and_reasons,
    }
    result = service.generate_complaint(case_data)

    duration_ms = int((time.time() - start_time) * 1000)
    logger.info(
        "complaint_generated",
        extra={"case_id": data.case_id, "duration_ms": duration_ms, "cause_of_action": data.cause_of_action},
    )
    return {"success": True, "data": result.model_dump(), "duration_ms": duration_ms}


@router.post("/litigation/defense/generate", response=dict[str, Any])
def generate_defense(request: Any, data: DefenseRequest) -> Any:
    """
    生成答辩状

    使用 LangChain LCEL 链生成答辩状文书.

    Args:
        data: 答辩状生成请求数据

    Returns:
        答辩状生成结果(JSON 格式)

    Requirements: 7.1, 2.3, 4.4
    """
    start_time = time.time()
    service = _get_litigation_generation_service()

    case_data = {
        "cause_of_action": data.cause_of_action,
        "plaintiff": data.plaintiff,
        "defendant": data.defendant,
        "defense_opinion": data.defense_opinion,
        "defense_reasons": data.defense_reasons,
    }
    result = service.generate_defense(case_data)
    duration_ms = int((time.time() - start_time) * 1000)
    logger.info(
        "defense_generated",
        extra={"case_id": data.case_id, "duration_ms": duration_ms, "cause_of_action": data.cause_of_action},
    )
    return {"success": True, "data": result.model_dump(), "duration_ms": duration_ms}


@router.post("/cases/{case_id}/litigation/{litigation_type}/download")
@rate_limit_from_settings("EXPORT", by_user=True)
def download_litigation_document(request: Any, case_id: int, litigation_type: str) -> Any:
    """
    生成并下载诉讼文档

    Args:
        case_id: 案件 ID
        litigation_type: 诉讼类型 (complaint=起诉状, defense=答辩状)

    Returns:
        文档文件下载

    Requirements: 7.1, 2.3, 4.4
    """
    from .download_response_factory import build_download_response

    start_time = time.time()
    service = _get_litigation_generation_service()
    if litigation_type == "complaint":
        filename, doc_bytes = service.generate_complaint_document(case_id)
    elif litigation_type == "defense":
        filename, doc_bytes = service.generate_defense_document(case_id)
    else:
        raise ValidationException(message=_("不支持的诉讼类型: %(t)s") % {"t": litigation_type}, code="INVALID_LITIGATION_TYPE")

    duration_ms = int((time.time() - start_time) * 1000)
    logger.info(
        "litigation_document_generated",
        extra={"case_id": case_id, "litigation_type": litigation_type, "duration_ms": duration_ms},
    )
    return build_download_response(
        content=doc_bytes,
        filename=filename,
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
