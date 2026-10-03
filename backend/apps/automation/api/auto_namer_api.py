"""
自动命名工具API
独立的API模块
"""

from typing import Any

from asgiref.sync import sync_to_async
from ninja import File, Router
from ninja.files import UploadedFile

from apps.automation.schemas import AutoToolProcessIn, AutoToolProcessOut
from apps.automation.services.ai.prompts import DEFAULT_FILENAME_PROMPT
from apps.core.infrastructure.throttling import rate_limit_from_settings

router = Router(tags=["自动命名"])


def _get_auto_namer_service() -> Any:
    from apps.core.dependencies import build_auto_namer_service

    return build_auto_namer_service()


@router.post("/process", response=AutoToolProcessOut)
@rate_limit_from_settings("UPLOAD")
async def auto_namer_process(  # pragma: no cover
    request: Any,
    file: UploadedFile = File(...),
    prompt: str = DEFAULT_FILENAME_PROMPT,
    # 留空走 AI 平台默认模型（/admin/core/llmprovider/）；Ollama 已下线
    model: str = "",
    limit: int | None = None,
    preview_page: int | None = None,
) -> AutoToolProcessOut:
    """自动命名工具API"""
    # 使用工厂函数获取服务
    service = _get_auto_namer_service()

    # 调用服务处理文档并生成命名建议
    result = await sync_to_async(service.process_document_for_naming, thread_sensitive=False)(
        uploaded_file=file, prompt=prompt, model=model, limit=limit, preview_page=preview_page
    )

    return AutoToolProcessOut(
        text=result.get("text"), llm_response=result.get("llm_response"), error=result.get("error")
    )


@router.post("/process-by-path", response=AutoToolProcessOut)
@rate_limit_from_settings("UPLOAD")
async def auto_namer_process_by_path(
    request: Any, payload: AutoToolProcessIn
) -> AutoToolProcessOut:  # pragma: no cover
    """通过路径处理自动命名工具（仅管理员：可读取 MEDIA_ROOT 内任意文件内容）"""
    # 安全：按路径读取文件内容属于跨租户读取面，收敛为管理员专用
    from apps.core.security.admin_access import ensure_admin_request

    ensure_admin_request(request)

    # 使用工厂函数获取服务
    service = _get_auto_namer_service()

    # 从文件路径提取文档内容
    from pathlib import Path

    file_path = Path(payload.file_path)
    # 安全：验证路径在 MEDIA_ROOT 内，防止路径遍历攻击
    from django.conf import settings

    media_root = Path(settings.MEDIA_ROOT).resolve()
    try:
        resolved_path = file_path.resolve()
        if not resolved_path.is_relative_to(media_root):
            return AutoToolProcessOut(text=None, llm_response=None, error="无效的文件路径")
    except (ValueError, OSError):
        return AutoToolProcessOut(text=None, llm_response=None, error="无效的文件路径")

    if not file_path.exists():
        return AutoToolProcessOut(
            text=None,
            llm_response=None,
            error="文件不存在: %(path)s" % {"path": payload.file_path},
        )

    from apps.automation.services.document.document_processing import extract_document_content

    extraction = await sync_to_async(extract_document_content, thread_sensitive=False)(
        file_path.as_posix(), limit=payload.limit, preview_page=payload.preview_page
    )

    text_value = (extraction.text or "").strip()
    if not text_value:
        return AutoToolProcessOut(text=None, llm_response=None, error="文档中没有提取到文字内容，无法生成命名")

    # 调用服务生成文件名
    filename_suggestion = await sync_to_async(service.generate_filename, thread_sensitive=False)(
        document_content=text_value, prompt=payload.prompt, model=payload.model
    )

    return AutoToolProcessOut(text=text_value, llm_response=filename_suggestion, error=None)
