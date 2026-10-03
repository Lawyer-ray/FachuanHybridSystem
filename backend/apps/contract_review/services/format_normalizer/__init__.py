"""格式规范化服务入口。

路径协议：落库一律存 media 相对路径；规范化产物经 default_storage
落入 ``contract_review/output``，禁止直写 media 目录。
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from apps.core.filesystem.upload_paths import MediaEntity
from apps.core.services.storage_service import sanitize_upload_filename

from .docx_format_normalizer import DocxFormatNormalizer

logger = logging.getLogger(__name__)

__all__ = ["DocxFormatNormalizer", "normalize_to_media"]


def normalize_to_media(  # pragma: no cover
    original_path: Path,
    reference_path: Path | None = None,
    use_llm: bool = True,
    llm_backend: str = "openai_compatible",
) -> str:
    """执行格式规范化并将产物经 default_storage 写入 media，返回相对路径。

    规范化在临时目录内完成，产物最终保存到
    ``{MediaEntity.CONTRACT_REVIEW_OUTPUT}/{清洗后的文件名}``，
    返回 default_storage 实际保存的相对路径（重名时由 storage 自动改名）。
    """
    original = Path(original_path)
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_output = Path(tmp_dir) / f"{original.stem}_规范化{original.suffix}"
        normalizer = DocxFormatNormalizer(original, tmp_output, reference_path=reference_path)
        result_path = normalizer.normalize(use_llm=use_llm, llm_backend=llm_backend)
        content = result_path.read_bytes()
        output_name = sanitize_upload_filename(result_path.name)

    rel_path = f"{MediaEntity.CONTRACT_REVIEW_OUTPUT}/{output_name}"
    saved_name = default_storage.save(rel_path, ContentFile(content))
    logger.info("格式规范化产物已保存: %s", saved_name)
    return saved_name
