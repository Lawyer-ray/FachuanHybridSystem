"""
自动命名工具API
独立的API模块
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from ninja import File, Router
from ninja.files import UploadedFile

from ..schemas import AutoToolProcessIn, AutoToolProcessOut
from ..services.ai.ollama_client import chat as ollama_chat
from ..services.ai.prompts import DEFAULT_FILENAME_PROMPT
from ..services.document.document_processing import process_uploaded_document

router = Router(tags=["Auto Namer"])


def _get_auto_namer_service() -> Any:
    """
    工厂函数：创建自动命名服务实例

    通过ServiceLocator获取自动命名服务，确保依赖解耦

    Returns:
        IAutoNamerService 实例
    """
    from apps.core.interfaces import ServiceLocator

    return ServiceLocator.get_auto_namer_service()


@router.post("/process", response=AutoToolProcessOut)
def auto_namer_process(
    request: Any,
    file: UploadedFile = File(...),
    prompt: str = DEFAULT_FILENAME_PROMPT,
    model: str = "qwen3:0.6b",
    limit: int | None = None,
    preview_page: int | None = None,
) -> Any:
    """自动命名工具API"""
    service = _get_auto_namer_service()
    result = service.process_document_for_naming(
        uploaded_file=file, prompt=prompt, model=model, limit=limit, preview_page=preview_page
    )
    return AutoToolProcessOut(
        text=result.get("text"), ollama_response=result.get("ollama_response"), error=result.get("error")
    )


@router.post("/process-by-path", response=AutoToolProcessOut)
def auto_namer_process_by_path(request: Any, payload: AutoToolProcessIn) -> Any:
    """通过路径处理自动命名工具"""
    service = _get_auto_namer_service()
    from pathlib import Path

    file_path = Path(payload.file_path)
    if not file_path.exists():
        return AutoToolProcessOut(text=None, ollama_response=None, error=f"文件不存在: {payload.file_path}")
    from ..services.document.document_processing import extract_document_content

    extraction = extract_document_content(
        file_path.as_posix(), limit=payload.limit, preview_page=payload.preview_page or 1
    )
    text_value = (extraction.text or "").strip()
    if not text_value:
        return AutoToolProcessOut(text=None, ollama_response=None, error="文档中没有提取到文字内容，无法生成命名")
    filename_suggestion = service.generate_filename(
        document_content=text_value, prompt=payload.prompt, model=payload.model
    )
    return AutoToolProcessOut(text=text_value, ollama_response=filename_suggestion, error=None)
