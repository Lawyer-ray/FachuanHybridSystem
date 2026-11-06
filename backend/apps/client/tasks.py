"""按需异步任务（通过 TaskServicePort.async_task 调用，非定时任务，无需 _register_schedule）。"""

import logging
from datetime import date
from typing import Any

from apps.client.services.identity_extraction import IdentityExtractionService
from apps.core.services.storage_service import delete_media_file, to_media_abs

logger = logging.getLogger("apps.client")


def execute_identity_doc_recognition(file_path: str, doc_type: str) -> dict[str, Any]:  # pragma: no cover
    abs_path = to_media_abs(file_path)
    try:
        content = abs_path.read_bytes()
        service = IdentityExtractionService()
        result = service.extract(content, doc_type)
        return {
            "doc_type": result.doc_type,
            "extracted_data": result.extracted_data,
            "confidence": result.confidence,
        }
    finally:
        delete_media_file(file_path)


def _resolve_expiry_model() -> str:
    """解析用于证件识别的模型名。

    不硬编码任何厂商/模型：取 LLMProvider 里优先级最高且启用的平台的 ``default_model``。
    运维在 /admin/core/llmprovider/ 换模型或换平台后，本任务自动跟随；
    平台自身配置的 fallback_models 由 llm_service.chat(fallback=True) 处理降级。
    无可用平台时返回空串，调用方退化为纯规则识别（不抛错，避免上传流程被打断）。
    """
    try:
        from apps.core.llm.config import LLMConfig

        return LLMConfig.get_openai_compatible_model() or ""
    except Exception:
        logger.warning("解析证件识别模型失败，退化为纯规则识别", exc_info=True)
        return ""


def recognize_expiry_date_task(doc_id: int, model: str | None = None) -> dict[str, Any]:  # pragma: no cover
    """识别证件到期日期并更新数据库。

    身份证类的「有效期限」是起止区间，正则极易把签发日错当到期日（实测 2025-11-07
    vs 真值 2045-11-07），因此这里显式传入模型让 LLM 参与交叉校验；模型名默认从
    AI 平台配置动态解析，不绑定具体厂商。
    """
    from apps.client.services.client_identity_doc_service import ClientIdentityDocService

    doc_service = ClientIdentityDocService()
    doc = doc_service.get_identity_doc(doc_id)
    # file_path 可为 NULL（待上传占位行），无文件时无到期日期可识别
    if not doc.file_path:
        return {"status": "skipped", "doc_id": doc_id, "expiry_date": None, "reason": "file_not_uploaded"}
    abs_path = to_media_abs(doc.file_path)
    if not abs_path.is_file():
        return {"status": "skipped", "doc_id": doc_id, "expiry_date": None, "reason": "file_missing"}
    content = abs_path.read_bytes()
    service = IdentityExtractionService()
    resolved_model = model if model is not None else _resolve_expiry_model()
    result = service.extract(content, doc.doc_type, model=resolved_model or None)
    expiry_str: str | None = (result.extracted_data or {}).get("expiry_date")
    if expiry_str:
        try:
            expiry_date = date.fromisoformat(expiry_str)
        except ValueError:
            logger.warning("证件到期日格式非法，跳过写库", extra={"doc_id": doc_id, "expiry_date": expiry_str})
            return {"status": "invalid", "doc_id": doc_id, "expiry_date": expiry_str}
        doc_service.update_expiry_date(doc_id, expiry_date)
        return {"status": "success", "doc_id": doc_id, "expiry_date": expiry_str, "model": resolved_model}
    return {"status": "no_expiry_found", "doc_id": doc_id, "expiry_date": None, "model": resolved_model}
