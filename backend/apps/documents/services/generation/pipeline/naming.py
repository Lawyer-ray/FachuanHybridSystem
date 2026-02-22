"""Business logic services."""

from __future__ import annotations

import re
from datetime import date


def _today_compact() -> str:
    return date.today().strftime("%Y%m%d")


def contract_docx_filename(*, template_name: str, contract_name: str, version: str = "V1") -> str:
    template_prefix = re.sub(r"\.(docx?|doc)$", "", template_name or "合同", flags=re.IGNORECASE)
    contract_display = contract_name or "未命名合同"
    return f"{template_prefix}（{contract_display}）{version}_{_today_compact()}.docx"


def supplementary_agreement_docx_filename(*, agreement_name: str, contract_name: str, version: str = "V1") -> str:
    agreement_display = agreement_name or "补充协议"
    contract_display = contract_name or "未命名合同"
    return f"{agreement_display}({contract_display}){version}_{_today_compact()}.docx"
