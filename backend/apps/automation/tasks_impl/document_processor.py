"""Module for document processor."""

from __future__ import annotations

from typing import Any

from apps.core.path import Path


def execute_document_process(
    file_path: str, kind: str, limit: int | None = None, preview_page: int | None = None
) -> dict[str, Any]:
    from apps.core.dependencies import build_document_processing_service

    service = build_document_processing_service()
    r = service.process_document(file_path=file_path, kind=kind, limit=limit, preview_page=preview_page)  # type: ignore
    return {"image_url": r.image_url, "text_excerpt": r.text_excerpt}


def execute_document_process_by_path(
    file_path: str,
    limit: int | None = None,
    preview_page: int | None = None,
) -> dict[str, Any]:
    from apps.core.dependencies import build_document_processing_service

    service = build_document_processing_service()
    r = service.process_document_by_path(file_path=file_path, limit=limit, preview_page=preview_page or 1)  # type: ignore
    return {"image_url": r.image_url, "text_excerpt": r.text_excerpt}


def execute_auto_namer_by_path(
    file_path: str,
    prompt: str,
    model: str,
    limit: int | None = None,
    preview_page: int | None = None,
    delete_after: bool = False,
) -> dict[str, Any]:
    from apps.automation.services.document.document_processing import extract_document_content
    from apps.core.interfaces import ServiceLocator

    p = Path(file_path)
    if not p.exists():
        return {"text": None, "ollama_response": None, "error": f"文件不存在: {file_path}"}

    try:
        extraction = extract_document_content(str(p), limit=limit, preview_page=preview_page)  # type: ignore
        text_value = (extraction.text or "").strip()
        if not text_value:
            return {"text": None, "ollama_response": None, "error": "文档中没有提取到文字内容,无法生成命名"}

        service = ServiceLocator.get_auto_namer_service()
        filename_suggestion = service.generate_filename(document_content=text_value, prompt=prompt, model=model)
        return {"text": text_value, "ollama_response": filename_suggestion, "error": None}
    finally:
        if delete_after:
            try:
                from apps.core.config import get_config

                media_root = get_config("django.media_root", None)
                if media_root:
                    root = Path(str(media_root)).resolve()
                    abs_path = p.resolve()
                    abs_path.relative_to(root)
                    abs_path.unlink(missing_ok=True)
            except Exception:
                # 静默处理:文件操作失败不影响主流程
                # 静默处理:文件操作失败不影响主流程
                # 静默处理:文件操作失败不影响主流程

                # 静默处理:文件操作失败不影响主流程
                pass
