"""Business logic services."""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import date

from apps.core.services.filename_template_service import FilenameTemplateService

# 半角/全角括号字符类：文件名模板默认产出全角「（）」，但模板可配置、历史文件也可能
# 是半角「()」，版本号探测必须两种都兼容，否则 max_version 恒 0、重生成会覆盖旧文件。
_OPEN_PAREN_CLASS = f"[{re.escape('(')}（]"
_CLOSE_PAREN_CLASS = f"[{re.escape(')')}）]"


def _today_compact() -> str:
    return date.today().strftime("%Y%m%d")


def _normalize_version(version: str) -> str:
    """将 'V1' 或 'V1.0' 等格式转为纯数字 '1'"""
    return re.sub(r"^V", "", version, flags=re.IGNORECASE)


def find_max_doc_version(*, names: Iterable[str], doc_type: str, case_name: str, date_str: str) -> int:
    """在既有文件名列表中探测「doc_type（case_name）V数字_日期.docx」的最大版本号。

    供合同/补充协议生成服务的 _get_next_version 共用（原先两处各写一份正则，一处半角
    一处全角互相不兼容）。括号同时匹配全角（）与半角()，无匹配返回 0（调用方 +1 得下一版）。
    """
    pattern = re.compile(
        rf"^{re.escape(doc_type)}{_OPEN_PAREN_CLASS}{re.escape(case_name)}{_CLOSE_PAREN_CLASS}"
        rf"V(\d+)_{date_str}\.docx$"
    )
    max_version = 0
    for name in names:
        match = pattern.match(name)
        if match:
            max_version = max(max_version, int(match.group(1)))
    return max_version


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
