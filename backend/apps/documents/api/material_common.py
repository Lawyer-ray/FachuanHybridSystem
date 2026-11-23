"""
授权 / 保全材料下载共用的「ACL + 落盘」口径

S01-04（2026-11-23 二轮审计）：原实现把 `_require_case_contract` / `_save_or_download`
逐字复制在 `authorization_material_api` 与 `preservation_materials_api` 两份，唯一差异是
多栏兜底传的 endpoint 常量。任何一处收紧（ACL 参数、subdir 默认值、写盘审计）都会漏改
另一处，ACL 漂移直接等于越权；现在只保留这一份实现，两个 API 模块各自传入 endpoint。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from asgiref.sync import sync_to_async

from .download_response_factory import build_download_response

logger = logging.getLogger("apps.documents.api")


def get_contract_folder_binding_service() -> Any:
    """工厂函数:获取合同文件夹绑定服务（落盘用）"""
    from apps.core.interfaces import ServiceLocator

    return ServiceLocator.get_contract_folder_binding_service()


async def require_case_contract(request: Any, case_id: int) -> Any:
    """获取案件绑定的合同 ID，无合同则返回 None。同时验证用户对案件的访问权限。"""
    from apps.cases.services.case.case_access_policy import CaseAccessPolicy
    from apps.core.security import get_request_access_context
    from apps.documents.services.case_contract_query import get_case_contract_info

    ctx = get_request_access_context(request)
    await sync_to_async(CaseAccessPolicy().ensure_access_ctx)(case_id=case_id, ctx=ctx)

    case = await sync_to_async(get_case_contract_info)(case_id)
    if not case:
        return None
    return case


async def save_or_download(
    request: Any,
    *,
    endpoint: str,
    binding_service_getter: Callable[[], Any],
    contract_id: int | None,
    case_id: int,
    content: bytes,
    filename: str,
    content_type: str,
    subdir_key: str = "contract_documents",
) -> Any:
    """如有合同文件夹绑定则保存文件，否则返回下载响应。"""
    from apps.agent.services.approval.write_guard import ensure_request_not_multi_lane

    # 入口 C 兜底：agent 多栏并答时不得向合同文件夹落盘（这一支会真写文件）
    await ensure_request_not_multi_lane(request, endpoint=endpoint)

    if contract_id is None:
        return build_download_response(content=content, filename=filename, content_type=content_type)

    binding_service = binding_service_getter()
    saved_path = await sync_to_async(binding_service.save_file_for_contract)(
        contract_id=contract_id,
        file_content=content,
        file_name=filename,
        subdir_key=subdir_key,
    )
    if saved_path:
        logger.info(
            "文件已保存到合同文件夹",
            extra={"case_id": case_id, "contract_id": contract_id, "file_name": filename, "path": saved_path},
        )
        return {
            "success": True,
            "message": f"文件已保存到: {saved_path}",
            "filename": filename,
            "folder_path": saved_path,
        }

    return build_download_response(content=content, filename=filename, content_type=content_type)
