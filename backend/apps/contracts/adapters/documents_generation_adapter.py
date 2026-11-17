"""documents 文书生成/预览流水线的 contracts 出口。

两个用途：
1. 归档文书生成 / 预览所需的上下文构建器与渲染器（build_* 工厂）；
2. 归档模板路径的 DB 查询（DocumentTemplate 是 documents 的 Model，
   跨模块 Model 查询按四层规范必须留在 documents 侧，contracts 只经此出口调用）。

所有对 documents 的 import 都在函数体内，契约模块不持有模块级跨模块引用。
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from apps.documents.services.generation.pipeline.context_builder import PipelineContextBuilder
    from apps.documents.services.generation.pipeline.preview import DocxPreviewService
    from apps.documents.services.generation.pipeline.renderer import DocxRenderer


def build_pipeline_context_builder() -> PipelineContextBuilder:
    """构造文书上下文构建器（合同/归档/诉讼共用同一实现）。"""
    from apps.documents.services.generation.pipeline import PipelineContextBuilder

    return PipelineContextBuilder()


def build_docx_renderer() -> DocxRenderer:
    """构造 docx 渲染器（docxtpl 渲染 + 占位符硬换行转换）。"""
    from apps.documents.services.generation.pipeline import DocxRenderer

    return DocxRenderer()


def build_docx_preview_service() -> DocxPreviewService:
    """构造 docx 模板预览服务（提取占位符并匹配上下文值）。"""
    from apps.documents.services.generation.pipeline import DocxPreviewService

    return DocxPreviewService()


def find_archive_template_path(archive_sub_type: str, case_type: str | None) -> Path | None:
    """在 documents 的 DocumentTemplate 中查归档模板的实际文件路径。

    匹配口径（与归档模板既有语义一致）：
    - 只取 template_type=ARCHIVE + archive_sub_type 匹配 + is_active=True；
    - 模板的 case_types 为空、含 "all"、或包含合同的 case_type 即视为适用；
    - 文件位置经 Model 的 get_file_location() 解析，取第一个真实存在的文件。

    Returns:
        模板文件路径；无匹配或文件不存在时返回 None（由调用方决定硬编码回退）。
    """
    from apps.documents.models import DocumentTemplate, DocumentTemplateType

    templates = DocumentTemplate.objects.filter(
        template_type=DocumentTemplateType.ARCHIVE,
        archive_sub_type=archive_sub_type,
        is_active=True,
    )

    for template in templates:
        case_types: list[Any] = template.case_types or []
        if not case_types or "all" in case_types or (case_type and case_type in case_types):
            file_location = template.get_file_location()
            if file_location and Path(file_location).exists():
                return Path(file_location)

    return None
