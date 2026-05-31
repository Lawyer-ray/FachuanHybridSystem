"""Business logic services."""

from __future__ import annotations

import re
from datetime import date

from apps.core.services.filename_template_service import FilenameTemplateService

def _today_compact() -> str:
    return date.today().strftime("%Y%m%d")

def _normalize_version(version: str) -> str:
    """将 'V1' 或 'V1.0' 等格式转为纯数字 '1'"""
    return re.sub(r"^V", "", version, flags=re.IGNORECASE)

def contract_docx_filename(*, template_name: str, contract_name: str, version: str = "V1") -> str:
    template_prefix = re.sub(r"\.(docx?|doc)$", "", template_name or "合同", flags=re.IGNORECASE)
    contract_display = contract_name or "未命名合同"
    return (
        FilenameTemplateService.render_generated_doc(
            doc_type=template_prefix,
            case_name=contract_display,
            version=_normalize_version(version),
            date=_today_compact(),
        )
        + ".docx"
    )

def supplementary_agreement_docx_filename(*, agreement_name: str, contract_name: str, version: str = "V1") -> str:
    agreement_display = agreement_name or "补充协议"
    contract_display = contract_name or "未命名合同"
    return (
        FilenameTemplateService.render_generated_doc(
            doc_type=agreement_display,
            case_name=contract_display,
            version=_normalize_version(version),
            date=_today_compact(),
        )
        + ".docx"
    )
