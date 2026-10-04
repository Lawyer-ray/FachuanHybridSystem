"""
文档处理工具API
独立的API模块
"""

from pathlib import Path
from typing import Any

from django.conf import settings
from ninja import Router

from apps.automation.schemas import DocumentProcessIn, DocumentProcessOut
from apps.core.exceptions import ValidationException
from apps.core.infrastructure.throttling import rate_limit_from_settings

router = Router(tags=["文档处理"])


def _get_document_processor_service() -> Any:
    from apps.core.dependencies import build_document_processing_service

    return build_document_processing_service()


def _resolve_media_file_path(file_path: str) -> str:
    """将用户提供的文件路径收敛到 MEDIA_ROOT 内，防止越界读取。"""
    media_root = Path(settings.MEDIA_ROOT).resolve()
    raw = Path(file_path).expanduser()
    resolved = raw.resolve() if raw.is_absolute() else (media_root / raw).resolve()
    if not resolved.is_relative_to(media_root):
        raise ValidationException(
            message="文件路径必须位于媒体目录内",
            code="INVALID_FILE_PATH",
            errors={"file_path": file_path},
        )
    return str(resolved)


def _extract_by_path(payload: DocumentProcessIn) -> DocumentProcessOut:
    service = _get_document_processor_service()
    resolved = _resolve_media_file_path(payload.file_path)
    result = service.extract_document_content_by_path(
        file_path=resolved, limit=payload.limit, preview_page=payload.preview_page
    )
    return DocumentProcessOut(image_url=result.get("image_url"), text_excerpt=result.get("text"))


@router.post("/process", response=DocumentProcessOut)
@rate_limit_from_settings("UPLOAD")
def process_document(request: Any, payload: DocumentProcessIn) -> DocumentProcessOut:  # pragma: no cover
    """文档处理API（仅管理员：按路径读取 MEDIA_ROOT 内文件内容属于跨租户读取面）"""
    # 安全：按路径读取文件内容属于跨租户读取面，收敛为管理员专用
    from apps.core.security.admin_access import ensure_admin_request

    ensure_admin_request(request)
    return _extract_by_path(payload)


@router.post("/process-by-path", response=DocumentProcessOut)
@rate_limit_from_settings("UPLOAD")
def process_document_by_path(request: Any, payload: DocumentProcessIn) -> DocumentProcessOut:  # pragma: no cover
    """通过路径处理文档（仅管理员：可读取 MEDIA_ROOT 内任意文件内容）"""
    # 安全：按路径读取文件内容属于跨租户读取面，收敛为管理员专用
    from apps.core.security.admin_access import ensure_admin_request

    ensure_admin_request(request)
    return _extract_by_path(payload)
