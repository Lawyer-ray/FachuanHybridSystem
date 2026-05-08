"""归档模板路径查找。"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from django.conf import settings

if TYPE_CHECKING:
    from apps.contracts.models import Contract

logger = logging.getLogger("apps.contracts.archive")

# 归档模板子类型 → 文件名映射
_ARCHIVE_TEMPLATE_FILES: dict[str, str] = {
    "case_cover": "1-案卷封面.docx",
    "closing_archive_register": "2-结案归档登记表.docx",
    "inner_catalog": "3-卷内目录.docx",
    "lawyer_work_log": "5-律师工作日志.docx",
    "case_summary": "7-办案小结.docx",
}


def get_template_path(template_subtype: str, contract: Contract | None = None) -> Path | None:
    """获取归档模板文件的完整路径。

    优先从 DocumentTemplate 数据库查找匹配合同 case_type 的归档模板，
    找不到再回退到硬编码的公有目录模板。
    """
    db_path = _get_template_path_from_db(template_subtype, contract)
    if db_path:
        return db_path

    filename = _ARCHIVE_TEMPLATE_FILES.get(template_subtype)
    if not filename:
        return None

    base_dir = getattr(settings, "DOCX_TEMPLATE_DIR", None)
    if base_dir:
        template_path = Path(base_dir) / "3-归档模板" / filename
    else:
        template_path = Path(__file__).parent.parent.parent.parent.parent / "documents" / "docx_templates" / "3-归档模板" / filename

    if template_path.exists():
        return template_path

    logger.warning("归档模板文件不存在: %s", template_path)
    return None


def _get_template_path_from_db(template_subtype: str, contract: Contract | None) -> Path | None:
    """从 DocumentTemplate 数据库查找匹配的归档模板路径。"""
    from apps.documents.models import DocumentTemplate, DocumentTemplateType

    templates = DocumentTemplate.objects.filter(
        template_type=DocumentTemplateType.ARCHIVE,
        archive_sub_type=template_subtype,
        is_active=True,
    )

    case_type = getattr(contract, "case_type", None) if contract else None

    for template in templates:
        case_types = template.case_types or []
        if not case_types or "all" in case_types or (case_type and case_type in case_types):
            file_location = template.get_file_location()
            if file_location and Path(file_location).exists():
                return Path(file_location)

    return None
